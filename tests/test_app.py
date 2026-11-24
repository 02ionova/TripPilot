"""Render the real UI with Streamlit's testing harness; no API calls."""

from conftest import make_build
from streamlit.testing.v1 import AppTest

from config import ROOT
from schemas import FinalResponse, Itinerary
from tools.registry import execute_tool


def test_app_renders():
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=20)
    assert not app.exception
    assert app.title[0].value == "TripPilot AI"
    assert app.button[0].label == "Generate Travel Plan"


def test_success_result_renders(request_data):
    app = AppTest.from_file(str(ROOT / "app.py"))
    plan = Itinerary.model_validate(
        execute_tool("build_itinerary", make_build(request_data))["data"]
    )
    app.session_state["result"] = FinalResponse(
        status="success", message="Mocked UI rendering test", itinerary=plan
    )
    app.session_state["trace"] = {"execution_mode": "mocked_unit_test", "events": []}
    app.run(timeout=20)
    assert not app.exception
    assert len(app.metric) == 3
    assert app.metric[1].value == "€243.00"


def test_error_result_renders():
    app = AppTest.from_file(str(ROOT / "app.py"))
    app.session_state["result"] = FinalResponse(status="error", message="Missing API key")
    app.session_state["trace"] = {"execution_mode": "mocked_unit_test", "events": []}
    app.run(timeout=20)
    assert not app.exception
    assert "Missing API key" in app.error[0].value


def test_date_widgets_reject_past_dates():
    from datetime import date

    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=20)
    assert not app.exception
    for widget in app.date_input:
        assert widget.min == date(2026, 11, 24)
        assert widget.value >= widget.min
    assert app.text_input[0].value == "Prague"
    assert app.text_input[1].value == "Rome"
