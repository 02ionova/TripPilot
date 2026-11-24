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
    assert app.selectbox(key="origin_city").value == "Prague"
    assert app.selectbox(key="destination_city").value == "Rome"


def test_city_search_is_available_without_form_enter_submission():
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=20)
    assert not app.exception
    assert not app.get("form")[0].proto.form.enter_to_submit
    origin = app.selectbox(key="origin_city")
    destination = app.selectbox(key="destination_city")
    assert origin.proto.accept_new_options
    assert destination.proto.accept_new_options
    assert "Berlin, Germany" in origin.options
    assert "Tokyo, Japan" in destination.options
    assert origin.value == "Prague"
    assert destination.value == "Rome"


def test_planning_runs_only_after_generate_button(monkeypatch):
    from types import SimpleNamespace

    calls = []

    def fake_run(agent, request):
        calls.append(request)
        agent.trace = SimpleNamespace(data={"events": [], "execution_mode": "mocked_unit_test"})
        return FinalResponse(status="error", message="Mocked button submission")

    monkeypatch.setattr("agent.TravelAgent.run", fake_run)
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=20)
    assert not calls
    app.selectbox(key="origin_city").set_value("Berlin")
    app.selectbox(key="destination_city").set_value("Lisbon")
    app.run(timeout=20)
    assert not calls
    app.selectbox(key="origin_city").set_value("Berlin")
    app.selectbox(key="destination_city").set_value("Lisbon")
    app.button[0].click().run(timeout=20)
    assert not app.exception
    assert len(calls) == 1
    assert calls[0].origin == "Berlin"
    assert calls[0].destination == "Lisbon"
