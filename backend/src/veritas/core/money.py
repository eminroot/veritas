"""Manat amounts.

Money is always an int number of qəpik (1 AZN = 100 qəpik). Floats never touch an
amount: text goes through a strict pattern or Decimal, and everything after that is
int arithmetic. The same rule holds in the contracts and in the database.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from decimal import Decimal

QAPIK_PER_AZN = 100

# Ten trillion manat. Far above anything real, and still exact as a JSON number
# (below 2**53) and inside a uint64 on-chain.
MAX_QAPIK = 10**15

# Whole manat either as plain digits or grouped in threes with spaces ("1 250"), then
# an optional decimal part. Grouping must be exact: "12 50" is refused, because
# someone who types it may well mean 12.50 and reading it as 1250 is a 100x error.
_AMOUNT = re.compile(r"(\d{1,3}(?: \d{3})+|\d{1,14})(?:[.,](\d{1,2}))?")
_SPACES = re.compile(r"\s+")


class MoneyError(ValueError):
    """Something that cannot be a valid manat amount."""


def check_qapik(qapik: int) -> int:
    """Return `qapik` if it is a non-negative int in range, raise otherwise."""
    if isinstance(qapik, bool) or not isinstance(qapik, int):
        raise MoneyError(f"qəpik must be an int, got {type(qapik).__name__}")
    if qapik < 0:
        raise MoneyError("amounts cannot be negative")
    if qapik > MAX_QAPIK:
        raise MoneyError("amount is out of range")
    return qapik


def parse_azn(value: str | int | Decimal) -> int:
    """Turn a manat amount into qəpik.

    Accepts "12", "12.5", "12,50", "1 250.00", "12.50 AZN" and "₼12", a whole number
    of manat as an int, or a Decimal. Spaces of any kind (the no-break space phones
    insert included) may only group the manat in threes. Rejects negatives, more
    than two decimals, any other thousands separator, and floats.
    """
    if isinstance(value, bool):
        raise MoneyError("booleans are not amounts")
    if isinstance(value, float):
        raise MoneyError("floats are not accepted for money, pass a str or a Decimal")
    if isinstance(value, int):
        return check_qapik(value * QAPIK_PER_AZN)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise MoneyError(f"not a finite amount: {value}")
        scaled = value * QAPIK_PER_AZN
        if scaled != scaled.to_integral_value():
            raise MoneyError(f"more than two decimals: {value}")
        return check_qapik(int(scaled))
    if isinstance(value, str):
        text = _SPACES.sub(" ", value).strip().upper().removesuffix("AZN").strip()
        text = text.removeprefix("₼").removesuffix("₼").strip()
        match = _AMOUNT.fullmatch(text)
        if not match:
            raise MoneyError(f"not a manat amount: {value!r}")
        whole, fraction = match.group(1).replace(" ", ""), match.group(2) or "0"
        return check_qapik(int(whole) * QAPIK_PER_AZN + int(fraction.ljust(2, "0")))
    raise MoneyError(f"unsupported type for money: {type(value).__name__}")


def format_azn(qapik: int, *, symbol: bool = False) -> str:
    """1250 -> "12.50", or "12.50 ₼" with symbol=True."""
    whole, fraction = divmod(check_qapik(qapik), QAPIK_PER_AZN)
    text = f"{whole}.{fraction:02d}"
    return f"{text} ₼" if symbol else text


def split_pro_rata(total: int, weights: Sequence[int]) -> list[int]:
    """Split `total` qəpik in proportion to `weights`, exactly.

    Largest remainder method: every part gets its floor share, then the qəpik that
    are left go one each to the parts with the biggest remainders, the earlier index
    winning a tie. The parts always add up to `total`, and a part whose weight is
    zero always gets zero.
    """
    check_qapik(total)
    if not weights:
        raise MoneyError("need at least one weight")
    for weight in weights:
        if isinstance(weight, bool) or not isinstance(weight, int) or weight < 0:
            raise MoneyError("weights must be non-negative ints")
    weight_sum = sum(weights)
    if weight_sum == 0:
        raise MoneyError("weights add up to zero")

    parts: list[int] = []
    remainders: list[tuple[int, int]] = []
    for index, weight in enumerate(weights):
        share, remainder = divmod(total * weight, weight_sum)
        parts.append(share)
        remainders.append((remainder, index))

    left = total - sum(parts)
    for _, index in sorted(remainders, key=lambda r: (-r[0], r[1]))[:left]:
        parts[index] += 1
    return parts
