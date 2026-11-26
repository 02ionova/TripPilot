"""Backup suggestions are observable, bounded and separate from validated offers."""

import io
import json
from datetime import date, datetime, timedelta
from zipfile import ZipFile

import pytest
from pydantic import ValidationError
from test_agent import MockClient, response

from agent import TravelAgent
from config import Settings
from display import display_date, display_datetime, display_duration
from fallback import generate_advice, unresolved_search_errors
from reporting import create_report_archive
from schemas import AIAdvice, FinalResponse, TravelRequest


def advice_content(raw):
    start, end = date.fromisoformat(raw["start_date"]), date.fromisoformat(raw["end_date"])
    return {
        "title": "Flexible city ideas",
        "summary": "General suggestions, subject to verification.",
        "days": [
            {
                "date": str(start + timedelta(days=i)),
                "title": "City exploration",
                "suggestions": ["Consider a museum; verify tickets and opening hours."],
            }
            for i in range((end - start).days + 1)
        ],
        "budget_guidance": ["Compare accommodation before booking."],
        "verification_steps": ["Check live transport and dietary suitability."],
    }


def run_backup(tmp_path, raw, content, **options):
    client = MockClient([response(content=json.dumps(content))])
    settings = Settings(
        data_mode="live", serpapi_api_key="", api_key="", enable_ai_fallback=True, **options
    )
    agent = TravelAgent(settings, client=client, trace_directory=tmp_path)
    return agent, client, agent.run(raw)


def test_missing_provider_backup_keeps_original_status_and_request(tmp_path, request_data):
    agent, client, result = run_backup(tmp_path, request_data, advice_content(request_data))
    assert result.status == "error" and result.ai_fallback.status == "available"
    assert result.itinerary is None and result.serpapi_requests == 0
    assert not result.ai_fallback.budget_validated
    assert not result.ai_fallback.availability_verified
    assert result.ai_fallback.usage.total_tokens == 20
    assert len(client.requests) == 1
    call = client.requests[0]
    assert "tools" not in call and call["timeout"] <= 30
    assert call["response_format"]["json_schema"]["strict"] is True
    assert json.loads(call["messages"][1]["content"])["original_request"] == request_data
    trace = json.loads(agent.trace.path.read_text())
    assert trace["final_status"] == "error" and trace["budget_validation"] is None
    assert any(e["kind"] == "ai_fallback_finished" for e in trace["events"])
    assert FinalResponse.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("enabled,valid", [(False, True), (True, False)])
def test_disabled_or_invalid_request_never_calls_backup(tmp_path, request_data, enabled, valid):
    client = MockClient([])
    agent = TravelAgent(
        Settings(data_mode="live", serpapi_api_key="", api_key="", enable_ai_fallback=enabled),
        client=client,
        trace_directory=tmp_path,
    )
    result = agent.run(request_data if valid else {})
    assert not client.requests and result.ai_fallback is None


def test_no_openai_credentials_never_calls_backup(tmp_path, request_data):
    agent = TravelAgent(
        Settings(data_mode="live", serpapi_api_key="", api_key="", enable_ai_fallback=True),
        trace_directory=tmp_path,
    )
    result = agent.run(request_data)
    assert result.status == "error" and result.ai_fallback is None


@pytest.mark.parametrize("content", [{}, {"days": []}])
def test_malformed_backup_does_not_mask_original_failure(tmp_path, request_data, content):
    _, client, result = run_backup(tmp_path, request_data, content)
    assert len(client.requests) == 1 and result.status == "error"
    assert "SERPAPI_API_KEY is missing" in result.message
    assert result.ai_fallback.status == "error" and result.ai_fallback.content is None


def test_wrong_dates_rejected(tmp_path, request_data):
    content = advice_content(request_data)
    content["days"][0]["date"] = "2027-04-09"
    _, _, result = run_backup(tmp_path, request_data, content)
    assert result.ai_fallback.status == "error"


def test_timeout_is_one_attempt_and_no_secret_exception_text(request_data):
    events = []
    client = MockClient([TimeoutError("private-key-must-not-be-logged")])
    result = generate_advice(
        TravelRequest.model_validate(request_data),
        {"search_hotels": {"code": "provider_timeout"}},
        Settings(enable_ai_fallback=True),
        client,
        lambda kind, **values: events.append({"kind": kind, **values}),
    )
    assert len(client.requests) == 1 and result.status == "error"
    assert "private-key-must-not-be-logged" not in json.dumps(events)
    assert result.usage.total_tokens is None


