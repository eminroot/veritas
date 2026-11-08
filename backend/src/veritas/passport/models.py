"""The Project Passport: everything a charity promises before it raises money.

A Passport is published as canonical JSON (RFC 8785), stored on IPFS, and its
SHA-256 is locked on-chain when the project launches. Changing it later takes a
donor vote, so the rules here are strict. A Passport that validates is consistent
with itself: budgets add up, milestones are in order, every site is a real polygon
in Azerbaijan and every decision rule is in range. Whether the VÖENs exist and the
officer is who they claim to be is checked elsewhere, against registries.
"""

from __future__ import annotations

import unicodedata
from datetime import UTC, date, datetime, time, timedelta, timezone
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from eth_utils import is_address, to_checksum_address
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictInt, model_validator

from veritas.chain.leaves import MAX_MILESTONES
from veritas.core.canonical import canonical_json, parse_canonical
from veritas.core.hashing import sha256
from veritas.core.identifiers import normalize_voen
from veritas.core.money import MAX_QAPIK
from veritas.domain.allocation import AllocationRule

PASSPORT_FORMAT = "veritas.passport/1"

# A rough box around Azerbaijan, Nakhchivan included. It catches swapped
# coordinates and typos. It is not a border check.
AZ_LONGITUDE = (44.5, 51.0)
AZ_LATITUDE = (38.0, 42.0)

# A site is a building, a street or a village, not a district. About 25 km.
MAX_SITE_SPAN_DEGREES = 0.25

# Azerbaijan has been on UTC+4 all year since 2016. Dates in a Passport are Baku
# dates: a window opens at 00:00 on its first day and closes at 24:00 on its last.
BAKU = timezone(timedelta(hours=4), "Asia/Baku")


class PassportError(ValueError):
    """Published Passport bytes that do not hold together."""


def _address(value: str) -> str:
    if not is_address(value):
        raise ValueError(f"not an address: {value!r}")
    return to_checksum_address(value)


def _line(value: str) -> str:
    """One line of text, in Unicode NFC.

    The same words typed on two phones can arrive composed or decomposed ("ə" as one
    code point or two). Canonical JSON keeps whatever it is given, so without NFC the
    same visible Passport could have two hashes.
    """
    value = unicodedata.normalize("NFC", value)
    if any(unicodedata.category(char) == "Cc" for char in value):
        raise ValueError("control characters and line breaks are not allowed here")
    return value


def _prose(value: str) -> str:
    """Paragraphs in NFC. Line breaks are fine, other control characters are not."""
    value = unicodedata.normalize("NFC", value).replace("\r\n", "\n")
    if any(unicodedata.category(char) == "Cc" and char != "\n" for char in value):
        raise ValueError("control characters are not allowed, only line breaks")
    return value


Voen = Annotated[str, AfterValidator(normalize_voen)]
Address = Annotated[str, AfterValidator(_address)]
Qapik = Annotated[StrictInt, Field(ge=0, le=MAX_QAPIK)]
PositiveQapik = Annotated[StrictInt, Field(gt=0, le=MAX_QAPIK)]
Name = Annotated[str, Field(min_length=1, max_length=200), AfterValidator(_line)]
Unit = Annotated[str, Field(min_length=1, max_length=32), AfterValidator(_line)]
Prose = Annotated[str, Field(min_length=1, max_length=4000), AfterValidator(_prose)]
Position = tuple[float, float]  # GeoJSON order: longitude, then latitude


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class Category(StrEnum):
    EDUCATION = "education"
    HEALTH = "health"
    WATER = "water"
    HOUSING = "housing"
    ENVIRONMENT = "environment"
    COMMUNITY = "community"
    EMERGENCY = "emergency"
    OTHER = "other"


class ProofKind(StrEnum):
    PHOTO = "photo"
    VIDEO = "video"
    INVOICE = "invoice"
    FISCAL_RECEIPT = "fiscal_receipt"
    DOCUMENT = "document"


class Organisation(_Model):
    legal_name: Name
    voen: Voen


class Officer(_Model):
    """The Verification Officer. `address` is their key, or their organisation's Safe."""

    name: Name
    organisation: Name
    address: Address


class BudgetLine(_Model):
    item: Name
    quantity: Annotated[StrictInt, Field(ge=1, le=10_000_000)]
    unit: Unit
    unit_price_qapik: Qapik
    amount_qapik: Qapik

    @model_validator(mode="after")
    def _amount_is_quantity_times_price(self) -> BudgetLine:
        if self.quantity * self.unit_price_qapik != self.amount_qapik:
            raise ValueError("amount_qapik must be quantity times unit_price_qapik")
        return self


