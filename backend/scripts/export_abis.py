"""Copy contract ABIs and bytecode from the Foundry build into the backend.

    cd contracts && forge build
    cd ../backend && uv run python scripts/export_abis.py

The backend reads `src/veritas/chain/artifacts/*.json` at runtime, so it never needs Foundry.
The bytecode is there too, for deploying to Anvil in tests and for the demo. The contracts are
built without metadata hashes, so the same sources give the same bytes on any machine, and CI
rebuilds and re-exports to check the committed files are current (`--check`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "contracts" / "out"
TARGET = ROOT / "backend" / "src" / "veritas" / "chain" / "artifacts"

CONTRACTS = (
    "VeritasHub",
    "VAZN",
    "PassportRegistry",
    "DonationLedger",
    "ReceiptToken",
    "VotingModule",
    "BankPayoutVault",
    "MilestoneEscrow",
    "EscrowFactory",
)


def render(name: str) -> str:
    built = json.loads((BUILD / f"{name}.sol" / f"{name}.json").read_text(encoding="utf-8"))
    artifact = {
        "contractName": name,
        "abi": built["abi"],
        "bytecode": built["bytecode"]["object"],
    }
    return json.dumps(artifact, indent=1, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    check = "--check" in argv
    TARGET.mkdir(parents=True, exist_ok=True)
    stale = []
    for name in CONTRACTS:
        path = TARGET / f"{name}.json"
        text = render(name)
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(name)
        else:
            path.write_text(text, encoding="utf-8", newline="\n")
    if stale:
        print("out of date, run scripts/export_abis.py:", ", ".join(stale))
        return 1
    print("artifacts are current" if check else f"exported {len(CONTRACTS)} artifacts")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
