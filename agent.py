"""Inspectable manual LLM loop: native tool calls, feedback, replanning, termination."""

import json
from collections import Counter
from pathlib import Path
from time import perf_counter, sleep
from typing import Callable

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)
from pydantic import ValidationError

from budgeting import budget_notice, maximum_budget
from cities import bind_city_label
from config import Settings
from planning import estimate_minimum_budget
from prompts import DEMONSTRATION_POLICY, LIVE_SYSTEM_PROMPT, SYSTEM_PROMPT
from schemas import BuildArgs, FinalDecision, FinalResponse, Itinerary, LiveBuildArgs, TravelRequest
from tools.catalog import simulation_notes
from tools.common import ToolFailure
from tools.registry import LIVE_REGISTRY, REGISTRY, execute_tool, tool_definitions
from tracing import Trace, now, redact


class TravelAgent:
    def __init__(
        self,
        settings: Settings | None = None,
        client=None,
        trace_directory: Path | None = None,
        on_event: Callable | None = None,
        demonstrate_recovery: bool = False,
        http_client=None,
        cache_path: Path | None = None,
    ):
        self.http_client = http_client
        self.cache_path = cache_path
        self.runtime = None
        self.demonstrate_recovery = demonstrate_recovery
        self.settings = settings or Settings()
        self.client = client
        self.trace_directory = trace_directory
        self.on_event = on_event
        self.trace = None

    def event(self, kind, **values):
        if self.runtime:
            self.trace.data["provider_stats"] = self.runtime.client.stats()
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
            stats = self.runtime.client.stats() if self.runtime else {}
            self.trace.data["provider_stats"] = stats
            self.trace.data["serpapi_requests"] = stats.get("serpapi_requests", 0)
            result = self.trace.finish(
                FinalResponse(
                    status="error",
                    message="Unexpected planning error. Inspect the sanitized trace and retry.",
                    data_source="live" if self.settings.data_mode == "live" else "simulated",
                    serpapi_requests=stats.get("serpapi_requests", 0),
                    provider_cache_hits=stats.get("provider_cache_hits", 0),
                )
            )
            if self.runtime:
                self.runtime.client.close()
            return result

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

        self.runtime = None
        live = self.settings.data_mode == "live"
        self.trace.data["data_mode"] = self.settings.data_mode
        budget_estimate = None

        def finish(status, message, itinerary=None):
            stats = self.runtime.client.stats() if self.runtime else {}
            self.trace.data["provider_stats"] = stats
            self.trace.data["serpapi_requests"] = stats.get("serpapi_requests", 0)
            if itinerary:
                notice = budget_notice(request.budget, itinerary.budget_breakdown.total)
                if notice:
                    message = message + " " + notice
            result = self.trace.finish(
                FinalResponse(
                    status=status,
                    message=message,
                    itinerary=itinerary,
                    budget_estimate=budget_estimate,
                    data_source="live" if live else "simulated",
                    serpapi_requests=stats.get("serpapi_requests", 0),
                    provider_cache_hits=stats.get("provider_cache_hits", 0),
                    retrieved_at=now() if live else None,
                )
            )
            if self.runtime:
                self.runtime.client.close()
            return result

        try:
            request = TravelRequest.model_validate(raw)
        except ValidationError as exc:
            details = "; ".join(error["msg"] for error in exc.errors(include_input=False))
            return finish("needs_clarification", "Please correct your request: " + details)
        if live:
            if not self.settings.serpapi_api_key:
                return finish(
                    "error",
                    "SERPAPI_API_KEY is missing. Configure it in .env and restart. Live Mode never switches to simulated data automatically.",
                )
            from providers.runtime import LiveTools

            self.runtime = LiveTools(
                request, self.settings, self.event, self.http_client, self.cache_path
            )
        else:
            try:
                budget_estimate = estimate_minimum_budget(request)
            except ToolFailure as exc:
                self.event("precheck_error", error=exc.error.model_dump())
                return finish("needs_clarification", exc.error.message)
            self.event(
                "budget_precheck",
                estimate=budget_estimate.model_dump(),
                summary="Checked the minimum required simulated costs before contacting the model.",
            )
            if budget_estimate.minimum_total > maximum_budget(request.budget):
                return finish(
                    "infeasible",
                    f"This trip needs at least EUR {budget_estimate.minimum_total:.2f} under the simulated prices. Your total budget is EUR {request.budget:.2f}, a shortfall of EUR {budget_estimate.shortfall:.2f}. This also exceeds the 10% flexible maximum of EUR {maximum_budget(request.budget):.2f}. Increase the budget, shorten the trip, or reduce the traveler count. No model requests were needed.",
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
            {
                "role": "system",
                "content": LIVE_SYSTEM_PROMPT
                + (
                    "\nFor this explicitly requested recovery demonstration, first search hotels with max_nightly_price=10. If no priced options meet that limit, independently broaden the filter using the already cached provider results. This is a demonstration constraint, not a claim about actual hotel prices."
                    if self.demonstrate_recovery
                    else ""
                )
                if live
                else SYSTEM_PROMPT
                + ("\n" + DEMONSTRATION_POLICY if self.demonstrate_recovery else ""),
            },
            {"role": "user", "content": request.model_dump_json()},
        ]
        if live:
            messages.append(
                {
                    "role": "user",
                    "content": f"Live Mode. SerpApi request cap: {self.settings.max_serpapi_requests}. Prefer broad searches and reuse cached results. Account/autocomplete/return-selection accounting is enforced by Python. No simulated catalogue or mathematical minimum-cost proof is available for this live trip.",
                }
            )
        else:
            messages.append(
                {
                    "role": "user",
                    "content": "Python simulated catalogue lower bound: "
                    + budget_estimate.model_dump_json()
                    + ". Simulation notes: "
                    + json.dumps(simulation_notes(request.origin, request.destination)),
                }
            )
        calls = Counter()
        searched = set()
        validated_itinerary = None
        failure_feedback_sent = False
        last_build_error = None
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
                        tools=tool_definitions(self.settings.data_mode, self.runtime),
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
                    # Store only allowlisted diagnostic fields, never raw bodies/headers.
                    self.event(
                        "api_error",
                        error=type(exc).__name__,
                        http_status=getattr(exc, "status_code", None),
                    )
                    if isinstance(exc, NotFoundError):
                        detail = f"OpenAI model '{self.settings.model}' was not found or is unavailable to this API project. Set OPENAI_MODEL=gpt-4.1-mini in .env and restart Streamlit, or choose another accessible model with function calling and structured outputs."
                    elif isinstance(exc, AuthenticationError):
                        detail = "OpenAI authentication failed. Check OPENAI_API_KEY in .env and restart Streamlit."
                    elif isinstance(exc, PermissionDeniedError):
                        detail = "OpenAI denied access. Check your API project permissions and model access."
                    elif isinstance(exc, BadRequestError):
                        detail = "OpenAI could not accept this request. Check that OPENAI_MODEL supports Chat Completions, function calling and JSON-schema structured outputs."
                    else:
                        detail = (
                            "OpenAI request failed. Check your account configuration and try again."
                        )
                    return finish("error", detail)
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
                    self.event("tool_started", iteration=iteration, tool=name)
                    tick = perf_counter()
                    signature = (name, arguments)
                    calls[signature] += 1
                    if calls[signature] > 2:
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
                            "data_source": "live" if live else "simulated",
                        }
                    else:
                        # Bind build requests to the original user input, preventing budget/date tampering.
                        try:
                            dispatch_arguments = arguments
                            if name == "build_itinerary":
                                selected = (
                                    LiveBuildArgs if live else BuildArgs
                                ).model_validate_json(arguments)
                                if live:
                                    selected.request = selected.request.model_copy(
                                        update={
                                            "origin": bind_city_label(
                                                selected.request.origin, request.origin
                                            ),
                                            "destination": bind_city_label(
                                                selected.request.destination, request.destination
                                            ),
                                        }
                                    )
                                    dispatch_arguments = selected.model_dump_json()
                                    if dispatch_arguments != arguments:
                                        self.event(
                                            "bound_request_arguments",
                                            tool=name,
                                            summary="Validated builder input against the original request; restored only user-supplied city qualifiers where omitted.",
                                        )
                                if selected.request != request:
                                    raise ValueError("Changed request")
                            result = execute_tool(
                                name, dispatch_arguments, self.runtime, mode=self.settings.data_mode
                            )
                        except ValidationError as exc:
                            result = {
                                "status": "error",
                                "data_source": "live" if live else "simulated",
                                "error": {
                                    "code": "invalid_arguments",
                                    "message": "; ".join(
                                        f"{'.'.join(map(str, e['loc']))}: {e['msg']}"
                                        for e in exc.errors(include_input=False)
                                    ),
                                    "suggestions": [
                                        "Correct the named fields. Times use HH:MM (for example 07:30). The original request may already be correct."
                                    ],
                                },
                            }
                        except ValueError:
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
                        if name == "build_itinerary":
                            validated_itinerary = None
                            last_build_error = result.get("error")
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
                    if live and result.get("error") and result["error"]["code"] == "ambiguous_city":
                        clarification = (
                            result["error"]["message"]
                            + " Please specify city and country. Options: "
                            + "; ".join(result["error"].get("suggestions", []))
                        )
                        self.event("clarification_required", summary=clarification)
                        return finish("needs_clarification", clarification)
                continue
            if message.refusal:
                return finish("error", "The model refused the planning request.")
            try:
                decision = FinalDecision.model_validate_json(message.content or "")
                if decision.status == "success":
                    if validated_itinerary is None or searched != set(
                        LIVE_REGISTRY if live else REGISTRY
                    ):
                        raise ValueError(
                            "Success requires every planning tool and a successful builder result."
                        )
                    return finish(
                        "success",
                        "Your travel plan is ready. The schedule and total estimated budget have been validated. Prices may change; no bookings have been made."
                        if live
                        else "Your simulated travel plan is ready. The schedule and total budget have been validated. No bookings have been made.",
                        validated_itinerary,
                    )
                if (
                    decision.status in {"error", "infeasible"}
                    and last_build_error
                    and not failure_feedback_sent
                ):
                    failure_feedback_sent = True
                    feedback = (
                        "The last builder error is recoverable and does not establish infeasibility. "
                        "Correct the actual schedule using this feedback, and search cheaper accommodation "
                        "or meals if cost is the issue. Do not simply describe a correction. "
                        + json.dumps(last_build_error)
                    )
                    self.event("replanning", iteration=iteration, summary=feedback)
                    messages.append({"role": "user", "content": feedback})
                    continue
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
        if validated_itinerary is not None and searched == set(LIVE_REGISTRY if live else REGISTRY):
            self.event(
                "validated_completion",
                summary="Completed from the validated final tool result at the iteration boundary.",
            )
            return finish(
                "success",
                "Your travel plan is ready. The schedule and total estimated budget have been validated. No bookings have been made.",
                validated_itinerary,
            )
        return finish(
            "iteration_limit",
            "The planner did not resolve all scheduling details within this attempt. No complete travel plan was produced. Please try generating again; you do not need to shorten the trip solely because of this technical limit.",
        )
