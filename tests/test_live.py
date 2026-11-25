"""Live-mode integration contracts exercised ONLY with mocked HTTP responses."""

import json
from datetime import date
from types import SimpleNamespace

import httpx
import pytest
from test_agent import response

from agent import TravelAgent
from config import Settings
from providers.http import ProviderClient
from providers.runtime import LiveTools
from providers.schedule import opening_windows
from schemas import (
    ActivityArgs,
    BuildArgs,
    FlightArgs,
    HotelArgs,
    RestaurantArgs,
    TravelRequest,
    WeatherArgs,
)
from tools.common import ToolFailure, dates
from tools.registry import execute_tool
from tracing import redact


def fixture_handler(request):
    p = dict(request.url.params)
    if request.url.path == "/account.json":
        return httpx.Response(
            200,
            json={
                "account_status": "Active",
                "total_searches_left": 250,
                "api_key": "fixture-serp-secret",
                "account_email": "private@example.test",
            },
        )
    if "geocoding" in request.url.host:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "name": "Rome",
                        "country": "Italy",
                        "country_code": "IT",
                        "population": 2000000,
                        "latitude": 41.9,
                        "longitude": 12.5,
                        "timezone": "Europe/Rome",
                    }
                ]
            },
        )
    if "open-meteo" in request.url.host:
        ds = dates(date.fromisoformat(p["start_date"]), date.fromisoformat(p["end_date"]))
        data = {
            "time": [str(d) for d in ds],
            "temperature_2m_min": [10] * len(ds),
            "temperature_2m_max": [20] * len(ds),
            "weather_code": [2] * len(ds),
            "wind_speed_10m_max": [12] * len(ds),
        }
        data[
            "precipitation_probability_max"
            if request.url.path.endswith("forecast")
            else "precipitation_sum"
        ] = [70 if request.url.path.endswith("forecast") else 0] * len(ds)
        return httpx.Response(200, json={"daily": data})
    engine = p.get("engine")
    if engine == "google_flights_autocomplete":
        city = p["q"]
        return httpx.Response(
            200,
            json={
                "suggestions": [
                    {
                        "name": city,
                        "type": "city",
                        "id": "/m/" + city.lower(),
                        "airports": [
                            {"name": city + " Airport", "id": "PRG" if city == "Prague" else "FCO"}
                        ],
                    }
                ]
            },
        )
    if engine == "google_flights":
        inbound = "departure_token" in p
        day = p["return_date"] if inbound else p["outbound_date"]
        raw = {
            "flights": [
                {
                    "airline": "Fixture Air",
                    "flight_number": "FX 123",
                    "departure_airport": {
                        "id": "FCO" if inbound else "PRG",
                        "time": day + (" 21:00" if inbound else " 07:00"),
                    },
                    "arrival_airport": {
                        "id": "PRG" if inbound else "FCO",
                        "time": day + (" 23:00" if inbound else " 09:00"),
                    },
                    "duration": 120,
                }
            ],
            "total_duration": 120,
            "type": "Round trip",
            "price": 200 * int(p["adults"]) if inbound else 9999,
            "booking_token": "booking" if inbound else None,
            "departure_token": None if inbound else "outbound-token",
        }
        return httpx.Response(
            200,
            json={
                "best_flights": [raw],
                "search_parameters": {"currency": "EUR", "adults": int(p["adults"])},
                "search_metadata": {"google_flights_url": "https://www.google.com/travel/flights"},
            },
        )
    if engine == "google_hotels":
        n = (date.fromisoformat(p["check_out_date"]) - date.fromisoformat(p["check_in_date"])).days
        return httpx.Response(
            200,
            json={
                "properties": [
                    {
                        "property_token": "hotel-provider-id",
                        "name": "Fixture Hotel",
                        "type": "hotel",
                        "address": "Fixture address",
                        "rate_per_night": {"extracted_after_taxes_fees": 50},
                        "total_rate": {"extracted_after_taxes_fees": 50 * n},
                        "overall_rating": 4.5,
                        "reviews": 250,
                        "gps_coordinates": {"latitude": 41.9, "longitude": 12.5},
                        "link": "https://hotel.example.test",
                        "images": [{"original_image": "https://hotel.example.test/photo.jpg"}],
                    }
                ],
                "serpapi_pagination": {"next_page_token": "page-two"},
            },
        )
    if engine == "google_maps":
        restaurant = "restaurant" in p["q"] or "cafe" in p["q"]
        return httpx.Response(
            200,
            json={
                "local_results": [
                    {
                        "title": "Fixture Vegan Cafe" if restaurant else "Fixture Museum",
                        "place_id": "cafe" if restaurant else "museum",
                        "type": "Vegetarian restaurant" if restaurant else "Museum",
                        "address": "Fixture street",
                        "rating": 4.6,
                        "reviews": 90,
                        "price": "$" if restaurant else "$$",
                        "gps_coordinates": {"latitude": 41.9001, "longitude": 12.5001},
                        "operating_hours": {
                            day: "8 AM–10 PM"
                            for day in [
                                "monday",
                                "tuesday",
                                "wednesday",
                                "thursday",
                                "friday",
                                "saturday",
                                "sunday",
                            ]
                        },
                        "website": "https://venue.example.test",
                        "thumbnail": "https://venue.example.test/photo.jpg",
                    }
                ]
            },
        )
    raise AssertionError("Unexpected fixture endpoint")