class ProofItem(_Model):
    kind: ProofKind
    description: Name
    min_count: Annotated[StrictInt, Field(ge=1, le=50)] = 1


class TimeWindow(_Model):
    """Baku dates, both days included."""

    opens: date
    closes: date

    @model_validator(mode="after")
    def _in_order(self) -> TimeWindow:
        if self.closes < self.opens:
            raise ValueError("the window closes before it opens")
        return self

    def opens_at(self) -> datetime:
        """00:00 Baku time on the first day, in UTC."""
        return datetime.combine(self.opens, time(), BAKU).astimezone(UTC)

    def closes_at(self) -> datetime:
        """24:00 Baku time on the last day, in UTC. The window is open before this."""
        return datetime.combine(self.closes + timedelta(days=1), time(), BAKU).astimezone(UTC)

    def contains(self, moment: datetime) -> bool:
        if moment.tzinfo is None:
            raise ValueError("compare aware datetimes only")
        return self.opens_at() <= moment < self.closes_at()


def _orientation(a: Position, b: Position, c: Position) -> int:
    cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return (cross > 0) - (cross < 0)


def _on_segment(a: Position, b: Position, p: Position) -> bool:
    """For a point known to be on the line through a and b: is it between them?"""
    within_x = min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
    within_y = min(a[1], b[1]) <= p[1] <= max(a[1], b[1])
    return within_x and within_y


def _segments_touch(a: Position, b: Position, c: Position, d: Position) -> bool:
    o1, o2 = _orientation(a, b, c), _orientation(a, b, d)
    o3, o4 = _orientation(c, d, a), _orientation(c, d, b)
    if o1 != o2 and o3 != o4:
        return True
    return (
        (o1 == 0 and _on_segment(a, b, c))
        or (o2 == 0 and _on_segment(a, b, d))
        or (o3 == 0 and _on_segment(c, d, a))
        or (o4 == 0 and _on_segment(c, d, b))
    )


def _crosses_itself(ring: list[Position]) -> bool:
    """True if two edges that are not neighbours touch. Rings have at most 500 points."""
    edges = list(zip(ring, ring[1:], strict=False))
    count = len(edges)
    for i in range(count):
        for j in range(i + 2, count):
            if i == 0 and j == count - 1:
                continue  # the first and last edge meet where the ring closes
            if _segments_touch(*edges[i], *edges[j]):
                return True
    return False


def _inside_ring(point: Position, ring: list[Position]) -> bool:
    """Even-odd rule: is the point strictly inside the ring?"""
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


class Site(_Model):
    """A GeoJSON Polygon. The first ring is the outline, any others are holes."""

    type: Literal["Polygon"]
    coordinates: Annotated[
        list[Annotated[list[Position], Field(min_length=4, max_length=500)]],
        Field(min_length=1, max_length=10),
    ]

    @model_validator(mode="after")
    def _real_site(self) -> Site:
        for ring in self.coordinates:
            if ring[0] != ring[-1]:
                raise ValueError("every ring must end where it starts")
            for lon, lat in ring:
                inside = (
                    AZ_LONGITUDE[0] <= lon <= AZ_LONGITUDE[1]
                    and AZ_LATITUDE[0] <= lat <= AZ_LATITUDE[1]
                )
                if not inside:
                    raise ValueError(
                        f"({lon}, {lat}) is outside Azerbaijan, coordinates go longitude first"
                    )
            if len(set(ring[:-1])) < 3:
                raise ValueError("every ring needs at least three distinct corners")
            if _crosses_itself(ring):
                raise ValueError("a ring crosses itself, draw the outline without crossings")
        outline = self.coordinates[0]
        lons = [lon for lon, _ in outline]
        lats = [lat for _, lat in outline]
        if max(max(lons) - min(lons), max(lats) - min(lats)) > MAX_SITE_SPAN_DEGREES:
            raise ValueError("the site is too big to check, outline the actual work site")
        for hole in self.coordinates[1:]:
            if not all(_inside_ring(point, outline) for point in hole[:-1]):
                raise ValueError("a hole must lie inside the outline")
        return self


MAX_PROOF_FILES = 100
"""The most files one capture session takes (veritas.evidence.manifest.MAX_ITEMS): a
checklist must fit in one bundle, since check 11 looks at one bundle."""


