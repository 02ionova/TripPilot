"""Open-Meteo forecast and a clearly labeled three-season climate estimate."""

from collections import Counter
from datetime import date, timedelta
from statistics import mean

import schemas
from providers.http import ProviderClient
from providers.locations import geocode
from providers.travel import source
from schemas import WeatherArgs, WeatherDay
from tools.common import ToolFailure, dates

WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Dense drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    80: "Rain showers",
    81: "Rain showers",
    82: "Heavy showers",
    95: "Thunderstorm",
}


def required_daily(payload: dict) -> dict:
    data = payload.get("daily", {})
    if not data.get("time"):
        raise ToolFailure(
            "weather_unavailable",
            "The weather provider returned no daily observations.",
            ["Retry later or change the date range."],
        )
    return data


def at(data: dict, name: str, index: int):
    values = data.get(name, [])
    return values[index] if index < len(values) else None


def historical_date(day: date, year: int) -> date:
    try:
        return day.replace(year=year)
    except ValueError:
        return date(year, 2, 28)  # Leap-day comparison uses Feb 28, noted below.


def weather(client: ProviderClient, args: WeatherArgs) -> list[WeatherDay]:
    city = geocode(client, args.destination)
    base = dict(
        latitude=city["latitude"],
        longitude=city["longitude"],
        timezone=city.get("timezone", "auto"),
    )
    requested = dates(args.start_date, args.end_date)
    today = schemas.current_date()
    forecast_days = [day for day in requested if today <= day <= today + timedelta(days=15)]
    result = {}
    if forecast_days:
        payload = client.get_json(
            "https://api.open-meteo.com/v1/forecast",
            {
                **base,
                "start_date": str(forecast_days[0]),
                "end_date": str(forecast_days[-1]),
                "daily": "temperature_2m_min,temperature_2m_max,precipitation_probability_max,weather_code,wind_speed_10m_max",
            },
            ttl=3600,
        )
        data = required_daily(payload)
        for index, raw_day in enumerate(data["time"]):
            low, high = at(data, "temperature_2m_min", index), at(data, "temperature_2m_max", index)
            if low is None or high is None:
                continue
            probability = at(data, "precipitation_probability_max", index)
            code = at(data, "weather_code", index)
            wet = (probability is not None and probability >= 50) or code in {
                51,
                53,
                55,
                61,
                63,
                65,
                80,
                81,
                82,
                95,
            }
            result[date.fromisoformat(raw_day)] = WeatherDay(
                date=raw_day,
                min_temperature=low,
                max_temperature=high,
                conditions=WEATHER_CODES.get(code, f"WMO weather code {code}"),
                rain_probability=probability / 100 if probability is not None else None,
                recommendation="indoor" if wet else "outdoor",
                information_type="Weather forecast",
                wind_speed_kmh=at(data, "wind_speed_10m_max", index),
                source=source(payload, "Open-Meteo", "https://open-meteo.com/en/docs"),
            )
    climate_days = [day for day in requested if day not in result]
    if climate_days:
        samples = {day: [] for day in climate_days}
        # Use completed comparable seasons; do not request future archive dates.
        latest_year = today.year - 1
        while historical_date(
            args.end_date, latest_year + (args.end_date.year - args.start_date.year)
        ) > today - timedelta(days=7):
            latest_year -= 1
        for year in range(latest_year, latest_year - 3, -1):
            mapped = {
                day: historical_date(day, year + (day.year - args.start_date.year))
                for day in climate_days
            }
            payload = client.get_json(
                "https://archive-api.open-meteo.com/v1/archive",
                {
                    **base,
                    "start_date": str(min(mapped.values())),
                    "end_date": str(max(mapped.values())),
                    "daily": "temperature_2m_min,temperature_2m_max,precipitation_sum,weather_code,wind_speed_10m_max",
                },
                ttl=86400,
            )
            data = required_daily(payload)
            indexes = {raw: i for i, raw in enumerate(data["time"])}
            for day, mapped_day in mapped.items():
                index = indexes.get(str(mapped_day))
                if index is None:
                    continue
                low, high = (
                    at(data, "temperature_2m_min", index),
                    at(data, "temperature_2m_max", index),
                )
                if low is None or high is None:
                    continue
                samples[day].append(
                    dict(
                        low=low,
                        high=high,
                        rain=at(data, "precipitation_sum", index),
                        wind=at(data, "wind_speed_10m_max", index),
                        code=at(data, "weather_code", index),
                        year=mapped_day.year,
                        payload=payload,
                    )
                )
        for day, rows in samples.items():
            if len(rows) < 2:
                raise ToolFailure(
                    "insufficient_climate_history",
                    f"Insufficient historical weather for {day}.",
                    ["Retry later; no weather values will be invented."],
                )
            rain_rows = [row for row in rows if row["rain"] is not None]
            wet_frequency = (
                sum(row["rain"] > 0.1 for row in rain_rows) / len(rain_rows) if rain_rows else None
            )
            winds = [row["wind"] for row in rows if row["wind"] is not None]
            label = WEATHER_CODES.get(
                Counter(row["code"] for row in rows).most_common(1)[0][0],
                "Variable historical conditions",
            )
            result[day] = WeatherDay(
                date=day,
                min_temperature=round(mean(row["low"] for row in rows), 1),
                max_temperature=round(mean(row["high"] for row in rows), 1),
                conditions=f"Historical seasonal sample: {label}",
                rain_probability=None,
                historical_wet_day_frequency=wet_frequency,
                recommendation="indoor"
                if wet_frequency is not None and wet_frequency >= 0.5
                else "outdoor",
                information_type="Historical climate estimate",
                wind_speed_kmh=round(mean(winds), 1) if winds else None,
                historical_years=[row["year"] for row in rows],
                source=source(
                    rows[-1]["payload"],
                    "Open-Meteo historical reanalysis",
                    "https://open-meteo.com/en/docs/historical-weather-api",
                ),
                notes=[
                    "Average of comparable dates from previous completed seasons, not a weather forecast.",
                    "Wet-day frequency is a historical sample frequency, not a predicted rain probability.",
                    "A historical February 29 maps to February 28 in non-leap years.",
                ],
            )
    return [result[day] for day in requested]
