"""Passport drafts with readable problems, and publishing the example Passport."""

import copy
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from support import CONTRACTOR, error, ok

from veritas.core.canonical import canonical_json
from veritas.core.hashing import sha256, to_hex
from veritas.db.models import BudgetLine, Charity, Milestone, PassportVersion, Site, User
from veritas.passport import Passport, load_passport
from veritas.services.cid import raw_cid
from veritas.services.passports import create_project

EXAMPLE = Path(__file__).resolve().parents[3] / "docs" / "examples" / "passport.example.json"
EXAMPLE_ID = "6f1c2a9e-3b7d-4e2a-9c41-8d5b2f0e7a13"
EXAMPLE_DIGEST = "0xfd7a873d24eb5749dd7359db25725b2bec83ba3747362ffd80db4f9c90c20f57"


@pytest.fixture
def example():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


@pytest.fixture
def example_project(db, verified_charity, charity_admin):
    """The project the example Passport describes: made like POST /v1/projects makes one,
    but with the example's fixed id."""
    charity = db.get(Charity, uuid.UUID(verified_charity["id"]))
    user = db.get(User, charity_admin.user_id)
    project, _ = create_project(db, charity, user, project_id=uuid.UUID(EXAMPLE_ID))
    db.commit()
    return f"/v1/projects/{project.id}"


def first(doc):
    return doc["milestones"][0]


def test_new_project_starts_with_a_draft_that_names_the_charity(
    client, charity_admin, verified_charity
):
    project = ok(
        client.post(
            "/v1/projects",
            json={"charity_id": verified_charity["id"]},
            headers=charity_admin.headers,
        ),
        201,
    )
    assert project["status"] == "draft"
    assert project["id"] != EXAMPLE_ID
    draft = ok(client.get(f"/v1/projects/{project['id']}/passport", headers=charity_admin.headers))
    assert draft["version"] == 1
    assert draft["draft"] == {
        "format": "veritas.passport/1",
        "project_id": project["id"],
        "version": 1,
        "charity": {"legal_name": "Bərəkət İctimai Birliyi", "voen": "1700000011"},
    }
    # A new draft is a checklist of what is still to fill in.
    assert draft["problems"] == [
        {"path": field, "message": "is required"}
        for field in (
            "title",
            "summary",
            "category",
            "contractor",
            "officer",
            "total_qapik",
            "milestones",
        )
    ]
    listed = ok(
        client.get(
            f"/v1/charities/{verified_charity['id']}/projects", headers=charity_admin.headers
        )
    )
    assert listed[0]["draft_version"] == 1
    assert listed[0]["published_version"] is None