class Milestone(_Model):
    index: Annotated[StrictInt, Field(ge=0, lt=MAX_MILESTONES)]
    title: Name
    deliverable: Prose
    """What will exist when the milestone is done. Photos are checked against it."""
    method: Prose
    """How the work will be done."""
    amount_qapik: PositiveQapik
    budget: Annotated[list[BudgetLine], Field(min_length=1, max_length=100)]
    proof: Annotated[list[ProofItem], Field(min_length=1, max_length=20)]
    window: TimeWindow
    site: Site

    @model_validator(mode="after")
    def _consistent(self) -> Milestone:
        if sum(line.amount_qapik for line in self.budget) != self.amount_qapik:
            raise ValueError("budget lines must add up to the milestone amount")
        if not any(item.kind is ProofKind.PHOTO for item in self.proof):
            raise ValueError("every milestone needs a photo, the challenge code is read from it")
        files = sum(item.min_count for item in self.proof)
        if files > MAX_PROOF_FILES:
            raise ValueError(
                f"the proof checklist asks for {files} files; one capture session holds at "
                f"most {MAX_PROOF_FILES}, so no evidence could ever meet it"
            )
        return self


class DecisionRules(_Model):
    vote_window_hours: Annotated[StrictInt, Field(ge=24, le=336)] = 72
    min_turnout_bps: Annotated[StrictInt, Field(ge=0, le=10_000)] = 1_000
    approval_bps: Annotated[StrictInt, Field(ge=5_000, lt=10_000)] = 5_000
    """A vote passes when the share of yes votes is above this. 5000 is more than half."""
    min_vote_qapik: Annotated[StrictInt, Field(ge=100, le=MAX_QAPIK)] = 500
    turnout_extension_hours: Annotated[StrictInt, Field(ge=0, le=168)] = 48
    low_turnout_fallback: Literal["officer_decision", "reject"] = "officer_decision"


class StopRules(_Model):
    evidence_grace_days: Annotated[StrictInt, Field(ge=0, le=90)] = 14
    choice_window_days: Annotated[StrictInt, Field(ge=7, le=90)] = 30
    unclaimed: Literal["refund", "redirect_same_category"] = "refund"


class PayOnProofRules(_Model):
    funds: Literal["next_milestone", "approved_milestone"] = "next_milestone"


class Passport(_Model):
    format: Literal["veritas.passport/1"] = PASSPORT_FORMAT
    project_id: UUID
    version: Annotated[StrictInt, Field(ge=1)]
    title: Name
    summary: Prose
    category: Category
    charity: Organisation
    contractor: Organisation
    officer: Officer
    currency: Literal["AZN"] = "AZN"
    total_qapik: PositiveQapik
    allocation: AllocationRule = AllocationRule.PRO_RATA
    milestones: Annotated[list[Milestone], Field(min_length=1, max_length=MAX_MILESTONES)]
    decision: DecisionRules = Field(default_factory=DecisionRules)
    stop: StopRules = Field(default_factory=StopRules)
    pay_on_proof: PayOnProofRules = Field(default_factory=PayOnProofRules)

    @model_validator(mode="after")
    def _consistent(self) -> Passport:
        for position, milestone in enumerate(self.milestones):
            if milestone.index != position:
                raise ValueError(
                    f"milestone {position} has index {milestone.index}, indexes run 0, 1, 2"
                )
        if sum(m.amount_qapik for m in self.milestones) != self.total_qapik:
            raise ValueError("milestone amounts must add up to total_qapik")
        opens = [m.window.opens for m in self.milestones]
        if opens != sorted(opens):
            raise ValueError("milestone windows must open in order")
        return self

    def milestone_amounts(self) -> list[int]:
        return [m.amount_qapik for m in self.milestones]

    def evidence_deadline(self, index: int) -> datetime:
        """When a milestone that still has no evidence lets anyone stop the project.

        The end of the milestone's window plus the grace period in the stop rules.
        """
        window = self.milestones[index].window
        return window.closes_at() + timedelta(days=self.stop.evidence_grace_days)

    def canonical_bytes(self) -> bytes:
        """The exact bytes to publish and hash."""
        return canonical_json(self.model_dump(mode="json"))

    def digest(self) -> bytes:
        """SHA-256 of the canonical bytes. This is the hash that goes on-chain."""
        return sha256(self.canonical_bytes())


def load_passport(data: bytes) -> Passport:
    """Read published Passport bytes and check they are exactly what the model publishes.

    Refuses bytes that are not canonical, that fail validation, or that leave out a
    field. A missing field would be filled with its default and change the hash.
    """
    passport = Passport.model_validate(parse_canonical(data))
    if passport.canonical_bytes() != data:
        raise PassportError("the bytes are not a complete Passport, some fields are missing")
    return passport
