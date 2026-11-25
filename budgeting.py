"""Shared total-party budget policy: prefer the target, allow at most 10% extra."""

from decimal import ROUND_DOWN, Decimal

BUDGET_FLEX_PERCENT = 10


def maximum_budget(budget: float | Decimal) -> Decimal:
    """Round down to cents so the monetary cap can never exceed 110%."""
    return (Decimal(str(budget)) * Decimal("1.10")).quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def budget_notice(budget: float, total: float | Decimal) -> str | None:
    """Describe an accepted overrun without changing the user's target budget."""
    target, amount = Decimal(str(budget)), Decimal(str(total))
    if amount <= target:
        return None
    excess = amount - target
    return (
        f"Budget alternative: EUR {excess:.2f} ({excess / target:.1%}) above your "
        f"EUR {target:.2f} target. Total estimated cost EUR {amount:.2f} is within "
        f"the permitted 10% flexibility (maximum EUR {maximum_budget(target):.2f}). "
        "This is a more expensive suggestion, not a booking."
    )
