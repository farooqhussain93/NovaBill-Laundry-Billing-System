from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def to_money(value: Any) -> float:
    try:
        return float(Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except Exception:
        return 0.0


def to_whole_number(value: Any, default: int = 0) -> int:
    try:
        amount = Decimal(str(value if value not in [None, ""] else default))
        return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except Exception:
        return int(default)


def money_text(value: Any, currency: str = "PKR") -> str:
    # NovaBill uses whole PKR totals for counter-friendly billing.
    amount = to_whole_number(value, 0)
    return f"{currency} {amount:,}"
