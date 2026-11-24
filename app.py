"""English Streamlit UI; business rules remain in the tools and agent."""

import json
from datetime import date

import streamlit as st
from pydantic import ValidationError

from agent import TravelAgent
from schemas import TravelRequest

st.set_page_config(page_title="TripPilot AI", page_icon="✈️", layout="wide")
st.title("TripPilot AI")
st.subheader("Your intelligent travel planning assistant")
st.info(
    "Educational simulation: all travel prices, schedules, availability and weather are simulated. This application does not make bookings."
)
with st.form("travel_request"):
    a, b, c = st.columns(3)
    origin = a.text_input("Departure city", "Prague")
    destination = b.selectbox("Destination", ["Rome", "Paris", "Barcelona", "Vienna", "Amsterdam"])
    travelers = c.number_input("Number of travelers", 1, 20, 1)
    a, b, c = st.columns(3)
    start = a.date_input("Start date", date(2027, 4, 10))
    end = b.date_input("End date", date(2027, 4, 13))
    budget = c.number_input("Total budget in EUR", min_value=1.0, value=600.0, step=25.0)
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
    diets = c.multiselect("Dietary preferences", ["vegetarian", "vegan", "gluten-free"])
    submitted = st.form_submit_button(
        "Generate Travel Plan", type="primary", use_container_width=True
    )

if submitted:
    try:
        request = TravelRequest(
            origin=origin,
            destination=destination,
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
        with st.status("Agent activity", expanded=True) as activity:

            def progress(event):
                if event["kind"] == "tool_call":
                    labels = {
                        "search_flights": "Searching for flights",
                        "get_weather": "Checking weather",
                        "search_hotels": "Searching accommodation",
                        "search_activities": "Finding activities",
                        "build_itinerary": "Validating the itinerary and budget",
                    }
                    st.write(
                        f"{labels.get(event['tool'], event['tool'])} — {event['result']['status']}"
                    )
                elif event["kind"] == "replanning":
                    st.write("Handling tool feedback and revising the plan.")
                elif event["kind"] == "api_retry":
                    st.write("Retrying a temporary API failure.")

            agent = TravelAgent(on_event=progress)
            result = agent.run(request)
            st.session_state["result"] = result
            st.session_state["trace"] = agent.trace.data
            activity.update(
                label=f"Agent finished: {result.status}",
                state="complete" if result.status == "success" else "error",
                expanded=False,
            )

if "result" in st.session_state:
    result = st.session_state["result"]
    trace = st.session_state["trace"]
    if result.status == "success":
        st.success(result.message)
        plan = result.itinerary
        summary = plan.trip_summary
        st.subheader(f"{summary.origin} → {summary.destination}")
        st.caption(
            f"{summary.start_date} – {summary.end_date} · {summary.travelers} traveler(s) · EUR"
        )
        budget_data = plan.budget_breakdown
        a, b, c = st.columns(3)
        a.metric("Total budget", f"€{budget_data.total + budget_data.remaining_budget:.2f}")
        b.metric("Estimated total cost", f"€{budget_data.total:.2f}")
        c.metric("Remaining budget", f"€{budget_data.remaining_budget:.2f}")
        days, travel, weather, costs = st.tabs(
            ["Day-by-day itinerary", "Flights & accommodation", "Weather", "Budget"]
        )
        with days:
            for day in plan.daily_itinerary:
                with st.expander(
                    f"{day.date} · {day.title} · €{day.estimated_cost:.2f}", expanded=True
                ):
                    st.caption(
                        f"{day.weather.conditions} · {day.weather.min_temperature}–{day.weather.max_temperature} °C · local transport €{day.local_transport:.2f}"
                    )
                    for slot in day.schedule:
                        st.write(
                            f"**{slot.start_time:%H:%M}–{slot.end_time:%H:%M} · {slot.meal.title() if slot.meal else 'Visit'}: {slot.activity.name}** — €{slot.total_cost:.2f}"
                        )
                        st.caption(slot.activity.description)
                    for text in day.recommendations:
                        st.caption(text)
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
                use_container_width=True,
            )
        with costs:
            components = {
                k: v
                for k, v in budget_data.model_dump().items()
                if k not in ["total", "remaining_budget"]
            }
            st.bar_chart(components)
            st.table(budget_data.model_dump())
        for text in plan.recommendations:
            st.write(text)
        for text in plan.warnings:
            st.warning(text)
    else:
        st.error(f"{result.status}: {result.message}")
    a, b = st.columns(2)
    a.download_button(
        "Download itinerary JSON",
        result.model_dump_json(indent=2),
        "itinerary.json",
        "application/json",
    )
    b.download_button(
        "Download execution trace JSON",
        json.dumps(trace, indent=2),
        "trace.json",
        "application/json",
    )
    with st.expander("Execution trace — observable actions and tool results"):
        st.json(trace)
