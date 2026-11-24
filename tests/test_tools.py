import pytest

from tools.registry import execute_tool, tool_definitions


def weather(destination="Rome", start="2027-04-10", end="2027-04-13"):
    return execute_tool(
        "get_weather", dict(destination=destination, start_date=start, end_date=end)
    )


def test_weather_lookup():
    result = weather()
    assert result["status"] == "ok"
    assert len(result["data"]) == 4
    assert result["data_source"] == "simulated"


def test_rain_recommends_indoors():
    assert weather("Paris")["data"][0]["recommendation"] == "indoor"


@pytest.mark.parametrize("city", ["Rome", "Paris", "Barcelona", "Vienna", "Amsterdam"])
def test_destinations_have_sufficient_activities(city):
    result = execute_tool("search_activities", {"destination": city})
    assert len([a for a in result["data"] if a["category"] == "attraction"]) >= 10
    assert any(a["price_per_person"] == 0 for a in result["data"])


def test_future_dates_repeat_seasonal_profile():
    assert weather(start="2030-04-10", end="2030-04-13")["status"] == "ok"


def test_new_destination_uses_simulated_weather():
    result = weather("Tokyo")
    assert result["status"] == "ok"
    assert result["data_source"] == "simulated"


def test_unsupported_dates():
    assert weather(start="2040-04-10", end="2040-04-13")["error"]["code"] == "invalid_arguments"


def test_flight_group_price():
    result = execute_tool(
        "search_flights",
        dict(
            origin="Prague",
            destination="Rome",
            departure_date="2027-04-10",
            return_date="2027-04-13",
            travelers=3,
        ),
    )
    assert result["data"][0]["total_price"] == 210
    assert result["data"][0]["return_departure_time"] == "21:00:00"


def test_no_flights():
    result = execute_tool(
        "search_flights",
        dict(
            origin="Prague",
            destination="Rome",
            departure_date="2027-04-10",
            return_date="2027-04-13",
            travelers=1,
            max_price=1,
        ),
    )
    assert result["error"]["code"] == "no_results"


def test_other_departure_city():
    result = execute_tool(
        "search_flights",
        dict(
            origin="Berlin",
            destination="Rome",
            departure_date="2027-04-10",
            return_date="2027-04-13",
            travelers=1,
        ),
    )
    assert result["status"] == "ok"
    assert result["data"][0]["origin"] == "Berlin"
    assert result["data"][0]["id"].startswith("synthetic-")


def test_hotel_nights_rooms_and_hostel_beds():
    result = execute_tool(
        "search_hotels",
        dict(destination="Rome", check_in="2027-04-10", check_out="2027-04-13", travelers=3),
    )
    hostel, budget = result["data"][:2]
    assert hostel["nights"] == 3 and hostel["rooms"] == 3 and hostel["total_cost"] == 207
    assert budget["rooms"] == 2 and budget["total_cost"] == 300


def test_hotel_recovery():
    args = dict(
        destination="Paris",
        check_in="2027-05-14",
        check_out="2027-05-16",
        travelers=1,
        max_nightly_price=30,
        accommodation_type="hotel",
    )
    assert execute_tool("search_hotels", args)["error"]["code"] == "no_results"
    args["accommodation_type"] = "hostel"
    assert execute_tool("search_hotels", args)["data"][0]["total_cost"] == 50


@pytest.mark.parametrize("diet", ["vegetarian", "vegan", "gluten-free"])
def test_dietary_filter(diet):
    result = execute_tool(
        "search_activities", dict(destination="Paris", dietary_preferences=[diet])
    )
    meals = [a for a in result["data"] if a["category"] == "meal"]
    assert meals and all(diet in a["dietary_compatibility"] for a in meals)


def test_indoor_filter():
    result = execute_tool("search_activities", dict(destination="Paris", environment="indoor"))
    assert all(a["environment"] == "indoor" for a in result["data"])


def test_no_activities():
    result = execute_tool(
        "search_activities", dict(destination="Paris", max_price=0, interests=["unknown"])
    )
    assert result["error"]["code"] == "no_results"


@pytest.mark.parametrize(
    "name,args",
    [
        ("unknown", {}),
        ("get_weather", "{bad"),
        ("search_hotels", {}),
        ("search_activities", {"destination": "Rome", "extra": 1}),
    ],
)
def test_dispatch_validation(name, args):
    assert execute_tool(name, args)["status"] == "error"


def test_five_schemas():
    schemas = tool_definitions()
    assert len(schemas) == 5
    assert all(t["function"]["parameters"]["additionalProperties"] is False for t in schemas)
