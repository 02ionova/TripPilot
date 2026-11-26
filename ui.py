"""Presentation of live provider records, quotes, estimates and provenance."""

from html import escape

import streamlit as st

from config import ROOT
from display import display_date, display_datetime, display_duration, money
from overview import render_budget, render_weather
from providers.travel import safe_url


def render_budget_metrics(plan) -> None:
    """Keep the original target visible and show overruns as positive extra cost."""
    b = plan.budget_breakdown
    target = b.total + b.remaining_budget
    left, middle, right = st.columns(3)
    left.metric("Total budget", money(target))
    middle.metric("Total estimated cost", money(b.total))
    if b.remaining_budget < 0:
        right.metric("Above target budget", money(-b.remaining_budget))
    else:
        right.metric("Remaining budget", money(b.remaining_budget))


def render_stop(slot, *, simulated: bool = False) -> None:
    """Render escaped provider text in visually distinct visit and meal cards."""
    place = slot.activity
    kind = "meal" if slot.meal else "visit"
    if slot.transfer_note:
        st.markdown(
            f'<div class="transfer-note">{escape(slot.transfer_note)}</div>', unsafe_allow_html=True
        )
    rating = f" · {place.rating}/5" if place.rating is not None and not simulated else ""
    reviews = f" · {place.reviews} reviews" if place.reviews is not None else ""
    label = "Simulated cost" if simulated else price_label(place.price_info)
    address = f'<div class="stop-meta">{escape(place.address)}</div>' if place.address else ""
    links = []
    for name, value in [("Google Maps ↗", place.url), ("Venue website ↗", place.website)]:
        url = safe_url(value)
        if url:
            links.append(
                f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{name}</a>'
            )
    st.markdown(
        f'<article class="stop-card {kind}">'
        f'<div class="stop-top"><span class="stop-time">{slot.start_time:%H:%M} – {slot.end_time:%H:%M}</span>'
        f'<span class="stop-tag">{escape(slot.meal.title() if slot.meal else "Explore")}</span></div>'
        f'<div class="stop-name">{escape(place.name)}</div>{address}'
        f'<div class="stop-meta">{label}: {money(slot.total_cost)} for all travelers{rating}{reviews}</div>'
        f'<div class="stop-links">{"".join(links)}</div></article>',
        unsafe_allow_html=True,
    )


def render_day_illustration(day, *, simulated: bool) -> None:
    """Reuse a retrieved venue thumbnail; never spend searches just for decoration."""
    venues = [s.activity for s in day.schedule]
    featured = sorted(venues, key=lambda p: p.category == "meal")
    photograph = (
        next((p for p in featured if safe_url(p.image_url)), None) if not simulated else None
    )
    if photograph:
        source_url = safe_url(photograph.url)
        caption = f"{escape(photograph.name)} · Provider photo"
        if source_url:
            caption = f'<a href="{escape(source_url, quote=True)}" target="_blank" rel="noopener noreferrer">{caption} ↗</a>'
        st.markdown(
            f'<figure class="day-photo"><img src="{escape(safe_url(photograph.image_url), quote=True)}" alt="{escape(photograph.name, quote=True)}" loading="lazy" referrerpolicy="no-referrer"><figcaption>{caption}</figcaption></figure>',
            unsafe_allow_html=True,
        )
    else:
        scene = (
            "museum"
            if any(p.category == "attraction" for p in venues)
            else "dining"
            if venues
            else "travel"
        )
        st.image(str(ROOT / "assets" / f"day-{scene}.svg"), width="stretch")
        st.caption(
            "Decorative illustration · Simulated venues"
            if simulated
            else "Decorative illustration · Venue photo unavailable"
        )
    if featured:
        st.caption(f"Featuring {featured[0].name}")
    else:
        st.caption("Your journey · Arrival or departure day")


def render_travel_card(
    kind: str, label: str, title: str, detail: str, url: str | None = None
) -> None:
    """Display existing itinerary facts; this renderer never searches or adds costs."""
    link = safe_url(url)
    links = (
        f'<div class="stop-links"><a href="{escape(link, quote=True)}" target="_blank" rel="noopener noreferrer">View source ↗</a></div>'
        if link
        else ""
    )
    st.markdown(
        f'<article class="stop-card {kind}"><div class="stop-top"><span class="stop-tag">{escape(label)}</span></div>'
        f'<div class="stop-name">{escape(title)}</div><div class="stop-meta">{escape(detail)}</div>{links}</article>',
        unsafe_allow_html=True,
    )


def journey_dates(plan):
    f = plan.selected_flights
    arrival = f.outbound_arrival.date() if f.outbound_arrival else f.departure_date
    departure = f.return_departure.date() if f.return_departure else f.return_date
    return arrival, departure