def test_recovered_search_and_invalid_arguments_do_not_trigger_backup():
    events = [
        {
            "kind": "tool_call",
            "tool": "search_hotels",
            "result": {"status": "error", "error": {"code": "no_results"}},
        },
        {"kind": "tool_call", "tool": "search_hotels", "result": {"status": "ok"}},
        {
            "kind": "tool_call",
            "tool": "search_flights",
            "result": {"status": "error", "error": {"code": "invalid_arguments"}},
        },
    ]
    assert unresolved_search_errors({"events": events}) == {}
    events.pop(1)
    assert set(unresolved_search_errors({"events": events})) == {"search_hotels"}


def test_exhausted_agent_loop_passes_actual_search_error_to_backup(
    tmp_path, request_data, monkeypatch
):
    """Exercise the transition from a real loop tool result to the auxiliary call."""
    monkeypatch.setattr(
        "agent.execute_tool",
        lambda *args, **kwargs: {
            "status": "error",
            "data": None,
            "data_source": "live",
            "error": {
                "code": "no_results",
                "message": "No matching hotels found.",
                "suggestions": ["Broaden filters."],
            },
        },
    )
    client = MockClient(
        [
            response("search_hotels", {"destination": "Rome"}),
            response(content=json.dumps(advice_content(request_data))),
        ]
    )
    agent = TravelAgent(
        Settings(
            data_mode="live",
            serpapi_api_key="fixture-key",
            api_key="",
            max_iterations=1,
            enable_ai_fallback=True,
        ),
        client=client,
        trace_directory=tmp_path,
        cache_path=tmp_path / "cache.sqlite",
    )
    result = agent.run(request_data)
    assert result.status == "iteration_limit" and result.ai_fallback.status == "available"
    assert len(client.requests) == 2
    backup_input = json.loads(client.requests[1]["messages"][1]["content"])
    assert backup_input["unavailable_searches"]["search_hotels"]["code"] == "no_results"
    assert result.serpapi_requests == 0 and result.itinerary is None


def test_backup_cannot_claim_budget_or_availability_verified(tmp_path, request_data):
    _, _, result = run_backup(tmp_path, request_data, advice_content(request_data))
    for field in ("budget_validated", "availability_verified"):
        raw = result.ai_fallback.model_dump()
        raw[field] = True
        with pytest.raises(ValidationError):
            AIAdvice.model_validate(raw)


def test_backup_in_full_report(tmp_path, request_data):
    agent, _, result = run_backup(tmp_path, request_data, advice_content(request_data))
    with ZipFile(io.BytesIO(create_report_archive(result, agent.trace.data, "live"))) as archive:
        assert len(archive.namelist()) == 8
        backup = json.loads(archive.read("ai_fallback.json"))
        assert backup["data_source"] == "unverified_ai" and backup["usage"]["total_tokens"] == 20
        assert json.loads(archive.read("budget_validation.json")) is None


@pytest.mark.parametrize(
    "minutes,expected",
    [(75, "1 h 15 min"), (60, "1 h"), (25, "25 min"), (0, "0 min"), (None, "Not supplied")],
)
def test_readable_duration(minutes, expected):
    assert display_duration(minutes) == expected


def test_readable_dates_preserve_local_clock():
    assert display_date(date(2027, 4, 10)) == "10 Apr 2027"
    assert (
        display_datetime(datetime.fromisoformat("2027-04-10T20:55:00+02:00"))
        == "10 Apr 2027 · 20:55"
    )


def test_backup_ui_renders_without_validated_budget(tmp_path, request_data, monkeypatch):
    from streamlit.testing.v1 import AppTest

    from config import ROOT

    _, _, result = run_backup(tmp_path, request_data, advice_content(request_data))
    monkeypatch.setenv("DATA_MODE", "live")
    app = AppTest.from_file(str(ROOT / "app.py"))
    app.session_state["result"] = result
    app.session_state["trace"] = {"events": []}
    app.run(timeout=20)
    assert not app.exception
    assert any("not verified" in c.value for c in app.caption)
    assert app.metric[2].value == "20"
    assert len(app.get("download_button")) == 1