BROKEN = {
    "line amount is not quantity times price": (
        lambda d: first(d)["budget"][1].update(quantity=31),
        "milestones[0].budget[1].amount_qapik",
        "must be quantity times unit price, which is 124000",
    ),
    "amount as a float": (
        lambda d: first(d)["budget"][1].update(amount_qapik=120000.0),
        "milestones[0].budget[1].amount_qapik",
        "must be a whole number of qəpik",
    ),
    "total as a string": (
        lambda d: d.update(total_qapik="2049000"),
        "total_qapik",
        "must be a whole number of qəpik",
    ),
    "budget lines do not add up": (
        lambda d: first(d).update(amount_qapik=420_100),
        "milestones[0].amount_qapik",
        "must equal the sum of the budget lines, which is 420000",
    ),
    "milestones do not add up": (
        lambda d: d.update(total_qapik=2_049_001),
        "total_qapik",
        "must equal the sum of the milestone amounts, which is 2049000",
    ),
    "missing title": (lambda d: d.pop("title"), "title", "is required"),
    "unknown field": (
        lambda d: d.update(colour="green"),
        "colour",
        "is not a known field, remove it",
    ),
    "indexes out of order": (
        lambda d: first(d).update(index=1),
        "milestones[0].index",
        "must be 0, indexes run 0, 1, 2 in order",
    ),
    "windows out of order": (
        lambda d: d["milestones"][1]["window"].update(opens="2027-02-01"),
        "milestones[1].window.opens",
        "must not be before milestone 0 opens on 2027-03-01",
    ),
    "vote window too short": (
        lambda d: d["decision"].update(vote_window_hours=2),
        "decision.vote_window_hours",
        "must be at least 24",
    ),
    "negative price": (
        lambda d: first(d)["budget"][0].update(unit_price_qapik=-1),
        "milestones[0].budget[0].unit_price_qapik",
        "cannot be negative",
    ),
    "unknown category": (
        lambda d: d.update(category="sport"),
        "category",
        'must be one of "education", "health", "water", "housing", "environment", '
        '"community", "emergency", "other"',
    ),
    "latitude first": (
        lambda d: first(d)["site"].update(
            coordinates=[[[40.79, 48.15], [40.79, 48.152], [40.7915, 48.152], [40.79, 48.15]]]
        ),
        "milestones[0].site.coordinates",
        "(40.79, 48.15) is outside Azerbaijan, coordinates go longitude first",
    ),
    "position with three numbers": (
        lambda d: first(d)["site"]["coordinates"][0].__setitem__(1, [48.152, 40.79, 7]),
        "milestones[0].site.coordinates[0][1]",
        "must be [longitude, latitude]",
    ),
    "no photo": (
        lambda d: first(d).update(proof=first(d)["proof"][1:]),
        "milestones[0].proof",
        "needs at least one photo, the challenge code is read from it",
    ),
    "window closes first": (
        lambda d: first(d)["window"].update(closes="2027-02-01"),
        "milestones[0].window.closes",
        "must not be before the day the window opens",
    ),
    "date written the local way": (
        lambda d: first(d)["window"].update(closes="31.03.2027"),
        "milestones[0].window.closes",
        "must be a date written as YYYY-MM-DD",
    ),
    "bad VÖEN": (
        lambda d: d["contractor"].update(voen="13000000"),
        "contractor.voen",
        "a VÖEN is 10 digits: '13000000'",
    ),
}


@pytest.mark.parametrize(("break_it", "path", "message"), BROKEN.values(), ids=BROKEN.keys())
def test_draft_problems_are_readable(
    client, charity_admin, example_project, example, break_it, path, message
):
    broken = copy.deepcopy(example)
    break_it(broken)
    saved = ok(
        client.put(f"{example_project}/passport", json=broken, headers=charity_admin.headers)
    )
    assert {"path": path, "message": message} in saved["problems"]
    # The draft is kept exactly as sent, mistakes and all.
    assert saved["draft"] == broken
    again = ok(client.get(f"{example_project}/passport", headers=charity_admin.headers))
    assert again["problems"] == saved["problems"]


def test_validate_checks_the_references_too(client, charity_admin, example_project, example):
    example["charity"]["voen"] = "1700000099"
    example["project_id"] = str(uuid.uuid4())
    example["version"] = 2
    ok(client.put(f"{example_project}/passport", json=example, headers=charity_admin.headers))
    result = ok(client.post(f"{example_project}/passport/validate", headers=charity_admin.headers))
    assert result == {
        "version": 1,
        "sha256": None,
        "problems": [
            {"path": "project_id", "message": f"must be {EXAMPLE_ID}, the id of this project"},
            {"path": "version", "message": "must be 1, the next version of this Passport"},
            {"path": "charity.voen", "message": "must be 1700000011, the VÖEN of your charity"},
            {
                "path": "contractor.voen",
                "message": "no contractor with this VÖEN is registered yet",
            },
            {
                "path": "officer.address",
                "message": "no Verification Officer is registered with this address",
            },
        ],
    }


