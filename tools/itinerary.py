"""Trusted arithmetic and schedule validation. LLM-supplied prices are never accepted."""

from decimal import Decimal

from schemas import (
    Activity,
    BudgetBreakdown,
    BuildArgs,
    FlightArgs,
    HotelArgs,
    Itinerary,
    ItineraryDay,
    ScheduledActivity,
    TripSummary,
    WeatherArgs,
)
from tools.common import ToolFailure, dates, load, success
from tools.flights import search_flights
from tools.hotels import search_hotels
from tools.weather import get_weather

TRANSPORT_PER_PERSON_DAY = Decimal("5")
PACE_LIMIT = {"relaxed": (2, 180), "moderate": (4, 360), "intensive": (6, 540)}


def minutes(value):
    if value.second or value.microsecond:
        raise ToolFailure("invalid_time", "Use minute precision for times.", ["Use HH:MM times."])
    return value.hour * 60 + value.minute


def invalid(message, suggestion="Revise the schedule and call build_itinerary again."):
    raise ToolFailure("invalid_itinerary", message, [suggestion])


def build_itinerary(args: BuildArgs):
    request = args.request
    flights = search_flights(
        FlightArgs(
            origin=request.origin,
            destination=request.destination,
            departure_date=request.start_date,
            return_date=request.end_date,
            travelers=request.travelers,
        )
    ).data
    hotels = search_hotels(
        HotelArgs(
            destination=request.destination,
            check_in=request.start_date,
            check_out=request.end_date,
            travelers=request.travelers,
        )
    ).data
    flight = next((f for f in flights if f.id == args.flight_id), None)
    hotel = next((h for h in hotels if h.id == args.hotel_id), None)
    if not flight or not hotel:
        invalid(
            "Unknown flight or hotel ID for this destination.",
            "Use IDs returned by searches for this trip.",
        )
    expected_dates = dates(request.start_date, request.end_date)
    if [d.date for d in args.days] != expected_dates:
        invalid("Days must cover every trip date exactly once, in order.")
    weather = get_weather(
        WeatherArgs(
            destination=request.destination,
            start_date=request.start_date,
            end_date=request.end_date,
        )
    ).data
    catalog = {x["id"]: Activity(**x) for x in load("activities", request.destination)}
    food = Decimal("0")
    activity_cost = Decimal("0")
    output_days = []
    max_count, max_minutes = PACE_LIMIT[request.pace]
    for selection, forecast in zip(args.days, weather):
        earliest = (
            minutes(flight.arrival_time) + 90 if selection.date == request.start_date else 8 * 60
        )
        latest = (
            minutes(flight.return_departure_time) - 120
            if selection.date == request.end_date
            else 22 * 60
        )
        resolved, meal_names, seen_attractions = [], set(), set()
        count = duration = 0
        day_cost = Decimal("0")
        previous_end = earliest - 15
        for slot in selection.schedule:
            item = catalog.get(slot.activity_id)
            if item is None:
                invalid(
                    f"Unknown activity ID {slot.activity_id}.",
                    "Use an activity ID from this destination.",
                )
            start, end = minutes(slot.start_time), minutes(slot.end_time)
            if start < earliest or end > latest:
                invalid(
                    f"{selection.date}: {item.name} falls outside {earliest // 60:02}:{earliest % 60:02}–{latest // 60:02}:{latest % 60:02} local time, including airport buffers."
                )
            if end - start < item.duration_minutes:
                invalid(f"{item.name} needs at least {item.duration_minutes} minutes.")
            if start < previous_end + 15:
                invalid("Schedule overlaps or lacks a 15-minute transfer buffer.")
            previous_end = end
            if item.category == "meal":
                if slot.meal is None or slot.meal in meal_names:
                    invalid(
                        "Each meal must have a unique breakfast/lunch/dinner label for its day."
                    )
                windows = {
                    "breakfast": (8 * 60, 11 * 60 + 30),
                    "lunch": (12 * 60, 15 * 60),
                    "dinner": (17 * 60, 21 * 60),
                }
                low, high = windows[slot.meal]
                if not low <= start <= high:
                    invalid(
                        f"{selection.date}: {slot.meal} at {slot.start_time:%H:%M} must start between {low // 60}:00 and {high // 60}:{high % 60:02}."
                    )
                if not set(request.dietary_preferences).issubset(item.dietary_compatibility):
                    invalid(f"{item.name} does not meet all dietary restrictions.")
                meal_names.add(slot.meal)
            else:
                if slot.meal is not None:
                    invalid("An attraction cannot be used as a meal.")
                if item.id in seen_attractions:
                    invalid("Do not repeat an attraction within the same day.")
                seen_attractions.add(item.id)
                if forecast.recommendation == "indoor" and item.environment == "outdoor":
                    invalid(f"Rain expected on {selection.date}; choose indoor alternatives.")
                count += 1
                duration += end - start
            cost = Decimal(str(item.price_per_person)) * request.travelers
            food += cost if item.category == "meal" else 0
            activity_cost += cost if item.category != "meal" else 0
            day_cost += cost
            resolved.append(
                ScheduledActivity(
                    activity=item,
                    start_time=slot.start_time,
                    end_time=slot.end_time,
                    meal=slot.meal,
                    total_cost=float(cost),
                )
            )
        required_meals = set()
        if earliest <= 11 * 60:
            required_meals.add("breakfast")
        if earliest <= 14 * 60 and latest >= 13 * 60:
            required_meals.add("lunch")
        if earliest <= 19 * 60 and latest >= 18 * 60:
            required_meals.add("dinner")
        if not required_meals.issubset(meal_names):
            invalid(
                f"{selection.date}: missing meals {sorted(required_meals - meal_names)}. Meals cannot be omitted to meet budget."
            )
        if count < 1 or count > max_count or duration > max_minutes:
            invalid(
                f"{request.pace} pace requires 1–{max_count} attractions and at most {max_minutes} attraction minutes per day."
            )
        transport = TRANSPORT_PER_PERSON_DAY * request.travelers
        output_days.append(
            ItineraryDay(
                date=selection.date,
                title=selection.title,
                weather=forecast,
                schedule=resolved,
                estimated_cost=float(day_cost + transport),
                local_transport=float(transport),
                recommendations=[
                    "Allow 15 minutes between visits; airport transfers have separate buffers.",
                    "Meal compatibility is simulated; confirm with the restaurant before real travel.",
                ],
            )
        )
    transport = TRANSPORT_PER_PERSON_DAY * len(args.days) * request.travelers
    total = (
        Decimal(str(flight.total_price))
        + Decimal(str(hotel.total_cost))
        + food
        + activity_cost
        + transport
    )
    remaining = Decimal(str(request.budget)) - total
    if remaining < 0:
        raise ToolFailure(
            "over_budget",
            f"Total EUR {total:.2f} exceeds budget by EUR {-remaining:.2f}.",
            [
                "Choose a hostel or cheaper flight.",
                "Replace paid attractions with free options.",
                "Keep all required meals.",
            ],
        )
    budget = BudgetBreakdown(
        flights=flight.total_price,
        accommodation=hotel.total_cost,
        food=float(food),
        activities=float(activity_cost),
        local_transport=float(transport),
        total=float(total),
        remaining_budget=float(remaining),
    )
    result = Itinerary(
        trip_summary=TripSummary(
            origin=request.origin,
            destination=request.destination,
            start_date=request.start_date,
            end_date=request.end_date,
            travelers=request.travelers,
        ),
        selected_flights=flight,
        selected_accommodation=hotel,
        daily_itinerary=output_days,
        budget_breakdown=budget,
        weather_summary=weather,
        recommendations=["Reserve tickets only after verifying real availability."],
        warnings=[
            "All prices, schedules, availability, restaurants and weather are simulated.",
            "EUR 5 per traveler per day covers simulated local transport and airport transfers; flights include no paid extras.",
            "Daily costs include meals, attractions and transport; flights and accommodation are charged once in the trip budget.",
        ],
    )
    return success(result)
