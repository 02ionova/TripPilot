"""Resolve real city coordinates and flight airport identifiers without LLM guesses."""

import re

from providers.http import ProviderClient
from tools.common import ToolFailure


def geocode(client: ProviderClient, city: str) -> dict:
    result = client.get_json(
        "https://geocoding-api.open-meteo.com/v1/search",
        {"name": city, "count": 10, "language": "en", "format": "json"},
        ttl=7 * 86400,
    )
    choices = result.get("results", [])
    if not choices:
        raise ToolFailure(
            "city_not_found",
            f"Could not locate {city}.",
            ["Specify the city and country, for example Paris, France."],
        )
    # Do not silently send people to a different Springfield/Paris. Country-qualified
    # queries are already narrowed by Open-Meteo; same-country suburbs are acceptable.
    countries = {c.get("country_code") for c in choices}
    if len(countries) > 1 and "," not in city:
        exact = [c for c in choices if c.get("name", "").casefold() == city.casefold()]
        populations = sorted(exact, key=lambda c: c.get("population", 0), reverse=True)
        if (
            len(populations) > 1
            and populations[1].get("population", 0) > populations[0].get("population", 0) * 0.2
        ):
            labels = [
                f"{c['name']}, {c.get('admin1', '')}, {c.get('country', '')}"
                for c in populations[:5]
            ]
            raise ToolFailure("ambiguous_city", f"Several locations match {city}.", labels)
    return max(choices, key=lambda c: c.get("population", 0))


def airport_id(client: ProviderClient, city: str) -> str:
    if re.fullmatch(r"[A-Z]{3}", city):
        return city
    result = client.search("google_flights_autocomplete", q=city, exclude_regions="true")
    options = [
        c for c in result.get("suggestions", []) if c.get("type") == "city" and c.get("airports")
    ]
    if not options:
        raise ToolFailure(
            "no_airport",
            f"No supported airport was found for {city}.",
            ["Specify a nearby airport's IATA code or a city with commercial air service."],
        )
    # Prefer exact city-name matches; country-qualified queries constrain autocomplete.
    target = city.split(",")[0].strip().casefold()
    exact = [c for c in options if c.get("name", "").split(",")[0].strip().casefold() == target]
    if len(exact) > 1 and "," not in city:
        raise ToolFailure(
            "ambiguous_city",
            f"Multiple airport locations match {city}.",
            [c["name"] for c in exact[:5]],
        )
    selected = (exact or options)[0]
    identifier = selected.get("id")
    if identifier and identifier.startswith(("/m/", "/g/")):
        return identifier
    codes = [a["id"] for a in selected["airports"] if re.fullmatch(r"[A-Z]{3}", a.get("id", ""))]
    if not codes:
        raise ToolFailure(
            "no_airport",
            f"The provider returned no usable airport identifiers for {city}.",
            ["Use an explicit IATA code."],
        )
    return ",".join(codes)