def test_publish_the_example_passport(
    client, db, charity_admin, example_project, example, verified_contractor, officer
):
    saved = ok(
        client.put(f"{example_project}/passport", json=example, headers=charity_admin.headers)
    )
    assert saved["problems"] == []
    checked = ok(client.post(f"{example_project}/passport/validate", headers=charity_admin.headers))
    assert checked == {"version": 1, "problems": [], "sha256": EXAMPLE_DIGEST}

    published = ok(client.post(f"{example_project}/publish", headers=charity_admin.headers))
    assert published["version"] == 1
    assert published["sha256"] == EXAMPLE_DIGEST
    assert published["url"] == f"/v1/projects/{EXAMPLE_ID}/passports/1"

    # The key property: the bytes served hash to the stored hash, which is the Passport's
    # own digest and the pinned one.
    response = client.get(published["url"])
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    body = response.content
    stored = db.scalars(select(PassportVersion).where(PassportVersion.version == 1)).one()
    passport = Passport.model_validate(example)
    assert to_hex(sha256(body)) == to_hex(stored.sha256) == to_hex(passport.digest())
    assert to_hex(sha256(body)) == EXAMPLE_DIGEST
    assert body == stored.canonical_bytes == passport.canonical_bytes() == canonical_json(example)
    assert load_passport(body) == passport
    assert response.headers["x-passport-sha256"] == EXAMPLE_DIGEST
    assert response.headers["x-passport-cid"] == published["cid"] == raw_cid(body)
    assert published["cid"].startswith("bafkrei")
    assert stored.status == "published"
    assert stored.draft_json is None

    # The milestone tables are a copy of the published Passport.
    milestones = db.scalars(select(Milestone).order_by(Milestone.index)).all()
    assert [m.amount_qapik for m in milestones] == [420_000, 1_383_000, 246_000]
    assert [m.status for m in milestones] == ["funding"] * 3
    assert milestones[0].opens_at == passport.milestones[0].window.opens_at()
    assert milestones[0].closes_at == passport.milestones[0].window.closes_at()
    assert milestones[0].evidence_deadline == passport.evidence_deadline(0)
    lines = db.scalars(
        select(BudgetLine)
        .where(BudgetLine.milestone_id == milestones[1].id)
        .order_by(BudgetLine.position)
    ).all()
    assert [(line.item, line.amount_qapik) for line in lines] == [
        ("Metal roof sheets", 756_000),
        ("Roof insulation", 252_000),
        ("Crew labour", 375_000),
    ]
    assert db.scalar(select(func.count()).select_from(BudgetLine)) == 8
    assert db.scalar(select(func.count()).select_from(Site)) == 3

    inside = text(
        "SELECT bool_and(ST_Covers(geom, ST_GeogFromText('POINT(48.151 40.7905)'))) FROM sites"
    )
    outside = text(
        "SELECT bool_or(ST_Covers(geom, ST_GeogFromText('POINT(48.16 40.7905)'))) FROM sites"
    )
    assert db.scalar(inside) is True
    assert db.scalar(outside) is False

    # The public pages show it; the draft is gone.
    listed = ok(client.get("/v1/projects"))
    assert [p["id"] for p in listed] == [EXAMPLE_ID]
    assert listed[0]["passport"]["sha256"] == EXAMPLE_DIGEST
    detail = ok(client.get(f"/v1/projects/{EXAMPLE_ID}"))
    assert detail["status"] == "published"
    assert detail["title"] == example["title"]
    assert detail["total_qapik"] == 2_049_000
    assert detail["charity"]["voen"] == "1700000011"
    assert [m["amount_qapik"] for m in detail["milestones"]] == [420_000, 1_383_000, 246_000]
    assert detail["milestones"][0]["sites"] == [first(example)["site"]]
    assert detail["milestones"][0]["budget"][0]["item"] == "Crew labour"
    error(client.get(f"{example_project}/passport", headers=charity_admin.headers), 404, "no_draft")


def test_publishing_a_new_version_supersedes_the_old_one(
    client, db, charity_admin, example_project, example, verified_contractor, officer
):
    ok(client.put(f"{example_project}/passport", json=example, headers=charity_admin.headers))
    ok(client.post(f"{example_project}/publish", headers=charity_admin.headers))
    milestone_ids = db.scalars(select(Milestone.id).order_by(Milestone.index)).all()

    revised = {**copy.deepcopy(example), "version": 2, "title": "New roof for the school"}
    saved = ok(
        client.put(f"{example_project}/passport", json=revised, headers=charity_admin.headers)
    )
    assert saved["version"] == 2
    assert saved["problems"] == []
    second = ok(client.post(f"{example_project}/publish", headers=charity_admin.headers))
    assert second["version"] == 2

    statuses = db.execute(
        select(PassportVersion.version, PassportVersion.status).order_by(PassportVersion.version)
    ).all()
    assert [tuple(row) for row in statuses] == [(1, "superseded"), (2, "published")]
    # Version 1 is still served exactly as it was published.
    assert to_hex(sha256(client.get(f"{example_project}/passports/1").content)) == EXAMPLE_DIGEST
    assert ok(client.get(f"/v1/projects/{EXAMPLE_ID}"))["title"] == "New roof for the school"
    db.expire_all()
    assert db.scalars(select(Milestone.id).order_by(Milestone.index)).all() == milestone_ids
    assert set(db.scalars(select(Milestone.passport_version))) == {2}


