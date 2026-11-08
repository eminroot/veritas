"""Passport problems in readable form. No database needed."""

import copy
import json
from pathlib import Path

import pytest

from veritas.passport.errors import check_passport, format_path
from veritas.passport.models import Passport

EXAMPLE = Path(__file__).resolve().parents[3] / "docs" / "examples" / "passport.example.json"


@pytest.fixture
def example():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("loc", "path"),
    [
        ((), ""),
        (("title",), "title"),
        (("milestones", 0, "budget", 1, "amount_qapik"), "milestones[0].budget[1].amount_qapik"),
        (
            ("milestones", 2, "site", "coordinates", 0, 3, 1),
            "milestones[2].site.coordinates[0][3][1]",
        ),
        (("body", "phone"), "body.phone"),
    ],
)
def test_paths_read_like_json(loc, path):
    assert format_path(loc) == path


def test_the_example_has_no_problems(example):
    passport, problems = check_passport(example)
    assert problems == []
    assert isinstance(passport, Passport)


def test_every_problem_is_listed_once_in_document_order(example):
    broken = copy.deepcopy(example)
    del broken["summary"]
    broken["milestones"][0]["budget"][0]["quantity"] = "12"
    broken["milestones"][2]["proof"][0]["min_count"] = 0
    broken["officer"]["address"] = "0x1234"
    passport, problems = check_passport(broken)
    assert passport is None
    assert problems == [
        {"path": "summary", "message": "is required"},
        {"path": "officer.address", "message": "not an address: '0x1234'"},
        {"path": "milestones[0].budget[0].quantity", "message": "must be a whole number"},
        {"path": "milestones[2].proof[0].min_count", "message": "must be at least 1"},
    ]


def test_a_draft_that_is_not_an_object(example):
    passport, problems = check_passport(["not", "a", "passport"])
    assert passport is None
    assert problems == [{"path": "", "message": "must be an object"}]


def test_ring_too_short(example):
    example["milestones"][1]["site"]["coordinates"] = [[[48.15, 40.79], [48.152, 40.79]]]
    _, problems = check_passport(example)
    assert problems == [
        {
            "path": "milestones[1].site.coordinates[0]",
            "message": "needs at least 4 positions, the last one the same as the first",
        }
    ]


def test_null_is_reported_as_missing(example):
    example["title"] = None
    example["charity"] = None
    _, problems = check_passport(example)
    assert problems == [
        {"path": "title", "message": "is required"},
        {"path": "charity", "message": "is required"},
    ]
