"""Configuration, read from VERITAS_* environment variables or a .env file.

Defaults only make a laptop work. Production must set the secrets, and the checks
below refuse to start with settings that would leak login codes or use the
development key.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Only for dev and test, where no VERITAS_SECRET_KEY is set. Production refuses it.
_DEV_SECRET_KEY = "veritas-development-key-never-use-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VERITAS_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    env: Literal["dev", "test", "prod"] = "dev"
    database_url: str = "postgresql+psycopg://postgres@localhost:5432/veritas_dev"
    storage_dir: Path = Path("data/storage")
    """Root of private file storage: KYB documents now, evidence originals later."""

    secret_key: SecretStr | None = None
    """Keys the HMAC that login codes are stored under. Required in production."""

    otp_ttl_seconds: int = Field(default=300, ge=30, le=3600)
    otp_max_attempts: int = Field(default=5, ge=1, le=20)
    otp_requests_per_hour: int = Field(default=5, ge=1, le=100)
    otp_echo: bool = False
    """Log login codes, so a developer can log in before SMS exists. Never in production."""

    session_ttl_days: int = Field(default=30, ge=1, le=365)

    # The web app's accounts: an email and a password, checked here.
    password_max_failures: int = Field(default=10, ge=3, le=100)
    """Wrong passwords in a row before the account refuses password logins for a while."""
    password_lock_minutes: int = Field(default=15, ge=1, le=24 * 60)
    password_reset_ttl_minutes: int = Field(default=30, ge=5, le=24 * 60)
    password_resets_per_hour: int = Field(default=5, ge=1, le=100)
    """Links to set a new password one account can be sent in an hour."""

    # Email, for the links to set a new password. Sent through SMTP when smtp_host is set.
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    """587 upgrades the connection with STARTTLS; 465 is TLS from the start."""
    smtp_starttls: bool = True
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    mail_from: str = "Veritas <no-reply@localhost>"
    mail_echo: bool = False
    """Write emails to the log instead of sending them, so a developer can follow their links.
    Never in production."""
    demo_login: bool = False
    """Let anyone sign in to the shared demo accounts, a donor and a verified organisation,
    from the web app's "Try the demo" buttons, with no password (POST /v1/auth/demo). For a
    demo site only, never one with real donors."""
    web_app_url: str = "http://localhost:8080"
    """Where the web app is: the links in emails point there."""

    # "Continue with Google" in the web app: Firebase signs the person in with Google, and the
    # web app trades the Firebase ID token for a session here.
    firebase_project_id: str | None = None
    """The Firebase project the web app's Google sign-in uses. Unset: Google sign-in is refused."""
    firebase_keys_url: str = (
        "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
    )
    """Where Google publishes the keys that sign Firebase ID tokens, as a JWKS."""
    cors_origins: list[str] = Field(default_factory=list)
    """Origins allowed to call the API from a browser, for a web app served from another
    origin, e.g. ["https://veritas.az"]. Empty: same origin only, which is how the dev server
    and nginx serve it (they pass /v1 through)."""
    key_challenge_ttl_seconds: int = Field(default=600, ge=60, le=3600)
    max_upload_bytes: int = Field(default=20 * 1024 * 1024, ge=1)

    # The chain. Without an RPC URL and a deployment the API runs without one: Passports
    # publish but never launch. Every environment that takes money sets both.
    chain_rpc_url: str | None = None
    deployment_file: Path | None = None
    """contracts/deployments/<chain id>.json, written by the deploy script."""
    chain_confirmations: int | None = Field(default=None, ge=0)
    """None: final means the node's "finalized" block. A number: that many blocks deep."""
    relayer_key: SecretStr | None = None
    """The relayer's private key. In production it lives in a cloud KMS instead."""
    admin_key: SecretStr | None = None
    """Only on Anvil and in the demo, so the relayer can send admin calls. Production
    sends those from the Safe."""
    relayer_min_priority_fee_gwei: int = Field(default=30, ge=0)

    # The card provider and the partner bank. In development both are the mocks in
    # veritas.mocks.app, which reads the mockbank_* settings as well.
    psp_base_url: str = "http://127.0.0.1:8100"
    psp_api_key: SecretStr = SecretStr("psp-development-key")
    psp_webhook_secret: SecretStr = SecretStr("whsec-development-secret")
    psp_webhook_url: str = "http://127.0.0.1:8000/v1/webhooks/psp"
    bank_base_url: str = "http://127.0.0.1:8100"
    bank_api_key: SecretStr = SecretStr("bank-development-key")
    mockbank_key: SecretStr | None = None
    """MockBank's signing key. Its address is the bank key the hub was deployed with."""
    mockbank_closed_accounts: list[str] = Field(default_factory=list)
    """IBANs MockBank treats as closed, to try a failed payout."""

    # Evidence. A field worker's phone gets a challenge code valid for a few minutes, uploads
    # what it captured, then a signed manifest; workers check, redact and publish the bundle.
    capture_session_minutes: int = Field(default=15, ge=1, le=120)
    """How long a challenge code is valid. Everything must be captured in this time."""
    evidence_upload_grace_minutes: int = Field(default=60, ge=0, le=24 * 60)
    """How long after the code expires files and the manifest may still arrive, for sites with
    a weak signal. Nothing captured after the code expired counts."""
    evidence_clock_skew_seconds: int = Field(default=120, ge=0, le=900)
    """How far a phone's clock may differ from ours before a capture time is not believed."""
    evidence_max_accuracy_m: float = Field(default=50, gt=0, le=1000)
    """A GPS fix less precise than this cannot place a capture on the site."""
    photo_reuse_clear_bits: int = Field(default=6, ge=0, le=64)
    """pHash and dHash both this close (in bits of 64) to another photo: the same photo, a
    hard fail."""
    photo_reuse_close_bits: int = Field(default=12, ge=0, le=64)
    """Both this close: worth the officer's look, an advisory."""
    attestation: Literal["dev", "platform"] | None = None
    """How app attestation tokens are checked. "dev": an HMAC the development build makes
    with attestation_dev_secret. "platform": App Attest and Play Integrity, which are not built
    yet, so every bundle fails check 1. Unset: "dev" outside production, "platform" in it."""
    attestation_dev_secret: SecretStr = SecretStr("veritas-development-attestation")
    """Keys the development attestation HMAC. The development build of the app knows it too."""
    ipfs_api_url: str = "http://127.0.0.1:5001"
    """Kubo's RPC API (not a gateway). Public copies are added and pinned there."""
    ipfs_fake: bool = False
    """Keep public copies in memory instead of sending them to Kubo. Never in production."""
    ipfs_timeout_seconds: float = Field(default=30, gt=0, le=600)
    redaction_cascade_dir: Path | None = None
    """A folder with OpenCV's Haar cascade files, for OpenCV builds that do not bundle them."""

    @model_validator(mode="after")
    def _safe_in_production(self) -> Settings:
        if self.env != "prod":
            return self
        if self.otp_echo:
            raise ValueError("VERITAS_OTP_ECHO must be off in production, it writes codes to logs")
        if self.mail_echo:
            raise ValueError("VERITAS_MAIL_ECHO must be off in production, it writes links to logs")
        key = self.secret_key.get_secret_value() if self.secret_key else ""
        if len(key) < 32 or key == _DEV_SECRET_KEY:
            raise ValueError("VERITAS_SECRET_KEY must be set in production, 32 characters or more")
        if self.chain_rpc_url is None or self.deployment_file is None:
            raise ValueError("production needs VERITAS_CHAIN_RPC_URL and VERITAS_DEPLOYMENT_FILE")
        if self.admin_key is not None:
            raise ValueError("VERITAS_ADMIN_KEY is for Anvil and the demo; production uses a Safe")
        for name in ("psp_api_key", "psp_webhook_secret", "bank_api_key"):
            if "development" in getattr(self, name).get_secret_value():
                raise ValueError(f"VERITAS_{name.upper()} must be set in production")
        return self

    @model_validator(mode="after")
    def _evidence_rules(self) -> Settings:
        if self.photo_reuse_close_bits < self.photo_reuse_clear_bits:
            raise ValueError(
                "VERITAS_PHOTO_REUSE_CLOSE_BITS must be at least VERITAS_PHOTO_REUSE_CLEAR_BITS"
            )
        if self.env != "prod":
            return self
        if self.attestation == "dev":
            raise ValueError(
                "VERITAS_ATTESTATION=dev is for development; production checks App Attest "
                "and Play Integrity"
            )
        if self.ipfs_fake:
            raise ValueError("VERITAS_IPFS_FAKE is for development; production publishes to Kubo")
        return self

    @property
    def chain_enabled(self) -> bool:
        return self.chain_rpc_url is not None and self.deployment_file is not None

    @property
    def attestation_scheme(self) -> str:
        """The attestation check in force: "dev" or "platform"."""
        if self.attestation is not None:
            return self.attestation
        return "platform" if self.env == "prod" else "dev"

    def hmac_key(self) -> bytes:
        if self.secret_key is None:
            return _DEV_SECRET_KEY.encode()
        return self.secret_key.get_secret_value().encode()


@lru_cache
def get_settings() -> Settings:
    return Settings()
