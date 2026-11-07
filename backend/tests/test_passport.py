import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from veritas.core.canonical import canonical_json
from veritas.core.hashing import to_hex
from veritas.passport import Passport, PassportError, load_passport

EXAMPLE = Path(__file__).parents[2] / "docs" / "examples" / "passport.example.json"

# Pinned on purpose. The same hash comes out of the JS `canonicalize` package for
# the example file, so if this changes, published Passports would stop verifying.
EXAMPLE_DIGEST = "0xfd7a873d24eb5749dd7359db25725b2bec83ba3747362ffd80db4f9c90c20f57"


@pytest.fixture
def doc():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def build(doc):
    return Passport.model_validate_json(json.dumps(doc))


def test_example_is_valid_and_hash_is_pinned(doc):
    passport = build(doc)
    assert to_hex(passport.digest()) == EXAMPLE_DIGEST
    assert passport.milestone_amounts() == [420_000, 1_383_000, 246_000]
    assert passport.canonical_bytes() == canonical_json(doc)


def test_published_bytes_load_back(doc):
    passport = build(doc)
    assert load_passport(passport.canonical_bytes()) == passport


def test_load_refuses_pretty_printed_bytes():
    with pytest.raises(ValueError):
        load_passport(EXAMPLE.read_bytes())


def test_load_refuses_a_passport_with_fields_left_out(doc):
    del doc["stop"]
    with pytest.raises(PassportError):
        load_passport(canonical_json(doc))


def test_any_change_changes_the_hash(doc):
    before = build(doc).digest()
    doc["milestones"][2]["proof"][0]["min_count"] = 3
    assert build(doc).digest() != before


def test_officer_address_is_checksummed(doc):
    doc["officer"]["address"] = doc["officer"]["address"].lower()
    assert build(doc).officer.address == "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65"


def first(doc):
    return doc["milestones"][0]


BROKEN = {
    "milestones do not add up to the total": lambda d: d.update(total_qapik=2_049_001),
    "budget lines do not add up": lambda d: first(d).update(amount_qapik=420_100),
    "line amount is not quantity times price": lambda d: first(d)["budget"][0].update(quantity=13),
    "amount given as a float": lambda d: first(d)["budget"][1].update(amount_qapik=120000.0),
    "amount given as a string": lambda d: d.update(total_qapik="2049000"),
    "bad charity VOEN": lambda d: d["charity"].update(voen="17000000"),
    "bad officer address": lambda d: d["officer"].update(address="0x1234"),
    "unknown field": lambda d: d.update(extra="surprise"),
    "unknown format": lambda d: d.update(format="veritas.passport/2"),
    "indexes out of order": lambda d: first(d).update(index=1),
    "windows out of order": lambda d: first(d)["window"].update(
        opens="2027-04-02", closes="2027-04-30"
    ),
    "window closes before it opens": lambda d: first(d)["window"].update(closes="2027-02-01"),
    "site with latitude first": lambda d: first(d)["site"].update(
        coordinates=[[[40.79, 48.15], [40.79, 48.152], [40.7915, 48.152], [40.79, 48.15]]]
    ),
    "ring left open": lambda d: first(d)["site"]["coordinates"][0].pop(),
    "site the size of a district": lambda d: first(d)["site"].update(
        coordinates=[[[48.0, 40.6], [48.5, 40.6], [48.5, 40.9], [48.0, 40.9], [48.0, 40.6]]]
    ),
    "no photo in the checklist": lambda d: first(d).update(proof=first(d)["proof"][1:]),
    "vote window too short": lambda d: d["decision"].update(vote_window_hours=2),
    "approval below half": lambda d: d["decision"].update(approval_bps=4_000),
    "empty title": lambda d: d.update(title="   "),
    "currency other than manat": lambda d: d.update(currency="USD"),
    "no milestones": lambda d: d.update(milestones=[], total_qapik=1),
}


@pytest.mark.parametrize("break_it", BROKEN.values(), ids=BROKEN.keys())
def test_inconsistent_passports_are_refused(doc, break_it):
    broken = copy.deepcopy(doc)
    break_it(broken)
    with pytest.raises(ValidationError):
        build(broken)