def render_daily_flights(plan, day, *, returning: bool) -> None:
    flight = plan.selected_flights
    legs = flight.return_segments if returning else flight.outbound_segments
    label = "Return flight" if returning else "Outbound flight"
    if legs:
        for leg in legs:
            if day.date not in {leg.departure.date(), leg.arrival.date()} and not (
                leg.departure.date() < day.date < leg.arrival.date()
            ):
                continue
            number = f" · {leg.flight_number}" if leg.flight_number else ""
            render_travel_card(
                "flight",
                label,
                f"{leg.departure_airport} → {leg.arrival_airport}",
                f"{leg.airline}{number} · {display_datetime(leg.departure)} → {display_datetime(leg.arrival)} (airport local times)"
                + (
                    f" · {display_duration(leg.duration_minutes)}"
                    if leg.duration_minutes is not None
                    else ""
                ),
                flight.search_url,
            )
    elif day.date == (flight.return_date if returning else flight.departure_date):
        start = flight.return_departure_time if returning else flight.departure_time
        end = flight.return_arrival_time if returning else flight.arrival_time
        origin = flight.destination if returning else flight.origin
        destination = flight.origin if returning else flight.destination
        render_travel_card(
            "flight",
            label,
            f"{origin} → {destination}",
            f"{flight.airline} · {start:%H:%M} → {end:%H:%M} · "
            + ("Simulated schedule" if plan.data_source == "simulated" else "Airport local times"),
            flight.search_url,
        )


def render_daily_stay(plan, day) -> None:
    hotel = plan.selected_accommodation
    arrival, departure = journey_dates(plan)
    if hotel and arrival <= day.date < departure:
        label = "Arrival accommodation" if day.date == arrival else "Overnight stay"
        render_travel_card(
            "stay",
            label,
            hotel.name,
            f"{hotel.address or hotel.neighborhood} · {hotel.rooms} room(s) · Full stay {money(hotel.total_cost)} for {hotel.nights} night(s), charged once in the trip budget.",
            hotel.url,
        )


def display_day_title(plan, day) -> str:
    """Do not advertise a restaurant visit when the day only has travel allowances."""
    if day.schedule:
        return day.title
    arrival, departure = journey_dates(plan)
    if day.date == arrival == departure:
        return "Arrival and return journey"
    if day.date == arrival:
        return f"Arrival in {plan.trip_summary.destination}"
    if day.date == departure:
        return "Return journey"
    return day.title


def render_itinerary_days(plan) -> None:
    """Day overview/photo alongside a color-coded chronological schedule."""
    simulated = plan.data_source == "simulated"
    for index, day in enumerate(plan.daily_itinerary, start=1):
        with st.container(border=True, key=f"itinerary_day_{index}"):
            overview, schedule = st.columns([1, 1.8], gap="large")
            with overview:
                st.markdown(
                    f'<div class="day-number">Day {index:02} · {day.date:%A, %d %B}</div><div class="day-title">{escape(display_day_title(plan, day))}</div>',
                    unsafe_allow_html=True,
                )
                render_day_illustration(day, simulated=simulated)
                w = day.weather
                st.caption(
                    f"{w.information_type} · {w.conditions} · {w.min_temperature:.0f}–{w.max_temperature:.0f} °C"
                )
                st.markdown(f"**{money(day.estimated_cost)}** · Daily estimated expenses")
                st.caption(
                    f"Local transport allowance: {money(day.local_transport)}. Flights and accommodation excluded from this daily figure."
                )
            with schedule:
                arrival, departure = journey_dates(plan)
                render_daily_flights(plan, day, returning=False)
                if day.date == arrival:
                    render_travel_card(
                        "transfer",
                        "Estimated arrival transfer",
                        "Airport → accommodation",
                        "Airport transfer allowance is included in the daily local transport budget. Arrival buffer: 90 minutes.",
                    )
                    render_daily_stay(plan, day)
                if day.date == departure and plan.selected_accommodation:
                    render_travel_card(
                        "stay",
                        "Departure day",
                        f"Check out · {plan.selected_accommodation.name}",
                        "Arrange check-out around the selected return flight; hotel-specific check-out time is not supplied.",
                    )
                for slot in day.schedule:
                    render_stop(slot, simulated=simulated)
                if not day.schedule:
                    food_allowance = day.estimated_cost - day.local_transport
                    if food_allowance > 0:
                        render_travel_card(
                            "meal",
                            "During your journey",
                            "Airport or in-transit meal allowance",
                            f"Estimated cost: {money(food_allowance)} for all travelers. Included in the daily total.",
                        )
                if arrival < day.date < departure:
                    render_daily_stay(plan, day)
                if day.date == departure:
                    render_travel_card(
                        "transfer",
                        "Estimated departure transfer",
                        "Accommodation → airport",
                        "Airport transfer allowance is included in the daily local transport budget. Be at the airport at least 2 hours before departure.",
                    )
                render_daily_flights(plan, day, returning=True)
    points = [
        {"lat": s.activity.coordinates.latitude, "lon": s.activity.coordinates.longitude}
        for d in plan.daily_itinerary
        for s in d.schedule
        if s.activity.coordinates
    ]
    if points:
        with st.expander("Explore your places on the map"):
            st.map(points)


