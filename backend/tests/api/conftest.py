"""Onboarding done through the API, for tests that need a verified charity and friends."""

import pytest
from support import CHARITY, CONTRACTOR, OFFICER, ok, upload


@pytest.fixture
def charity_admin(login):
    return login("+994 50 111 11 11")


@pytest.fixture
def new_charity(client, charity_admin):
    def create(**changes):
        response = client.post(
            "/v1/charities", json={**CHARITY, **changes}, headers=charity_admin.headers
        )
        return ok(response, 201)

    return create


@pytest.fixture
def verified_charity(client, charity_admin, admin, new_charity):
    charity = new_charity()
    base = f"/v1/charities/{charity['id']}"
    ok(upload(client, f"{base}/documents", charity_admin), 201)
    ok(client.post(f"{base}/submit", headers=charity_admin.headers))
    return ok(client.post(f"{base}/verify", json={}, headers=admin.headers))


@pytest.fixture
def verified_contractor(client, charity_admin, admin, verified_charity):
    body = {**CONTRACTOR, "charity_id": verified_charity["id"]}
    contractor = ok(client.post("/v1/contractors", json=body, headers=charity_admin.headers), 201)
    url = f"/v1/contractors/{contractor['id']}/verify"
    return ok(client.post(url, json={}, headers=admin.headers))


@pytest.fixture
def officer(client, admin):
    return ok(client.post("/v1/officers", json=OFFICER, headers=admin.headers), 201)


@pytest.fixture
def chain_app(app, chain):
    """The app with a chain, as it runs wherever money moves. Undone after the test."""
    app.state.chain = chain
    yield app
    app.state.chain = None


@pytest.fixture
def sessions(engine):
    from veritas.db.session import make_session_factory

    return make_session_factory(engine)


@pytest.fixture
def mocks(app, settings, chain, accounts, sessions):
    """The mock card provider and MockBank as an HTTP app, wired into the API like the real
    services would be. MockBank signs with the key the hub was deployed with as the bank."""
    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    from veritas.mocks.app import create_mock_app
    from veritas.payments.clients import BankClient, PspClient

    mock_settings = settings.model_copy(
        update={"mockbank_key": SecretStr(accounts["bank"].key.hex())}
    )
    mock_app = create_mock_app(mock_settings, chain=chain.contracts, sessions=sessions)
    http = TestClient(mock_app)
    psp = PspClient(http, settings.psp_api_key.get_secret_value())
    bank = BankClient(http, settings.bank_api_key.get_secret_value())
    before = (app.state.psp, app.state.bank)
    app.state.psp, app.state.bank = psp, bank
    yield {"psp": psp, "bank": bank, "http": http, "settings": mock_settings}
    app.state.psp, app.state.bank = before


@pytest.fixture
def field_evidence(client, app, settings, sessions, charity_admin, accounts):
    """Real evidence for the decision flows (see decisionkit.FieldEvidence)."""
    from decisionkit import FieldEvidence

    from veritas.api.routes.evidence import evidence_clock

    evidence = FieldEvidence(client, app, settings, sessions, charity_admin, accounts["charity"])
    app.dependency_overrides[evidence_clock] = evidence.clock
    yield evidence
    app.dependency_overrides.pop(evidence_clock, None)
