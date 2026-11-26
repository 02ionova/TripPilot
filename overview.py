"""Weather and spending views derived solely from the validated itinerary."""

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from html import escape
from statistics import mean

import streamlit as st

from display import display_date, money
from schemas import Itinerary, WeatherDay

BUDGET_CATEGORIES = {
    "flights": ("Flights", "#776286", "↗"),
    "accommodation": ("Accommodation", "#557C80", "⌂"),
    "food": ("Food", "#BF9657", "◒"),
    "activities": ("Activities", "#A66F69", "✧"),
    "local_transport": ("Local transportation", "#7A8DAD", "⇄"),
}


@dataclass(frozen=True)
class WeatherOverview:
    low: float
    high: float
    condition: str
    tone: str
    icon: str
    clothing: list[str]
    source_label: str


def weather_overview(days: list[WeatherDay]) -> WeatherOverview | None:
    """Summarize daily observations; historical data never becomes a forecast."""
    if not days:
        return None
    kinds = []
    for day in days:
        text = day.conditions.lower()
        kinds.append(
            "snow"
            if any(w in text for w in ("snow", "sleet", "freezing"))
            else "rain"
            if any(w in text for w in ("rain", "drizzle", "storm", "shower"))
            else "cloud"
            if any(w in text for w in ("cloud", "overcast"))
            else "sun"
            if any(w in text for w in ("sun", "clear"))
            else "fog"
            if any(w in text for w in ("fog", "mist"))
            else "mixed"
        )
    dominant = Counter(kinds).most_common(1)[0][0]
    labels = {
        "rain": ("Rainy spells", "☂"),
        "snow": ("Snowy conditions", "❄"),
        "cloud": ("Mostly cloudy", "☁"),
        "sun": ("Mostly sunny", "☀"),
        "fog": ("Misty conditions", "≋"),
        "mixed": ("Mixed conditions", "◐"),
    }
    condition, icon = labels[dominant]
    low, high = min(w.min_temperature for w in days), max(w.max_temperature for w in days)
    daytime = mean(w.max_temperature for w in days)
    clothing = [
        "Insulated coat, warm layers, scarf and gloves."
        if low <= 0
        else "A warm jacket and knitwear for chilly mornings and evenings."
        if low < 10
        else "A light jacket or cardigan for cooler mornings and evenings."
    ]
    if daytime >= 25:
        clothing.append("Breathable clothes, sunglasses, a sun hat and sunscreen for daytime.")
    elif daytime >= 18:
        clothing.append("Light, removable layers for milder afternoons.")
    wet = any(k in {"rain", "snow"} for k in kinds) or any(
        (w.rain_probability is not None and w.rain_probability >= 0.5)
        or (w.historical_wet_day_frequency is not None and w.historical_wet_day_frequency >= 0.4)
        for w in days
    )
    if wet:
        clothing.append("Pack a waterproof layer and a compact umbrella; rain is possible.")
    if any(w.wind_speed_kmh is not None and w.wind_speed_kmh >= 25 for w in days):
        clothing.append("Choose a wind-resistant outer layer.")
    clothing.append("Comfortable walking shoes" + (" with water-resistant uppers." if wet else "."))
    labels_present = {w.information_type for w in days}
    source_label = (
        "Simulated weather"
        if labels_present == {"simulated"}
        else "Historical climate estimate"
        if labels_present == {"Historical climate estimate"}
        else "Forecast + historical climate estimate"
        if "Historical climate estimate" in labels_present
        else "Weather forecast"
    )
    return WeatherOverview(low, high, condition, dominant, icon, clothing, source_label)


