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
    assert not app.get("download_button")
    assert not app.json
    assert not any("Execution trace" in x.label for x in app.expander)


def test_error_result_renders():
    app = AppTest.from_file(str(ROOT / "app.py"))
    app.session_state["result"] = FinalResponse(status="error", message="Missing API key")
    app.session_state["trace"] = {"execution_mode": "mocked_unit_test", "events": []}
    app.run(timeout=20)
    assert not app.exception
    assert "Missing API key" in app.error[0].value
    assert not app.get("download_button")
    assert not app.json


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
    # Independent widgets never submit an Enter-bound form; only the button plans.
    assert not app.get("form")
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


def test_compact_mode_toggle_has_help_and_clears_previous_result():
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=20)
    toggle = app.toggle(key="live_mode")
    assert "external providers" in toggle.proto.help
    assert "simulated" in toggle.proto.help
    assert not app.sidebar.radio and not app.sidebar.toggle
    app.session_state["result"] = FinalResponse(status="error", message="Old result")
    app.session_state["trace"] = {"events": []}
    toggle.set_value(True).run(timeout=20)
    assert not app.exception
    assert "result" not in app.session_state


def test_flexible_budget_and_daily_cards_render(request_data):
    request_data["budget"] = 230
    plan = Itinerary.model_validate(
        execute_tool("build_itinerary", make_build(request_data))["data"]
    )
    app = AppTest.from_file(str(ROOT / "app.py"))
    app.session_state["result"] = FinalResponse(
        status="success", message="Alternative", itinerary=plan
    )
    app.session_state["trace"] = {"events": []}
    app.run(timeout=20)
    assert not app.exception
    assert app.metric[0].value == "€230.00"
    assert app.metric[2].label == "Above target budget" and app.metric[2].value == "€13.00"
    assert any("10% flexibility" in w.value for w in app.warning)
    markup = " ".join(m.value for m in app.markdown)
    assert "stop-card meal" in markup and "stop-card visit" in markup
    assert "Day 01" in markup and "Day 04" in markup
    assert len(app.get("image")) == 4


def test_traveler_changes_adjust_current_budget_without_planning(monkeypatch):
    calls = []

    def unexpected_plan(*args, **kwargs):
        calls.append(True)
        raise AssertionError("Changing the traveler count must not generate a plan")

    monkeypatch.setattr("agent.TravelAgent.run", unexpected_plan)
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=20)
    assert app.number_input(key="trip_budget").value == 600
    app.number_input(key="travelers").set_value(2).run(timeout=20)
    assert app.number_input(key="trip_budget").value == 1100
    app.number_input(key="travelers").set_value(4).run(timeout=20)
    assert app.number_input(key="trip_budget").value == 2100
    app.number_input(key="trip_budget").set_value(1800.0).run(timeout=20)
    app.number_input(key="travelers").set_value(5).run(timeout=20)
    assert app.number_input(key="trip_budget").value == 2300
    app.number_input(key="travelers").set_value(3).run(timeout=20)
    assert app.number_input(key="trip_budget").value == 1300
    app.run(timeout=20)
    assert app.number_input(key="trip_budget").value == 1300
    app.number_input(key="trip_budget").set_value(100.0).run(timeout=20)
    app.number_input(key="travelers").set_value(1).run(timeout=20)
    assert app.number_input(key="trip_budget").value == 1
    assert not calls and not app.exception


def test_live_notice_is_subtle_and_readable(monkeypatch):
    monkeypatch.setenv("DATA_MODE", "live")
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=20)
    assert not app.exception
    assert not app.info
    assert any(
        'class="provider-note"' in m.value and "Prices and availability may change" in m.value
        for m in app.markdown
    )
