# Roadmap

How we get from the design in [ARCHITECTURE.md](../ARCHITECTURE.md) to a working demo and then to something a bank would sign off on. Every phase ends with code that runs and has tests. Phases are in dependency order; later ones can overlap once their inputs exist.

## Where things stand

Phase 1 is done: its CI run on GitHub is green. Phases 2 to 6 and 8 are built and pass locally: 74 Foundry tests, and 563 backend tests against PostgreSQL 17 with PostGIS and a local Anvil chain. Those include end-to-end flows that take a card payment, through evidence captured on a phone and checked, all the way to the contractor's payout, and a stopped project back to every donor as refunds and redirects. Each of these phases is done once CI runs its tests green on GitHub; the workflows for the contracts and for the backend with PostGIS and Anvil are in `.github/workflows`.

Phase 7, AI and documents, is next. Until it lands, the evidence report marks the challenge-code, deliverable, invoice, e-kassa, VÖEN and AI-image checks as not run, and the officer reviews those items by hand. Photos stay out of the public copy of evidence until the server has a face and number plate detector: OpenCV 5, which the backend installs, no longer ships the Haar cascades the default detector uses. Even with one, a photo goes public only once the charity admin who signs the bundle confirms it shows no face or plate. App Attest and Play Integrity are not built yet either, so in production every bundle fails the attestation check for now. A live escrow keeps the charity key it was launched with; replacing a lost one is an open question in ARCHITECTURE.md. Nothing is deployed to Amoy yet.

## Ground rules

- Every module ships with tests. A phase is not done until its tests run in CI.
- Money is integer qəpik everywhere: Python, Solidity, JSON and the database.
- Nothing personal goes on-chain or to IPFS.
- Anything that is hashed is hashed over the exact bytes that were published.
- Live escrow contracts are never upgradeable.
- When the code and ARCHITECTURE.md disagree, fix one of them in the same change.

## Phase 1: Backend foundations

The pure building blocks everything else imports. No database, no network.

- [x] Repo hygiene: gitignore, gitattributes, editorconfig
- [x] Python package under `backend/` with uv, Ruff and pytest
- [x] Money in qəpik: parsing, formatting, exact pro rata splits
- [x] Donation allocation across milestones (pro rata and sequential)
- [x] Hashing helpers (SHA-256 for documents, keccak256 for chain data)
- [x] Canonical JSON (RFC 8785) and document hashes
- [x] Merkle trees identical to OpenZeppelin's `StandardMerkleTree`, checked against vectors from the JS library
- [x] Donation leaf format shared with the contracts
- [x] VÖEN, Azerbaijani IBAN and phone number validation
- [x] Project Passport schema with all consistency rules, an example Passport and a pinned hash
- [x] CI running lint, format check and tests

Done when CI is green and the example Passport always produces the same hash.

## Phase 2: Contracts

- [x] Foundry project with OpenZeppelin Contracts 5
- [x] `vAZN` with bank-signed mint and burn, transfers limited to Veritas contracts
- [x] `PassportRegistry`, `EscrowFactory` and `MilestoneEscrow` clones with the milestone state machine
- [x] `DonationLedger` for hourly batch roots
- [x] `VotingModule` with EIP-712 votes, Merkle eligibility proofs, turnout and fallback rules
- [x] `ReceiptToken` (ERC-721 plus ERC-5192 lock) and key rotation with a 48 hour delay
- [x] `BankPayoutVault`, payout confirmation and failed payout handling
- [x] Stop, refund and redirect
- [x] EIP-712 message definitions shared with Python, with digests checked on both sides
- [x] Unit and fuzz tests, deploy scripts for Anvil and Amoy

Done when a whole milestone (create, fund, evidence, decision, vote, release, payout) passes in Foundry tests and messages signed in Python verify on-chain.

## Phase 3: Database and API skeleton

- [x] SQLAlchemy models and Alembic migrations for the tables in ARCHITECTURE.md section 10
- [x] FastAPI app: settings, error format, health check, OpenAPI
- [x] Phone OTP login (codes printed to the log in dev), device key registration
- [x] Charity and contractor onboarding records (KYB fields, documents)
- [x] Passport drafts, validation errors a person can read, publishing with stored canonical bytes
- [x] Tests against a real PostgreSQL with PostGIS

Done when a charity can draft and publish a Passport through the API and the stored bytes hash to the published value.

## Phase 4: Chain plumbing

- [x] ABIs exported from the Foundry build into the backend
- [x] `chain_outbox` and the relayer: one lock, nonce handling, fee bumps, finality, retries
- [x] Indexer: finalised blocks only, `chain_events`, status updates, alerts on mismatches
- [x] Integration tests against Anvil

Done when publishing a Passport ends with an on-chain project whose events show up in PostgreSQL.

## Phase 5: Money in

- [x] Mock card provider: signed webhooks, saved cards, merchant-initiated charges, refunds
- [x] MockBank: escrow account, its own signing key, statements
- [x] Donation intake: signature check, second lookup, exactly-once insert, allocation leaves
- [x] Hourly batch: tree, bank attestation, anchoring, receipt tokens, donor proofs
- [x] Daily reconciliation and the automatic release freeze

Done when a demo card payment becomes an "in escrow" receipt whose Merkle proof verifies on-chain.

## Phase 6: Evidence

- [x] Capture sessions with one-time challenge codes
- [x] Upload API, private storage, manifest signatures, app attestation (mocked in dev)
- [x] Deterministic checks: hashes, geofence, time window, photo reuse with pHash and dHash
- [x] Redaction and IPFS publishing through Kubo
- [x] Check report, its hash and anchoring

Done when an evidence bundle goes from upload to an anchored report, and every failed check says why.

## Phase 7: AI and documents

- [ ] Ollama client with JSON schema output and a small labelled evaluation set
- [ ] Challenge code reading and the deliverable check
- [ ] Invoice OCR with Tesseract and the rule that every extracted number must appear in the text
- [ ] e-kassa receipt and VÖEN lookups, with a manual fallback for officers
- [ ] C2PA reading and the AI-image score as advisory signals

Done when the reports for the sample bundles match the hand-labelled expectations.

## Phase 8: Decisions and payouts

- [x] Officer review and signed decisions, including overrides with a reason
- [x] Ballots and votes with Merkle eligibility proofs
- [x] Release instruction, MockBank payout, confirmation and burn
- [x] Pay-on-Proof charges after an approval
- [x] Stop, refund and redirect from the API

Done when the demo runs from a donation to a contractor payout, and a stopped project returns or moves every donor's money.

## Phase 9: App

- [ ] Expo app shell, navigation, Azerbaijani and English, keys in SecureStore
- [ ] Donor: browse, donate, receipt timeline, vote, pledges, refund or redirect
- [ ] Charity: Passport builder, capture flow with the challenge code and GPS
- [ ] Officer: review queue and decision signing

Done when the whole demo can be done from the app.

## Phase 10: Public pieces

- [ ] Static verifier page that reads the chain and IPFS directly
- [ ] Impact map
- [ ] PDF receipts for tax and CSR reporting

Done when a receipt verifies from a downloaded copy of the verifier page with our API switched off.

## Phase 11: Demo and deployment

- [ ] Docker Compose for the whole stack
- [ ] Amoy deployment, demo seed data and a scripted walkthrough
- [ ] Basic monitoring and alerts

Done when one command brings the demo up and the walkthrough passes.

## Phase 12: Hardening

- [ ] Security review of contracts, API and key handling
- [ ] Load test for batching and the indexer
- [ ] Documentation pass

Done when every open finding is fixed or written down with a reason.
