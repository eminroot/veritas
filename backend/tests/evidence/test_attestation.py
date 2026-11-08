"""App attestation: the development scheme, the production stand-in and the settings around them."""

from __future__ import annotations

import uuid

import pytest
from pydantic import SecretStr, ValidationError

from veritas.evidence.attestation import (
    DevAttestation,
    PlatformAttestation,
    attestation_verifier,
    dev_token,
)
from veritas.settings import Settings

SECRET = b"test attestation secret"
DEVICE = "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65"
SESSION = uuid.UUID("6f1c2a9e-3b7d-4e2a-9c41-8d5b2f0e7a13")
BUNDLE = bytes(range(32))
PRODUCTION = {
    "env": "prod",
    "secret_key": SecretStr("x" * 32),
    "chain_rpc_url": "https://polygon-rpc.example",
    "deployment_file": "deployments/137.json",
    "psp_api_key": SecretStr("live-psp-key"),
    "psp_webhook_secret": SecretStr("live-webhook-secret"),
    "bank_api_key": SecretStr("live-bank-key"),
}


def verify(token, device=DEVICE, session=SESSION, bundle=BUNDLE, verifier=None):
    verifier = verifier or DevAttestation(SECRET)
    return verifier.verify(
        token, platform="android", device=device, session_id=session, bundle_hash=bundle
    )


def test_a_dev_token_is_good_for_one_device_session_and_manifest():
    token = dev_token(SECRET, device=DEVICE, session_id=SESSION, bundle_hash=BUNDLE)
    assert token.startswith("dev1.") and len(token) == 5 + 64
    assert verify(token).valid

    for wrong in (
        {"device": "0x0000000000000000000000000000000000000001"},
        {"session": uuid.uuid4()},
        {"bundle": bytes(32)},
    ):
        result = verify(token, **wrong)
        assert not result.valid
        assert result.reason == (
            "the attestation token was not made for this device, session and manifest"
        )


def test_missing_and_foreign_tokens_are_refused():
    assert verify(None).reason == "the app sent no attestation token"
    assert verify("").reason == "the app sent no attestation token"
    assert verify("eyJhbGciOiJFUzI1NiJ9.play-integrity").reason == (
        "the attestation token is not one this server knows"
    )
    other_secret = dev_token(
        b"another secret", device=DEVICE, session_id=SESSION, bundle_hash=BUNDLE
    )
    assert not verify(other_secret).valid


def test_the_production_scheme_accepts_nothing_until_it_is_built():
    token = dev_token(SECRET, device=DEVICE, session_id=SESSION, bundle_hash=BUNDLE)
    result = verify(token, verifier=PlatformAttestation())
    assert not result.valid and result.scheme == "platform"
    assert "not built yet" in result.reason
    web = PlatformAttestation().verify(
        token, platform="web", device=DEVICE, session_id=SESSION, bundle_hash=BUNDLE
    )
    assert "a browser cannot attest" in web.reason


def test_the_scheme_follows_the_environment():
    assert Settings(_env_file=None).attestation_scheme == "dev"
    assert isinstance(attestation_verifier(Settings(_env_file=None)), DevAttestation)
    production = Settings(_env_file=None, **PRODUCTION)
    assert production.attestation_scheme == "platform"
    assert isinstance(attestation_verifier(production), PlatformAttestation)
    forced = Settings(_env_file=None, attestation="platform")
    assert isinstance(attestation_verifier(forced), PlatformAttestation)


def test_production_refuses_the_development_scheme_and_the_fake_ipfs():
    with pytest.raises(ValidationError, match="VERITAS_ATTESTATION=dev"):
        Settings(_env_file=None, **PRODUCTION, attestation="dev")
    with pytest.raises(ValidationError, match="VERITAS_IPFS_FAKE"):
        Settings(_env_file=None, **PRODUCTION, ipfs_fake=True)
    assert Settings(_env_file=None, attestation="dev", ipfs_fake=True).ipfs_fake


def test_evidence_settings_have_laptop_defaults_and_sane_bounds():
    settings = Settings(_env_file=None)
    assert settings.capture_session_minutes == 15
    assert settings.evidence_upload_grace_minutes == 60
    assert settings.evidence_max_accuracy_m == 50
    assert (settings.photo_reuse_clear_bits, settings.photo_reuse_close_bits) == (6, 12)
    assert settings.ipfs_api_url == "http://127.0.0.1:5001" and not settings.ipfs_fake
    with pytest.raises(ValidationError, match="CLOSE_BITS must be at least"):
        Settings(_env_file=None, photo_reuse_clear_bits=10, photo_reuse_close_bits=8)
