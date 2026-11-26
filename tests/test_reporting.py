"""Full report export is complete, isolated to the current run and secret-safe."""

import io
import json
from zipfile import ZipFile

from conftest import make_build

from reporting import create_report_archive
from schemas import FinalResponse, Itinerary
from tools.registry import execute_tool


def test_complete_report_archive(request_data, monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "private-serp-for-test")
    plan = Itinerary.model_validate(
        execute_tool("build_itinerary", make_build(request_data))["data"]
    )
    result = FinalResponse(status="success", message="Ready", itinerary=plan)
    trace = {
        "run_id": "test-run",
        "request": request_data,
        "api_key": "private-serp-for-test",
        "events": [
            {
                "kind": "tool_call",
                "timestamp": "now",
                "tool": "search_hotels",
                "tool_call_id": "call-1",
                "result": {"status": "ok"},
            }
        ],
        "budget_validation": {"valid": True},
    }
    with ZipFile(io.BytesIO(create_report_archive(result, trace, "demo"))) as archive:
        assert set(archive.namelist()) == {
            "README.md",
            "request.json",
            "result.json",
            "execution_trace.json",
            "runtime.log",
            "information.json",
            "budget_validation.json",
        }
        assert (
            json.loads(archive.read("result.json"))["itinerary"]["budget_breakdown"]["total"] == 243
        )
        assert json.loads(archive.read("request.json")) == request_data
        assert json.loads(archive.read("budget_validation.json"))["valid"]
        assert "search_hotels" in archive.read("runtime.log").decode()
        assert "Prague" in archive.read("README.md").decode()
        assert all(
            b"private-serp-for-test" not in archive.read(name) for name in archive.namelist()
        )


def test_failure_report_still_contains_diagnostics():
    result = FinalResponse(status="error", message="Provider unavailable", data_source="live")
    trace = {
        "request": {"destination": "Amsterdam, Netherlands"},
        "events": [],
        "final_status": "error",
    }
    with ZipFile(io.BytesIO(create_report_archive(result, trace, "live"))) as archive:
        assert json.loads(archive.read("result.json"))["status"] == "error"
        assert json.loads(archive.read("budget_validation.json")) is None
        assert "Provider unavailable" in archive.read("README.md").decode()
