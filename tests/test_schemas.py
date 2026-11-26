import pytest
from pydantic import ValidationError

from schemas import BudgetBreakdown, FinalResponse, TravelRequest


def test_valid_request(request_data):
    request = TravelRequest(**request_data)
    assert request.travelers == 1
    assert request.budget == 600


@pytest.mark.parametrize(
    "field,value",
    [
        ("budget", 0),
        ("budget", -1),
        ("budget", float("nan")),
        ("budget", float("inf")),
        ("travelers", 0),
        ("travelers", -2),
        ("travelers", 1.5),
        ("origin", " "),
        ("destination", ""),
        ("end_date", "2027-04-09"),
        ("end_date", "2027-05-10"),
        ("start_date", "bad"),
        ("start_date", "2020-01-01"),
        ("dietary_preferences", ["unknown"]),
        ("interests", [" "]),
    ],
)
def test_invalid_input(request_data, field, value):
    request_data[field] = value
    with pytest.raises(ValidationError):
        TravelRequest(**request_data)


def test_missing_fields():
    with pytest.raises(ValidationError):
        TravelRequest.model_validate({})


def test_success_requires_itinerary():
    with pytest.raises(ValidationError):
        FinalResponse(status="success", message="Done")


def test_failure_cannot_contain_plan():
    with pytest.raises(ValidationError):
        FinalResponse(status="infeasible", message="No", itinerary={})


def test_budget_sum_validation():
    with pytest.raises(ValidationError):
        BudgetBreakdown(
            flights=1,
            accommodation=1,
            food=1,
            activities=1,
            local_transport=1,
            total=6,
            remaining_budget=0,
        )


def test_past_departure_rejected(request_data, monkeypatch):
    from datetime import date

    monkeypatch.setattr("schemas.current_date", lambda: date(2027, 4, 11))
    with pytest.raises(ValidationError, match="Start date cannot be before today"):
        TravelRequest(**request_data)


def test_today_departure_allowed(request_data, monkeypatch):
    from datetime import date

    monkeypatch.setattr("schemas.current_date", lambda: date(2027, 4, 10))
    assert TravelRequest(**request_data).start_date == date(2027, 4, 10)


@pytest.mark.parametrize(
    "value,expected", [("7:30", "07:30"), ("8:15", "08:15"), ("07:30", "07:30")]
)
def test_schedule_accepts_single_digit_hour(value, expected):
    from schemas import ScheduledSelection

    slot = ScheduledSelection(activity_id="retrieved-id", start_time=value, end_time="09:00")
    assert slot.start_time.strftime("%H:%M") == expected


@pytest.mark.parametrize("value", ["25:00", "7:65", "not a time"])
def test_schedule_rejects_invalid_clocks(value):
    from schemas import ScheduledSelection

    with pytest.raises(ValidationError):
        ScheduledSelection(activity_id="retrieved-id", start_time=value, end_time="09:00")