@pytest.fixture
def live_settings():
    return Settings(
        data_mode="live",
        serpapi_api_key="fixture-serp-secret",
        api_key="unused-openai",
        max_serpapi_requests=15,
    )


@pytest.fixture
def runtime(tmp_path, request_data, live_settings):
    request_data["budget"] = 2000
    return LiveTools(
        TravelRequest(**request_data),
        live_settings,
        http_client=httpx.Client(transport=httpx.MockTransport(fixture_handler)),
        cache_path=tmp_path / "cache.sqlite",
    )


def populate(runtime, restrict_hotel=False):
    r = runtime.request
    runtime.get_weather(
        WeatherArgs(destination=r.destination, start_date=r.start_date, end_date=r.end_date)
    )
    runtime.search_flights(
        FlightArgs(
            origin=r.origin,
            destination=r.destination,
            departure_date=r.start_date,
            return_date=r.end_date,
            travelers=r.travelers,
        )
    )
    runtime.search_hotels(
        HotelArgs(
            destination=r.destination,
            check_in=r.start_date,
            check_out=r.end_date,
            travelers=r.travelers,
        )
    )
    runtime.search_activities(ActivityArgs(destination=r.destination, interests=["museums"]))
    runtime.search_restaurants(
        RestaurantArgs(destination=r.destination, dietary_preferences=["vegetarian"])
    )


def selection(runtime):
    r = runtime.request
    meal = next(a for a, _ in runtime.activities.values() if a.category == "meal")
    visit = next(a for a, _ in runtime.activities.values() if a.category == "attraction")
    schedule = [
        dict(activity_id=meal.id, start_time="10:30", end_time="11:15", meal="breakfast"),
        dict(activity_id=meal.id, start_time="12:00", end_time="12:45", meal="lunch"),
        dict(activity_id=visit.id, start_time="13:00", end_time="14:00"),
        dict(activity_id=meal.id, start_time="17:00", end_time="17:45", meal="dinner"),
    ]
    return BuildArgs(
        request=r,
        flight_id=next(iter(runtime.flights)),
        hotel_id=next(iter(runtime.hotels)),
        days=[
            dict(date=d, title="Fixture day", schedule=schedule)
            for d in dates(r.start_date, r.end_date)
        ],
    )


def test_roundtrip_uses_return_quote_not_outbound_or_double_count(runtime):
    r = runtime.request
    result = runtime.search_flights(
        FlightArgs(
            origin=r.origin,
            destination=r.destination,
            departure_date=r.start_date,
            return_date=r.end_date,
            travelers=2,
        )
    ).data[0]
    assert result.total_price == 400
    assert result.price_per_traveler == 200
    assert result.return_segments and result.outbound_segments
    assert result.price_info.kind == "retrieved"
    assert runtime.client.serpapi_requests == 4