def price_label(info) -> str:
    return "Retrieved price" if info and info.kind == "retrieved" else "Estimated cost"


def render_live_plan(result):
    plan = result.itinerary
    summary = plan.trip_summary
    st.subheader(f"{summary.origin} → {summary.destination}")
    st.caption(
        f"{display_date(summary.start_date)} – {display_date(summary.end_date)} · {summary.travelers} traveler(s) · EUR · Live Mode"
    )
    render_budget_metrics(plan)
    if result.retrieved_at:
        st.caption(f"Travel information retrieved: {display_datetime(result.retrieved_at)} UTC")
    st.subheader("Your day-by-day itinerary")
    render_itinerary_days(plan)
    travel, weather, budget = st.tabs(["Flights & stay", "Weather", "Budget"])
    with travel:
        flight = plan.selected_flights
        st.markdown(f"**{flight.airline}**")
        st.write(
            f"{price_label(flight.price_info)}: {money(flight.total_price)} total round trip for {summary.travelers} traveler(s)."
        )
        for title, legs in [
            ("Outbound", flight.outbound_segments),
            ("Return", flight.return_segments),
        ]:
            st.markdown(
                f"**{title} · {'Direct flight' if len(legs) == 1 else str(len(legs) - 1) + ' stop(s)'}**"
            )
            st.dataframe(
                [
                    {
                        "Airline": leg.airline,
                        "Flight": leg.flight_number,
                        "From": leg.departure_airport,
                        "Departure (local)": display_datetime(leg.departure),
                        "To": leg.arrival_airport,
                        "Arrival (local)": display_datetime(leg.arrival),
                        "Duration": display_duration(leg.duration_minutes),
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
                f"{flight.source.provider} · retrieved {display_datetime(flight.source.retrieved_at)} UTC"
            )
        hotel = plan.selected_accommodation
        if hotel:
            st.markdown(f"**{hotel.name}**")
            if hotel.image_url:
                st.image(hotel.image_url, width=500)
            st.write(hotel.address or hotel.neighborhood)
            st.write(
                f"{price_label(hotel.price_info)}: {money(hotel.total_cost)} for {hotel.nights} nights / {hotel.rooms} room(s). Retrieved or derived nightly unit rate: {money(hotel.price_per_night)}."
            )
            st.caption(
                (f"Rating {hotel.rating}/5" if hotel.rating is not None else "Rating unavailable")
                + (f" · {hotel.reviews} reviews" if hotel.reviews is not None else "")
            )
            if hotel.url:
                st.link_button("View accommodation", hotel.url)
        else:
            st.caption("No overnight accommodation needed.")
    with weather:
        render_weather(plan)
    with budget:
        render_budget(plan)


def render_ai_advice(advice) -> None:
    """Keep unverified model suggestions visibly separate from trusted itineraries."""
    st.subheader("AI backup response")
    st.caption(
        "OpenAI general-knowledge suggestions · No live search · Prices, availability and budget are not verified"
    )
    if advice.status != "available":
        st.write(advice.error)
        return
    model, duration, tokens = st.columns(3)
    model.metric("AI model", advice.model)
    duration.metric("Response time", f"{advice.duration_seconds:.1f} s")
    tokens.metric(
        "Tokens used",
        advice.usage.total_tokens if advice.usage.total_tokens is not None else "Not reported",
    )
    content = advice.content
    st.markdown(f"**{content.title}**")
    st.write(content.summary)
    for day in content.days:
        with st.container(border=True):
            st.markdown(f"**{display_date(day.date)} · {day.title}**")
            for suggestion in day.suggestions:
                st.write(f"• {suggestion}")
    if content.budget_guidance:
        st.markdown("**Budget approach**")
        for text in content.budget_guidance:
            st.write(f"• {text}")
    if content.verification_steps:
        with st.expander("What to verify before booking"):
            for text in content.verification_steps:
                st.write(f"• {text}")
