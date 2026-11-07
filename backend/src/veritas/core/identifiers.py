"""Identifiers we accept from charities, contractors and donors.

These checks only cover the shape of a value. Whether a VÖEN exists and is active,
or whether an account belongs to the contractor, is a lookup with the State Tax
Service or the bank and happens elsewhere.
"""

from __future__ import annotations

import re


class IdentifierError(ValueError):
    """A value that is not a valid identifier of its kind."""


_VOEN = re.compile(r"\d{10}")
_AZ_IBAN = re.compile(r"AZ\d{2}[A-Z]{4}[A-Z0-9]{20}")
_PHONE_JUNK = re.compile(r"[\s()\-]")
_LOCAL_NUMBER = re.compile(r"[1-9]\d{8}")


def normalize_voen(value: str) -> str:
    """A VÖEN (taxpayer number) is ten digits. Spaces are dropped."""
    text = re.sub(r"\s+", "", str(value))
    if not _VOEN.fullmatch(text):
        raise IdentifierError(f"a VÖEN is 10 digits: {value!r}")
    return text


def normalize_az_iban(value: str) -> str:
    """An Azerbaijani IBAN: AZ, two check digits, a 4 letter bank code, 20 characters.

    Spaces are dropped, letters are upper-cased and the check digits are verified
    with the usual ISO 13616 mod 97 rule.
    """
    text = re.sub(r"\s+", "", str(value)).upper()
    if not _AZ_IBAN.fullmatch(text):
        raise IdentifierError(f"not an Azerbaijani IBAN: {value!r}")
    rearranged = text[4:] + text[:4]
    if int("".join(str(int(char, 36)) for char in rearranged)) % 97 != 1:
        raise IdentifierError(f"IBAN check digits do not match: {value!r}")
    return text


def normalize_az_phone(value: str) -> str:
    """Return a phone number as +994 and nine digits.

    Accepts the ways people actually type them: "+994 50 123 45 67",
    "050-123-45-67", "994501234567", "00994501234567", "(012) 345 67 89".
    """
    text = _PHONE_JUNK.sub("", str(value))
    if text.startswith("+994"):
        rest = text[4:]
    elif text.startswith("00994"):
        rest = text[5:]
    elif text.startswith("994") and len(text) == 12:
        rest = text[3:]
    elif text.startswith("0") and len(text) == 10:
        rest = text[1:]
    else:
        raise IdentifierError(f"not an Azerbaijani phone number: {value!r}")
    if not _LOCAL_NUMBER.fullmatch(rest):
        raise IdentifierError(f"not an Azerbaijani phone number: {value!r}")
    return "+994" + rest
