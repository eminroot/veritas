"""The demo accounts behind the web app's "Try the demo" buttons, made the first time anyone
asks and reused after that.

A donor: the same account `scripts/seed_demo.py` makes. An organisation: a member of a
charity that Veritas has already verified, with a verified contractor and an active
Verification Officer, so that a project can be planned and published right away. They are
shared by everyone who presses the button, and they exist only where VERITAS_DEMO_LOGIN is on.
"""

from __future__ import annotations

import secrets
from typing import Literal

from eth_utils import to_checksum_address
from sqlalchemy import select
from sqlalchemy.orm import Session

from veritas.core.identifiers import normalize_az_iban, normalize_az_phone, normalize_voen
from veritas.db.models import Charity, CharityMember, Contractor, Officer, User
from veritas.db.models.organisations import (
    CharityStatus,
    ContractorStatus,
    MemberRole,
    OfficerStatus,
    RegistryStatus,
)
from veritas.db.session import db_now
from veritas.services import passwords

DemoKind = Literal["donor", "organisation"]

DONOR_EMAIL = "admin@gmail.com"
DONOR_NAME = "Demo Account"
ORGANISATION_EMAIL = "organisation@demo.veritas.az"
ORGANISATION_NAME = "Demo Organisation"

CHARITY = {
    "legal_name": "First Steps Children's Fund",
    "voen": "1700000045",
    "legal_form": "Foundation",
    "legal_address": "Bakı, Səməd Vurğun küçəsi 34",
    "director_name": "Aysel Quliyeva",
    "contact_email": "hello@firststeps.example.az",
    "contact_phone": "(012) 555 01 02",
    "website": None,
}
CONTRACTOR = {
    "legal_name": "Kəpəz Construction",
    "voen": "1300000052",
    "iban": "AZ21 NABZ 0000 0000 1370 1000 1944",
    "legal_address": "Gəncə, Atatürk prospekti 12",
    "director_name": "Elnur Məmmədov",
}
OFFICER = {
    "name": "Nigar Əliyeva",
    "organisation": "Caspian Audit Partners",
    "address": "0x90f79bf6eb2c4f870365e785982e1f101e93b906",
}


def _user(session: Session, email: str, name: str) -> User:
    user = session.scalars(select(User).where(User.email == email)).first()
    if user is None:
        # Every account needs a way in; this one's is a password nobody knows. The donor's
        # is set to the published one by scripts/seed_demo.py.
        password = passwords.hash_password(secrets.token_urlsafe(24))
        user = User(email=email, display_name=name, password_hash=password)
        session.add(user)
        session.flush()
    return user


def _organisation(session: Session, user: User) -> None:
    """The verified charity, its contractor and the officer its Passports name."""
    now = db_now(session)
    voen = normalize_voen(CHARITY["voen"])
    charity = session.scalars(select(Charity).where(Charity.voen == voen)).first()
    if charity is None:
        charity = Charity(
            legal_name=CHARITY["legal_name"],
            voen=voen,
            legal_form=CHARITY["legal_form"],
            legal_address=CHARITY["legal_address"],
            director_name=CHARITY["director_name"],
            contact_email=CHARITY["contact_email"],
            contact_phone=normalize_az_phone(CHARITY["contact_phone"]),
            website=CHARITY["website"],
            created_by=user.id,
        )
        session.add(charity)
        session.flush()
    # Verified, whatever someone did to it since: the demo always starts from there.
    if charity.status != CharityStatus.VERIFIED:
        charity.status = CharityStatus.VERIFIED
        charity.submitted_at = charity.submitted_at or now
        charity.verified_at = now
        charity.review_notes = "Demo organisation: verified by Veritas for the demo."
    member = session.scalars(
        select(CharityMember).where(
            CharityMember.charity_id == charity.id, CharityMember.user_id == user.id
        )
    ).first()
    if member is None:
        session.add(CharityMember(charity_id=charity.id, user_id=user.id, role=MemberRole.ADMIN))

    contractor_voen = normalize_voen(CONTRACTOR["voen"])
    contractor = session.scalars(
        select(Contractor).where(Contractor.voen == contractor_voen)
    ).first()
    if contractor is None:
        contractor = Contractor(
            legal_name=CONTRACTOR["legal_name"],
            voen=contractor_voen,
            iban=normalize_az_iban(CONTRACTOR["iban"]),
            legal_address=CONTRACTOR["legal_address"],
            director_name=CONTRACTOR["director_name"],
            charity_id=charity.id,
            created_by=user.id,
        )
        session.add(contractor)
    contractor.status = ContractorStatus.VERIFIED
    contractor.verified_at = contractor.verified_at or now
    contractor.registry_status = RegistryStatus.ACTIVE
    contractor.registry_checked_at = contractor.registry_checked_at or now

    address = to_checksum_address(OFFICER["address"])
    officer = session.scalars(select(Officer).where(Officer.address == address)).first()
    if officer is None:
        officer = Officer(
            name=OFFICER["name"],
            organisation=OFFICER["organisation"],
            address=address,
            created_by=user.id,
        )
        session.add(officer)
    officer.status = OfficerStatus.ACTIVE
    session.flush()


def demo_user(session: Session, kind: DemoKind) -> User:
    """The demo account of this kind, made or put back the way the demo needs it."""
    if kind == "donor":
        return _user(session, DONOR_EMAIL, DONOR_NAME)
    user = _user(session, ORGANISATION_EMAIL, ORGANISATION_NAME)
    _organisation(session, user)
    return user
