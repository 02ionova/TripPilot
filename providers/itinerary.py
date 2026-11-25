"""Build a live itinerary exclusively from offers held in this agent run's store."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from budgeting import budget_notice, maximum_budget
from providers.schedule import open_for_slot, transfer
from scheduling import required_meals
from schemas import (
    BudgetBreakdown,
    BuildArgs,
    CostItem,
    Itinerary,
    ItineraryDay,
    ScheduledActivity,
    TripSummary,
)
from tools.common import ToolFailure, dates
from tools.itinerary import PACE_LIMIT


def reject(code: str, message: str, *suggestions: str):
    raise ToolFailure(
        code,
        message,
        list(suggestions) or ["Correct the affected date/slot and call build_itinerary again."],
    )


def build_live_itinerary(runtime, args: BuildArgs) -> Itinerary:
    request = runtime.request
    if args.request != request:
        reject("request_mismatch", "The builder request must match the original user request.")
    flight_entry = runtime.flights.get(args.flight_id)
    if not flight_entry:
        reject("unknown_flight", "Select a complete round trip from search_flights in this run.")
    flight, flight_args = flight_entry
    if (
        flight_args.origin,
        flight_args.destination,
        flight_args.departure_date,
        flight_args.return_date,
        flight_args.travelers,
    ) != (
        request.origin,
        request.destination,
        request.start_date,
        request.end_date,
        request.travelers,
    ):
        reject(
            "flight_request_mismatch",
            "The flight quote does not match the original cities, dates and travelers.",
        )
    arrival = flight.outbound_arrival
    departure = flight.return_departure
    if not arrival or not departure or departure <= arrival:
        reject(
            "invalid_flight_window",
            "The flight does not provide a usable on-site date/time window.",
        )
    hotel = None
    nights = (departure.date() - arrival.date()).days
    if nights > 0:
        entry = runtime.hotels.get(args.hotel_id)
        if not entry:
            reject("unknown_hotel", "Select a hotel returned by search_hotels in this run.")
        hotel, hotel_args = entry
        if (
            hotel_args.destination,
            hotel_args.travelers,
            hotel_args.check_in,
            hotel_args.check_out,
        ) != (request.destination, request.travelers, arrival.date(), departure.date()):
            reject(
                "hotel_dates_mismatch",
                f"Accommodation must cover {arrival.date()}–{departure.date()} for {request.travelers} travelers.",
                "Search accommodation using the destination arrival and return-departure dates, which may differ from the outbound departure date.",
            )
    elif args.hotel_id:
        reject(
            "unneeded_accommodation",
            "This trip has no destination overnight stay; hotel_id must be null.",
        )
    expected = dates(request.start_date, request.end_date)
    if [d.date for d in args.days] != expected:
        reject("missing_days", "Supply all trip dates once, in order, including travel-only days.")
    weather = []
    for day in expected:
        observation = runtime.weather.get((request.destination, day))
        if not observation:
            reject(
                "missing_weather",
                f"No forecast/climate data has been retrieved for {day}.",
                "Use get_weather for the complete user date range.",
            )
        weather.append(observation)
    costs = []

    def charge(category, label, amount, kind, source=None, notes=None):
        costs.append(
            CostItem(
                category=category,
                label=label,
                amount=float(amount),
                kind=kind,
                source=source,
                notes=notes or [],
            )
        )

    charge(
        "flights",
        flight.airline,
        flight.total_price,
        flight.price_info.kind,
        flight.source,
        flight.notes + flight.price_info.notes,
    )
    if hotel:
        charge(
            "accommodation",
            hotel.name,
            hotel.total_cost,
            hotel.price_info.kind,
            hotel.source,
            hotel.notes,
        )
    output = []
    warnings = [
        "Prices and availability may change. No bookings have been made.",
        "Estimated costs are planning allowances, not confirmed quotes. Confirm admission, opening hours, transport and dietary suitability before travel.",
    ]
    if hotel:
        warnings.extend(hotel.notes)
    count_limit, minute_limit = PACE_LIMIT[request.pace]
    for selection, forecast in zip(args.days, weather):
        earliest = max(datetime.combine(selection.date, time(8)), arrival + timedelta(minutes=90))
        latest = min(datetime.combine(selection.date, time(22)), departure - timedelta(minutes=120))
        on_site = (
            earliest < latest
            and earliest.date() == selection.date
            and latest.date() == selection.date
        )
        required = (
            required_meals(earliest.hour * 60 + earliest.minute, latest.hour * 60 + latest.minute)
            if on_site
            else set()
        )
        meals = set()
        seen = set()
        count = duration = 0
        slots = []
        previous_end = None
        previous_coords = hotel.coordinates if hotel else None
        day_cost = Decimal(0)
        advice = []
        if not on_site and selection.schedule:
            reject(
                "outside_flight_window",
                f"{selection.date} is a travel-only day; do not schedule destination visits.",
            )
        for slot in selection.schedule:
            entry = runtime.activities.get(slot.activity_id)
            if not entry or entry[1] != request.destination:
                reject(
                    "unknown_activity",
                    f"Unknown place ID {slot.activity_id}; use retrieved places for this destination.",
                )
            place = entry[0]
            start = datetime.combine(selection.date, slot.start_time)
            end = datetime.combine(selection.date, slot.end_time)
            if slot.start_time.second or slot.end_time.second or end <= start:
                reject("invalid_times", f"{selection.date}: use increasing HH:MM times.")
            if start < earliest or end > latest:
                reject(
                    "outside_flight_window",
                    f"{selection.date}: {place.name} must fit {earliest:%Y-%m-%d %H:%M}–{latest:%Y-%m-%d %H:%M}, including arrival/departure buffers.",
                )
            if (end - start).total_seconds() < place.duration_minutes * 60:
                reject(
                    "short_visit",
                    f"{selection.date}: allow at least {place.duration_minutes} estimated minutes for {place.name}.",
                )
            gap, note = transfer(previous_coords, place.coordinates)
            if previous_end and start < previous_end + timedelta(minutes=gap):
                reject(
                    "transfer_or_overlap",
                    f"{selection.date}: allow {gap} minutes before {place.name}. {note}",
                    "Cluster nearby places or increase the gap. Transfers are estimated, not routed directions.",
                )
            availability = open_for_slot(
                place,
                selection.date,
                slot.start_time.hour * 60 + slot.start_time.minute,
                slot.end_time.hour * 60 + slot.end_time.minute,
            )
            if availability is False:
                reject(
                    "place_closed",
                    f"{place.name} is closed during the proposed {selection.date} {slot.start_time:%H:%M}–{slot.end_time:%H:%M} visit.",
                    "Choose a supported opening interval or another retrieved venue.",
                )
            if availability is None:
                advice.append(
                    f"{place.name}: opening hours unavailable or unparseable; confirm the proposed visit time."
                )
            if place.category == "meal":
                if slot.meal is None or slot.meal in meals:
                    reject(
                        "meal_labels",
                        f"{selection.date}: assign breakfast, lunch and dinner once each.",
                    )
                windows = {
                    "breakfast": (8 * 60, 11 * 60 + 30),
                    "lunch": (12 * 60, 15 * 60),
                    "dinner": (17 * 60, 21 * 60),
                }
                low, high = windows[slot.meal]
                minute = slot.start_time.hour * 60 + slot.start_time.minute
                if not low <= minute <= high:
                    reject(
                        "meal_time",
                        f"{selection.date}: {slot.meal} starts outside {low // 60}:00–{high // 60}:{high % 60:02}.",
                    )
                meals.add(slot.meal)
                if request.dietary_preferences:
                    missing = set(request.dietary_preferences) - set(place.dietary_compatibility)
                    advice.append(
                        f"{place.name}: "
                        + (
                            "the provider has no explicit indication for "
                            + ", ".join(sorted(missing))
                            + ". "
                            if missing
                            else "Provider dietary indications are available, but are not certification. "
                        )
                        + "Confirm suitability with the venue before ordering."
                    )
            else:
                if slot.meal is not None or place.id in seen:
                    reject(
                        "invalid_activity",
                        f"{selection.date}: an attraction cannot be a meal or repeat within the same day.",
                    )
                seen.add(place.id)
                count += 1
                duration += int((end - start).total_seconds() / 60)
                if forecast.recommendation == "indoor" and place.environment == "outdoor":
                    reject(
                        "weather_conflict",
                        f"{selection.date}: choose indoor alternatives to {place.name} because rain is expected or the historical sample is wet.",
                    )
                if place.environment == "unknown":
                    advice.append(
                        f"{place.name}: indoor/outdoor classification is unknown; verify weather protection."
                    )
            amount = Decimal(str(place.price_per_person)) * request.travelers
            charge(
                "food" if place.category == "meal" else "activities",
                f"{selection.date}: {place.name}",
                amount,
                place.price_info.kind,
                place.source,
                place.price_info.notes,
            )
            day_cost += amount
            slots.append(
                ScheduledActivity(
                    activity=place,
                    start_time=slot.start_time,
                    end_time=slot.end_time,
                    meal=slot.meal,
                    total_cost=float(amount),
                    transfer_minutes=gap,
                    transfer_note=note,
                )
            )
            previous_end = end
            previous_coords = place.coordinates
        if not required.issubset(meals):
            reject(
                "missing_meals",
                f"{selection.date}: missing {sorted(required - meals)}. Keep all required meals when reducing costs.",
            )
        if on_site and (latest - earliest).total_seconds() >= 2 * 3600 and count < 1:
            reject(
                "empty_day",
                f"{selection.date}: include at least one attraction in the available on-site window.",
            )
        if count > count_limit or duration > minute_limit:
            reject(
                "pace_limit",
                f"{selection.date}: {request.pace} permits at most {count_limit} attractions/{minute_limit} attraction minutes; received {count}/{duration}.",
            )
        transport = Decimal(str(runtime.settings.estimated_transport_per_day)) * request.travelers
        if selection.date == arrival.date():
            transport += (
                Decimal(str(runtime.settings.estimated_airport_transfer_per_leg))
                * request.travelers
            )
        if selection.date == departure.date():
            transport += (
                Decimal(str(runtime.settings.estimated_airport_transfer_per_leg))
                * request.travelers
            )
        charge(
            "local_transport",
            f"{selection.date}: local and airport transport",
            transport,
            "estimated",
            notes=[
                "EUR 8/person/day local transport plus EUR 12/person per airport transfer; not a retrieved fare."
            ],
        )
        if not meals:
            allowance = Decimal(str(runtime.settings.estimated_meal_eur)) * request.travelers
            charge(
                "food",
                f"{selection.date}: travel-day meal allowance",
                allowance,
                "estimated",
                notes=["Airport/in-transit meal allowance; no restaurant is invented."],
            )
            day_cost += allowance
            advice.append(
                "A travel-day meal allowance is included because no on-site meal is scheduled; arrange food at the airport or in transit."
            )
        output.append(
            ItineraryDay(
                date=selection.date,
                title=selection.title,
                weather=forecast,
                schedule=slots,
                estimated_cost=float(day_cost + transport),
                local_transport=float(transport),
                recommendations=list(dict.fromkeys(advice)),
            )
        )
    totals = {
        key: sum((Decimal(str(c.amount)) for c in costs if c.category == key), Decimal(0))
        for key in ("flights", "accommodation", "food", "activities", "local_transport")
    }
    total = sum(totals.values(), Decimal(0))
    remaining = Decimal(str(request.budget)) - total
    if total > maximum_budget(request.budget):
        breakdown = ", ".join(f"{key} EUR {amount:.2f}" for key, amount in totals.items())
        reject(
            "over_budget",
            f"Total estimated cost EUR {total:.2f} exceeds the maximum including 10% flexibility (EUR {maximum_budget(request.budget):.2f}). Components: {breakdown}.",
            "Select cheaper retrieved flights/accommodation, lower-cost restaurant estimates or attractions with confirmed free admission. Do not omit meals or claim missing admission prices are zero.",
        )
    notice = budget_notice(request.budget, total)
    if notice:
        warnings.insert(0, notice)
    budget = BudgetBreakdown(
        **{k: float(v) for k, v in totals.items()},
        total=float(total),
        remaining_budget=float(remaining),
    )
    return Itinerary(
        trip_summary=TripSummary(
            origin=request.origin,
            destination=request.destination,
            start_date=request.start_date,
            end_date=request.end_date,
            travelers=request.travelers,
        ),
        selected_flights=flight,
        selected_accommodation=hotel,
        daily_itinerary=output,
        budget_breakdown=budget,
        weather_summary=weather,
        recommendations=[
            "Follow source links to verify the selected quotes and book directly with the provider.",
            "Group nearby venues; transfer durations are geographic estimates, not verified route schedules.",
        ],
        warnings=list(dict.fromkeys(warnings)),
        data_source="live",
        cost_items=costs,
    )