def test_filters_reuse_http_results_and_no_results_are_recoverable(runtime):
    r = runtime.request
    args = HotelArgs(
        destination=r.destination,
        check_in=r.start_date,
        check_out=r.end_date,
        travelers=1,
        max_nightly_price=1,
    )
    first = execute_tool("search_hotels", args.model_dump(mode="json"), runtime)
    assert first["error"]["code"] == "no_priced_hotels"
    result = runtime.search_hotels(args.model_copy(update={"max_nightly_price": 100}))
    assert result.data[0].total_cost == 150
    assert runtime.client.serpapi_requests == 1
    assert runtime.client.cache_hits >= 1


def test_hotels_group_rooms_taxes_and_total_rate(runtime):
    r = runtime.request
    hotel = runtime.search_hotels(
        HotelArgs(
            destination=r.destination, check_in=r.start_date, check_out=r.end_date, travelers=3
        )
    ).data[0]
    assert hotel.nights == 3 and hotel.rooms == 2
    assert hotel.total_cost == 300 and hotel.price_per_night == 50
    assert hotel.taxes_included is True
    assert hotel.price_info.kind == "estimated"
    assert hotel.image_url and hotel.reviews == 250


def test_unknown_admission_and_meal_costs_are_estimated(runtime):
    result = runtime.search_activities(ActivityArgs(destination="Rome")).data[0]
    assert result.price_per_person == 15 and result.price_info.kind == "estimated"
    assert result.opening_hours and result.address and result.url
    meal = runtime.search_restaurants(
        RestaurantArgs(destination="Rome", dietary_preferences=["halal"])
    ).data[0]
    assert meal.price_info.kind == "estimated"
    assert "halal" not in meal.dietary_compatibility
    assert any("not a guarantee" in note for note in meal.notes)


def test_forecast_and_historical_labels(runtime):
    forecasts = runtime.get_weather(
        WeatherArgs(destination="Rome", start_date="2026-11-24", end_date="2026-11-25")
    ).data
    assert forecasts[0].information_type == "Weather forecast"
    assert forecasts[0].rain_probability == 0.7 and forecasts[0].wind_speed_kmh == 12
    assert forecasts[0].recommendation == "indoor"
    climate = runtime.get_weather(
        WeatherArgs(destination="Rome", start_date="2027-04-10", end_date="2027-04-13")
    ).data
    assert all(w.information_type == "Historical climate estimate" for w in climate)
    assert climate[0].rain_probability is None
    assert len(climate[0].historical_years) == 3
    assert runtime.client.serpapi_requests == 0


def test_builder_uses_store_costs_and_no_additional_requests(runtime):
    populate(runtime)
    count = runtime.client.serpapi_requests
    plan = runtime.build_itinerary(selection(runtime)).data
    assert plan.data_source == "live" and plan.budget_breakdown.total == 586
    assert len(plan.cost_items) > 10
    assert runtime.client.serpapi_requests == count == 7
    assert all(slot.activity.source for day in plan.daily_itinerary for slot in day.schedule)


def test_live_budget_rejection_and_unknown_id(runtime):
    populate(runtime)
    args = selection(runtime)
    runtime.request = runtime.request.model_copy(update={"budget": 100})
    args.request = runtime.request
    result = execute_tool("build_itinerary", args.model_dump(mode="json"), runtime)
    assert result["error"]["code"] == "over_budget" and result["data_source"] == "live"
    args.flight_id = "invented"
    assert (
        execute_tool("build_itinerary", args.model_dump(mode="json"), runtime)["error"]["code"]
        == "unknown_flight"
    )


def test_confirmed_closed_places_rejected(runtime):
    populate(runtime)
    key = next(key for key, (a, _) in runtime.activities.items() if a.category == "attraction")
    activity, city = runtime.activities[key]
    runtime.activities[key] = (
        activity.model_copy(update={"opening_hours": {"saturday": "Closed"}}),
        city,
    )
    result = execute_tool("build_itinerary", selection(runtime).model_dump(mode="json"), runtime)
    assert result["error"]["code"] == "place_closed"


