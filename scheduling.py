"""Shared local-time rules for the lower-bound check and itinerary validator."""

from datetime import date, time


def minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def site_window(
    day: date, start: date, end: date, arrival: time, departure: time
) -> tuple[int, int]:
    earliest = minutes(arrival) + 90 if day == start else 8 * 60
    latest = minutes(departure) - 120 if day == end else 22 * 60
    return earliest, latest


def required_meals(earliest: int, latest: int) -> set[str]:
    meals = set()
    if earliest <= 11 * 60:
        meals.add("breakfast")
    if earliest <= 14 * 60 and latest >= 13 * 60:
        meals.add("lunch")
    if earliest <= 19 * 60 and latest >= 18 * 60:
        meals.add("dinner")
    return meals
