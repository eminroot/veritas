import pytest

from veritas.core.canonical import (
    CanonicalJSONError,
    canonical_hash,
    canonical_json,
    parse_canonical,
)
from veritas.core.hashing import sha256


def test_keys_sorted_without_whitespace():
    value = {"b": 1, "a": [3, {"d": 1, "c": 2}]}
    assert canonical_json(value) == b'{"a":[3,{"c":2,"d":1}],"b":1}'


def test_rfc_8785_sample():
    value = {
        "numbers": [333333333.33333329, 1e30, 4.50, 2e-3, 0.000000000000000000000000001],
        "string": '€$\x0f\nA\'B"\\\\"/',
        "literals": [None, True, False],
    }
    expected = (
        r'{"literals":[null,true,false],'
        r'"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27],'
        r'"string":"€$\u000f\nA'
        "'"
        r'B\"\\\\\"/"}'
    )
    assert canonical_json(value) == expected.encode("utf-8")


def test_whole_floats_print_like_ints():
    assert canonical_json([1.0, 49.0, 40.4093, -0.0]) == b"[1,49,40.4093,0]"


def test_keys_sort_by_utf16_code_units():
    # U+1F600 is stored as the surrogate pair D83D DE00, which sorts before U+FB01.
    assert canonical_json({"ﬁ": 1, "\U0001f600": 2}) == '{"😀":2,"ﬁ":1}'.encode()


def test_azerbaijani_text_stays_readable():
    assert canonical_json({"rayon": "Qəbələ"}) == '{"rayon":"Qəbələ"}'.encode()


def test_hash_is_sha256_of_canonical_bytes():
    value = {"z": [1, 2], "a": "x"}
    assert canonical_hash(value) == sha256(b'{"a":"x","z":[1,2]}')


def test_parse_accepts_canonical_bytes():
    data = canonical_json({"b": [True, None], "a": 1})
    assert parse_canonical(data) == {"a": 1, "b": [True, None]}


@pytest.mark.parametrize(
    "data",
    [
        b'{"b":1, "a":2}',
        b'{"b":1,"a":2}',
        b'{"a":1,"a":2}',
        b'{"a":1.50}',
        b"\xff",
        b"not json",
        b'{"a":NaN}',
    ],
)
def test_parse_refuses_anything_else(data):
    with pytest.raises(CanonicalJSONError):
        parse_canonical(data)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 2**60, {1: "a"}, b"bytes"])
def test_values_json_cannot_carry(value):
    with pytest.raises(CanonicalJSONError):
        canonical_json(value)
