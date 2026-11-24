"""Curated JSON fixtures plus deterministic, explicitly generic city/route fixtures.

Unknown city labels are accepted as labels, not geocoded. Templates never invent
real landmarks, weather forecasts, airline routes or geographic distances.
"""

import hashlib
import json
from copy import deepcopy

from cities import normalize_city_name
from config import ROOT


def stable_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def templates() -> dict:
    return json.loads((ROOT / "data" / "generic_templates.json").read_text())


def curated_destination(destination: str) -> bool:
    data = json.loads((ROOT / "data" / "hotels.json").read_text())["destinations"]
    return normalize_city_name(destination) in data


def destination_options(kind: str, destination: str) -> list | dict:
    city = normalize_city_name(destination)
    curated = json.loads((ROOT / "data" / f"{kind}.json").read_text())["destinations"]
    if city in curated:
        return curated[city]
    generated = deepcopy(templates()[kind])
    if kind == "weather":
        return generated
    prefix = "generic-" + stable_key(city)
    for index, option in enumerate(generated, 1):
        if kind == "flights":
            option["id"] = f"{prefix}-flight-{index}"
        elif kind == "hotels":
            option["id"] = f"{prefix}-hotel-{index}"
            option["name"] = f"{city}: {option['name']}"
        else:
            label = "meal" if option["category"] == "meal" else "activity"
            option["id"] = f"{prefix}-{label}-{index}"
            option["name"] = f"{city}: {option['name']}"
    return generated


def flight_options(origin: str, destination: str) -> list[dict]:
    origin, destination = normalize_city_name(origin), normalize_city_name(destination)
    if origin == destination:
        raise ValueError("Departure and destination cities must be different.")
    if origin == "Prague" and curated_destination(destination):
        return destination_options("flights", destination)
    # SHA-256 makes route IDs/rates stable across processes and independent of dates.
    # The rates/times are fixtures; they imply no real route, distance or time zone.
    route = stable_key(origin + "\0" + destination)
    options = deepcopy(templates()["flights"])
    base_price = 90 + int(route[:4], 16) % 71
    for index, (option, supplement) in enumerate(zip(options, [0, 55, 140]), 1):
        option["id"] = f"synthetic-{route}-flight-{index}"
        option["price_per_traveler"] = base_price + supplement
    return options


def simulation_notes(origin: str, destination: str) -> list[str]:
    notes = []
    if normalize_city_name(origin) != "Prague" or not curated_destination(destination):
        notes.append(
            "This route uses generic synthetic flights. Route existence, flight duration, dates, times and time zones are not verified; this is not a real transport recommendation."
        )
    if not curated_destination(destination):
        notes.append(
            "This destination uses generic accommodation, activity and meal templates, not verified local establishments or landmarks."
        )
        notes.append(
            "Weather uses neutral fictional climate placeholders, not location-specific seasonal weather or a forecast."
        )
    return notes