def render_weather(plan: Itinerary) -> None:
    profile = weather_overview(plan.weather_summary)
    if profile is None:
        st.caption("Weather information is unavailable for these dates.")
        return
    st.subheader("What to expect at your destination")
    summary = plan.trip_summary
    dates = f"{display_date(summary.start_date)} – {display_date(summary.end_date)}"
    st.caption(f"{summary.destination} · {dates}")
    left, right = st.columns(2, gap="medium")
    with left:
        st.markdown(
            f'<section class="weather-card weather-{profile.tone}">'
            f'<div class="overview-eyebrow">{escape(profile.source_label)}</div>'
            f'<div class="weather-head"><span class="weather-symbol" aria-hidden="true">{profile.icon}</span>'
            f'<span class="weather-condition">{profile.condition}</span></div>'
            f'<div class="weather-range">{profile.low:g}° <span>to</span> {profile.high:g}°C</div>'
            '<p class="overview-note">Temperature range across your stay · Most common daily conditions</p>'
            + (
                '<p class="overview-note">Seasonal guidance from previous years, not a forecast for your dates.</p>'
                if "Historical" in profile.source_label or "historical" in profile.source_label
                else ""
            )
            + "</section>",
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(
            '<section class="weather-card packing-card"><div class="overview-eyebrow">Pack for your trip</div>'
            '<h3>Wear it well</h3><ul class="packing-list">'
            + "".join(f"<li>{escape(t)}</li>" for t in profile.clothing)
            + "</ul></section>",
            unsafe_allow_html=True,
        )
    if any(w.source for w in plan.weather_summary):
        st.caption("Weather data: Open-Meteo · Location data: GeoNames · CC BY 4.0")


def split_cost_label(label: str) -> tuple[str, str | None]:
    """Separate provider item names from machine-readable date prefixes."""
    match = re.match(r"^(\d{4}-\d{2}-\d{2}):\s*(.*)$", label)
    if match:
        try:
            return match[2], display_date(date.fromisoformat(match[1]))
        except ValueError:
            pass
    return label, None


def render_budget(plan: Itinerary) -> None:
    b = plan.budget_breakdown
    st.subheader("Your travel budget, at a glance")
    st.caption(f"Estimated spending for all {plan.trip_summary.travelers} traveler(s) · EUR")
    segments, rows, angle = [], [], 0.0
    for key, (name, color, icon) in BUDGET_CATEGORIES.items():
        amount = getattr(b, key)
        share = amount / b.total if b.total > 0 else 0
        if amount > 0:
            end = angle + share * 360
            segments.append(f"{color} {angle:.6f}deg {end:.6f}deg")
            angle = end
        rows.append(
            f'<div class="budget-legend-row"><span class="budget-dot" style="background:{color}"></span>'
            f'<div class="budget-category">{name}<small>{share:.0%} of estimated spending</small></div>'
            f"<strong>{money(amount)}</strong></div>"
        )
    gradient = ", ".join(segments) if segments else "#E8E9EF 0deg 360deg"
    remaining_label = "Above target budget" if b.remaining_budget < 0 else "Left to enjoy"
    st.markdown(
        '<section class="budget-overview">'
        '<div class="budget-donut-wrap">'
        f'<div class="budget-donut" role="img" aria-label="Spending by category. Total {escape(money(b.total))}. See adjacent breakdown." style="background:conic-gradient({gradient})">'
        f'<div class="budget-donut-hole"><span>Total estimated</span><strong>{money(b.total)}</strong><small>for your whole trip</small></div></div></div>'
        '<div class="budget-legend">'
        + "".join(rows)
        + f'<div class="budget-balance{" over-target" if b.remaining_budget < 0 else ""}"><span>{remaining_label}</span><strong>{money(abs(b.remaining_budget))}</strong></div>'
        + "</div></section>",
        unsafe_allow_html=True,
    )
    if not plan.cost_items:
        return
    st.subheader("Retrieved prices and estimated costs")
    st.caption("A closer look at each category · All amounts cover the whole party")
    for key, (name, color, icon) in BUDGET_CATEGORIES.items():
        items = [item for item in plan.cost_items if item.category == key]
        if not items:
            continue
        with st.expander(
            f"{name} · {money(getattr(b, key))}", expanded=key in {"flights", "accommodation"}
        ):
            cards = []
            for item in items:
                name_label, day_label = split_cost_label(item.label)
                kind = "Retrieved price" if item.kind == "retrieved" else "Estimated cost"
                cards.append(
                    '<article class="expense-row">'
                    f'<span class="expense-icon" style="color:{color}" aria-hidden="true">{icon}</span>'
                    f'<div class="expense-description"><div class="expense-name">{escape(name_label)}</div>'
                    '<div class="expense-meta">'
                    + (f"<span>{escape(day_label)}</span>" if day_label else "")
                    + f'<span class="cost-badge {item.kind}">{kind}</span></div></div>'
                    f'<strong class="expense-amount">{money(item.amount)}</strong></article>'
                )
            st.markdown(
                '<div class="expense-list">' + "".join(cards) + "</div>", unsafe_allow_html=True
            )
