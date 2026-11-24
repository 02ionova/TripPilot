"""Conservative parsing of provider opening hours and estimated geographic transfers."""

import math
import re
from datetime import date

from schemas import Activity, Coordinates

DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def clock(text: str, period: str | None = None) -> int | None:
    match = re.fullmatch(r"\s*(\d{1,2})(?::(\d{2}))?\s*(AM|PM)?\s*", text, re.I)
    if not match:
        return None
    hour, minute = int(match[1]), int(match[2] or 0)
    suffix = (match[3] or period or "").upper()
    if minute > 59 or hour > 24:
        return None
    if suffix:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if suffix == "PM" else 0)
    if hour == 24 and minute:
        return None
    return hour * 60 + minute


def opening_windows(text: str) -> list[tuple[int, int]] | None:
    normalized = re.sub(r"\s+", " ", text).strip().replace("a.m.", "AM").replace("p.m.", "PM")
    if "closed" in normalized.lower() and "temporarily" not in normalized.lower():
        return []
    if "24 hours" in normalized.lower() or normalized.lower() == "24/7":
        return [(0, 1440)]
    windows = []
    for part in re.split(r"[,;]", normalized):
        pair = re.split(r"\s*[–—−-]\s*", part)
        if len(pair) != 2:
            return None
        left, right = pair
        end_period = re.search(r"(AM|PM)", right, re.I)
        first = clock(left)
        last = clock(right)
        if end_period and not re.search(r"(AM|PM)", left, re.I):
            initial = int(re.search(r"\d+", left)[0]) if re.search(r"\d+", left) else 0
            final = int(re.search(r"\d+", right)[0]) if re.search(r"\d+", right) else 0
            inferred = "AM" if end_period[0].upper() == "PM" and initial > final else end_period[0]
            first = clock(left, inferred)
        if first is None or last is None:
            return None
        if last <= first:
            last += 1440
        windows.append((first, last))
    return windows or None


def open_for_slot(place: Activity, day: date, start: int, end: int) -> bool | None:
    if place.permanently_closed or place.temporarily_closed:
        return False
    current = place.opening_hours.get(DAY_NAMES[day.weekday()])
    previous = place.opening_hours.get(DAY_NAMES[(day.weekday() - 1) % 7])
    windows = opening_windows(current) if current is not None else None
    prior = opening_windows(previous) if previous is not None else None
    if windows is not None and any(low <= start and end <= high for low, high in windows):
        return True
    if prior and any(
        low - 1440 <= start and end <= high - 1440 for low, high in prior if high > 1440
    ):
        return True
    return False if windows is not None else None


def transfer(previous: Coordinates | None, current: Coordinates | None) -> tuple[int, str]:
    if previous is None or current is None:
        return 20, "Estimated transfer: 20 minutes; coordinates unavailable."
    lat1, lat2 = math.radians(previous.latitude), math.radians(current.latitude)
    dlat = lat2 - lat1
    dlon = math.radians(current.longitude - previous.longitude)
    hav = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    distance = 6371 * 2 * math.asin(min(1, math.sqrt(hav)))
    if distance <= 3:
        duration = max(15, math.ceil(distance * 1.3 / 4.5 * 60) + 5)
        return (
            duration,
            f"Estimated walking transfer: about {distance * 1.3:.1f} km / {duration} minutes; road routing is not verified.",
        )
    duration = max(25, math.ceil(distance * 1.3 / 18 * 60) + 15)
    return (
        duration,
        f"Estimated public-transport transfer: {duration} minutes for about {distance:.1f} km straight-line distance; verify service and route.",
    )
