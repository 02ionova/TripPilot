"""Bounded constraint search for times, using only LLM-selected/retrieved venues.

This is a tool implementation, not an agent orchestration loop: the LLM still
chooses tools, flight/hotel/attraction IDs, dates/themes, searches and alternatives.
"""

from datetime import datetime, time, timedelta

from providers.schedule import open_for_slot, transfer
from scheduling import required_meals
from schemas import DaySelection, ScheduledSelection
from tools.common import ToolFailure

MEAL_WINDOWS = {
    "breakfast": (8 * 60, 11 * 60 + 30),
    "lunch": (12 * 60, 15 * 60),
    "dinner": (17 * 60, 21 * 60),
}


def arrange(runtime, args):
    entry = runtime.flights.get(args.flight_id)
    if not entry:
        return args  # The authoritative validator supplies the ID error.
    flight = entry[0]
    if not flight.outbound_arrival or not flight.return_departure:
        return args
    arrival = flight.outbound_arrival
    departure = flight.return_departure
    hotel = runtime.hotels.get(args.hotel_id)
    hotel_coordinates = hotel[0].coordinates if hotel else None
    restaurants = [
        p
        for p, destination in runtime.activities.values()
        if destination == runtime.request.destination and p.category == "meal"
    ]
    if not restaurants:
        raise ToolFailure(
            "missing_restaurants",
            "Retrieve restaurant/cafe options before arranging a schedule.",
            ["Call search_restaurants; no venues or menu prices will be invented."],
        )
    result = []
    for day in args.days:
        earliest = max(datetime.combine(day.date, time(8)), arrival + timedelta(minutes=90))
        latest = min(datetime.combine(day.date, time(22)), departure - timedelta(minutes=120))
        on_site = earliest < latest and earliest.date() == day.date and latest.date() == day.date
        if not on_site:
            result.append(DaySelection(date=day.date, title=day.title, schedule=[]))
            continue
        lower = earliest.hour * 60 + earliest.minute
        upper = latest.hour * 60 + latest.minute
        selected = []
        for slot in day.schedule:
            stored = runtime.activities.get(slot.activity_id)
            if not stored or stored[1] != runtime.request.destination:
                raise ToolFailure(
                    "unknown_activity",
                    f"Unknown retrieved venue ID {slot.activity_id}.",
                    ["Use IDs from successful searches for the original destination."],
                )
            if stored[0].category == "attraction" and stored[0].id not in [p.id for p in selected]:
                selected.append(stored[0])
        mandatory = [
            m for m in ("breakfast", "lunch", "dinner") if m in required_meals(lower, upper)
        ]
        # Travel-only/short arrival windows do not fabricate visits or venues.
        if upper - lower < 120 and not mandatory:
            result.append(DaySelection(date=day.date, title=day.title, schedule=[]))
            continue
        if not selected and upper - lower >= 120:
            raise ToolFailure(
                "missing_attraction_selection",
                f"{day.date}: choose at least one retrieved attraction for this on-site day.",
                ["Add an attraction ID; automatic timing does not invent a sightseeing plan."],
            )
        nodes = 0

        def solve(remaining, meals, cursor, previous, slots):
            nonlocal nodes
            nodes += 1
            if nodes > 6000:
                return None
            if not remaining and not meals:
                return slots
            tasks = []
            if meals:
                label = meals[0]
                ordered = sorted(
                    restaurants,
                    key=lambda p: (
                        len(
                            set(runtime.request.dietary_preferences) - set(p.dietary_compatibility)
                        ),
                        p.price_per_person,
                        transfer(previous, p.coordinates)[0],
                    ),
                )
                tasks.extend((p, label) for p in ordered)
            attractions = sorted(remaining, key=lambda p: transfer(previous, p.coordinates)[0])
            attraction_tasks = [(p, None) for p in attractions]
            # Use time before the next meal rather than waiting several hours.
            if (
                meals
                and attractions
                and cursor + attractions[0].duration_minutes + 30 <= MEAL_WINDOWS[meals[0]][0]
            ):
                tasks = attraction_tasks + tasks
            else:
                tasks += attraction_tasks
            for place, meal in tasks:
                gap, _ = transfer(previous, place.coordinates)
                start = max(lower, cursor + gap)
                if meal:
                    start = max(start, MEAL_WINDOWS[meal][0])
                    deadline = min(upper - place.duration_minutes, MEAL_WINDOWS[meal][1])
                else:
                    deadline = upper - place.duration_minutes
                start = ((start + 4) // 5) * 5
                while start <= deadline:
                    end = start + place.duration_minutes
                    if open_for_slot(place, day.date, start, end) is not False:
                        break
                    start += 5
                if start > deadline:
                    continue
                slot = ScheduledSelection(
                    activity_id=place.id,
                    start_time=time(start // 60, start % 60),
                    end_time=time(end // 60, end % 60),
                    meal=meal,
                )
                found = solve(
                    [p for p in remaining if p.id != place.id] if meal is None else remaining,
                    meals[1:] if meal else meals,
                    end,
                    place.coordinates,
                    slots + [slot],
                )
                if found is not None:
                    return found
            return None

        scheduled = solve(selected, mandatory, lower, hotel_coordinates, [])
        if scheduled is None:
            raise ToolFailure(
                "no_feasible_schedule",
                f"{day.date}: retrieved venue hours, transfers and selected visits do not fit the available {lower // 60:02}:{lower % 60:02}–{upper // 60:02}:{upper % 60:02} window.",
                [
                    "Retrieve breakfast cafes if no restaurant opens before 11:30.",
                    "Select fewer/nearer attractions or another flight; the builder will not use a confirmed closed venue.",
                ],
            )
        result.append(DaySelection(date=day.date, title=day.title, schedule=scheduled))
    return args.model_copy(update={"days": result, "auto_schedule": False})
