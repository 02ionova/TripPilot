"""English Streamlit UI; business rules remain in the tools and agent."""

from dataclasses import replace
from datetime import date, timedelta

import streamlit as st
from pydantic import ValidationError

from agent import TravelAgent
from budgeting import maximum_budget
from city_suggestions import city_label, city_options
from config import Settings
from design import apply_styles
from information import render_information
from schemas import TravelRequest, current_date
from ui import render_budget_metrics, render_itinerary_days, render_live_plan

st.set_page_config(page_title="TripPilot AI", page_icon="✈️", layout="wide")
apply_styles()
settings = Settings()

st.session_state.setdefault("trip_budget", 600.0)
st.session_state.setdefault("previous_travelers", 1)


def adjust_budget_for_travelers() -> None:
    """Adjust the current editable budget by EUR 500 per added/removed traveler."""
    count = st.session_state["travelers"]
    difference = count - st.session_state["previous_travelers"]
    st.session_state["trip_budget"] = max(
        1.0, float(st.session_state["trip_budget"]) + difference * 500.0
    )
    st.session_state["previous_travelers"] = count


heading, mode_control = st.columns([4, 1], vertical_alignment="center")
with heading:
    st.markdown(
        '<div class="journey-kicker">Thoughtfully planned. Ready to explore.</div>',
        unsafe_allow_html=True,
    )
    st.title("TripPilot AI")
    st.caption("Your intelligent travel planning assistant")
with mode_control:
    live_enabled = st.toggle(
        "Live Mode",
        value=settings.data_mode == "live",
        key="live_mode",
        help="On: Live Mode searches real flights, hotels, places and weather through external providers. Off: Demo Mode uses simulated travel data. Both modes use AI to plan; neither makes bookings.",
    )
mode_label = "Live Mode" if live_enabled else "Demo Mode"
mode = "live" if mode_label == "Live Mode" else "demo"
settings = replace(settings, data_mode=mode)
if st.session_state.get("selected_data_mode", mode) != mode or (
    st.session_state.get("result") is not None
    and (st.session_state["result"].data_source == "live") != (mode == "live")
):
    st.session_state.pop("result", None)
    st.session_state.pop("trace", None)
st.session_state["selected_data_mode"] = mode
if mode == "demo":
    mode_control.caption("Demo · Simulated data")
quota_status = st.empty()
with st.container(border=True, key="travel_request_panel"):
    a, b, c = st.columns(3)
    cities = city_options()
    origin = a.selectbox(
        "Departure city",
        cities,
        index=cities.index("Prague"),
        format_func=city_label,
        accept_new_options=True,
        key="origin_city",
        placeholder="Search or enter a departure city",
        help="Type to filter city suggestions. Select a city or add your own. Enter selects a city; only the Generate Travel Plan button starts planning.",
    )
    destination = b.selectbox(
        "Destination",
        cities,
        index=cities.index("Rome"),
        format_func=city_label,
        accept_new_options=True,
        key="destination_city",
        placeholder="Search or enter a destination city",
        help="Type to filter city suggestions. If your city is not listed, enter City, Country as a new option.",
    )
    travelers = c.number_input(
        "Number of travelers",
        1,
        20,
        1,
        key="travelers",
        on_change=adjust_budget_for_travelers,
        help="Each added traveler increases the budget by EUR 500. Removing a traveler subtracts EUR 500. You can edit the total budget at any time.",
    )
    a, b, c = st.columns(3)
    today = current_date()
    default_start = max(today, date(2027, 4, 10))
    default_end = min(default_start + timedelta(days=3), date(2035, 12, 31))
    start = a.date_input("Start date", default_start, min_value=today, max_value=date(2035, 12, 31))
    end = b.date_input("End date", default_end, min_value=today, max_value=date(2035, 12, 31))
    budget = c.number_input(
        "Total budget in EUR",
        min_value=1.0,
        key="trip_budget",
        step=100.0,
        help="Target total for all travelers. If needed, the planner may suggest a clearly marked alternative up to 10% above this amount.",
    )
    a, b, c = st.columns(3)
    pace = a.selectbox("Travel pace", ["relaxed", "moderate", "intensive"], index=1)
    interests = b.multiselect(
        "Interests",
        [
            "Architecture",
            "Museums",
            "History",
            "Local food",
            "Nature",
            "Shopping",
            "Nightlife",
            "Photography",
            "Relaxation",
        ],
        default=["Architecture", "History", "Local food"],
    )
    dietary_selection = c.multiselect(
        "Dietary preferences",
        ["none", "vegetarian", "vegan", "gluten-free", "halal"],
        default=["none"],
        format_func=lambda value: {
            "none": "No restrictions",
            "vegetarian": "Vegetarian",
            "vegan": "Vegan",
            "gluten-free": "Gluten-free",
            "halal": "Halal",
        }[value],
    )
    diets = [value for value in dietary_selection if value != "none"]
    submitted = st.button("Generate Travel Plan", type="primary", width="stretch")

