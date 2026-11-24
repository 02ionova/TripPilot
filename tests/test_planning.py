"""Regression for the screenshot: reject an unaffordable trip before paid calls."""

from datetime import date

from conftest import make_build
from streamlit.testing.v1 import AppTest
from test_agent import MockClient

from agent import TravelAgent
from config import ROOT, Settings
from planning import estimate_minimum_budget
from schemas import TravelRequest
from tools.registry import execute_tool


def vienna_request(budget=600):
    return dict(
        origin="Prague",
        destination="Vienna",
        start_date="2026-11-24",
        end_date="2026-11-29",
        budget=budget,
        travelers=2,
        pace="intensive",
        interests=["architecture", "history", "local food"],
        dietary_preferences=[],
    )


def test_vienna_minimum_matches_trusted_components():
    estimate = estimate_minimum_budget(TravelRequest(**vienna_request()))
    assert estimate.model_dump() == dict(
        flights=170,
        accommodation=230,
        food=252,
        activities=0,
        local_transport=60,
        minimum_total=712,
        available_budget=600,
        shortfall=112,
    )


def test_impossible_budget_returns_without_llm(tmp_path):
    client = MockClient([])
    agent = TravelAgent(Settings(api_key=""), client=client, trace_directory=tmp_path)
    result = agent.run(vienna_request())
    assert result.status == "infeasible"
    assert result.budget_estimate.shortfall == 112
    assert "712.00" in result.message
    assert not client.requests
    assert not agent.trace.data["iterations"]
    assert agent.trace.path.exists()


def test_minimum_budget_is_attainable_for_screenshot_data():
    raw = vienna_request(712)
    estimate = estimate_minimum_budget(TravelRequest(**raw))
    result = execute_tool("build_itinerary", make_build(raw))
    assert result["status"] == "ok", result
    assert result["data"]["budget_breakdown"]["total"] == estimate.minimum_total
    assert estimate.shortfall == 0


def test_lower_bound_scales_with_travelers(request_data):
    one = estimate_minimum_budget(TravelRequest(**request_data))
    request_data["travelers"] = 2
    two = estimate_minimum_budget(TravelRequest(**request_data))
    assert one.minimum_total == 243
    assert two.minimum_total == 486


def test_single_day_no_accommodation(request_data):
    request_data["end_date"] = request_data["start_date"]
    estimate = estimate_minimum_budget(TravelRequest(**request_data))
    assert estimate.accommodation == 0
    assert estimate.food == 21
    assert estimate.local_transport == 5


def test_vienna_form_shows_budget_gap_without_api(monkeypatch, tmp_path):
    def unexpected_api(*args, **kwargs):
        raise AssertionError("An impossible budget must not contact OpenAI")

    monkeypatch.setattr("agent.OpenAI", unexpected_api)
    monkeypatch.setattr("tracing.ROOT", tmp_path)
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=20)
    app.selectbox(key="destination_city").set_value("Vienna")
    app.selectbox[2].set_value("intensive")
    app.number_input[0].set_value(2)
    app.date_input[0].set_value(date(2026, 11, 24))
    app.date_input[1].set_value(date(2026, 11, 29))
    app.button[0].click().run(timeout=20)
    assert not app.exception
    assert not app.error
    assert [metric.value for metric in app.metric] == ["€600.00", "€712.00", "€112.00"]
    assert any("712.00" in warning.value for warning in app.warning)
    assert not any("Handling tool feedback" in item.value for item in app.markdown)
