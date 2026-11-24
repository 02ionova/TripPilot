"""Normalize user-entered city labels without claiming geocoding or verification."""

import unicodedata


def normalize_city_name(value: str) -> str:
    city = " ".join(unicodedata.normalize("NFC", value).split()).title()
    if not city or len(city) > 120 or not any(char.isalpha() for char in city):
        raise ValueError("Enter a city name containing letters (maximum 120 characters).")
    if any(unicodedata.category(char).startswith("C") for char in city):
        raise ValueError("City names cannot contain control characters.")
    return city
