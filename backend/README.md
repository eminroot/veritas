# Veritas backend

Python services for Veritas: the API, the background workers, the chain relayer and the indexer. The design they follow is in [ARCHITECTURE.md](../ARCHITECTURE.md).

## Setup

You need [uv](https://docs.astral.sh/uv/). It installs Python 3.12 by itself if you don't have it. The API and its database tests also need PostgreSQL 17 with PostGIS.

```bash
cd backend
uv sync
cp .env.example .env   # then point VERITAS_DATABASE_URL at your database
```

Settings come from `VERITAS_*` environment variables or `.env`; `.env.example` lists them all.

## Everyday commands

```bash
uv run pytest
uv run ruff check .
uv run ruff format .
```

### Database tests

Tests that need PostgreSQL are skipped unless `VERITAS_TEST_DATABASE_URL` points at a server's `postgres` database, as a user that can create databases and the PostGIS extension. Each run creates its own `veritas_test_<8 hex>` database, migrates it with Alembic and drops it at the end; tables are emptied before every test.

```bash
VERITAS_TEST_DATABASE_URL=postgresql+psycopg://postgres@localhost:5432/postgres uv run pytest
```

### Chain tests

Tests that need a chain start their own [Anvil](https://getfoundry.sh/anvil/) and are skipped when it is not installed (set `VERITAS_ANVIL` if `anvil` is not on PATH). The system is deployed once per run and every test works on a snapshot that is thrown away after it. The flows in `tests/api/test_flow_*.py` run the API, PostgreSQL, the mock card provider and MockBank, the relayer and the indexer together against it: launching a Passport, a card donation to an in-escrow receipt, a milestone from evidence to the contractor's payout, a stopped project giving every donor's money back or moving it on.

```bash
VERITAS_TEST_DATABASE_URL=... VERITAS_ANVIL=$(which anvil) uv run pytest
```

### Contract artifacts and vectors

The backend reads the contracts' ABIs and bytecode from `src/veritas/chain/artifacts/`, so it never needs Foundry at runtime. After changing a contract:

```bash
(cd ../contracts && forge build)
uv run python scripts/export_abis.py          # CI runs it with --check
uv run python scripts/make_contract_vectors.py
```

The second script signs a whole project's life in Python and writes `contracts/test/fixtures/PythonVectors.sol`, which `contracts/test/PythonSigned.t.sol` replays against the real contracts. `tests/test_contract_vectors.py` fails if the file is stale.

### Migrations

```bash
uv run alembic upgrade head                                   # the database in VERITAS_DATABASE_URL
uv run alembic -x url=postgresql+psycopg://... upgrade head   # any other database
uv run alembic revision -m "money tables" --rev-id 0002       # migrations are numbered by hand
```

`tests/db` checks that the migrations build exactly what the models in `src/veritas/db/models` describe, so a model change needs a migration in the same change.

### Running the API

```bash
uv run alembic upgrade head
uv run uvicorn veritas.api.app:create_app --factory --reload
```

The OpenAPI docs are at http://localhost:8000/docs. Without `VERITAS_CHAIN_RPC_URL` and `VERITAS_DEPLOYMENT_FILE` the API runs without a chain: Passports publish but never launch. There is no SMS sender yet: with `VERITAS_OTP_ECHO=true` (never in production) the login code shows up in the console as `Login code for +994501234567 is 123456`. No endpoint makes a user a Veritas admin; on a local database do it by hand after logging in once:

```sql
UPDATE users SET is_admin = true WHERE phone = '+994501234567';
```

### Running the chain side

On a local Anvil (`anvil --slots-in-an-epoch 1`), deploy with `forge script` from `contracts/` (see its README), then start the mock card provider and MockBank and the worker next to the API:

```bash
export VERITAS_CHAIN_RPC_URL=http://127.0.0.1:8545
export VERITAS_DEPLOYMENT_FILE=../contracts/deployments/31337.json
export VERITAS_RELAYER_KEY=0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d  # Anvil account 1
export VERITAS_ADMIN_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80    # Anvil account 0
export VERITAS_MOCKBANK_KEY=0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a  # Anvil account 2
uv run uvicorn veritas.mocks.app:create_mock_app --factory --port 8100
uv run python -m veritas.workers
```

The worker runs the relayer, the indexer, every periodic job (hourly batches, the daily reconciliation, closing votes, releases, payouts, Pay-on-Proof charges, finishing receipt key rotations after their 48 hours, sending refused check reports again, deadline stops and claim defaults) and, in development, the evidence pipeline, which takes no new bundle after a few seconds of a tick. Those keys are Anvil's public test keys; never use them anywhere else. In production run two processes, so checking and redacting photos never holds up the relayer: `uv run python -m veritas.workers chain` for the chain and the jobs, and `uv run python -m veritas.workers evidence` for the evidence pipeline, which needs no chain; several evidence processes share bundles safely. A part that fails (the RPC endpoint timing out, say) is logged and tried again next tick; it never ends the process.

### Evidence

A field worker starts a capture session for a milestone (`POST /v1/projects/{id}/milestones/{index}/capture-sessions`) and gets a one-time challenge code, valid for 15 minutes, with the site's geofence and the Passport's proof checklist. The app uploads each file it captured with its SHA-256, capture time and GPS fix, then the manifest: canonical JSON listing every file, signed by the phone's registered key with `personal_sign` over `Veritas evidence manifest\n0x<SHA-256 of the manifest bytes>`. The bundle hash is the SHA-256 of those exact bytes.

The evidence pipeline (`veritas.evidence.pipeline`) runs the checks of ARCHITECTURE.md section 9 that need no AI (1, 2, 3, 5 and 11; the others are recorded as not run until Phase 7), stores the report, and builds the public copy in private storage: the redacted photos, the report, and a public manifest whose CID is the one anchored. A charity admin looks at the redacted photos (`GET /v1/evidence/{id}/items/{item_id}/public`) and signs the EIP-712 `Evidence` message (`GET /v1/evidence/{id}/evidence-message`, then `POST /v1/evidence/{id}/anchor` with `publish_photos`, the photos that show no face or number plate; the others stay private). Signed with the key the project was launched with, which the escrow keeps even after the charity changes its key. The relayer sends `submitEvidence` and `recordChecks`, the pipeline adds and pins the public copy on IPFS, and the indexer marks the bundle anchored. A bundle whose checks failed is anchored too, and every failed check says why. Signed evidence the chain refused becomes `void`, with the reason, and the milestone takes new evidence. A bundle the worker keeps failing on is retried with a growing pause and raises an `evidence_stuck` alert. Reviewers (the charity's members and the project's officer) get every bundle with its challenge code, and the signed manifest byte for byte at `GET /v1/evidence/{id}/manifest`.

- **Attestation.** Production will check App Attest and Play Integrity, which are not built yet, so there every bundle fails check 1 for now. In development the app sends `dev1.` and an HMAC-SHA256, keyed with `VERITAS_ATTESTATION_DEV_SECRET`, over the device address, session id and bundle hash; production refuses `VERITAS_ATTESTATION=dev`.
- **IPFS.** Public copies go to Kubo's RPC API at `VERITAS_IPFS_API_URL` (default `http://127.0.0.1:5001`), added with CIDv1 and raw leaves, and pinned. Every published file fits in one 256 KiB block, so its CID is the SHA-256 of the file. Without a node, `VERITAS_IPFS_FAKE=true` keeps them in memory (never in production).
- **Redaction.** Public photos are rebuilt from their pixels, so no EXIF, GPS or phone data survives, and faces and number plates are blurred with OpenCV's Haar cascades. OpenCV 5 no longer ships the cascades: with it no photo is published (the public copy lists them by count) and an alert says so. Even with a detector, a photo goes public only once the signing admin confirms it. Invoices, receipts, documents and videos stay private until they can be masked.
- **Uploads.** A photo's work is bounded before it is decoded (pixels, bytes per pixel, JPEG scans, shape), and it is decoded before the session is locked. JSON bodies may be 1 MB; only the file upload routes take up to `VERITAS_MAX_UPLOAD_BYTES`.
- **Tuning.** `VERITAS_CAPTURE_SESSION_MINUTES`, `VERITAS_EVIDENCE_UPLOAD_GRACE_MINUTES`, `VERITAS_EVIDENCE_CLOCK_SKEW_SECONDS`, `VERITAS_EVIDENCE_MAX_ACCURACY_M` and `VERITAS_PHOTO_REUSE_CLEAR_BITS` / `VERITAS_PHOTO_REUSE_CLOSE_BITS` set the windows and thresholds the checks use.

## Layout

```
src/veritas/core/         money, hashing, canonical JSON, identifier checks
src/veritas/chain/        Merkle trees, leaves and EIP-712 messages shared with the contracts,
                          their ABIs, the outbox, relayer, indexer and event handlers
src/veritas/domain/       rules that don't depend on storage, such as allocation
src/veritas/passport/     the Project Passport schema, and its problems in readable words
src/veritas/db/           SQLAlchemy base, models and sessions (sync, psycopg 3)
src/veritas/services/     what the API does: login, key proofs, onboarding, publishing
src/veritas/api/          FastAPI app factory, routers, dependencies and the error format
src/veritas/settings.py   configuration from VERITAS_* variables
src/veritas/storage.py    private file storage (a local directory now, S3 later)
src/veritas/payments/     money in: webhooks, donation intake, batches, reconciliation
src/veritas/decisions/    officer decisions, votes, payouts, Pay-on-Proof, stops and claims,
                          and moving a donor's receipt to a new key
src/veritas/evidence/     capture sessions, uploads, the checks and the report
src/veritas/mocks/        the stand-in card provider and MockBank, served over HTTP
src/veritas/workers.py    the background processes: relayer, indexer, periodic jobs, evidence
scripts/                  ABI export and the Python-signed contract vectors
migrations/               Alembic migrations: 0001_people_and_projects.py, then 0002, ...
tests/                    pytest suite; fixtures/ holds vectors made with other tools
tests/db/, tests/api/     database and API tests against PostgreSQL, and the end-to-end flows
tests/chain/              contracts and codecs against Anvil
```

The Merkle vectors in `tests/fixtures/merkle_vectors.json` come from OpenZeppelin's JS library. `make_merkle_vectors.mjs` next to them rebuilds the file.
