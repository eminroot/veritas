import json
from pathlib import Path
from uuid import UUID

import pytest
from eth_abi import encode

from veritas.chain.project import (
    CREDITS_TYPE,
    Credit,
    ProjectConfig,
    contractor_hash,
    credits_hash,
    launch_message,
)
from veritas.core.hashing import keccak256
from veritas.passport import Passport

EXAMPLE = Path(__file__).parents[2] / "docs" / "examples" / "passport.example.json"
CHARITY = "0x976EA74026E726554dB657fA54763abd0C3a0aa9"


@pytest.fixture
def passport():
    return Passport.model_validate_json(EXAMPLE.read_text(encoding="utf-8"))


def test_config_from_the_example_passport(passport):
    config = ProjectConfig.from_passport(passport, CHARITY.lower())
    assert config.charity == CHARITY
    assert config.officer == "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65"
    assert config.category == 0  # education
    assert config.allocation == 0  # pro rata
    assert config.budgets == (420_000, 1_383_000, 246_000)
    # Milestone 0 closes at 24:00 Baku on 2027-03-31 (20:00 UTC), then 14 days of grace.
    assert config.evidence_deadlines[0] == 1807732800
    assert config.rules.vote_window == 72 * 3600
    assert config.rules.turnout_extension == 48 * 3600
    assert config.rules.fallback_approves
    assert config.stop.choice_window == 30 * 86400
    assert not config.stop.unclaimed_redirects
    assert config.contractor_hash == contractor_hash("1300000021")


def test_any_rule_change_changes_the_config_hash(passport):
    config = ProjectConfig.from_passport(passport, CHARITY)
    assert len(config.hash()) == 32
    doc = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    doc["decision"]["min_turnout_bps"] = 1500
    changed = ProjectConfig.from_passport(Passport.model_validate(doc), CHARITY)
    assert changed.hash() != config.hash()


def test_contractor_hash_normalises_the_voen():
    assert contractor_hash(" 130 000 0021 ") == contractor_hash("1300000021")
    assert contractor_hash("1300000021") == keccak256(b"veritas:contractor:1300000021")


def test_launch_message(passport):
    config = ProjectConfig.from_passport(passport, CHARITY)
    message = launch_message(passport, config, passport.digest(), "bafy")
    assert message["projectId"] == passport.project_id.bytes
    assert message["version"] == 1
    assert message["configHash"] == config.hash()
    other = ProjectConfig.from_passport(
        passport.model_copy(update={"project_id": UUID(int=5)}), CHARITY
    )
    with pytest.raises(ValueError):
        launch_message(passport, other, passport.digest(), "bafy")
    with pytest.raises(ValueError):
        launch_message(passport.model_copy(update={"version": 2}), config, b"\x00" * 32, "x")


def test_credits_hash():
    credits = [Credit(UUID(int=1), (100, 0, 5)), Credit(UUID(int=2), (7,))]
    expected = keccak256(encode([CREDITS_TYPE], [[c.abi_value() for c in credits]]))
    assert credits_hash(credits) == expected
    assert credits_hash(credits[::-1]) != expected
