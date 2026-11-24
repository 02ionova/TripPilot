"""Normalize user-entered city labels without claiming geocoding or verification."""

import unicodedata


def normalize_city_name(value: str) -> str:
    city = " ".join(unicodedata.normalize("NFC", value).split()).title()
    if not city or len(city) > 120 or not any(char.isalpha() for char in city):
        raise ValueError("Enter a city name containing letters (maximum 120 characters).")
    if any(unicodedata.category(char).startswith("C") for char in city):
        raise ValueError("City names cannot contain control characters.")
    return city


def bind_city_label(value: str, selected: str) -> str:
    """Restore only an omitted qualifier already explicitly selected by the user.

    Never add a country to an ambiguous user input or accept a different country.
    """
    value, selected = normalize_city_name(value), normalize_city_name(selected)
    if value == selected or ("," not in value and value == selected.split(",")[0].strip()):
        return selected
    raise ValueError("Use the city and country from the original request.")
