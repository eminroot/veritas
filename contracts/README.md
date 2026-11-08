# Veritas contracts

Solidity 0.8.38, OpenZeppelin Contracts 5.7 and Foundry 1.9. What the contracts do and why is in [ARCHITECTURE.md](../ARCHITECTURE.md), sections 4 to 7.

## Setup

```bash
git submodule update --init --recursive   # forge-std and OpenZeppelin, pinned in foundry.lock
forge build --sizes
forge test
```

## The contracts

| Contract | Role |
| - | - |
| `VeritasHub` | Roles, one-time wiring, the release pause, 48-hour key changes, and the one EIP-712 domain |
| `VAZN` | The manat mirror. Two decimals, so balances are qəpik. Minted only by the ledger, burned only by the vault, and it never leaves Veritas contracts |
| `PassportRegistry` | Passport hash, CID, version and contractor per project, and the amendment flow |
| `EscrowFactory` | Launches a project from the charity's signed `ProjectLaunch` as an EIP-1167 clone |
| `MilestoneEscrow` | One project's milestones and money: evidence, checks, decision, vote, release, stop and claims |
| `DonationLedger` | Hourly batch roots, settlement in provider mode, the daily bank attestation, leaf proofs |
| `VotingModule` | Milestone, amendment and stop votes with Merkle eligibility proofs |
| `ReceiptToken` | Locked ERC-721 (ERC-5192) receipts, one per donor key per project, with key rotation |
| `BankPayoutVault` | Released money waiting for the bank's signed confirmation or failure |

`src/libraries/VeritasTypes.sol` holds the leaf format, the project config and every EIP-712 type string. `backend/src/veritas/chain` builds the same bytes in Python.

## Tests

- `test/Core.t.sol`, `Ledger.t.sol`, `Milestone.t.sol`, `Stop.t.sol`: each contract's rules, the whole milestone road, stopping, claims and amendments.
- `test/Fuzz.t.sol` and the allocation fuzz test in `Stop.t.sol`: whatever the amounts, donors' shares of what is left are exact and never add up to more than the escrow holds, and a split never exceeds what a milestone needs.
- `test/PythonSigned.t.sol` replays a project's whole life with every signature, Merkle root and proof made by the Python backend (`backend/scripts/make_contract_vectors.py` writes `test/fixtures/PythonVectors.sol`). If the two sides disagree on one byte, a call reverts. It also checks the Solidity allocation against 40 cases computed in Python.

`FOUNDRY_PROFILE=ci forge test` runs the fuzz tests with more runs, as CI does.

## Deploying

The deploy script deploys and wires everything and writes `deployments/<chain id>.json`, which the backend reads (`VERITAS_DEPLOYMENT_FILE`).

On Anvil, with its default accounts as admin (0), relayer (1) and bank (2):

```bash
anvil --slots-in-an-epoch 1
forge script script/Deploy.s.sol --rpc-url http://127.0.0.1:8545 --broadcast \
  --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
```

On Polygon Amoy, set `VERITAS_ADMIN` (the admin Safe), `VERITAS_RELAYER` and `VERITAS_BANK` and deploy from a keystore account:

```bash
forge script script/Deploy.s.sol --rpc-url $AMOY_RPC_URL --broadcast --account deployer
```

After a contract change, re-export the ABIs into the backend (`backend/scripts/export_abis.py`); CI fails if they differ from the build. The build has no metadata hash, so the same sources give the same bytecode on every machine.

## Size

`MilestoneEscrow` is about 23 KB of the 24 KB limit. Amendments live in `PassportRegistry` partly to keep it there. New escrow features should come with a look at `forge build --sizes`.
