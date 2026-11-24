"""Local city suggestions for the searchable selectors; not a geocoding service."""

import json
from functools import lru_cache

from config import ROOT


@lru_cache(maxsize=1)
def city_countries() -> dict[str, str]:
    return {
        city["name"]: city["country"]
        for city in json.loads((ROOT / "data" / "cities.json").read_text())
    }


def city_options() -> list[str]:
    return list(city_countries())


def city_label(city: str) -> str:
    """Show country context while returning the unchanged city value to the agent."""
    country = city_countries().get(city)
    return f"{city}, {country}" if country else city
