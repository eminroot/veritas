import pytest

from veritas.core.identifiers import (
    IdentifierError,
    normalize_az_iban,
    normalize_az_phone,
    normalize_voen,
)

# The Azerbaijan example from the SWIFT IBAN registry.
REGISTRY_IBAN = "AZ21NABZ00000000137010001944"


def test_voen():
    assert normalize_voen("1234567890") == "1234567890"
    assert normalize_voen(" 123 456 7890 ") == "1234567890"


@pytest.mark.parametrize("bad", ["12345", "12345678901", "abcdefghij", "12345-67890", ""])
def test_bad_voen(bad):
    with pytest.raises(IdentifierError):
        normalize_voen(bad)


def test_iban():
    assert normalize_az_iban(REGISTRY_IBAN) == REGISTRY_IBAN
    assert normalize_az_iban("az21 nabz 0000 0000 1370 1000 1944") == REGISTRY_IBAN


@pytest.mark.parametrize(
    "bad",
    [
        "AZ22NABZ00000000137010001944",
        "AZ21NABZ00000000137010001945",
        "TR330006100519786457841326",
        "AZ21NABZ0000000013701000194",
        "AZ21NAB100000000137010001944",
        "",
    ],
)
def test_bad_iban(bad):
    with pytest.raises(IdentifierError):
        normalize_az_iban(bad)


@pytest.mark.parametrize(
    "typed",
    [
        "+994 50 123 45 67",
        "050-123-45-67",
        "050.123.45.67",
        "994501234567",
        "00994501234567",
        "+994(50)1234567",
    ],
)
def test_phone_formats(typed):
    assert normalize_az_phone(typed) == "+994501234567"


def test_landline():
    assert normalize_az_phone("(012) 345 67 89") == "+994123456789"


@pytest.mark.parametrize(
    "bad",
    ["+99450123456", "+9945012345678", "+7 999 123 45 67", "501234567", "+994 05 123 45 67", ""],
)
def test_bad_phone(bad):
    with pytest.raises(IdentifierError):
        normalize_az_phone(bad)
