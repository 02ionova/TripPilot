"""Presentation of live provider records, quotes, estimates and provenance."""

import streamlit as st


def price_label(info) -> str:
    return "Retrieved price" if info and info.kind == "retrieved" else "Estimated cost"


def render_live_plan(result):
    plan = result.itinerary
    summary = plan.trip_summary
    st.success(result.message)
    st.subheader(f"{summary.origin} → {summary.destination}")
    st.caption(
        f"{summary.start_date} – {summary.end_date} · {summary.travelers} traveler(s) · EUR · Live Mode"
    )
    b = plan.budget_breakdown
    left, middle, right = st.columns(3)
    left.metric("Total budget", f"€{b.total + b.remaining_budget:.2f}")
    middle.metric("Total estimated cost", f"€{b.total:.2f}")
    right.metric("Remaining budget", f"€{b.remaining_budget:.2f}")
    st.caption(
        f"SerpApi searches used: {result.serpapi_requests} · Provider cache hits: {result.provider_cache_hits} · Result assembled: {result.retrieved_at:%Y-%m-%d %H:%M UTC}"
        if result.retrieved_at
        else f"SerpApi searches used: {result.serpapi_requests}"
    )
    days, travel, weather, budget, sources = st.tabs(
        ["Day-by-day itinerary", "Flights & stay", "Weather", "Budget", "Sources & assumptions"]
    )
    with days:
        for day in plan.daily_itinerary:
            with st.expander(
                f"{day.date} · {day.title} · €{day.estimated_cost:.2f}", expanded=True
            ):
                w = day.weather
                rain = (
                    f" · rain probability {w.rain_probability:.0%}"
                    if w.rain_probability is not None
                    else ""
                )
                st.caption(
                    f"{w.information_type} · {w.conditions} · {w.min_temperature:.1f}–{w.max_temperature:.1f} °C{rain}"
                )
                if not day.schedule:
                    st.write("Travel day — no destination visits scheduled.")
                for slot in day.schedule:
                    place = slot.activity
                    st.markdown(
                        f"**{slot.start_time:%H:%M}–{slot.end_time:%H:%M} · {slot.meal.title() if slot.meal else 'Visit'} · {place.name}**"
                    )
                    st.caption(
                        f"{price_label(place.price_info)}: €{slot.total_cost:.2f} for all travelers · "
                        + (f"Rating {place.rating}/5 · " if place.rating is not None else "")
                        + (
                            f"{place.reviews} reviews"
                            if place.reviews is not None
                            else "Review count unavailable"
                        )
                    )
                    if place.address:
                        st.write(place.address)
                    if place.url:
                        st.link_button("View on Google Maps", place.url)
                    if place.website:
                        st.link_button("Venue website", place.website)
                    if slot.transfer_note:
                        st.caption(slot.transfer_note)
                    if place.price_info:
                        for text in place.price_info.notes:
                            st.caption(text)
                    if slot.meal and place.dietary_status == "unverified":
                        st.caption(
                            "Dietary suitability is unverified. Confirm directly with the venue."
                        )
                for text in day.recommendations:
                    st.caption(text)
        points = [
            {"lat": s.activity.coordinates.latitude, "lon": s.activity.coordinates.longitude}
            for d in plan.daily_itinerary
            for s in d.schedule
            if s.activity.coordinates
        ]
        if points:
            st.map(points)
    with travel:
        flight = plan.selected_flights
        st.markdown(f"**{flight.airline}**")
        st.write(
            f"{price_label(flight.price_info)}: €{flight.total_price:.2f} total round trip for {summary.travelers} traveler(s)."
        )
        for title, legs in [
            ("Outbound", flight.outbound_segments),
            ("Return", flight.return_segments),
        ]:
            st.markdown(f"**{title} · {max(0, len(legs) - 1)} stop(s)**")
            st.dataframe(
                [
                    {
                        "Airline": leg.airline,
                        "Flight": leg.flight_number,
                        "From": leg.departure_airport,
                        "Departure (airport local time)": str(leg.departure),
                        "To": leg.arrival_airport,
                        "Arrival (airport local time)": str(leg.arrival),
                        "Duration (minutes)": leg.duration_minutes,
                    }
                    for leg in legs
                ],
                hide_index=True,
                width="stretch",
            )
        if flight.search_url:
            st.link_button("View flight search", flight.search_url)
        if flight.source:
            st.caption(
                f"{flight.source.provider} · retrieved {flight.source.retrieved_at:%Y-%m-%d %H:%M UTC}"
            )
        hotel = plan.selected_accommodation
        if hotel:
            st.markdown(f"**{hotel.name}**")
            if hotel.image_url:
                st.image(hotel.image_url, width=500)
            st.write(hotel.address or hotel.neighborhood)
            st.write(
                f"{price_label(hotel.price_info)}: €{hotel.total_cost:.2f} for {hotel.nights} nights / {hotel.rooms} room(s). Retrieved or derived nightly unit rate: €{hotel.price_per_night:.2f}."
            )
            st.caption(
                (f"Rating {hotel.rating}/5" if hotel.rating is not None else "Rating unavailable")
                + (f" · {hotel.reviews} reviews" if hotel.reviews is not None else "")
            )
            for text in hotel.notes:
                st.caption(text)
            if hotel.url:
                st.link_button("View accommodation", hotel.url)
        else:
            st.info("No overnight accommodation is needed for this trip.")
    with weather:
        st.dataframe(
            [
                {
                    "Date": str(w.date),
                    "Information": w.information_type,
                    "Min °C": w.min_temperature,
                    "Max °C": w.max_temperature,
                    "Rain probability": w.rain_probability,
                    "Historical wet-day frequency": w.historical_wet_day_frequency,
                    "Wind km/h": w.wind_speed_kmh,
                    "Conditions": w.conditions,
                    "Historical years": ", ".join(map(str, w.historical_years)),
                }
                for w in plan.weather_summary
            ],
            hide_index=True,
            width="stretch",
        )
        if any(w.information_type == "Historical climate estimate" for w in plan.weather_summary):
            st.info(
                "Historical climate estimates summarize comparable dates in previous seasons. They are not a forecast for your trip."
            )
        st.caption(
            "Weather: Open-Meteo · Geocoding: GeoNames via Open-Meteo · Attribution: CC BY 4.0"
        )
        st.link_button("Open-Meteo data and attribution", "https://open-meteo.com/")
    with budget:
        names = {
            "flights": "Flights",
            "accommodation": "Accommodation",
            "food": "Food",
            "activities": "Activities",
            "local_transport": "Local transportation",
        }
        st.bar_chart({names[k]: getattr(b, k) for k in names})
        st.table(
            {
                "Category": [names[k] for k in names]
                + ["Total estimated cost", "Remaining budget"],
                "EUR": [getattr(b, k) for k in names] + [b.total, b.remaining_budget],
            }
        )
        st.subheader("Retrieved prices and estimated costs")
        st.dataframe(
            [
                {
                    "Category": names[c.category],
                    "Item": c.label,
                    "EUR (all travelers)": c.amount,
                    "Cost type": "Retrieved price" if c.kind == "retrieved" else "Estimated cost",
                }
                for c in plan.cost_items
            ],
            hide_index=True,
            width="stretch",
        )
        st.caption(
            "No estimates are represented as confirmed quotes. Taxes, room availability, admission and meal prices may need verification."
        )
    with sources:
        for text in plan.warnings:
            st.warning(text)
        for text in plan.recommendations:
            st.write(text)
        for item in plan.cost_items:
            if item.notes:
                st.markdown(f"**{item.label}**")
                for text in item.notes:
                    st.caption(text)
