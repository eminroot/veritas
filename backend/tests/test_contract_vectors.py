"""The Solidity fixture signed in Python must match what the Python code makes today.

`contracts/test/PythonSigned.t.sol` replays it on-chain. If someone changes a message type, a
leaf or the config here without regenerating it, this test says so before Foundry does.
"""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "make_contract_vectors.py"


def load_script():
    spec = importlib.util.spec_from_file_location("make_contract_vectors", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_python_vectors_fixture_is_current():
    script = load_script()
    if not script.OUTPUT.exists():
        pytest.skip("contracts are not checked out next to the backend")
    assert script.OUTPUT.read_text(encoding="utf-8") == script.build(), (
        "run `uv run python scripts/make_contract_vectors.py` and commit the result"
    )


def test_vectors_are_deterministic():
    script = load_script()
    assert script.build() == script.build()
