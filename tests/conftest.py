import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import ROOT
from schemas import TravelRequest


@pytest.fixture
def request_data():
    return json.loads((ROOT / "examples/rome.json").read_text())


@pytest.fixture
def paris_data():
    return json.loads((ROOT / "examples/paris.json").read_text())


def make_build(raw):
    from tools.common import dates

    request = TravelRequest.model_validate(raw)
    prefix = request.destination[:3].lower()
    days = []
    for day in dates(request.start_date, request.end_date):
        days.append(
            {
                "date": str(day),
                "title": "Heritage and local flavors",
                "schedule": [
                    {
                        "activity_id": f"{prefix}-meal-1",
                        "start_time": "10:30",
                        "end_time": "11:15",
                        "meal": "breakfast",
                    },
                    {
                        "activity_id": f"{prefix}-meal-1",
                        "start_time": "12:00",
                        "end_time": "12:45",
                        "meal": "lunch",
                    },
                    {"activity_id": f"{prefix}-act-11", "start_time": "13:00", "end_time": "14:00"},
                    {
                        "activity_id": f"{prefix}-meal-1",
                        "start_time": "17:00",
                        "end_time": "17:45",
                        "meal": "dinner",
                    },
                ],
            }
        )
    return {
        "request": deepcopy(raw),
        "flight_id": f"{prefix}-flight-1",
        "hotel_id": f"{prefix}-hotel-1",
        "days": days,
    }


@pytest.fixture
def build_args(request_data):
    return make_build(request_data)


@pytest.fixture(autouse=True)
def fixed_application_date(monkeypatch):
    """Keep historical example-based tests deterministic as real time advances."""
    from datetime import date

    monkeypatch.setattr("schemas.current_date", lambda: date(2026, 11, 24))
