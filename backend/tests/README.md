# Backend tests

Every test lives here, grouped by what it exercises. The contract tests are in
[`contracts/test`](../../contracts/test/README.md), where Foundry looks for them.

```bash
cd backend
export UV_PROJECT_ENVIRONMENT=...   # only if a machine-wide value points elsewhere
export VERITAS_TEST_DATABASE_URL=postgresql+psycopg://postgres@localhost:5432/postgres
export VERITAS_ANVIL=/path/to/anvil   # or have anvil on PATH
uv run pytest                         # everything
uv run pytest tests/evidence          # one folder
uv run pytest -k recovery             # by name
```

Without `VERITAS_TEST_DATABASE_URL`, tests that need PostgreSQL are skipped; without Anvil, those
that need a chain are. Each test session creates its own database (`veritas_test_<8 hex>`),
migrates it with Alembic and drops it at the end, and runs its own Anvil, so sessions can run
side by side. Tables are emptied before every test.

## How the tests are built

- **Real dependencies, not mocks.** Database tests run against PostgreSQL with PostGIS, because
  the triggers, partial unique indexes and geofence maths are part of what is tested. Chain
  tests deploy the real contracts to Anvil and drive them through the relayer and the indexer,
  the same code that runs in production. Only the card provider, the bank and IPFS are stand-ins
  (`veritas.mocks`, `FakeIpfs`), and they are reached over the same interfaces as the real ones.
- **End-to-end flows.** The `test_flow_*` files each follow one story from the first request to
  the last event on-chain, with a short docstring that tells the story.
- **Every refusal says why.** Tests check the error code and usually the wording, because a
  refusal a person cannot act on is a bug too.

Shared helpers:

| File | What it gives the tests |
| - | - |
| `conftest.py` | The test database, the app and its client, login, Anvil and a fresh deployment of the contracts |
| `chainkit.py` | Starting Anvil and mining blocks |
| `api/conftest.py`, `api/support.py` | Logged-in people (admin, charity admin, officer, field worker), a verified charity and contractor, response helpers |
| `api/flowkit.py` | Launching the example project on-chain, donating, delivering webhooks, running the relayer and indexer |
| `api/decisionkit.py` | Real field evidence for the decision flows (capture, checks, signing), officer and donor signatures, moving chain time |
| `evidence/kit.py` | Made-up photos and captures, manifests, device signatures, attestation tokens and the evidence clock |
| `fixtures/` | Merkle vectors made with OpenZeppelin's own JavaScript library (`make_merkle_vectors.mjs`) |

## Core: values and formats (no database)

| Test | What it checks | Why |
| - | - | - |
| `test_money.py` | Parsing and formatting manat amounts as integer qəpik, and splitting an amount exactly | Money is never a float; a split must always add up to the total |
| `test_allocation.py` | How a donation is split over milestones (pro rata over what is still needed, or in order) | Every qəpik lands somewhere and no milestone is overfunded |
| `test_identifiers.py` | VÖEN, Azerbaijani IBAN and phone number validation | Bad identifiers are refused at the door, not discovered at payout |
| `test_canonical.py` | RFC 8785 canonical JSON, including Azerbaijani text and key order | Anything hashed must be hashed over exactly one spelling of the document |
| `test_hashing.py` | SHA-256 helpers and hex round trips | Hashes are compared byte for byte everywhere |
| `test_passport.py` | The Project Passport schema: the example validates, its hash is pinned, inconsistent Passports and bad sites are refused, checklists fit one capture session | The Passport is the promise donors fund; its rules and hash must never drift |
| `test_project.py` | The on-chain project config derived from a Passport, and its hash | The escrow enforces exactly the rules the Passport states |
| `test_merkle.py` | Merkle trees and donation leaves against OpenZeppelin's own vectors | A donor's proof built here must verify in the contracts |
| `test_eip712.py` | EIP-712 type strings, digests, signatures (low s only) and the JSON the app signs | The backend and the contracts must agree on every signed byte |
| `test_contract_vectors.py` | The Solidity fixture signed in Python matches what the Python code makes today | Keeps `contracts/test/PythonSigned.t.sol` honest when Python changes |
| `test_webhooks.py` | Signing and verifying card provider webhooks | Only signed, fresh webhooks can create a donation |

## Database (`db/`)

| Test | What it checks | Why |
| - | - | - |
| `test_migrations.py` | The migrations build exactly what the models describe, and undo cleanly | Code and schema can never disagree silently |
| `test_schema.py` | What PostgreSQL enforces by itself: unique keys, checks, final rows | The data stays right even if application code has a bug |

## Chain plumbing (`chain/`)

| Test | What it checks | Why |
| - | - | - |
| `test_codec.py` | Contract call arguments survive JSON in the outbox, and events decode | The outbox stores calls as JSON; nothing may be lost on the way |
| `test_contracts.py` | Artifacts, the deployment file, and launching the example Passport on Anvil | The backend talks to exactly the contracts that were built |

## API and end-to-end flows (`api/`)

