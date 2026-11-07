"""The Project Passport: everything a charity promises before it raises money.

A Passport is published as canonical JSON (RFC 8785), stored on IPFS, and its
SHA-256 is locked on-chain when the project launches. Changing it later takes a
donor vote, so the rules here are strict. A Passport that validates is consistent
with itself: budgets add up, milestones are in order, every site is a real polygon
in Azerbaijan and every decision rule is in range. Whether the VÖENs exist and the
officer is who they claim to be is checked elsewhere, against registries.
"""

from __future__ import annotations

from datetime import date
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


class PassportError(ValueError):
    """Published Passport bytes that do not hold together."""


def _address(value: str) -> str:
    if not is_address(value):
        raise ValueError(f"not an address: {value!r}")
    return to_checksum_address(value)


Voen = Annotated[str, AfterValidator(normalize_voen)]
Address = Annotated[str, AfterValidator(_address)]
Qapik = Annotated[StrictInt, Field(ge=0, le=MAX_QAPIK)]
PositiveQapik = Annotated[StrictInt, Field(gt=0, le=MAX_QAPIK)]
Name = Annotated[str, Field(min_length=1, max_length=200)]
Prose = Annotated[str, Field(min_length=1, max_length=4000)]
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
    unit: Annotated[str, Field(min_length=1, max_length=32)]
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
    opens: date
    closes: date

    @model_validator(mode="after")
    def _in_order(self) -> TimeWindow:
        if self.closes < self.opens:
            raise ValueError("the window closes before it opens")
        return self


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
        outline = self.coordinates[0]
        if len(set(outline[:-1])) < 3:
            raise ValueError("an outline needs at least three distinct corners")
        lons = [lon for lon, _ in outline]
        lats = [lat for _, lat in outline]
        if max(max(lons) - min(lons), max(lats) - min(lats)) > MAX_SITE_SPAN_DEGREES:
            raise ValueError("the site is too big to check, outline the actual work site")
        return self


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
