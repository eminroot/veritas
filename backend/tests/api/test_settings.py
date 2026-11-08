import pytest
from pydantic import SecretStr, ValidationError

from veritas.settings import Settings

STRONG = SecretStr("x" * 32)


def test_defaults_work_on_a_laptop():
    settings = Settings(_env_file=None)
    assert settings.env == "dev"
    assert settings.otp_ttl_seconds == 300
    assert settings.otp_max_attempts == 5
    assert settings.session_ttl_days == 30
    assert settings.otp_echo is False
    assert settings.hmac_key()


def test_read_from_veritas_environment_variables(monkeypatch):
    monkeypatch.setenv("VERITAS_OTP_ECHO", "true")
    monkeypatch.setenv("VERITAS_DATABASE_URL", "postgresql+psycopg://u@db:5432/x")
    settings = Settings(_env_file=None)
    assert settings.otp_echo is True
    assert settings.database_url == "postgresql+psycopg://u@db:5432/x"


def test_production_never_logs_login_codes():
    with pytest.raises(ValidationError, match="OTP_ECHO"):
        Settings(_env_file=None, env="prod", otp_echo=True, secret_key=STRONG)


@pytest.mark.parametrize("key", [None, SecretStr("short")])
def test_production_needs_a_real_secret_key(key):
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(_env_file=None, env="prod", secret_key=key)


PRODUCTION = {
    "env": "prod",
    "secret_key": STRONG,
    "chain_rpc_url": "https://polygon-rpc.example",
    "deployment_file": "deployments/137.json",
    "psp_api_key": SecretStr("live-psp-key"),
    "psp_webhook_secret": SecretStr("live-webhook-secret"),
    "bank_api_key": SecretStr("live-bank-key"),
}


def test_production_with_everything_set():
    settings = Settings(_env_file=None, **PRODUCTION)
    assert settings.hmac_key() == b"x" * 32
    assert settings.chain_enabled


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"chain_rpc_url": None}, "CHAIN_RPC_URL"),
        ({"deployment_file": None}, "DEPLOYMENT_FILE"),
        ({"admin_key": SecretStr("0x" + "11" * 32)}, "ADMIN_KEY"),
        ({"psp_webhook_secret": SecretStr("whsec-development-secret")}, "PSP_WEBHOOK_SECRET"),
    ],
)
def test_production_refuses_development_chain_and_payment_settings(change, message):
    with pytest.raises(ValidationError, match=message):
        Settings(_env_file=None, **(PRODUCTION | change))


def test_without_a_chain_the_api_still_runs():
    assert not Settings(_env_file=None).chain_enabled
