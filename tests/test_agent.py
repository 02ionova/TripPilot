"""Scripted SDK-shaped responses test the loop; these are NOT real LLM runs."""

import json
from types import SimpleNamespace

import httpx
import pytest
from conftest import make_build
from openai import APIConnectionError, AuthenticationError
from openai.types.chat import ChatCompletion

from agent import TravelAgent
from config import Settings
from tracing import redact


class MockClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.requests.append(json.loads(json.dumps(kwargs)))
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return value


def response(name=None, args=None, content=None):
    message = {"role": "assistant", "content": content}
    if name:
        message["tool_calls"] = [
            {
                "id": f"call_{name}_{len(json.dumps(args))}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }
        ]
    return ChatCompletion.model_validate(
        {
            "id": "mock-completion",
            "object": "chat.completion",
            "created": 1,
            "model": "mock",
            "choices": [
                {"index": 0, "message": message, "finish_reason": "tool_calls" if name else "stop"}
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        }
    )


def flow(raw, recover=False):
    city, start, end = raw["destination"], raw["start_date"], raw["end_date"]
    messages = [
        response("get_weather", dict(destination=city, start_date=start, end_date=end)),
        response(
            "search_flights",
            dict(
                origin="Prague",
                destination=city,
                departure_date=start,
                return_date=end,
                travelers=1,
            ),
        ),
    ]
    hotel = dict(destination=city, check_in=start, check_out=end, travelers=1)
    if recover:
        messages.append(
            response(
                "search_hotels", dict(**hotel, max_nightly_price=30, accommodation_type="hotel")
            )
        )
    messages.extend(
        [
            response("search_hotels", hotel),
            response(
                "search_activities",
                dict(destination=city, dietary_preferences=raw["dietary_preferences"]),
            ),
            response("build_itinerary", make_build(raw)),
            response(
                content=json.dumps(
                    {"status": "success", "message": "Validated simulated travel plan."}
                )
            ),
        ]
    )
    return messages


def run(tmp_path, raw, responses, iterations=15):
    client = MockClient(responses)
    agent = TravelAgent(
        Settings(max_iterations=iterations, api_key="", data_mode="demo"),
        client=client,
        trace_directory=tmp_path,
    )
    return agent, client, agent.run(raw)


def test_full_success_trace(tmp_path, request_data):
    agent, client, result = run(tmp_path, request_data, flow(request_data))
    assert result.status == "success"
    trace = json.loads(agent.trace.path.read_text())
    assert trace["final_status"] == "success" and trace["budget_validation"]["valid"]
    assert trace["execution_mode"] == "mocked_unit_test"
    assert trace["iterations"][0]["token_usage"]["total_tokens"] == 20
    assert len([e for e in trace["events"] if e["kind"] == "tool_call"]) == 5
    for index, req in enumerate(client.requests[1:], start=1):
        tool_messages = [m for m in req["messages"] if m["role"] == "tool"]
        assert tool_messages
        assert all(m["tool_call_id"] for m in tool_messages)


def test_full_recovery(tmp_path, paris_data):
    agent, client, result = run(tmp_path, paris_data, flow(paris_data, True))
    assert result.status == "success"
    events = agent.trace.data["events"]
    errors = [e for e in events if e["kind"] == "tool_call" and e["result"]["status"] == "error"]
    assert len(errors) == 1 and errors[0]["result"]["error"]["code"] == "no_results"
    assert any(e["kind"] == "replanning" for e in events)
    assert "no_results" in json.dumps(client.requests[3]["messages"])


def test_iteration_limit(tmp_path, request_data):
    agent, _, result = run(tmp_path, request_data, [response("unknown", {})] * 2, iterations=2)
    assert result.status == "iteration_limit" and agent.trace.path.exists()


def test_fake_success_rejected(tmp_path, request_data):
    _, _, result = run(
        tmp_path,
        request_data,
        [response(content='{"status":"success","message":"fake"}')],
        iterations=1,
    )
    assert result.status == "iteration_limit"


def test_invalid_final_recovery(tmp_path, request_data):
    _, _, result = run(
        tmp_path,
        request_data,
        [
            response(content="not JSON"),
            response(content='{"status":"infeasible","message":"No plan"}'),
        ],
    )
    assert result.status == "infeasible"


def test_request_tampering(tmp_path, request_data):
    build = make_build(request_data)
    build["request"]["budget"] = 99999
    agent, _, result = run(
        tmp_path, request_data, [response("build_itinerary", build)], iterations=1
    )
    assert result.status == "iteration_limit"
    assert any(
        e.get("result", {}).get("error", {}).get("code") == "request_mismatch"
        for e in agent.trace.data["events"]
    )


def test_missing_key(tmp_path, request_data):
    agent = TravelAgent(Settings(api_key=""), trace_directory=tmp_path)
    assert agent.run(request_data).status == "error"
    assert agent.trace.path.exists()


def test_bad_request_trace(tmp_path):
    agent = TravelAgent(Settings(api_key=""), trace_directory=tmp_path)
    assert agent.run({}).status == "needs_clarification"
    assert agent.trace.path.exists()


@pytest.mark.parametrize("status", ["infeasible", "needs_clarification", "error"])
def test_clean_termination(tmp_path, request_data, status):
    _, _, result = run(
        tmp_path, request_data, [response(content=json.dumps(dict(status=status, message="Test")))]
    )
    assert result.status == status


def test_repeat_calls_bounded(tmp_path, request_data):
    agent, _, _ = run(tmp_path, request_data, [response("unknown", {})] * 3, iterations=3)
    calls = [e for e in agent.trace.data["events"] if e["kind"] == "tool_call"]
    assert calls[-1]["result"]["error"]["code"] == "repeated_call_limit"


def test_api_retries(tmp_path, request_data, monkeypatch):
    monkeypatch.setattr("agent.sleep", lambda _: None)
    error = APIConnectionError(request=httpx.Request("POST", "https://api.openai.com"))
    agent, client, result = run(tmp_path, request_data, [error] * 3)
    assert result.status == "error" and len(client.requests) == 3
    assert len([e for e in agent.trace.data["events"] if e["kind"] == "api_retry"]) == 3


def test_auth_error(tmp_path, request_data):
    error = AuthenticationError(
        "Bad key",
        response=httpx.Response(401, request=httpx.Request("POST", "https://api.openai.com")),
        body=None,
    )
    _, client, result = run(tmp_path, request_data, [error])
    assert result.status == "error" and len(client.requests) == 1


def test_secret_redaction(tmp_path, monkeypatch, request_data):
    monkeypatch.setenv("OPENAI_API_KEY", "test-environment-sensitive-value")
    value = redact(
        {
            "api_key": "abc",
            "nested": ["sk-test-secret", "Bearer private", "test-environment-sensitive-value"],
            "authorization": "token",
        }
    )
    assert value == {
        "api_key": "[REDACTED]",
        "nested": ["[REDACTED]", "[REDACTED]", "[REDACTED]"],
        "authorization": "[REDACTED]",
    }
    agent, _, _ = run(
        tmp_path, request_data, [response(content='{"status":"error","message":"sk-test-secret"}')]
    )
    assert "sk-test-secret" not in agent.trace.path.read_text()


def test_unexpected_sdk_error_has_trace(tmp_path, request_data):
    agent, _, result = run(tmp_path, request_data, [RuntimeError("internal detail")])
    assert result.status == "error" and agent.trace.path.exists()
    assert "internal detail" not in agent.trace.path.read_text()


def test_model_not_found_has_actionable_error(tmp_path, request_data):
    from openai import NotFoundError

    error = NotFoundError(
        "sensitive server body must not be logged",
        response=httpx.Response(404, request=httpx.Request("POST", "https://api.openai.com")),
        body=None,
    )
    agent, client, result = run(tmp_path, request_data, [error])
    assert result.status == "error" and len(client.requests) == 1
    assert "OPENAI_MODEL=gpt-4.1-mini" in result.message
    assert "restart Streamlit" in result.message
    events = [e for e in agent.trace.data["events"] if e["kind"] == "api_error"]
    assert events[0]["http_status"] == 404
    assert "sensitive server body" not in agent.trace.path.read_text()


def test_past_dates_stop_before_api(tmp_path, request_data):
    request_data.update(start_date="2026-04-14", end_date="2026-04-16")
    agent, client, result = run(tmp_path, request_data, [])
    assert result.status == "needs_clarification"
    assert "before today" in result.message
    assert not client.requests
    assert agent.trace.path.exists()


def test_identical_cities_stop_before_api(tmp_path, request_data):
    request_data["origin"] = request_data["destination"]
    _, client, result = run(tmp_path, request_data, [])
    assert result.status == "needs_clarification"
    assert "different" in result.message
    assert not client.requests


def test_settings_reload_model_from_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "example-model")
    assert Settings().model == "example-model"


def test_recoverable_build_error_cannot_end_run_prematurely(tmp_path, request_data):
    responses = flow(request_data)
    bad_build = make_build(request_data)
    bad_build["days"][0]["schedule"][0]["meal"] = "lunch"
    responses[-2:-2] = [
        response("build_itinerary", bad_build),
        response(content=json.dumps({"status": "error", "message": "Lunch time needs correction"})),
    ]
    agent, client, result = run(tmp_path, request_data, responses)
    assert result.status == "success"
    assert any(
        event["kind"] == "replanning"
        and "does not establish infeasibility" in event.get("summary", "")
        for event in agent.trace.data["events"]
    )
    assert any(
        "Correct the actual schedule" in json.dumps(call["messages"]) for call in client.requests
    )


def test_explicit_demo_mode_overrides_live_environment(tmp_path, request_data, monkeypatch):
    """CLI/sidebar Demo choice must reach dispatch even with the Live default."""
    monkeypatch.setenv("DATA_MODE", "live")
    agent, _, result = run(tmp_path, request_data, flow(request_data))
    assert result.status == "success"
    assert result.data_source == "simulated"
    assert agent.trace.data["data_mode"] == "demo"
    assert not agent.runtime


def test_invalid_schedule_field_has_precise_feedback(tmp_path, request_data):
    build = make_build(request_data)
    build["days"][0]["schedule"][0]["start_time"] = "25:00"
    agent, _, result = run(
        tmp_path, request_data, [response("build_itinerary", build)], iterations=1
    )
    error = next(
        e["result"]["error"] for e in agent.trace.data["events"] if e["kind"] == "tool_call"
    )
    assert result.status == "iteration_limit"
    assert error["code"] == "invalid_arguments"
    assert "days.0.schedule.0.start_time" in error["message"]
    assert "request_mismatch" not in error["message"]


def test_revised_build_not_locked_out_after_four_different_errors(tmp_path, request_data):
    responses = flow(request_data)
    bad_calls = []
    for invalid_hour in [25, 26, 27, 28]:
        build = make_build(request_data)
        build["days"][0]["schedule"][0]["start_time"] = f"{invalid_hour}:00"
        bad_calls.append(response("build_itinerary", build))
    responses[-2:-2] = bad_calls
    agent, _, result = run(tmp_path, request_data, responses)
    assert result.status == "success"
    errors = [
        e["result"]["error"]["code"]
        for e in agent.trace.data["events"]
        if e["kind"] == "tool_call" and e["result"]["status"] == "error"
    ]
    assert errors == ["invalid_arguments"] * 4


def test_validated_last_iteration_build_finishes_success(tmp_path, request_data):
    responses = flow(request_data)[:-1]
    agent, client, result = run(tmp_path, request_data, responses, iterations=len(responses))
    assert result.status == "success"
    assert len(client.requests) == len(responses)
    assert agent.trace.data["budget_validation"]["valid"]
