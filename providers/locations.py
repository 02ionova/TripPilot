"""Resolve real city coordinates and flight airport identifiers without LLM guesses."""

import re
import unicodedata

from providers.http import ProviderClient
from tools.common import ToolFailure


def location_key(value: str) -> str:
    """Compare provider country/admin labels without accents or a leading 'The'."""
    value = re.sub(r"^the\s+", "", value.strip().casefold())
    value = "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))
    value = re.sub(r"[\W_]", "", value)
    return {
        "usa": "us",
        "unitedstates": "us",
        "unitedstatesofamerica": "us",
        "uk": "gb",
        "unitedkingdom": "gb",
        "greatbritain": "gb",
        "czechrepublic": "cz",
        "czechia": "cz",
    }.get(value, value)


def geocode(client: ProviderClient, city: str) -> dict:
    parts = [part.strip() for part in city.split(",") if part.strip()]
    qualifiers = [location_key(part) for part in parts[1:]]

    def matches(place):
        labels = {
            location_key(str(place.get(key) or ""))
            for key in ("country", "country_code", "admin1", "admin2", "admin3", "admin4")
        }
        return all(part in labels for part in qualifiers)

    result = client.get_json(
        "https://geocoding-api.open-meteo.com/v1/search",
        {"name": city, "count": 10, "language": "en", "format": "json"},
        ttl=7 * 86400,
    )
    choices = result.get("results", [])
    if qualifiers:
        choices = [place for place in choices if matches(place)]
        if not choices:
            # Some valid labels (Netherlands vs The Netherlands) return no matches
            # for a combined query. Retry the city once and enforce every qualifier
            # ourselves; never silently choose a city in another country.
            fallback = client.get_json(
                "https://geocoding-api.open-meteo.com/v1/search",
                {"name": parts[0], "count": 100, "language": "en", "format": "json"},
                ttl=7 * 86400,
            )
            choices = [place for place in fallback.get("results", []) if matches(place)]
    if not choices:
        raise ToolFailure(
            "city_not_found",
            f"Could not locate {city}.",
            [
                "Specify city and country or administrative region; no different country will be substituted."
            ],
        )
    exact = [
        place for place in choices if location_key(place.get("name", "")) == location_key(parts[0])
    ]
    candidates = exact or choices
    populations = sorted(candidates, key=lambda c: c.get("population") or 0, reverse=True)
    if len(populations) > 1:
        different_regions = len({(c.get("country_code"), c.get("admin1")) for c in populations}) > 1
        substantial = (populations[1].get("population") or 0) > (
            populations[0].get("population") or 0
        ) * 0.2
        if different_regions and (qualifiers or substantial):
            labels = [
                f"{c['name']}, {c.get('admin1', '')}, {c.get('country', '')}"
                for c in populations[:5]
            ]
            raise ToolFailure("ambiguous_city", f"Several locations match {city}.", labels)
    return populations[0]


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