def test_geographic_transfer_rejects_too_short_gap(runtime):
    from schemas import Coordinates

    populate(runtime)
    key = next(key for key, (a, _) in runtime.activities.items() if a.category == "attraction")
    activity, city = runtime.activities[key]
    runtime.activities[key] = (
        activity.model_copy(update={"coordinates": Coordinates(latitude=42.1, longitude=12.8)}),
        city,
    )
    result = execute_tool("build_itinerary", selection(runtime).model_dump(mode="json"), runtime)
    assert result["error"]["code"] == "transfer_or_overlap"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Closed", []),
        ("Open 24 hours", [(0, 1440)]),
        ("10 AM–5 PM", [(600, 1020)]),
        ("10 AM–2 AM", [(600, 1560)]),
        ("not supplied", None),
    ],
)
def test_opening_hour_formats(raw, expected):
    assert opening_windows(raw) == expected


def test_persistent_cache_and_limit(tmp_path, live_settings):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"ok": True})

    first = ProviderClient(
        live_settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        cache_path=tmp_path / "cache.sqlite",
    )
    first.get_json(
        "https://serpapi.com/search.json", {"engine": "google_maps", "q": "same"}, serp=True
    )
    second = ProviderClient(
        live_settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        cache_path=tmp_path / "cache.sqlite",
    )
    second.get_json(
        "https://serpapi.com/search.json", {"q": "same", "engine": "google_maps"}, serp=True
    )
    assert len(calls) == 1 and second.serpapi_requests == 0 and second.cache_hits == 1
    second.settings = Settings(
        data_mode="live", serpapi_api_key="fixture-serp-secret", max_serpapi_requests=1
    )
    second.get_json("https://serpapi.com/search.json", {"q": "different"}, serp=True)
    with pytest.raises(ToolFailure, match="limit"):
        second.get_json("https://serpapi.com/search.json", {"q": "third"}, serp=True)


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "invalid_api_key"),
        (429, "quota_or_rate_limit"),
        (400, "provider_http_error"),
        (500, "provider_http_error"),
    ],
)
def test_http_errors_are_structured(tmp_path, live_settings, status, code):
    client = ProviderClient(
        live_settings,
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(status, json={"error": "sensitive provider body"})
            )
        ),
        cache_path=tmp_path / "cache.sqlite",
    )
    with pytest.raises(ToolFailure) as error:
        client.get_json("https://serpapi.com/search.json", {}, serp=True)
    assert error.value.error.code == code
    assert "sensitive" not in error.value.error.message
    assert client.serpapi_requests == (2 if status == 500 else 1)


def test_secret_redaction_for_serp_urls_and_account(tmp_path, live_settings, monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "fixture-serp-secret")
    events = []
    client = ProviderClient(
        live_settings,
        on_event=lambda kind, **values: events.append(dict(kind=kind, **values)),
        client=httpx.Client(transport=httpx.MockTransport(fixture_handler)),
        cache_path=tmp_path / "cache.sqlite",
    )
    result = client.account()
    assert "api_key" not in result and "account_email" not in result
    assert client.serpapi_requests == 0
    assert "fixture-serp-secret" not in json.dumps(events)
    assert "secret-value" not in redact(
        "https://serpapi.com/search.json?api_key=secret-value&q=Rome"
    )
    assert "fixture-serp-secret" not in repr(live_settings)


def test_missing_serp_key_has_no_demo_fallback(tmp_path, request_data):
    agent = TravelAgent(
        Settings(data_mode="live", serpapi_api_key="", api_key="unused"), trace_directory=tmp_path
    )
    result = agent.run(request_data)
    assert result.status == "error" and result.data_source == "live"
    assert "SERPAPI_API_KEY" in result.message
    assert not agent.trace.data["iterations"]


