"""Weather guidance and compact money presentation never change trusted costs."""

from datetime import date

import pytest

from display import money
from overview import split_cost_label, weather_overview
from schemas import WeatherDay


@pytest.mark.parametrize(
    "value,expected",
    [
        (310, "€310"),
        (1272, "€1,272"),
        (98.5, "€98.50"),
        (-12, "€-12"),
        (12.345, "€12.35"),
        (-0.001, "€0"),
    ],
)
def test_compact_money_preserves_cents(value, expected):
    assert money(value) == expected


def day(**updates):
    return WeatherDay.model_validate(
        {
            "date": date(2027, 4, 10),
            "min_temperature": 4.1,
            "max_temperature": 14.9,
            "conditions": "Historical seasonal sample: Overcast",
            "recommendation": "indoor",
            "information_type": "Historical climate estimate",
            **updates,
        }
    )


def test_weather_uses_range_common_conditions_and_historical_label():
    profile = weather_overview(
        [
            day(),
            day(min_temperature=6, max_temperature=16),
            day(conditions="Rain", historical_wet_day_frequency=0.67),
        ]
    )
    assert profile.low == 4.1 and profile.high == 16
    assert profile.condition == "Mostly cloudy"
    assert profile.source_label == "Historical climate estimate"
    assert any("warm jacket" in text for text in profile.clothing)
    assert any("waterproof" in text for text in profile.clothing)


def test_cold_windy_weather_changes_packing():
    profile = weather_overview(
        [
            day(
                conditions="Snow",
                min_temperature=-5,
                max_temperature=1,
                wind_speed_kmh=30,
                information_type="Weather forecast",
            )
        ]
    )
    assert profile.source_label == "Weather forecast" and profile.tone == "snow"
    assert any("gloves" in text for text in profile.clothing)
    assert any("wind-resistant" in text for text in profile.clothing)


def test_hot_sunny_weather_and_missing_data():
    profile = weather_overview(
        [
            day(
                conditions="Clear sky",
                min_temperature=21,
                max_temperature=32,
                information_type="simulated",
            )
        ]
    )
    assert profile.tone == "sun" and profile.source_label == "Simulated weather"
    assert any("sunscreen" in text for text in profile.clothing)
    assert not any("umbrella" in text for text in profile.clothing)
    assert weather_overview([]) is None


def test_expense_date_separated_from_name():
    assert split_cost_label("2026-12-22: Colosseum") == ("Colosseum", "22 Dec 2026")
    assert split_cost_label("Ryanair") == ("Ryanair", None)
    assert split_cost_label("2026-99-22: unknown") == ("2026-99-22: unknown", None)
