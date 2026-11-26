"""One accessible information popover for shared notices and itinerary assumptions."""

from html import escape

import streamlit as st


def information_groups(mode: str, result=None) -> dict[str, list[str]]:
    groups = {
        "Travel information": [
            "Travel information is retrieved from external data providers. Prices and availability may change. Estimated expenses are clearly marked."
            if mode == "live"
            else "Demo Mode: all prices, schedules, places, availability and weather are simulated.",
            "No bookings or reservations are made by this application.",
            "Use City, Country for ambiguous names. City suggestions do not restrict supported destinations.",
        ],
        "Budget and estimates": [
            "The budget covers all travelers. We prefer your target; a clearly marked alternative may cost up to 10% more. The budget metrics always show any excess.",
            "Adding or removing one traveler adjusts your editable budget by EUR 500. The budget buttons use EUR 100 steps; any custom amount can be entered.",
            "Flights and accommodation are charged once per trip; day totals cover meals, activities and local transport.",
            "Unconfirmed admission, meals and transport use labeled planning estimates. Verify actual prices, taxes and availability before booking.",
        ],
        "Planning and sources": [
            "Only Generate Travel Plan starts planning. Editing fields does not make provider searches.",
            "Live Mode uses external providers. Demo Mode uses simulated datasets. Both modes use an AI agent.",
            "Weather beyond the forecast horizon is a Historical climate estimate, not a prediction for your trip.",
            "Travel times between places are geographic estimates, not verified directions or transport timetables.",
            "Confirm venue hours and dietary suitability directly. Search results do not certify allergy safety or halal compliance.",
        ],
    }
    if result is None:
        return groups
    if result.data_source == "live":
        groups["Provider usage"] = [
            f"SerpApi searches: {result.serpapi_requests}; provider cache hits: {result.provider_cache_hits}."
        ]
    if result.status != "success":
        return groups
    plan = result.itinerary
    groups["This trip"] = list(plan.warnings) + list(plan.recommendations)
    groups["Flight and stay"] = list(plan.selected_flights.notes)
    if plan.selected_flights.price_info:
        groups["Flight and stay"].extend(plan.selected_flights.price_info.notes)
    if plan.selected_accommodation:
        groups["Flight and stay"].extend(plan.selected_accommodation.notes)
    groups["Cost assumptions"] = list(
        dict.fromkeys(text for item in plan.cost_items for text in item.notes)
    )
    for day in plan.daily_itinerary:
        notes = list(day.recommendations) + list(day.weather.notes)
        for slot in day.schedule:
            notes.extend(f"{slot.activity.name}: {text}" for text in slot.activity.notes)
        if notes:
            groups[f"{day.date} · Practical notes"] = list(dict.fromkeys(notes))
    return groups


def render_information(mode: str, result=None) -> None:
    """Hover, focus or tap the single edge control; scroll within long notes."""
    sections = []
    seen = set()
    for title, notes in information_groups(mode, result).items():
        unique = []
        for note in notes:
            if note and note not in seen:
                unique.append(note)
                seen.add(note)
        if unique:
            sections.append(
                f"<section><h3>{escape(title)}</h3><ul>"
                + "".join(f"<li>{escape(n)}</li>" for n in unique)
                + "</ul></section>"
            )
    st.markdown(
        '<div class="travel-information" tabindex="0" role="button" '
        'aria-label="Travel information, estimates and practical notes" '
        'aria-describedby="travel-information-content">'
        '<span class="information-symbol" aria-hidden="true">i</span>'
        '<div class="information-popover" role="tooltip" id="travel-information-content">'
        "<h2>Good to know</h2>" + "".join(sections) + "</div></div>",
        unsafe_allow_html=True,
    )