def test_full_live_tool_loop_and_hotel_recovery(tmp_path, request_data, live_settings):
    request_data["budget"] = 2000

    class ScriptedClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=self)
            self.stage = 0
            self.agent = None

        def create(self, **kwargs):
            self.stage += 1
            r = self.agent.runtime.request
            hotel = dict(
                destination=r.destination,
                check_in=str(r.start_date),
                check_out=str(r.end_date),
                travelers=r.travelers,
            )
            scripted = {
                1: (
                    "get_weather",
                    dict(
                        destination=r.destination,
                        start_date=str(r.start_date),
                        end_date=str(r.end_date),
                    ),
                ),
                2: (
                    "search_flights",
                    dict(
                        origin=r.origin,
                        destination=r.destination,
                        departure_date=str(r.start_date),
                        return_date=str(r.end_date),
                        travelers=r.travelers,
                    ),
                ),
                3: ("search_hotels", dict(**hotel, max_nightly_price=1)),
                4: ("search_hotels", hotel),
                5: ("search_activities", dict(destination=r.destination, interests=["museums"])),
                6: (
                    "search_restaurants",
                    dict(destination=r.destination, dietary_preferences=["vegetarian"]),
                ),
            }
            if self.stage in scripted:
                return response(*scripted[self.stage])
            if self.stage == 7:
                return response(
                    "build_itinerary", selection(self.agent.runtime).model_dump(mode="json")
                )
            return response(content=json.dumps({"status": "success", "message": "Done"}))

    ai = ScriptedClient()
    agent = TravelAgent(
        live_settings,
        client=ai,
        http_client=httpx.Client(transport=httpx.MockTransport(fixture_handler)),
        cache_path=tmp_path / "http.sqlite",
        trace_directory=tmp_path,
    )
    ai.agent = agent
    result = agent.run(request_data)
    assert result.status == "success" and result.data_source == "live", result
    assert result.serpapi_requests == 7 and result.provider_cache_hits > 0
    assert agent.trace.data["execution_mode"] == "mocked_unit_test"
    assert agent.trace.data["data_mode"] == "live"
    assert any(event["kind"] == "replanning" for event in agent.trace.data["events"])
    assert agent.trace.data["budget_validation"]["valid"]


def test_negative_results_are_not_requested_twice(tmp_path, live_settings):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200, json={"error": "Google Flights hasn't returned any results for this query."}
        )

    client = ProviderClient(
        live_settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        cache_path=tmp_path / "cache.sqlite",
    )
    for _ in range(2):
        with pytest.raises(ToolFailure) as error:
            client.get_json(
                "https://serpapi.com/search.json", {"engine": "google_flights"}, serp=True
            )
        assert error.value.error.code == "no_results"
    assert len(calls) == 1 and client.serpapi_requests == 1


def test_timeout_retries_are_bounded(tmp_path, live_settings):
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("fixture", request=request)

    client = ProviderClient(
        live_settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        cache_path=tmp_path / "cache.sqlite",
    )
    with pytest.raises(ToolFailure) as error:
        client.get_json("https://serpapi.com/search.json", {}, serp=True)
    assert error.value.error.code == "provider_timeout"
    assert len(calls) == client.serpapi_requests == 2


def test_account_quota_zero_prevents_search(tmp_path, live_settings):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"total_searches_left": 0, "account_status": "Active"})

    client = ProviderClient(
        live_settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        cache_path=tmp_path / "cache.sqlite",
    )
    with pytest.raises(ToolFailure) as error:
        client.search("google_maps", q="Rome")
    assert error.value.error.code == "quota_exhausted"
    assert calls == ["/account.json"] and client.serpapi_requests == 0


def test_unpriced_hotels_never_get_invented_prices(tmp_path, live_settings, request_data):
    def handler(request):
        if request.url.params.get("engine") == "google_hotels":
            return httpx.Response(200, json={"properties": [{"name": "Unpriced hotel"}]})
        return fixture_handler(request)

    runtime = LiveTools(
        TravelRequest(**request_data),
        live_settings,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        cache_path=tmp_path / "cache.sqlite",
    )
    result = execute_tool(
        "search_hotels",
        dict(
            destination="Rome",
            check_in=request_data["start_date"],
            check_out=request_data["end_date"],
            travelers=1,
        ),
        runtime,
    )
    assert result["error"]["code"] == "no_priced_hotels" and result["data"] is None


