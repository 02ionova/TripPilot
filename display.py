"""Consistent human-facing dates/times; serialized API/trace values stay ISO."""

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def money(value: float | Decimal) -> str:
    """Hide zero cents, preserve real cents and group thousands for display only."""
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount == 0:
        amount = abs(amount)
    formatted = f"{amount:,.2f}"
    return "€" + (formatted[:-3] if formatted.endswith(".00") else formatted)


def display_date(value: date) -> str:
    return f"{value.day} {MONTHS[value.month - 1]} {value.year}"


def display_datetime(value: datetime) -> str:
    return f"{display_date(value)} · {value:%H:%M}"


def display_duration(minutes: int | None) -> str:
    if minutes is None:
        return "Not supplied"
    hours, remainder = divmod(minutes, 60)
    return (
        " ".join(
            part
            for part in (f"{hours} h" if hours else "", f"{remainder} min" if remainder else "")
            if part
        )
        or "0 min"
    )
