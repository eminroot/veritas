"""The demo sign-in behind the web app's "Try the demo" buttons: off unless switched on, no
password, and an organisation that can plan and publish a project straight away."""

import json
from pathlib import Path

import pytest
from support import error, ok

from veritas.services import demo

EXAMPLE = Path(__file__).resolve().parents[3] / "docs" / "examples" / "passport.example.json"


@pytest.fixture
def demo_on(app, monkeypatch):
    monkeypatch.setattr(app.state.settings, "demo_login", True)


def bearer(token):
    return {"Authorization": f"Bearer {token['access_token']}"}


def test_off_unless_the_server_switches_it_on(client):
    error(client.post("/v1/auth/demo", json={"kind": "donor"}), 404, "demo_off")


def test_the_donor_demo_signs_in_without_a_password(client, demo_on):
    token = ok(client.post("/v1/auth/demo", json={"kind": "donor"}))
    me = ok(client.get("/v1/me", headers=bearer(token)))
    assert me["user"]["email"] == demo.DONOR_EMAIL
    assert me["memberships"] == []


def test_the_organisation_demo_is_verified_with_a_contractor_and_an_officer(client, demo_on):
    token = ok(client.post("/v1/auth/demo", json={"kind": "organisation"}))
    headers = bearer(token)
    me = ok(client.get("/v1/me", headers=headers))
    [membership] = me["memberships"]
    assert membership["charity_name"] == demo.CHARITY["legal_name"]
    assert (membership["charity_status"], membership["role"]) == ("verified", "admin")
    contractors = ok(client.get("/v1/contractors", headers=headers))
    assert [(c["legal_name"], c["status"]) for c in contractors] == [
        (demo.CONTRACTOR["legal_name"], "verified")
    ]
    officers = ok(client.get("/v1/officers", headers=headers))
    assert demo.OFFICER["name"] in [o["name"] for o in officers]


def test_pressing_it_again_reuses_the_same_accounts(client, demo_on):
    first = ok(client.post("/v1/auth/demo", json={"kind": "organisation"}))
    again = ok(client.post("/v1/auth/demo", json={"kind": "organisation"}))
    assert first["user"]["id"] == again["user"]["id"]
    assert first["access_token"] != again["access_token"]
    me = ok(client.get("/v1/me", headers=bearer(again)))
    assert len(me["memberships"]) == 1


def test_only_a_donor_or_an_organisation(client, demo_on):
    assert client.post("/v1/auth/demo", json={"kind": "officer"}).status_code == 422


def test_the_demo_organisation_can_plan_and_publish_a_project(client, demo_on):
    headers = bearer(ok(client.post("/v1/auth/demo", json={"kind": "organisation"})))
    [membership] = ok(client.get("/v1/me", headers=headers))["memberships"]
    project = ok(
        client.post("/v1/projects", json={"charity_id": membership["charity_id"]}, headers=headers),
        201,
    )
    contractor = ok(client.get("/v1/contractors", headers=headers))[0]
    officer = next(
        o
        for o in ok(client.get("/v1/officers", headers=headers))
        if o["name"] == demo.OFFICER["name"]
    )

    passport = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    passport["project_id"] = project["id"]
    passport["charity"] = {"legal_name": demo.CHARITY["legal_name"], "voen": demo.CHARITY["voen"]}
    passport["contractor"] = {"legal_name": contractor["legal_name"], "voen": contractor["voen"]}
    passport["officer"] = {
        "name": officer["name"],
        "organisation": officer["organisation"],
        "address": officer["address"],
    }

    base = f"/v1/projects/{project['id']}"
    saved = ok(client.put(f"{base}/passport", json=passport, headers=headers))
    assert saved["problems"] == []
    published = ok(client.post(f"{base}/publish", headers=headers))
    assert published["version"] == 1
