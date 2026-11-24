"""Conservative catalogue cost lower bound, before any paid LLM request.

This rejects only mathematically unaffordable trips. Passing the check does not
prove that a valid schedule exists and never bypasses the LLM or final builder.
"""

from datetime import time
from decimal import Decimal
from math import ceil

from scheduling import required_meals, site_window
from schemas import BudgetEstimate, TravelRequest
from tools.common import ToolFailure, dates, load
from tools.itinerary import TRANSPORT_PER_PERSON_DAY


def estimate_minimum_budget(request: TravelRequest) -> BudgetEstimate:
    flights = load("flights", request.destination)
    hotels = load("hotels", request.destination)
    activities = load("activities", request.destination)
    profiles = load("weather", request.destination)
    meals = [
        a
        for a in activities
        if a["category"] == "meal"
        and set(request.dietary_preferences).issubset(a["dietary_compatibility"])
    ]
    if not meals:
        raise ToolFailure(
            "no_compatible_meals",
            "No simulated meals support all dietary restrictions.",
            ["Change the destination or contact the planner about additional meal data."],
        )
    trip_dates = dates(request.start_date, request.end_date)
    nights = (request.end_date - request.start_date).days
    lodging = min(
        Decimal(str(h["price_per_night"])) * ceil(request.travelers / h["capacity"]) * nights
        for h in hotels
    )
    cheapest_meal = min(Decimal(str(a["price_per_person"])) for a in meals)
    attraction_cost = Decimal(0)
    for day in trip_dates:
        season = (
            "winter"
            if day.month in [12, 1, 2]
            else "spring"
            if day.month <= 5
            else "summer"
            if day.month <= 8
            else "autumn"
        )
        rainy = profiles[season]["rain_probability"] >= 0.5
        eligible = [
            a
            for a in activities
            if a["category"] == "attraction" and (not rainy or a["environment"] == "indoor")
        ]
        if not eligible:
            raise ToolFailure(
                "no_weather_alternative",
                "No weather-compatible attractions are available.",
                ["Choose other dates or a different destination."],
            )
        # Ignore interests/durations here deliberately: a lower bound must never overstate cost.
        attraction_cost += (
            min(Decimal(str(a["price_per_person"])) for a in eligible) * request.travelers
        )
    candidates = []
    for flight in flights:
        meal_count = sum(
            len(
                required_meals(
                    *site_window(
                        day,
                        request.start_date,
                        request.end_date,
                        time.fromisoformat(flight["arrival_time"]),
                        time.fromisoformat(flight["return_departure_time"]),
                    )
                )
            )
            for day in trip_dates
        )
        flight_cost = Decimal(str(flight["price_per_traveler"])) * request.travelers
        food = cheapest_meal * meal_count * request.travelers
        candidates.append((flight_cost + food, flight_cost, food))
    _, flight_cost, food = min(candidates)
    transport = TRANSPORT_PER_PERSON_DAY * len(trip_dates) * request.travelers
    total = flight_cost + lodging + food + attraction_cost + transport
    return BudgetEstimate(
        flights=float(flight_cost),
        accommodation=float(lodging),
        food=float(food),
        activities=float(attraction_cost),
        local_transport=float(transport),
        minimum_total=float(total),
        available_budget=request.budget,
        shortfall=float(max(Decimal(0), total - Decimal(str(request.budget)))),
    )