if submitted:
    try:
        request = TravelRequest(
            origin=city_label(origin) if mode == "live" else origin,
            destination=city_label(destination) if mode == "live" else destination,
            start_date=start,
            end_date=end,
            budget=budget,
            travelers=travelers,
            pace=pace,
            interests=interests,
            dietary_preferences=diets,
        )
    except ValidationError as exc:
        st.error(
            "Please correct your request: "
            + "; ".join(e["msg"] for e in exc.errors(include_input=False))
        )
    else:
        st.session_state.pop("result", None)
        st.session_state.pop("trace", None)
        with st.status("Checking your trip budget…", expanded=False) as activity:
            current_step = st.empty()

            def progress(event):
                labels = {
                    "search_flights": "Comparing round-trip flights…",
                    "get_weather": "Checking the weather…",
                    "search_hotels": "Comparing accommodation…",
                    "search_activities": "Finding places to explore…",
                    "search_restaurants": "Finding restaurants and cafes…",
                    "build_itinerary": "Checking the schedule and total cost…",
                }
                if event["kind"] == "provider_request":
                    count = event.get("counters", {}).get("serpapi_requests", 0)
                    quota_status.caption(
                        f"SerpApi searches used: {count} / {settings.max_serpapi_requests}"
                    )
                    return
                if event["kind"] == "budget_precheck":
                    text = "Minimum costs checked. Preparing your itinerary…"
                elif event["kind"] == "tool_started":
                    text = labels.get(event["tool"], "Planning your trip…")
                elif event["kind"] == "replanning":
                    text = "Adjusting the plan to your requirements…"
                elif event["kind"] == "api_retry":
                    text = "The planning service is temporarily busy. Retrying…"
                else:
                    return
                # Replace one message instead of appending a long technical log.
                activity.update(label=text)
                current_step.caption(text)

            agent = TravelAgent(settings=settings, on_event=progress)
            result = agent.run(request)
            st.session_state["result"] = result
            st.session_state["trace"] = agent.trace.data
            final_label = {
                "success": "Your travel plan is ready",
                "infeasible": "No complete plan found — review the suggestions below",
                "needs_clarification": "Please review your trip details",
            }.get(result.status, "Planning could not be completed")
            current_step.empty()
            activity.update(
                label=final_label,
                state="error" if result.status in {"error", "iteration_limit"} else "complete",
                expanded=False,
            )

if "result" in st.session_state:
    result = st.session_state["result"]
    if result.status == "success" and result.data_source == "live":
        render_live_plan(result)
    elif result.status == "success":
        st.caption("Your simulated travel plan is ready.")
        plan = result.itinerary
        summary = plan.trip_summary
        st.subheader(f"{summary.origin} → {summary.destination}")
        st.caption(
            f"{summary.start_date} – {summary.end_date} · {summary.travelers} traveler(s) · EUR"
        )
        budget_data = plan.budget_breakdown
        render_budget_metrics(plan)
        st.subheader("Your day-by-day itinerary")
        render_itinerary_days(plan)
        travel, weather, costs = st.tabs(["Flights & accommodation", "Weather", "Budget"])
        with travel:
            f, h = plan.selected_flights, plan.selected_accommodation
            st.markdown(f"**{f.airline}** · {f.id} · round trip €{f.total_price:.2f}")
            st.write(
                f"Outbound {f.departure_date}: {f.departure_time:%H:%M} → {f.arrival_time:%H:%M}; return {f.return_date}: {f.return_departure_time:%H:%M} → {f.return_arrival_time:%H:%M}. All times local."
            )
            st.markdown(
                f"**{h.name}** · {h.accommodation_type} · {h.neighborhood} · rating {h.rating}/10"
            )
            st.write(
                f"{h.nights} nights × {h.rooms} rooms/beds × €{h.price_per_night:.2f} = €{h.total_cost:.2f}"
            )
        with weather:
            st.dataframe(
                [w.model_dump(mode="json") for w in plan.weather_summary],
                hide_index=True,
                width="stretch",
            )
        with costs:
            components = {
                k: v
                for k, v in budget_data.model_dump().items()
                if k not in ["total", "remaining_budget"]
            }
            st.bar_chart(components)
            st.table(budget_data.model_dump())
    elif result.status == "infeasible":
        st.write(result.message)
        estimate = result.budget_estimate
        if estimate and estimate.shortfall > 0:
            a, b, c = st.columns(3)
            a.metric("Your total budget", f"€{estimate.available_budget:.2f}")
            b.metric("Minimum required", f"€{estimate.minimum_total:.2f}")
            c.metric("Budget shortfall", f"€{estimate.shortfall:.2f}")
            st.caption(
                "Minimum costs for all travelers using the cheapest compatible simulated options. No bookings have been made."
            )
            st.table(
                {
                    "Category": [
                        "Round-trip flights",
                        "Accommodation",
                        "Meals",
                        "Attractions",
                        "Local transport",
                    ],
                    "Minimum cost (EUR)": [
                        estimate.flights,
                        estimate.accommodation,
                        estimate.food,
                        estimate.activities,
                        estimate.local_transport,
                    ],
                }
            )
            st.caption(
                f"Flexible maximum: EUR {maximum_budget(estimate.available_budget):.2f} (+10%)."
            )
    elif result.status == "needs_clarification":
        st.write(result.message)
    else:
        st.error(result.message)
    if result.data_source == "live" and result.status != "success":
        st.caption(
            f"SerpApi searches used: {result.serpapi_requests} · Provider cache hits: {result.provider_cache_hits}"
        )

render_information(mode, st.session_state.get("result"))