def test_publish_needs_a_verified_charity(client, charity_admin, new_charity, example):
    charity = new_charity()
    project = ok(
        client.post(
            "/v1/projects", json={"charity_id": charity["id"]}, headers=charity_admin.headers
        ),
        201,
    )
    example["project_id"] = project["id"]
    url = f"/v1/projects/{project['id']}"
    ok(client.put(f"{url}/passport", json=example, headers=charity_admin.headers))
    error(client.post(f"{url}/publish", headers=charity_admin.headers), 409, "charity_not_verified")


def test_publish_needs_a_verified_contractor(
    client, charity_admin, example_project, example, verified_charity, officer
):
    body = {**CONTRACTOR, "charity_id": verified_charity["id"]}
    ok(client.post("/v1/contractors", json=body, headers=charity_admin.headers), 201)
    ok(client.put(f"{example_project}/passport", json=example, headers=charity_admin.headers))
    response = client.post(f"{example_project}/publish", headers=charity_admin.headers)
    refused = error(response, 422, "passport_invalid")
    assert refused["details"] == [
        {"path": "contractor.voen", "message": "this contractor is not verified yet"}
    ]


def test_publish_needs_an_active_officer(
    client, admin, charity_admin, example_project, example, verified_contractor, officer
):
    ok(client.post(f"/v1/officers/{officer['id']}/deactivate", headers=admin.headers))
    ok(client.put(f"{example_project}/passport", json=example, headers=charity_admin.headers))
    response = client.post(f"{example_project}/publish", headers=charity_admin.headers)
    refused = error(response, 422, "passport_invalid")
    assert refused["details"] == [
        {"path": "officer.address", "message": "this Verification Officer is not active"}
    ]


def test_publish_needs_the_right_project_id(
    client, charity_admin, example_project, example, verified_contractor, officer
):
    example["project_id"] = str(uuid.uuid4())
    ok(client.put(f"{example_project}/passport", json=example, headers=charity_admin.headers))
    response = client.post(f"{example_project}/publish", headers=charity_admin.headers)
    refused = error(response, 422, "passport_invalid")
    assert refused["details"] == [
        {"path": "project_id", "message": f"must be {EXAMPLE_ID}, the id of this project"}
    ]


def test_only_charity_admins_publish(
    client, charity_admin, example_project, example, verified_charity, login
):
    url = f"/v1/charities/{verified_charity['id']}/members"
    ok(client.post(url, json={"phone": "+994554444444"}, headers=charity_admin.headers), 201)
    worker = login("+994554444444")
    ok(client.put(f"{example_project}/passport", json=example, headers=worker.headers))
    error(client.post(f"{example_project}/publish", headers=worker.headers), 403, "role_required")

    stranger = login("+994 70 666 66 66")
    error(client.get(f"{example_project}/passport", headers=stranger.headers), 403, "not_a_member")


def test_drafts_are_not_public(client, charity_admin, example_project):
    assert ok(client.get("/v1/projects")) == []
    error(client.get(f"/v1/projects/{EXAMPLE_ID}"), 404, "not_found")
    error(client.get(f"{example_project}/passports/1"), 404, "not_found")


def test_drafts_must_fit_in_the_database(client, charity_admin, example_project):
    url = f"{example_project}/passport"
    headers = {**charity_admin.headers, "Content-Type": "application/json"}
    response = client.put(url, content=b'{"title": NaN}', headers=headers)
    error(response, 422, "draft_not_storable")
    error(
        client.put(url, json={"title": "a\u0000b"}, headers=charity_admin.headers),
        422,
        "draft_not_storable",
    )
    error(
        client.put(url, json=["not", "an", "object"], headers=charity_admin.headers),
        422,
        "invalid_request",
    )
