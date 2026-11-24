"""Arbitrary city labels use deterministic, clearly fictional catalogue fixtures."""

import json

import pytest
from pydantic import ValidationError
from streamlit.testing.v1 import AppTest
from test_agent import response, run

from config import ROOT
from planning import estimate_minimum_budget
from schemas import TravelRequest
from tools.catalog import flight_options, simulation_notes
from tools.common import dates, load
from tools.registry import execute_tool


def custom_request():
    return dict(
        origin="Berlin",
        destination="Lisbon",
        start_date="2027-04-10",
        end_date="2027-04-13",
        budget=600,
        travelers=1,
        pace="moderate",
        interests=["history", "architecture"],
        dietary_preferences=["vegetarian"],
    )


def custom_build(raw):
    request = TravelRequest(**raw)
    catalog = load("activities", request.destination)
    meal = next(a for a in catalog if a["category"] == "meal")
    activity = next(a for a in catalog if a["category"] == "attraction")
    return dict(
        request=raw,
        flight_id=flight_options(request.origin, request.destination)[0]["id"],
        hotel_id=load("hotels", request.destination)[0]["id"],
        days=[
            dict(
                date=str(day),
                title="Generic simulated city day",
                schedule=[
                    dict(
                        activity_id=meal["id"],
                        start_time="10:30",
                        end_time="11:15",
                        meal="breakfast",
                    ),
                    dict(
                        activity_id=meal["id"], start_time="12:00", end_time="12:45", meal="lunch"
                    ),
                    dict(activity_id=activity["id"], start_time="13:00", end_time="14:00"),
                    dict(
                        activity_id=meal["id"], start_time="17:00", end_time="17:45", meal="dinner"
                    ),
                ],
            )
            for day in dates(request.start_date, request.end_date)
        ],
    )


def test_custom_route_builder_and_precheck_agree():
    raw = custom_request()
    estimate = estimate_minimum_budget(TravelRequest(**raw))
    result = execute_tool("build_itinerary", custom_build(raw))
    assert result["status"] == "ok", result
    assert result["data"]["budget_breakdown"]["total"] == estimate.minimum_total
    assert result["data"]["selected_flights"]["origin"] == "Berlin"
    assert result["data"]["trip_summary"]["destination"] == "Lisbon"
    assert any("not verified" in note for note in result["data"]["warnings"])
    assert any("generic accommodation" in note for note in result["data"]["warnings"])


def test_custom_route_full_mocked_agent(tmp_path):
    raw = custom_request()
    responses = [
        response(
            "get_weather",
            dict(destination="Lisbon", start_date=raw["start_date"], end_date=raw["end_date"]),
        ),
        response(
            "search_flights",
            dict(
                origin="Berlin",
                destination="Lisbon",
                departure_date=raw["start_date"],
                return_date=raw["end_date"],
                travelers=1,
            ),
        ),
        response(
            "search_hotels",
            dict(
                destination="Lisbon",
                check_in=raw["start_date"],
                check_out=raw["end_date"],
                travelers=1,
            ),
        ),
        response(
            "search_activities", dict(destination="Lisbon", dietary_preferences=["vegetarian"])
        ),
        response("build_itinerary", custom_build(raw)),
        response(
            content=json.dumps(dict(status="success", message="Simulated itinerary validated"))
        ),
    ]
    agent, client, result = run(tmp_path, raw, responses)
    assert result.status == "success"
    assert len({e["tool"] for e in agent.trace.data["events"] if e["kind"] == "tool_call"}) == 5
    assert "generic" in json.dumps(client.requests[0]["messages"])


def test_catalogues_are_stable_and_destination_specific():
    one = load("activities", "Lisbon")
    assert one == load("activities", "  lisbon  ")
    assert len([a for a in one if a["category"] == "attraction"]) >= 10
    other = load("activities", "Tokyo")
    assert {a["id"] for a in one}.isdisjoint(a["id"] for a in other)


def test_route_ids_are_bound_to_origin():
    assert flight_options("Berlin", "Rome") != flight_options("Madrid", "Rome")
    assert flight_options("Berlin", "Rome") == flight_options(" berlin ", " ROME ")
    assert flight_options("Prague", "Rome")[0]["id"] == "rom-flight-1"


def test_wrong_route_id_rejected():
    raw = custom_request()
    args = custom_build(raw)
    args["flight_id"] = flight_options("Madrid", "Lisbon")[0]["id"]
    assert execute_tool("build_itinerary", args)["status"] == "error"


@pytest.mark.parametrize(
    "origin,destination", [("São Paulo", "東京"), ("New York", "Cape Town"), ("Прага", "Вена")]
)
def test_unicode_and_global_city_labels(origin, destination):
    raw = custom_request()
    raw.update(origin=origin, destination=destination, budget=1000)
    result = execute_tool("build_itinerary", custom_build(raw))
    assert result["status"] == "ok", result
    assert simulation_notes(origin, destination)


@pytest.mark.parametrize("city", ["", "   ", "12345", "x" * 121])
def test_invalid_city_labels(city):
    raw = custom_request()
    raw["origin"] = city
    with pytest.raises(ValidationError):
        TravelRequest(**raw)


def test_identical_cities_rejected_after_normalization():
    raw = custom_request()
    raw.update(origin="  LISBON ", destination="lisbon")
    with pytest.raises(ValidationError, match="different"):
        TravelRequest(**raw)


def test_ui_accepts_any_origin_and_destination(monkeypatch, tmp_path):
    monkeypatch.setattr("tracing.ROOT", tmp_path)
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=20)
    app.selectbox(key="origin_city").set_value("New York")
    app.selectbox(key="destination_city").set_value("Tokyo")
    app.number_input[1].set_value(1.0)
    app.button[0].click().run(timeout=20)
    assert not app.exception
    assert app.selectbox(key="origin_city").value == "New York"
    assert app.selectbox(key="destination_city").value == "Tokyo"
    assert app.session_state["result"].status == "infeasible"
    assert app.session_state["trace"]["request"]["origin"] == "New York"
