# Roadmap

How we get from the design in [ARCHITECTURE.md](../ARCHITECTURE.md) to a working demo and then to something a bank would sign off on. Every phase ends with code that runs and has tests. Phases are in dependency order; later ones can overlap once their inputs exist.

## Where things stand

Phase 1 is in progress. Nothing runs end to end yet.

## Ground rules

- Every module ships with tests. A phase is not done until its tests run in CI.
- Money is integer qəpik everywhere: Python, Solidity, JSON and the database.
- Nothing personal goes on-chain or to IPFS.
- Anything that is hashed is hashed over the exact bytes that were published.
- Live escrow contracts are never upgradeable.
- When the code and ARCHITECTURE.md disagree, fix one of them in the same change.

## Phase 1: Backend foundations

The pure building blocks everything else imports. No database, no network.

- [ ] Repo hygiene: gitignore, gitattributes, editorconfig
- [ ] Python package under `backend/` with uv, Ruff and pytest
- [ ] Money in qəpik: parsing, formatting, exact pro rata splits
- [ ] Donation allocation across milestones (pro rata and sequential)
- [ ] Hashing helpers (SHA-256 for documents, keccak256 for chain data)
- [ ] Canonical JSON (RFC 8785) and document hashes
- [ ] Merkle trees identical to OpenZeppelin's `StandardMerkleTree`, checked against vectors from the JS library
- [ ] Donation leaf format shared with the contracts
- [ ] VÖEN, Azerbaijani IBAN and phone number validation
- [ ] Project Passport schema with all consistency rules, an example Passport and a pinned hash
- [ ] CI running lint, format check and tests

Done when CI is green and the example Passport always produces the same hash.

## Phase 2: Contracts

- [ ] Foundry project with OpenZeppelin Contracts 5
- [ ] `vAZN` with bank-signed mint and burn, transfers limited to Veritas contracts
- [ ] `PassportRegistry`, `EscrowFactory` and `MilestoneEscrow` clones with the milestone state machine
- [ ] `DonationLedger` for hourly batch roots
- [ ] `VotingModule` with EIP-712 votes, Merkle eligibility proofs, turnout and fallback rules
- [ ] `ReceiptToken` (ERC-721 plus ERC-5192 lock) and key rotation with a 48 hour delay
- [ ] `BankPayoutVault`, payout confirmation and failed payout handling
- [ ] Stop, refund and redirect
- [ ] EIP-712 message definitions shared with Python, with digests checked on both sides
- [ ] Unit and fuzz tests, deploy scripts for Anvil and Amoy

Done when a whole milestone (create, fund, evidence, decision, vote, release, payout) passes in Foundry tests and messages signed in Python verify on-chain.

## Phase 3: Database and API skeleton

- [ ] SQLAlchemy models and Alembic migrations for the tables in ARCHITECTURE.md section 10
- [ ] FastAPI app: settings, error format, health check, OpenAPI
- [ ] Phone OTP login (codes printed to the log in dev), device key registration
- [ ] Charity and contractor onboarding records (KYB fields, documents)
- [ ] Passport drafts, validation errors a person can read, publishing with stored canonical bytes
- [ ] Tests against a real PostgreSQL with PostGIS

Done when a charity can draft and publish a Passport through the API and the stored bytes hash to the published value.

## Phase 4: Chain plumbing

- [ ] ABIs exported from the Foundry build into the backend
- [ ] `chain_outbox` and the relayer: one lock, nonce handling, fee bumps, finality, retries
- [ ] Indexer: finalised blocks only, `chain_events`, status updates, alerts on mismatches
- [ ] Integration tests against Anvil

Done when publishing a Passport ends with an on-chain project whose events show up in PostgreSQL.

## Phase 5: Money in

- [ ] Mock card provider: signed webhooks, saved cards, merchant-initiated charges, refunds
- [ ] MockBank: escrow account, its own signing key, statements
- [ ] Donation intake: signature check, second lookup, exactly-once insert, allocation leaves
- [ ] Hourly batch: tree, bank attestation, anchoring, receipt tokens, donor proofs
- [ ] Daily reconciliation and the automatic release freeze

Done when a demo card payment becomes an "in escrow" receipt whose Merkle proof verifies on-chain.

## Phase 6: Evidence

- [ ] Capture sessions with one-time challenge codes
- [ ] Upload API, private storage, manifest signatures, app attestation (mocked in dev)
- [ ] Deterministic checks: hashes, geofence, time window, photo reuse with pHash and dHash
- [ ] Redaction and IPFS publishing through Kubo
- [ ] Check report, its hash and anchoring

Done when an evidence bundle goes from upload to an anchored report, and every failed check says why.

## Phase 7: AI and documents

- [ ] Ollama client with JSON schema output and a small labelled evaluation set
- [ ] Challenge code reading and the deliverable check
- [ ] Invoice OCR with Tesseract and the rule that every extracted number must appear in the text
- [ ] e-kassa receipt and VÖEN lookups, with a manual fallback for officers
- [ ] C2PA reading and the AI-image score as advisory signals

Done when the reports for the sample bundles match the hand-labelled expectations.

## Phase 8: Decisions and payouts

- [ ] Officer review and signed decisions, including overrides with a reason
- [ ] Ballots and votes with Merkle eligibility proofs
- [ ] Release instruction, MockBank payout, confirmation and burn
- [ ] Pay-on-Proof charges after an approval
- [ ] Stop, refund and redirect from the API

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
