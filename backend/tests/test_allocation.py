import random

import pytest

from veritas.core.money import MoneyError
from veritas.domain.allocation import AllocationRule, OverfundingError, allocate


def test_pro_rata_follows_what_is_still_needed():
    assert allocate(10_000, [50_000, 30_000, 20_000], "pro_rata") == [5_000, 3_000, 2_000]


def test_pro_rata_skips_funded_milestones():
    assert allocate(9_000, [0, 30_000, 60_000], AllocationRule.PRO_RATA) == [0, 3_000, 6_000]


def test_pro_rata_spreads_odd_qapik():
    assert allocate(101, [1_000, 1_000, 1_000], "pro_rata") == [34, 34, 33]


def test_sequential_fills_in_order():
    assert allocate(70_000, [50_000, 30_000, 20_000], "sequential") == [50_000, 20_000, 0]
    assert allocate(5_000, [0, 30_000, 20_000], "sequential") == [0, 5_000, 0]


def test_exact_remaining_amount_is_accepted():
    assert allocate(100_000, [50_000, 30_000, 20_000], "pro_rata") == [50_000, 30_000, 20_000]
    assert allocate(100_000, [50_000, 30_000, 20_000], "sequential") == [50_000, 30_000, 20_000]


@pytest.mark.parametrize("rule", list(AllocationRule))
def test_overfunding_is_refused(rule):
    with pytest.raises(OverfundingError):
        allocate(100_001, [50_000, 30_000, 20_000], rule)
    with pytest.raises(OverfundingError):
        allocate(1, [0, 0], rule)


@pytest.mark.parametrize(
    ("amount", "remaining", "rule"),
    [(0, [100], "pro_rata"), (100, [], "pro_rata"), (100, [-5, 200], "sequential")],
)
def test_bad_input(amount, remaining, rule):
    with pytest.raises(MoneyError):
        allocate(amount, remaining, rule)


def test_unknown_rule():
    with pytest.raises(ValueError):
        allocate(100, [100], "biggest_first")


@pytest.mark.parametrize("rule", list(AllocationRule))
def test_parts_add_up_and_never_exceed_need(rule):
    rng = random.Random(11)
    for _ in range(2_000):
        remaining = [rng.choice([0, rng.randint(1, 10**8)]) for _ in range(rng.randint(1, 10))]
        if sum(remaining) == 0:
            remaining[-1] = 1
        amount = rng.randint(1, sum(remaining))
        parts = allocate(amount, remaining, rule)
        assert sum(parts) == amount
        assert all(0 <= part <= need for part, need in zip(parts, remaining, strict=True))
