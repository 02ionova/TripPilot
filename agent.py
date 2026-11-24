"""Inspectable manual LLM loop: native tool calls, feedback, replanning, termination."""

import json
from collections import Counter
from pathlib import Path
from time import perf_counter, sleep
from typing import Callable

from openai import APIConnectionError, APIError, APITimeoutError, OpenAI, RateLimitError
from pydantic import ValidationError

from config import Settings
from prompts import SYSTEM_PROMPT
from schemas import BuildArgs, FinalDecision, FinalResponse, Itinerary, TravelRequest
from tools.registry import REGISTRY, execute_tool, tool_definitions
from tracing import Trace, redact


class TravelAgent:
    def __init__(
        self,
        settings: Settings | None = None,
        client=None,
        trace_directory: Path | None = None,
        on_event: Callable | None = None,
    ):
        self.settings = settings or Settings()
        self.client = client
        self.trace_directory = trace_directory
        self.on_event = on_event
        self.trace = None

    def event(self, kind, **values):
        event = self.trace.event(kind, **values)
        if self.on_event:
            self.on_event(event)

    def run(self, raw_request: TravelRequest | dict) -> FinalResponse:
        """Contain unexpected SDK/runtime errors and still finalize the run trace."""
        try:
            return self._run(raw_request)
        except Exception as exc:
            if self.trace is None:
                raise
            self.trace.event("unexpected_error", error=type(exc).__name__)
            return self.trace.finish(
                FinalResponse(
                    status="error",
                    message="Unexpected planning error. Inspect the sanitized trace and retry.",
                )
            )

    def _run(self, raw_request: TravelRequest | dict) -> FinalResponse:
        raw = (
            raw_request.model_dump(mode="json")
            if isinstance(raw_request, TravelRequest)
            else raw_request
        )
        self.trace = Trace(
            raw,
            self.settings.model,
            self.trace_directory,
            "mocked_unit_test"
            if self.client is not None and not isinstance(self.client, OpenAI)
            else "real_llm",
        )

        def finish(status, message, itinerary=None):
            return self.trace.finish(
                FinalResponse(status=status, message=message, itinerary=itinerary)
            )

        try:
            request = TravelRequest.model_validate(raw)
        except ValidationError:
            return finish(
                "needs_clarification",
                "Provide valid origin, destination, dates (1–14 days, 2026–2035), positive total budget and traveler count.",
            )
        if self.client is None:
            if not self.settings.api_key:
                return finish(
                    "error", "OPENAI_API_KEY is missing. Add it to .env to run the real agent."
                )
            # Explicit retry policy below; disable SDK retries to bound paid attempts.
            self.client = OpenAI(
                api_key=self.settings.api_key, timeout=self.settings.timeout, max_retries=0
            )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": request.model_dump_json()},
        ]
        calls = Counter()
        failures = Counter()
        searched = set()
        validated_itinerary = None
        for iteration in range(1, self.settings.max_iterations + 1):
            started = perf_counter()
            self.event(
                "iteration",
                iteration=iteration,
                summary="Requesting the next observable planning action.",
            )
            response = None
            for attempt in range(3):
                try:
                    response = self.client.chat.completions.create(
                        model=self.settings.model,
                        messages=messages,
                        tools=tool_definitions(),
                        response_format={
                            "type": "json_schema",
                            "json_schema": {
                                "name": "planning_decision",
                                "strict": True,
                                "schema": FinalDecision.model_json_schema(),
                            },
                        },
                        parallel_tool_calls=False,
                    )
                    break
                except (APITimeoutError, APIConnectionError, RateLimitError) as exc:
                    self.event(
                        "api_retry",
                        iteration=iteration,
                        attempt=attempt + 1,
                        error=type(exc).__name__,
                    )
                    if attempt == 2:
                        return finish(
                            "error",
                            "OpenAI request failed after three attempts. Check connectivity and rate limits.",
                        )
                    sleep(0.5 * 2**attempt)
                except APIError as exc:
                    self.event("api_error", error=type(exc).__name__)
                    return finish(
                        "error",
                        "OpenAI rejected the request. Check API credentials, model access and account configuration.",
                    )
            message = response.choices[0].message
            observable = message.model_dump(exclude_none=True)
            usage = response.usage.model_dump() if response.usage else None
            self.trace.data["iterations"].append(
                redact(
                    {
                        "iteration": iteration,
                        "assistant_response": observable,
                        "token_usage": usage,
                        "duration_seconds": round(perf_counter() - started, 4),
                    }
                )
            )
            # Preserve the complete assistant message INCLUDING all tool-call IDs.
            messages.append(observable)
            if message.tool_calls:
                for call in message.tool_calls:
                    name, arguments = call.function.name, call.function.arguments
                    tick = perf_counter()
                    signature = (name, arguments)
                    calls[signature] += 1
                    if calls[signature] > 2 or failures[name] >= 4:
                        result = {
                            "status": "error",
                            "data": None,
                            "error": {
                                "code": "repeated_call_limit",
                                "message": "Repeated tool call/failure limit reached. Change strategy or terminate.",
                                "suggestions": [
                                    "Choose different arguments or return infeasible/error."
                                ],
                            },
                            "data_source": "simulated",
                        }
                    else:
                        # Bind build requests to the original user input, preventing budget/date tampering.
                        try:
                            if name == "build_itinerary":
                                selected = BuildArgs.model_validate_json(arguments)
                                if selected.request != request:
                                    raise ValueError("Changed request")
                            result = execute_tool(name, arguments)
                        except (ValidationError, ValueError):
                            result = {
                                "status": "error",
                                "error": {
                                    "code": "request_mismatch",
                                    "message": "Use the exact original request and valid build arguments.",
                                    "suggestions": ["Copy the original validated request."],
                                },
                            }
                    if result["status"] == "ok":
                        searched.add(name)
                        if name == "build_itinerary":
                            validated_itinerary = Itinerary.model_validate(result["data"])
                    else:
                        failures[name] += 1
                        if name == "build_itinerary":
                            validated_itinerary = None
                        self.event(
                            "replanning",
                            iteration=iteration,
                            tool=name,
                            summary="Tool returned an error; feedback sent to model.",
                            error=result.get("error"),
                        )
                    self.event(
                        "tool_call",
                        iteration=iteration,
                        tool=name,
                        tool_call_id=call.id,
                        arguments=arguments,
                        result=result,
                        duration_seconds=round(perf_counter() - tick, 4),
                    )
                    # One tool result per tool-call ID is mandatory for API conversation integrity.
                    messages.append(
                        {"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)}
                    )
                continue
            if message.refusal:
                return finish("error", "The model refused the planning request.")
            try:
                decision = FinalDecision.model_validate_json(message.content or "")
                if decision.status == "success":
                    if validated_itinerary is None or searched != set(REGISTRY):
                        raise ValueError(
                            "Success requires all five tools and a successful builder result."
                        )
                    return finish("success", decision.message, validated_itinerary)
                return finish(decision.status, decision.message)
            except (ValidationError, ValueError) as exc:
                feedback = (
                    str(exc)
                    if not isinstance(exc, ValidationError)
                    else "Final response does not match the required JSON schema."
                )
                self.event("replanning", iteration=iteration, summary=feedback)
                messages.append(
                    {
                        "role": "user",
                        "content": feedback
                        + " Correct the response or complete the missing tools.",
                    }
                )
        return finish(
            "iteration_limit",
            "Maximum agent iterations reached. Try a shorter trip or adjust constraints.",
        )