| Test | What it checks | Why |
| - | - | - |
| `test_health.py` | Liveness, readiness (database and PostGIS), the error format and OpenAPI | Operators and the app rely on one predictable error shape |
| `test_settings.py` | Settings from the environment, and what production refuses | Development shortcuts must never reach production |
| `test_limits.py` | Body size limits: small for JSON, large only for file uploads, always the JSON error | No one can make the API parse half a gigabyte before logging in |
| `test_assistant.py` | The assistant: what it sends the model (rules, facts, `store: false`), signed earlier replies and forged ones left out, plain prompt injections refused without a model call, an answer that leaks its rules withheld, hidden characters removed, the per-visitor and daily limits, the model failing | A chat on a public page is a way in for abuse and for prompt injection |
| `test_assistant_route.py` | The real app serves the assistant, and says when it is off | Wired in, not only written |
| `test_auth.py` | Phone login with one-time codes: hashing, attempts, expiry, rate limits, logout | Accounts are only as safe as the login |
| `test_demo_account.py` | The demo account: the seed script makes it with the published email and password, and puts it back after someone changes or locks it | The judges' way in must always work |
| `test_demo_login.py` | The demo buttons' sign-in: refused unless switched on; the donor and the organisation each get a session; the organisation is verified, with a verified contractor and an officer, and can publish the example Passport; signing in again reuses the same accounts; any other kind is refused | One click must open a demo that works, and nothing else |
| `test_password_auth.py` | Email and password accounts: scrypt hashes, one account per email, the lock after wrong passwords, emailed links to set a new one, changing it | For most people on the web, the password is the way in |
| `test_web_sign_in.py` | Google sign-in with a Firebase ID token: Google's signature, the project, expiry, a verified email, joining the account that has the email, key caching, CORS | A forged or stale token must never become a session |
| `test_devices.py` | Registering a phone's key, revoking it, logging out everywhere | A lost phone must lose every session it had |
| `test_storage.py` | Private file storage: keys cannot escape its root | Evidence originals stay private |
| `test_cid.py` | Our CID calculation matches IPFS | Anchored CIDs must point at the published files |
| `test_onboarding.py` | Charities, contractors and officers from registration to verification | Only verified parties can launch or be paid |
| `test_problems.py`, `test_passports.py` | Passport drafts with readable problems, and publishing | A charity is told exactly what to fix |
| `test_relayer.py` | The relayer and indexer alone: failures, crashes, fee bumps, repeats | A chain call happens exactly once, even across crashes |
| `test_worker.py` | The worker process: relayer, indexer, evidence and jobs per tick, and surviving a failing part | One broken part must not stop the rest |
| `test_flow_launch.py` | Publishing a Passport launches the project on-chain and the events come back | Phase 4 end to end |
| `test_flow_donation.py` | A card payment becomes an "in escrow" receipt with a Merkle proof; reconciliation | Phase 5 end to end |
| `test_money_edges.py` | A project that stops while donations are in flight; a donation bigger than the need | Money at the edges never gets stuck |
| `test_flow_evidence.py` | Evidence from a phone to a check report anchored on a real escrow; photos published only once confirmed | Phase 6 end to end |
| `test_flow_payout.py` | From card donations to the contractor's payout, on real evidence | Phase 8 end to end, with no critical alert along the way |
| `test_flow_decisions.py` | Pay-on-Proof, overrides and rejections, a payout the bank cannot make, a missed deadline | The other roads through Phase 8 |
| `test_decision_refusals.py` | Decision and stop endpoints refuse what the contracts would refuse | A refusal comes with a reason, not a reverted transaction |
| `test_decision_signers.py` | An officer's Safe (ERC-1271), high-s signatures, decisions and votes signed again after a refusal, votes during a key move, stopped projects | The API accepts exactly what the escrow accepts |
| `test_flow_stop.py` | A stopped project: refunds, redirects and defaults, with a charity key change and a stranger trying to interfere | Every donor's money comes back or moves on |
| `test_flow_recovery.py` | Moving a receipt to a new key, with the old phone or after losing it; strangers, late cards, guessing and refusals | A donor's identity cannot be taken over |
| `test_flow_amendment.py` | Changing the contractor needs the donors' vote | A live Passport changes only with consent |

## Evidence (`evidence/`)

| Test | What it checks | Why |
| - | - | - |
| `test_capture.py` | Capture sessions: the challenge code, geofence, checklist, and when a session is refused | Evidence starts with a code that proves when it was taken |
| `test_uploads.py` | What is stored and what is refused: hashes, types, damaged EXIF, MPO, decompression bombs, impossible times, revoked keys | Bad or hostile files are refused before anything is stored |
| `test_manifest.py` | The signed manifest: canonical, honest about the uploads, signed by the phone, malformed input refused | The bundle hash covers exactly what was captured |
| `test_attestation.py` | App attestation: the development scheme and the production stand-in | Production never accepts the development token |
| `test_checks.py` | Each deterministic check with evidence that passes and evidence that fails | Every failed check says why |
| `test_reuse.py` | Check 5: reused photos, near copies, copies stored later, crafted decoys | A photo cannot be used twice, and an original is never blamed for its copy |
| `test_report.py` | The check report's canonical bytes and pinned hash | The anchored report hash means the same thing forever |
| `test_redaction.py` | Metadata stripped and faces and plates blurred in the public copy | Nothing personal goes to IPFS |
| `test_pipeline.py` | The evidence worker: checks, the private public copy, pinning after signing, retries and alerts | One bad bundle cannot hold up the others, and nothing unconfirmed is published |
| `test_ipfs.py` | The Kubo client against a mock transport, and the fake | CIDs from IPFS match what we anchor |
| `test_anchoring.py` | The charity's signature, the launch key, void bundles, re-sent checks | Evidence the chain refused never blocks a milestone |
| `test_events.py` | A bundle is anchored only when the chain recorded what was signed | The database and the chain tell donors one story |
| `test_reading.py` | Who reads what: reviewers see everything (code, manifest, redacted copies), the public sees what was anchored | Private evidence stays private |
| `test_schema.py` | Evidence rows the database keeps final: checks, reports, signed copies, listed files | What was anchored cannot be edited afterwards |
