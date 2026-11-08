"""What the database guarantees on its own, whatever the application gets wrong."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, text, update
from sqlalchemy.exc import IntegrityError

from veritas.core.hashing import sha256
from veritas.db.models import BudgetLine, Charity, Milestone, PassportVersion, Project, User

BYTES = b'{"format":"veritas.passport/1"}'
NOW = datetime(2026, 11, 8, tzinfo=UTC)


@pytest.fixture
def project(db):
    user = User(phone="+994501234567")
    db.add(user)
    db.flush()
    charity = Charity(
        legal_name="Test charity",
        voen="1700000011",
        legal_form="Public union",
        legal_address="Bakı",
        director_name="Director",
        contact_email="a@b.az",
        contact_phone="+994123456789",
        created_by=user.id,
    )
    db.add(charity)
    db.flush()
    project = Project(charity_id=charity.id, created_by=user.id)
    db.add(project)
    db.commit()
    return project


def published(project, **changes):
    fields = {
        "project_id": project.id,
        "version": 1,
        "status": "published",
        "canonical_bytes": BYTES,
        "sha256": sha256(BYTES),
        "cid": "bafkreiexample",
        "published_at": NOW,
        "created_by": project.created_by,
    }
    return PassportVersion(**{**fields, **changes})


def refused(db, reason, statement=None):
    """The pending change, or `statement`, is refused with `reason` in the error."""
    with pytest.raises(IntegrityError, match=reason):
        if statement is not None:
            db.execute(statement)
        db.flush()
    db.rollback()


def test_money_is_bigint_everywhere(db):
    types = db.execute(
        text(
            "SELECT DISTINCT data_type FROM information_schema.columns"
            " WHERE table_schema = 'public' AND column_name LIKE '%qapik'"
        )
    ).scalars()
    assert set(types) == {"bigint"}


def test_statuses_are_text_not_enum_types(db):
    enums = "SELECT count(*) FROM pg_type WHERE typtype = 'e'"
    assert db.scalar(text(enums)) == 0


def test_published_bytes_must_hash_to_the_stored_sha256(db, project):
    db.add(published(project, sha256=sha256(BYTES + b" ")))
    refused(db, "ck_passports_sha256_matches_bytes")


def test_a_published_version_needs_its_bytes_and_cid(db, project):
    db.add(published(project, cid=None))
    refused(db, "ck_passports_draft_or_published")


def test_a_published_version_never_changes_and_is_never_deleted(db, project):
    row = published(project)
    db.add(row)
    db.commit()

    other = b'{"format":"veritas.passport/1","x":1}'
    change = (
        update(PassportVersion)
        .where(PassportVersion.id == row.id)
        .values(canonical_bytes=other, sha256=sha256(other))
    )
    refused(db, "cannot be changed", change)
    refused(db, "cannot be deleted", delete(PassportVersion).where(PassportVersion.id == row.id))

    # Its status may still move on, and the charity signature can be added later.
    db.execute(
        update(PassportVersion)
        .where(PassportVersion.id == row.id)
        .values(status="superseded", charity_signature=bytes(65))
    )
    db.commit()


def test_one_draft_per_project(db, project):
    for version in (1, 2):
        db.add(
            PassportVersion(
                project_id=project.id,
                version=version,
                draft_json={},
                created_by=project.created_by,
            )
        )
    refused(db, "uq_passports_one_draft")


def test_budget_line_amount_is_quantity_times_unit_price(db, project):
    milestone = Milestone(
        project_id=project.id,
        index=0,
        title="Roof",
        amount_qapik=1000,
        window_opens=NOW.date(),
        window_closes=NOW.date(),
        opens_at=NOW,
        closes_at=NOW.replace(day=9),
        evidence_deadline=NOW.replace(day=20),
        passport_version=1,
    )
    db.add(milestone)
    db.flush()
    db.add(
        BudgetLine(
            milestone_id=milestone.id,
            position=0,
            item="Sheets",
            quantity=3,
            unit="m2",
            unit_price_qapik=300,
            amount_qapik=1000,
        )
    )
    refused(db, "ck_budget_lines_amount_is_quantity_times_price")


def test_phone_numbers_are_stored_normalised(db):
    db.add(User(phone="050 123 45 67"))
    refused(db, "ck_users_phone_format")