def test_ambiguity_ends_with_user_clarification(tmp_path, live_settings, request_data):
    from test_agent import MockClient

    def handler(request):
        if request.url.params.get("engine") == "google_flights_autocomplete":
            return httpx.Response(
                200,
                json={
                    "suggestions": [
                        {
                            "name": "Prague, Czechia",
                            "type": "city",
                            "id": "/m/one",
                            "airports": [{"id": "PRG"}],
                        },
                        {
                            "name": "Prague, Oklahoma",
                            "type": "city",
                            "id": "/m/two",
                            "airports": [{"id": "OKC"}],
                        },
                    ]
                },
            )
        return fixture_handler(request)

    ai = MockClient(
        [
            response(
                "search_flights",
                dict(
                    origin="Prague",
                    destination="Rome",
                    departure_date=request_data["start_date"],
                    return_date=request_data["end_date"],
                    travelers=1,
                ),
            )
        ]
    )
    agent = TravelAgent(
        live_settings,
        client=ai,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        trace_directory=tmp_path,
        cache_path=tmp_path / "cache.sqlite",
    )
    result = agent.run(request_data)
    assert result.status == "needs_clarification"
    assert "Prague, Czechia" in result.message
    assert len(ai.requests) == 1 and result.serpapi_requests == 1


def test_live_ui_renders_sources_prices_and_estimates(runtime, monkeypatch):
    monkeypatch.setenv("DATA_MODE", "live")
    from streamlit.testing.v1 import AppTest

    from config import ROOT
    from schemas import FinalResponse

    populate(runtime)
    result = FinalResponse(
        status="success",
        message="Live fixture UI",
        data_source="live",
        itinerary=runtime.build_itinerary(selection(runtime)).data,
        serpapi_requests=7,
    )
    app = AppTest.from_file(str(ROOT / "app.py"))
    app.session_state["result"] = result
    app.session_state["trace"] = {"data_mode": "live", "events": []}
    app.run(timeout=20)
    assert not app.exception
    assert len(app.metric) == 3
    assert any("Retrieved prices and estimated costs" in item.value for item in app.subheader)


def test_live_default_header_and_no_simulation_fallback(monkeypatch):
    from streamlit.testing.v1 import AppTest

    from config import ROOT

    monkeypatch.setenv("DATA_MODE", "live")
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=20)
    assert not app.exception
    assert app.toggle(key="live_mode").value is True
    assert not app.sidebar.radio
    assert any(
        "Travel information is retrieved from external data providers." in item.value
        for item in app.markdown
    )
    assert not any("Educational simulation" in item.value for item in app.markdown)


def test_user_supplied_city_qualifiers_are_restored_without_guessing(tmp_path, live_settings):
    from cities import bind_city_label

    assert bind_city_label("Rome", "Rome, Italy") == "Rome, Italy"
    with pytest.raises(ValueError):
        bind_city_label("Rome, Georgia", "Rome, Italy")
    with pytest.raises(ValueError):
        bind_city_label("Rome, Italy", "Rome")
    raw = dict(
        origin="Prague, Czechia",
        destination="Rome, Italy",
        start_date="2027-04-10",
        end_date="2027-04-13",
        budget=2000,
        travelers=1,
    )
    runtime = LiveTools(
        TravelRequest(**raw),
        live_settings,
        http_client=httpx.Client(transport=httpx.MockTransport(fixture_handler)),
        cache_path=tmp_path / "cache.sqlite",
    )
    result = runtime.search_flights(
        FlightArgs(
            origin="Prague",
            destination="Rome",
            departure_date=raw["start_date"],
            return_date=raw["end_date"],
            travelers=1,
        )
    )
    assert result.data[0].origin == "Prague, Czechia"
    assert result.data[0].destination == "Rome, Italy"
    assert runtime.flights[result.data[0].id][1].origin == raw["origin"]


