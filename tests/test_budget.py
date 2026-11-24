from conftest import make_build

from tools.registry import execute_tool


def test_correct_total(build_args):
    result = execute_tool("build_itinerary", build_args)
    assert result["status"] == "ok", result
    budget = result["data"]["budget_breakdown"]
    assert budget == dict(
        flights=70,
        accommodation=69,
        food=84,
        activities=0,
        local_transport=20,
        total=243,
        remaining_budget=357,
    )
    assert sum(d["estimated_cost"] for d in result["data"]["daily_itinerary"]) == 104


def test_paris_budget_and_diet(paris_data):
    result = execute_tool("build_itinerary", make_build(paris_data))
    assert result["status"] == "ok", result
    assert result["data"]["budget_breakdown"]["total"] == 203
    assert all(
        "vegetarian" in s["activity"]["dietary_compatibility"]
        for d in result["data"]["daily_itinerary"]
        for s in d["schedule"]
        if s["meal"]
    )


def test_multiple_travelers(build_args):
    build_args["request"]["travelers"] = 2
    result = execute_tool("build_itinerary", build_args)
    assert result["data"]["budget_breakdown"]["total"] == 486


def test_over_budget(build_args):
    build_args["request"]["budget"] = 200
    result = execute_tool("build_itinerary", build_args)
    assert result["error"]["code"] == "over_budget"
    assert result["error"]["suggestions"]


def test_unknown_activity(build_args):
    build_args["days"][0]["schedule"][2]["activity_id"] = "invented"
    assert execute_tool("build_itinerary", build_args)["error"]["code"] == "invalid_itinerary"


def test_unknown_hotel(build_args):
    build_args["hotel_id"] = "par-hotel-1"
    assert execute_tool("build_itinerary", build_args)["status"] == "error"


def test_overlap(build_args):
    build_args["days"][0]["schedule"][2]["start_time"] = "12:30"
    assert "overlap" in execute_tool("build_itinerary", build_args)["error"]["message"]


def test_airport_buffer(build_args):
    build_args["days"][0]["schedule"][0]["start_time"] = "09:30"
    assert "outside" in execute_tool("build_itinerary", build_args)["error"]["message"]


def test_rain_rejected(paris_data):
    args = make_build(paris_data)
    args["days"][0]["schedule"][2]["activity_id"] = "par-act-1"
    assert "Rain" in execute_tool("build_itinerary", args)["error"]["message"]


def test_dietary_rejected(paris_data):
    args = make_build(paris_data)
    args["days"][0]["schedule"][0]["activity_id"] = "par-meal-4"
    assert "dietary" in execute_tool("build_itinerary", args)["error"]["message"]


def test_missing_meal(build_args):
    build_args["days"][0]["schedule"].pop(0)
    assert "missing meals" in execute_tool("build_itinerary", build_args)["error"]["message"]


def test_day_coverage(build_args):
    build_args["days"].pop()
    assert "every trip date" in execute_tool("build_itinerary", build_args)["error"]["message"]


def test_pace_limit(paris_data):
    args = make_build(paris_data)
    args["days"][1]["schedule"][2]["end_time"] = "16:15"
    assert "pace" in execute_tool("build_itinerary", args)["error"]["message"]


def test_duration_validation(build_args):
    build_args["days"][0]["schedule"][2]["end_time"] = "13:30"
    assert "at least" in execute_tool("build_itinerary", build_args)["error"]["message"]


def test_single_day_no_lodging(request_data):
    request_data["end_date"] = request_data["start_date"]
    result = execute_tool("build_itinerary", make_build(request_data))
    assert result["status"] == "ok"
    assert result["data"]["selected_accommodation"]["nights"] == 0
    assert result["data"]["budget_breakdown"]["accommodation"] == 0
