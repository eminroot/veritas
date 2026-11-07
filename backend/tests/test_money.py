import random
from decimal import Decimal

import pytest

from veritas.core.money import (
    MAX_QAPIK,
    MoneyError,
    check_qapik,
    format_azn,
    parse_azn,
    split_pro_rata,
)


@pytest.mark.parametrize(
    ("text", "qapik"),
    [
        ("12", 1200),
        ("12.5", 1250),
        ("12,50", 1250),
        ("0.01", 1),
        ("0", 0),
        (" 1 250.00 AZN ", 125000),
        ("12.50 azn", 1250),
        ("₼3", 300),
        ("3₼", 300),
        ("1 000", 100000),
    ],
)
def test_parse_text(text, qapik):
    assert parse_azn(text) == qapik


def test_parse_int_and_decimal():
    assert parse_azn(5) == 500
    assert parse_azn(Decimal("12.34")) == 1234
    assert parse_azn(Decimal("7")) == 700


@pytest.mark.parametrize(
    "bad",
    ["12.345", "-1", "abc", "", "1,250.00", "12.", ".5", "1e3", "12 50 50.5.5"],
)
def test_parse_rejects_bad_text(bad):
    with pytest.raises(MoneyError):
        parse_azn(bad)


@pytest.mark.parametrize("bad", [12.5, True, Decimal("NaN"), Decimal("1.234"), -3, None])
def test_parse_rejects_bad_values(bad):
    with pytest.raises(MoneyError):
        parse_azn(bad)


def test_check_qapik_range():
    assert check_qapik(0) == 0
    assert check_qapik(MAX_QAPIK) == MAX_QAPIK
    for bad in (-1, MAX_QAPIK + 1, 1.0, True, "5"):
        with pytest.raises(MoneyError):
            check_qapik(bad)


def test_format():
    assert format_azn(1250) == "12.50"
    assert format_azn(5) == "0.05"
    assert format_azn(0) == "0.00"
    assert format_azn(123456789) == "1234567.89"
    assert format_azn(1250, symbol=True) == "12.50 ₼"


def test_format_and_parse_round_trip():
    for qapik in (0, 1, 99, 100, 101, 999_999, MAX_QAPIK):
        assert parse_azn(format_azn(qapik)) == qapik


def test_split_exact_when_divisible():
    assert split_pro_rata(10_000, [50_000, 30_000, 20_000]) == [5_000, 3_000, 2_000]


def test_split_leftover_goes_to_largest_remainders():
    assert split_pro_rata(101, [1, 1, 1]) == [34, 34, 33]
    assert split_pro_rata(1, [1, 1, 1]) == [1, 0, 0]
    assert split_pro_rata(10, [1, 2]) == [3, 7]


def test_split_zero_weight_gets_nothing():
    assert split_pro_rata(1_000, [0, 3, 0, 1]) == [0, 750, 0, 250]


def test_split_always_adds_up():
    rng = random.Random(7)
    for _ in range(2_000):
        weights = [rng.choice([0, rng.randint(1, 10**9)]) for _ in range(rng.randint(1, 12))]
        if sum(weights) == 0:
            weights[0] = 1
        total = rng.randint(0, 10**12)
        parts = split_pro_rata(total, weights)
        assert sum(parts) == total
        for part, weight in zip(parts, weights, strict=True):
            exact = total * weight / sum(weights)
            assert abs(part - exact) < 1
            if weight == 0:
                assert part == 0


@pytest.mark.parametrize("weights", [[], [0, 0], [1, -1], [1, 2.0], [True]])
def test_split_rejects_bad_weights(weights):
    with pytest.raises(MoneyError):
        split_pro_rata(100, weights)