def test_auto_schedule_repairs_times_using_only_retrieved_ids(runtime):
    from providers.schedule import open_for_slot
    from schemas import LiveBuildArgs

    populate(runtime)
    args = LiveBuildArgs.model_validate(selection(runtime).model_dump(mode="json"))
    args.auto_schedule = True
    # These suggestions are deliberately impossible; auto mode must place actual
    # retrieved venues into valid windows rather than trusting LLM time arithmetic.
    for day in args.days:
        for slot in day.schedule:
            slot.start_time = __import__("datetime").time(1)
            slot.end_time = __import__("datetime").time(2)
    count = runtime.client.serpapi_requests
    plan = runtime.build_itinerary(args).data
    assert plan.budget_breakdown.total == 586
    assert runtime.client.serpapi_requests == count
    for day in plan.daily_itinerary:
        assert {s.meal for s in day.schedule if s.meal} == {"breakfast", "lunch", "dinner"}
        for slot in day.schedule:
            assert slot.activity.id in runtime.activities
            assert (
                open_for_slot(
                    slot.activity,
                    day.date,
                    slot.start_time.hour * 60 + slot.start_time.minute,
                    slot.end_time.hour * 60 + slot.end_time.minute,
                )
                is not False
            )


def test_auto_schedule_respects_early_return_as_travel_only_day(runtime):
    from datetime import datetime

    from schemas import LiveBuildArgs

    populate(runtime)
    key = next(iter(runtime.flights))
    flight, args = runtime.flights[key]
    runtime.flights[key] = (
        flight.model_copy(
            update={
                "return_departure": datetime.combine(
                    runtime.request.end_date, __import__("datetime").time(6)
                )
            }
        ),
        args,
    )
    selected = selection(runtime)
    selected.auto_schedule = True
    plan = runtime.build_itinerary(
        LiveBuildArgs.model_validate(selected.model_dump(mode="json"))
    ).data
    assert not plan.daily_itinerary[-1].schedule
    assert any(
        "meal allowance" in note.lower() for note in plan.daily_itinerary[-1].recommendations
    )


@pytest.mark.parametrize("target,accepted", [(600, True), (550, True), (532.72, False)])
def test_live_flexible_budget_is_checked_from_trusted_prices(runtime, target, accepted):
    populate(runtime)
    runtime.request = runtime.request.model_copy(update={"budget": target})
    args = selection(runtime)
    before = runtime.client.serpapi_requests
    result = execute_tool("build_itinerary", args.model_dump(mode="json"), runtime)
    assert (result["status"] == "ok") is accepted
    assert runtime.client.serpapi_requests == before
    if accepted:
        assert result["data"]["budget_breakdown"]["total"] == 586
        assert result["data"]["budget_breakdown"]["remaining_budget"] == target - 586
        if target < 586:
            assert any("Budget alternative" in w for w in result["data"]["warnings"])
    else:
        assert result["error"]["code"] == "over_budget"


def test_closed_attraction_identified_before_meal_search_and_replaced(runtime):
    """Regression: the screenshot kept a Monday-closed museum across five builds."""
    populate(runtime)
    args = selection(runtime)
    args.auto_schedule = True
    museum = next(p for p, _ in runtime.activities.values() if p.category == "attraction")
    # April 12, 2027 is Monday. Other retrieved venues remain available.
    closed = museum.model_copy(update={"opening_hours": {"monday": "Closed"}})
    alternative = museum.model_copy(
        update={"id": "fixture-alternative", "name": "Alternative gallery"}
    )
    runtime.activities[closed.id] = (closed, runtime.request.destination)
    runtime.activities[alternative.id] = (alternative, runtime.request.destination)
    before = runtime.client.serpapi_requests
    result = execute_tool("build_itinerary", args.model_dump(mode="json"), runtime)
    error = result["error"]
    assert error["code"] == "selected_place_closed"
    assert "2027-04-12" in error["message"] and closed.name in error["message"]
    assert "fixture-alternative" in " ".join(error["suggestions"])
    for day in args.days:
        if str(day.date) == "2027-04-12":
            for slot in day.schedule:
                if slot.activity_id == closed.id:
                    slot.activity_id = alternative.id
    revised = runtime.build_itinerary(args).data
    assert revised.daily_itinerary[2].schedule
    assert runtime.client.serpapi_requests == before


def test_maps_thumbnail_reused_without_extra_requests(runtime):
    result = runtime.search_activities(ActivityArgs(destination="Rome")).data[0]
    assert result.image_url == "https://venue.example.test/photo.jpg"
    assert runtime.client.serpapi_requests == 1
