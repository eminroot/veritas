"""Capture sessions: the challenge code, the geofence and checklist, and when they are refused."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from eth_account import Account
from sqlalchemy import select, update

from veritas.db.models import Device, Milestone, Project, ProjectStatus
from veritas.db.models.evidence import CaptureSession
from veritas.evidence.capture import CODE_ALPHABET, new_code

from .conftest import EXAMPLE_ID
from .kit import register_device, start


def error(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()["error"]
    assert body["code"] == code, body
    return body


def test_a_session_gives_a_code_the_site_and_the_checklist(
    client, clock, project, field_worker, phone
):
    response = start(client, field_worker, project.id, phone)
    assert response.status_code == 201, response.text
    session = response.json()

    assert re.fullmatch(r"[A-HJ-NP-Z2-9]{6}", session["challenge_code"])
    issued = datetime.fromisoformat(session["issued_at"])
    assert issued == clock.now
    assert datetime.fromisoformat(session["expires_at"]) - issued == timedelta(minutes=15)
    assert datetime.fromisoformat(session["upload_until"]) - issued == timedelta(minutes=75)
    assert session["status"] == "open"
    assert session["attempt"] == 1
    assert session["device_address"] == phone.address
    assert session["window_opens_at"] == "2027-02-28T20:00:00Z"
    assert session["window_closes_at"] == "2027-03-31T20:00:00Z"

    (site,) = session["geofence"]
    assert site["type"] == "Polygon"
    assert site["coordinates"][0][:2] == [[48.15, 40.79], [48.152, 40.79]]
    assert [(line["kind"], line["min_count"]) for line in session["checklist"]] == [
        ("photo", 4),
        ("invoice", 1),
        ("fiscal_receipt", 1),
    ]
    assert session["accepted_types"]["photo"] == ["image/jpeg", "image/png"]
    assert session["items"] == [] and session["bundle_id"] is None

    again = client.get(f"/v1/capture-sessions/{session['id']}", headers=field_worker.headers)
    assert again.json()["challenge_code"] == session["challenge_code"]


def test_codes_use_an_alphabet_without_look_alikes():
    codes = {new_code() for _ in range(500)}
    assert len(codes) > 490
    assert set("".join(codes)) <= set(CODE_ALPHABET)
    assert not set("0O1I") & set(CODE_ALPHABET)


def test_one_open_session_per_milestone(client, clock, db, project, field_worker, phone):
    first = start(client, field_worker, project.id, phone).json()
    body = error(start(client, field_worker, project.id, phone), 409, "session_open")
    assert "Baku time" in body["message"]

    clock.advance(minutes=76)  # past the first session's upload time
    second = start(client, field_worker, project.id, phone)
    assert second.status_code == 201, second.text
    assert second.json()["challenge_code"] != first["challenge_code"]
    assert db.get(CaptureSession, first["id"]).status == "expired"


def test_only_members_with_their_own_live_key_start_sessions(
    client, clock, db, project, field_worker, stranger, phone
):
    error(start(client, stranger, project.id, phone), 403, "not_a_member")

    someone_elses = Account.create()
    register_device(client, stranger, someone_elses)
    error(start(client, field_worker, project.id, someone_elses), 403, "device_not_yours")
    error(start(client, field_worker, project.id, Account.create()), 403, "device_not_yours")

    db.execute(update(Device).where(Device.address == phone.address).values(revoked_at=clock.now))
    db.commit()
    error(start(client, field_worker, project.id, phone), 403, "device_revoked")


def test_the_milestone_must_be_taking_evidence(client, clock, db, project, field_worker, phone):
    clock.now = datetime(2027, 2, 28, 19, 0, tzinfo=UTC)  # 23:00 Baku, the day before
    body = error(start(client, field_worker, project.id, phone), 409, "window_not_open")
    assert "1 March 2027" in body["message"]

    clock.now = datetime(2027, 4, 14, 21, 0, tzinfo=UTC)  # after the 14 day grace period
    body = error(start(client, field_worker, project.id, phone), 409, "deadline_passed")
    assert "2027-04-15 00:00:00 Baku time" in body["message"]

    clock.now = datetime(2027, 4, 2, 6, 0, tzinfo=UTC)  # window closed, deadline not passed
    assert start(client, field_worker, project.id, phone).status_code == 201


def test_a_milestone_under_review_takes_no_new_evidence(
    client, clock, db, project, field_worker, phone
):
    db.execute(
        update(Milestone)
        .where(Milestone.project_id == EXAMPLE_ID, Milestone.index == 0)
        .values(status="checked", attempt=1)
    )
    db.commit()
    body = error(start(client, field_worker, project.id, phone), 409, "milestone_not_open")
    assert "checked" in body["message"]

    # After a rejection the charity may try again, as attempt 2.
    db.execute(
        update(Milestone)
        .where(Milestone.project_id == EXAMPLE_ID, Milestone.index == 0)
        .values(status="rejected", resubmit_deadline=clock.now + timedelta(days=10))
    )
    db.commit()
    session = start(client, field_worker, project.id, phone).json()
    assert session["attempt"] == 2


def test_the_project_must_be_live(client, clock, db, project, field_worker, phone):
    db.execute(
        update(Project).where(Project.id == EXAMPLE_ID).values(status=ProjectStatus.PUBLISHED)
    )
    db.commit()
    error(start(client, field_worker, project.id, phone), 409, "project_not_live")


def test_unknown_milestones_and_projects(client, clock, project, field_worker, phone):
    error(start(client, field_worker, project.id, phone, index=7), 404, "not_found")
    other = "00000000-0000-4000-8000-000000000000"
    error(start(client, field_worker, other, phone), 404, "not_found")


def test_sessions_are_private_to_the_charity(client, clock, db, project, field_worker, stranger):
    phone = Account.create()
    register_device(client, field_worker, phone)
    session = start(client, field_worker, project.id, phone).json()
    response = client.get(f"/v1/capture-sessions/{session['id']}", headers=stranger.headers)
    error(response, 403, "not_a_member")
    assert db.scalars(select(CaptureSession)).one().created_by == field_worker.user_id
