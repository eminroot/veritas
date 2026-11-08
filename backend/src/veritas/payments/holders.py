"""Which account a donor key belongs to.

A holder is the key a donor's phone derives for one project, so no two accounts ever have a
reason to use the same key, in any project. Votes, choices and the recovery of a receipt
after a lost phone all trust that the holder is that donor's, so a key belongs to the first
account that uses it anywhere, and no other account may donate, pledge or redirect money
under it in any project. Holder keys are public on-chain (ReceiptMinted), so without this
anyone could make a small donation under someone else's key, in that project or in the one
a default redirect will move the donor's money to, and then claim the receipt as theirs.
"""

from __future__ import annotations

import uuid

from sqlalchemy import and_, or_, select, union
from sqlalchemy.orm import Session

from veritas.db.models.decisions import Claim
from veritas.db.models.money import Donation, Pledge
from veritas.services.errors import Conflict


def holder_owners(session: Session, holder: str) -> set[uuid.UUID]:
    """Every account that has used `holder`, in any project: its donations, its pledges, and
    redirects under it. More than one means something went wrong."""
    donations = select(Donation.user_id).where(
        Donation.holder == holder, Donation.user_id.is_not(None)
    )
    pledges = select(Pledge.user_id).where(Pledge.holder == holder)
    # A redirect without a new key keeps the donor's key in the other project.
    redirects = select(Claim.user_id).where(
        Claim.target_project_id.is_not(None),
        or_(
            Claim.details["new_holder"].astext == holder,
            and_(~Claim.details.has_key("new_holder"), Claim.holder == holder),
        ),
        Claim.user_id.is_not(None),
    )
    return set(session.scalars(union(donations, pledges, redirects)))


def holder_owner(session: Session, holder: str) -> uuid.UUID | None:
    """The account the holder belongs to, or None if nobody has used it."""
    owners = holder_owners(session, holder)
    if len(owners) > 1:
        raise Conflict(
            "holder_shared",
            "This key was used by more than one account; Veritas support has to sort it out.",
        )
    return next(iter(owners), None)


def check_holder(session: Session, holder: str, user_id: uuid.UUID) -> None:
    """Refuse a holder that already belongs to another account."""
    owner = holder_owner(session, holder)
    if owner is not None and owner != user_id:
        raise Conflict(
            "holder_taken",
            "This key belongs to another account. The app makes a new key for each project; "
            "donate with that one.",
        )
