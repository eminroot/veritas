"""Passport problems in words a charity employee can act on.

Pydantic says what is wrong in its own terms: "Input should be a valid integer"
at ('milestones', 0, 'budget', 1, 'amount_qapik'). This module turns each error
into a JSON-style path, "milestones[0].budget[1].amount_qapik", and a short
message: "must be a whole number of qəpik". Rules that check a whole object
(budget lines adding up, milestone indexes in order) are reported on the field
the person has to change, with the number it should be when we can work it out.

The same wording serves API request errors, so `describe` and `format_path` are
used by the API's error handler too.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from datetime import date
from typing import Any, TypedDict

from pydantic import ValidationError
from pydantic_core import ErrorDetails

from veritas.passport.models import Passport


class Problem(TypedDict):
    path: str
    message: str


def check_passport(data: Any) -> tuple[Passport | None, list[Problem]]:
    """Validate a draft. Returns the Passport and no problems, or None and the problems."""
    try:
        return Passport.model_validate(data), []
    except ValidationError as exc:
        return None, readable_problems(exc)


def readable_problems(exc: ValidationError) -> list[Problem]:
    problems: list[Problem] = []
    for error in exc.errors(include_url=False):
        problem = _object_rule(error) or _position_rule(error)
        if problem is None:
            problem = Problem(path=format_path(error["loc"]), message=describe(error))
        if problem not in problems:
            problems.append(problem)
    return problems


def format_path(loc: Sequence[str | int]) -> str:
    """('milestones', 0, 'budget', 1, 'amount_qapik') -> 'milestones[0].budget[1].amount_qapik'."""
    path = ""
    for part in loc:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}" if path else str(part)
    return path


def describe(error: ErrorDetails) -> str:
    """One short message for one error, written to follow the field's path."""
    kind = error["type"]
    ctx = error.get("ctx") or {}
    field = next((part for part in reversed(error["loc"]) if isinstance(part, str)), "")
    money = field.endswith("_qapik")

    if kind == "missing":
        return "is required"
    if kind == "extra_forbidden":
        return "is not a known field, remove it"
    if kind.endswith("_type") and error.get("input") is None:
        return "is required"
    if kind in ("int_type", "int_parsing", "int_from_float"):
        return "must be a whole number of qəpik" if money else "must be a whole number"
    if kind in ("float_type", "float_parsing", "finite_number"):
        return "must be a number"
    if kind == "string_type":
        return "must be text"
    if kind in ("bool_type", "bool_parsing"):
        return "must be true or false"
    if kind == "string_too_short":
        minimum = ctx.get("min_length", 1)
        return "must not be empty" if minimum == 1 else f"must be at least {minimum} characters"
    if kind == "string_too_long":
        return f"must be at most {ctx.get('max_length')} characters"
    if kind == "string_pattern_mismatch":
        return "is not in the expected format"
    if kind == "too_short":
        return f"needs at least {_items(ctx.get('min_length', 1))}"
    if kind == "too_long":
        return f"can have at most {_items(ctx.get('max_length', 0))}"
    if kind in ("list_type", "tuple_type", "set_type", "iterable_type"):
        return "must be a list"
    if kind in ("model_type", "dict_type", "model_attributes_type"):
        return "must be an object"
    if kind in ("literal_error", "enum"):
        return _one_of(str(ctx.get("expected", "")))
    if kind in ("uuid_type", "uuid_parsing", "uuid_version"):
        return "must be a UUID, like 6f1c2a9e-3b7d-4e2a-9c41-8d5b2f0e7a13"
    if kind.startswith("date"):
        return "must be a date written as YYYY-MM-DD"
    if kind == "greater_than_equal" and ctx.get("ge") == 0:
        return "cannot be negative"
    if kind in _BOUNDS:
        word, key = _BOUNDS[kind]
        return f"must be {word} {ctx.get(key)}" + (" qəpik" if money else "")
    if kind == "json_invalid":
        return "is not valid JSON"
    if kind == "value_error" and "error" in ctx:
        return str(ctx["error"])
    return error["msg"]


_BOUNDS = {
    "greater_than_equal": ("at least", "ge"),
    "greater_than": ("more than", "gt"),
    "less_than_equal": ("at most", "le"),
    "less_than": ("less than", "lt"),
}


def _items(count: object) -> str:
    return f"{count} item" if count == 1 else f"{count} items"


