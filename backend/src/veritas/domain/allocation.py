"""How one donation is split across a project's milestones.

The Passport picks the rule. Each non-zero part becomes its own Merkle leaf, so the
split has to be exact and repeatable: the same inputs always give the same parts.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from veritas.core.money import MoneyError, check_qapik, split_pro_rata


class AllocationRule(StrEnum):
    PRO_RATA = "pro_rata"
    """In proportion to what each milestone still needs."""

    SEQUENTIAL = "sequential"
    """Fill the earliest milestone that still needs money first."""


class OverfundingError(MoneyError):
    """The donation is bigger than what the project still needs."""


def allocate(amount: int, remaining: Sequence[int], rule: AllocationRule | str) -> list[int]:
    """Split `amount` qəpik over milestones that still need `remaining` qəpik each.

    No milestone ever gets more than it still needs, so an amount above the total
    still needed is refused rather than silently capped.
    """
    rule = AllocationRule(rule)
    check_qapik(amount)
    if not remaining:
        raise MoneyError("a project has at least one milestone")
    for need in remaining:
        check_qapik(need)
    if amount == 0:
        raise MoneyError("nothing to allocate")
    needed = sum(remaining)
    if amount > needed:
        raise OverfundingError(f"{amount} qəpik is more than the {needed} qəpik still needed")

    if rule is AllocationRule.PRO_RATA:
        return split_pro_rata(amount, remaining)

    parts: list[int] = []
    left = amount
    for need in remaining:
        take = min(need, left)
        parts.append(take)
        left -= take
    return parts
