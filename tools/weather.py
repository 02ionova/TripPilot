"""Seasonal simulations, repeatable for dates in 2026–2035."""

from schemas import WeatherArgs, WeatherDay
from tools.common import dates, load, success


def get_weather(args: WeatherArgs):
    profiles = load("weather", args.destination)
    result = []
    for day in dates(args.start_date, args.end_date):
        season = (
            "winter"
            if day.month in [12, 1, 2]
            else "spring"
            if day.month <= 5
            else "summer"
            if day.month <= 8
            else "autumn"
        )
        profile = profiles[season]
        wet = profile["rain_probability"] >= 0.5
        result.append(
            WeatherDay(
                date=day,
                **profile,
                conditions="Rain likely" if wet else "Partly sunny",
                recommendation="indoor" if wet else "outdoor",
            )
        )
    return success(result)