def _one_of(expected: str) -> str:
    choices = re.findall(r"'([^']*)'", expected)
    if len(choices) == 1:
        return f'must be "{choices[0]}"'
    if choices:
        return "must be one of " + ", ".join(f'"{choice}"' for choice in choices)
    return f"must be {expected}"


def _object_rule(error: ErrorDetails) -> Problem | None:
    """Move a whole-object rule onto the field that has to change."""
    if error["type"] != "value_error":
        return None
    message = str((error.get("ctx") or {}).get("error", ""))
    loc = tuple(error["loc"])
    data = error.get("input")
    for pattern, rule in _OBJECT_RULES:
        match = re.match(pattern, message)
        if match:
            path, text = rule(match, data)
            return Problem(path=format_path(loc + path), message=text)
    if loc and loc[-1] == "site":
        return Problem(path=format_path((*loc, "coordinates")), message=message)
    return None


def _position_rule(error: ErrorDetails) -> Problem | None:
    """A GeoJSON ring that is too short, or a position with the wrong number of numbers."""
    loc = tuple(error["loc"])
    if "coordinates" not in loc or not isinstance(loc[-1], int):
        return None
    is_tuple = (error.get("ctx") or {}).get("field_type") == "Tuple"
    if error["type"] in ("too_long", "too_short") and is_tuple:
        return Problem(path=format_path(loc), message="must be [longitude, latitude]")
    if error["type"] == "too_short" and loc[-2] == "coordinates":
        message = "needs at least 4 positions, the last one the same as the first"
        return Problem(path=format_path(loc), message=message)
    if error["type"] == "missing" and len(loc) >= 2 and isinstance(loc[-2], int):
        return Problem(path=format_path(loc[:-1]), message="must be [longitude, latitude]")
    return None


def _total(items: Any, key: str = "amount_qapik") -> int | None:
    try:
        return sum(int(item[key]) for item in items)
    except (TypeError, KeyError, ValueError):
        return None


def _which(text: str, number: int | None) -> str:
    return text if number is None else f"{text}, which is {number}"


def _line_amount(match: re.Match[str], line: Any) -> tuple[tuple[str | int, ...], str]:
    try:
        expected: int | None = int(line["quantity"]) * int(line["unit_price_qapik"])
    except (TypeError, KeyError, ValueError):
        expected = None
    return ("amount_qapik",), _which("must be quantity times unit price", expected)


def _milestone_amount(match: re.Match[str], milestone: Any) -> tuple[tuple[str | int, ...], str]:
    budget = milestone.get("budget") if isinstance(milestone, dict) else None
    text = "must equal the sum of the budget lines"
    return ("amount_qapik",), _which(text, _total(budget))


def _total_amount(match: re.Match[str], passport: Any) -> tuple[tuple[str | int, ...], str]:
    milestones = passport.get("milestones") if isinstance(passport, dict) else None
    text = "must equal the sum of the milestone amounts"
    return ("total_qapik",), _which(text, _total(milestones))


def _index(match: re.Match[str], passport: Any) -> tuple[tuple[str | int, ...], str]:
    position = int(match.group(1))
    return ("milestones", position, "index"), f"must be {position}, indexes run 0, 1, 2 in order"


def _windows(match: re.Match[str], passport: Any) -> tuple[tuple[str | int, ...], str]:
    try:
        opens = [_date(m["window"]["opens"]) for m in passport["milestones"]]
    except (TypeError, KeyError, ValueError):
        opens = []
    for position in range(1, len(opens)):
        if opens[position] < opens[position - 1]:
            path = ("milestones", position, "window", "opens")
            return (
                path,
                f"must not be before milestone {position - 1} opens on {opens[position - 1]}",
            )
    return ("milestones",), "milestone windows must open in order"


def _date(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


_Rule = Callable[[re.Match[str], Any], tuple[tuple[str | int, ...], str]]

_OBJECT_RULES: list[tuple[str, _Rule]] = [
    (r"amount_qapik must be quantity times unit_price_qapik", _line_amount),
    (r"budget lines must add up", _milestone_amount),
    (r"milestone amounts must add up", _total_amount),
    (r"milestone (\d+) has index", _index),
    (r"milestone windows must open in order", _windows),
    (
        r"every milestone needs a photo",
        lambda m, d: (("proof",), "needs at least one photo, the challenge code is read from it"),
    ),
    (
        r"the window closes before it opens",
        lambda m, d: (("closes",), "must not be before the day the window opens"),
    ),
]
