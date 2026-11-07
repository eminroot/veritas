# Veritas architecture

This is how Veritas is put together: the parts of the system, the technology, exactly what goes on the blockchain and what does not, and how money and evidence travel from a donor to a contractor. When the design changes, this file changes with it.

## 1. Goals and constraints

- **Donors should not have to trust us.** Every promise, donation, decision and payout has to be checkable from public data, without asking Veritas.
- **No crypto in the donor's face.** Donors pay by card in manat. They never need a wallet, never pay gas and never see a token.
- **Money stays in a bank.** Crypto escrow has no clear legal basis in Azerbaijan yet. The manat sits in an escrow account at a licensed partner bank. The blockchain holds the rules and the record, and tells the bank when money may move.
- **Nothing personal on-chain.** The chain gets hashes, amounts and decisions. Names, phone numbers, card data, faces and bank accounts stay off it.
- **Evidence stays on our servers.** Photos and invoices are analysed with local models. Nothing is sent to an outside AI service.
- **AI advises, humans decide, the chain enforces.** No model output can release money.

## 2. System overview

```mermaid
flowchart LR
  subgraph clients [Clients]
    APP[Expo app<br/>donors, charities, officers]
    VER[Public verifier]
  end
  subgraph servers [Veritas servers]
    API[FastAPI]
    DB[(PostgreSQL<br/>and PostGIS)]
    WRK[Workers]
    AI[Ollama<br/>vision and text models]
    S3[(Private storage<br/>originals)]
    IPFS[(IPFS<br/>public copies)]
    REL[Relayer]
    IDX[Indexer]
  end
  subgraph outside [Outside parties]
    PSP[Card provider]
    BANK[Partner bank]
    CHAIN[Contracts on Polygon]
  end
  APP ==> API
  PSP ==>|signed webhooks| API
  BANK ==>|signed attestations| API
  API ==> DB
  API ==> S3
  WRK ==> DB
  WRK -.-> S3
  WRK ==> AI
  WRK ==> IPFS
  WRK ==>|charges and refunds| PSP
  REL ==>|outbox| DB
  REL ==>|transactions| CHAIN
  IDX -.->|events| CHAIN
  IDX ==> DB
  BANK -.->|release instructions| CHAIN
  VER -.-> CHAIN
  VER -.-> IPFS
```

Thick arrows call or write. Dotted arrows only read.

**Client app.** One Expo codebase for iOS, Android and web. Donors give, track, vote and choose refunds or redirects. Charity field staff capture evidence. Verification Officers, the independent reviewers named in each Passport (an audit firm or a partner organisation, for example), review and sign. The app only talks to our API and never calls the chain, but it holds the user's own signing key (section 5).

**API.** A FastAPI service for accounts, Passports, donations, evidence intake, votes, timelines and the impact map.

**PostgreSQL.** The main database. PostGIS holds project sites and geofences. The same database runs the job queue and the outbox for chain writes, and keeps a copy of every contract event.

**Workers.** Background jobs: the evidence pipeline, hourly donation batches, Pay-on-Proof charges, daily reconciliation and push notifications.

**Ollama.** Serves a vision model and a text model on our own hardware.

**Storage.** Original evidence goes to private S3-compatible storage. A redacted public copy goes to our IPFS node and is pinned by an independent provider as well, so it survives even if we don't.

**Relayer.** The only process that sends transactions, and the one that pays the gas. On its own it cannot release money, vote or confirm a payout (section 5).

**Indexer.** Reads contract events from finalised blocks into PostgreSQL, so timelines load fast. Every status still links to its transaction on the public explorer.

**Card provider.** Takes card payments, keeps saved cards for Pay-on-Proof and handles refunds.

**Partner bank.** Holds the escrow account, pays contractors, and signs deposits, payouts and the daily balance with its own key. Ideally it is also the card acquirer, so it sees every payment as it happens. In the demo this is a small MockBank service with its own key.

**Public verifier.** A static page that checks a receipt against the chain and IPFS through public endpoints. It never calls our API, so it still tells the truth if our servers are down or lying. Anyone can host a copy.

## 3. Tech stack

| Area | Choice | Why |
| - | - | - |
| App | Expo (React Native, TypeScript) | Camera, GPS, secure key storage and app attestation need a real native app. The same code builds the web version. |
| API | Python 3.12, FastAPI, Pydantic v2 | One language for the API, the evidence checks and the models. Pydantic models double as the JSON schema the AI has to follow. |
| Database | PostgreSQL 17 with PostGIS, SQLAlchemy 2, Alembic | One database for data, geofences, jobs and the chain outbox. |
| Jobs | Procrastinate | A task queue on top of PostgreSQL, with retries, locks and periodic jobs. No Redis to run. |
| Image checks | Pillow, OpenCV, imagehash, c2pa-python | Hashes, perceptual hashes, metadata and content credentials. |
| OCR | Tesseract 5 with Azerbaijani, Russian and English | Runs locally and reads Azerbaijani Latin script. |
| AI | Ollama with a vision model (Qwen2.5-VL 7B or Gemma 3 12B to start) and a text model | Local, cheap per check, JSON output that follows a schema. We pick the final models after testing on our own samples. |
| Storage | Private S3-compatible bucket, IPFS (Kubo) plus a second pinning provider | Private originals, public copies anyone can check. |
| Contracts | Solidity 0.8, OpenZeppelin Contracts 5, Foundry | Audited building blocks and fast tests with fuzzing. |
| Chain access | web3.py | The relayer and the indexer stay in Python. |
| Network | Polygon Amoy for the demo, Polygon PoS for production | Public EVM chain, fees well under a cent, mature explorers. Base would work the same way. |
| Maps | MapLibre with OpenStreetMap data | Impact map without a paid map API. |
| PDFs | WeasyPrint | Receipts for tax and CSR reporting. |
| Tooling | uv, Ruff, pytest, Docker Compose | Simple and fast. |

A few of these need a reason.

**PostgreSQL as the job queue.** Every chain write starts as a row in an outbox table, written in the same transaction as the change that caused it. If that transaction commits, the chain write will happen exactly once. If it rolls back, the write never existed. A separate Redis queue can't promise that without extra work. At our volume PostgreSQL carries the queue easily, and Celery with Redis is the fallback if that ever changes.

**Solidity, not Vyper.** Vyper reads like Python, but Solidity has OpenZeppelin's audited contracts and far more auditors. Contract tests are written in Solidity with Foundry, and end-to-end tests in Python with pytest and web3.py against a local Anvil chain.

**No ERC-4337.** Account abstraction is the usual way to hide gas from users. We don't need it, because donors never hold anything on-chain. Each user signs messages with a key on their phone, the relayer submits them and pays, and our contracts check the signature (EIP-712). Same experience, much less infrastructure. If stablecoin donations from abroad come later, smart wallets can come with them.

**vAZN instead of MockUSDC.** The escrows count money in vAZN, an accounting token where 1 vAZN is 1 manat in the bank's escrow account. Only a bank signature can mint or burn it, and it can only move between Veritas contracts, so it can't leave the system or be traded. It keeps the books in manat and makes the escrow balance visible on the explorer. The same escrow can hold a real stablecoin later (section 6).

## 4. What goes on-chain

The rule: the chain stores commitments (hashes), amounts, decisions and the rules that connect them. Everything else lives in PostgreSQL and storage.

| What | On-chain | Off-chain | Why it needs the chain |
| - | - | - | - |
| Project Passport | Hash, IPFS CID, version, milestone amounts, contractor (as a hash), decision rules | The full document | Promises can't be edited once money comes in. Changes need a donor vote. |
| Donations | Hourly Merkle root, totals per milestone, bank signature | Who the donor is, card data, each donation row | Totals can't be inflated or quietly cut, and every donor can prove their donation is in. |
| Escrow and release rules | Balance and state of each milestone, release conditions | Nothing | "No release without approval" is enforced by code that nobody, us included, can change. |
| Evidence | Bundle hash, CID of the public copy, charity signature, time | The files, exact GPS, device data | Donors can prove the evidence they see is exactly what was submitted. |
| Checks and AI review | Report hash and its pass or fail flags | The full report | The report can't be rewritten after donors vote on it. |
| Votes | Every signed vote and the result | Who the voter is | We can't invent, drop or change votes. |
| Officer decisions | Signed decision, hash of the reason | The reason text | Every approval has a key attached to it forever. |
| Payouts | Release instruction, invoice hash, bank confirmation | Bank account details, the invoice file | Every manat leaving escrow matches an approved milestone. |
| Pay-on-Proof | The approval each charge depends on | Card tokens, charge attempts | A charge with no approval behind it is provably wrong. |
| Stop, refund, redirect | Stop decision, each donor's signed choice, moved balances | Card refunds | Money in a stopped project can't get stuck or move without the donor's say. |
| Donation receipt | One locked token per donor per project (ERC-5192) | Who the donor is | The donor's on-chain identity for that project. Votes and choices hang off it. |
| Reconciliation | Daily balance attestation signed by the bank | Bank statements | Releases stop by themselves when the numbers don't match. |

**Off-chain on purpose:** accounts and login, KYC and KYB, card data, all personal data, the evidence files, running the AI, search, comments, notifications, the map, PDF receipts, analytics and fraud scoring. None of these get more trustworthy on a chain, and personal data must never be there.

**What the chain cannot do.** It cannot see the physical world. A staged photo with a valid hash is still staged, and catching that is the job of the evidence checks, the officer and the donors. Also, in bank mode the contract does not hold the manat. It decides when money may move, and any other movement shows up at the next daily reconciliation, which freezes releases. Enforcement fully in code, with the contract holding the money, comes with stablecoin mode.

## 5. Keys and roles

If the relayer signed everything, the chain would only prove what Veritas said. So every party signs its own actions, and the relayer is just the courier that pays the fee.

| Key | Held by | Can do |
| - | - | - |
| Relayer | Veritas backend, in a cloud KMS in production | Pay gas and submit transactions that carry other parties' signatures. Signs only Veritas's own claims: check reports, and the hourly donation batch when the bank can't |
| Charity | A charity staff member's phone | Sign the Passport and evidence |
| Officer | The Verification Officer's phone, or a Safe multisig of their organisation | Approve or reject a milestone |
| Donor | The donor's phone, one key per project | Vote, choose a refund or a redirect |
| Bank | The partner bank (MockBank in the demo) | Sign deposits, payouts, refunds and the daily balance, which mint and burn vAZN |
| Admin | Safe multisig of Veritas and independent members | Register charities and officers, pause releases. Cannot move money or change a live project's rules |

The donor never sees any of this. The app creates the key on first launch, keeps it in the phone's secure storage (iOS Keychain or Android Keystore, through Expo SecureStore) and uses it behind Face ID or a fingerprint. It derives a separate key for each project, so donations to different projects can't be linked on-chain. If the phone is lost, the donor proves who they are again with their phone number and card, and we submit a key rotation that waits 48 hours on-chain, during which the old key can still cancel it. Synced passkeys are a later improvement.

## 6. Contracts

| Contract | What it does |
| - | - |
| `EscrowFactory` | Creates one `MilestoneEscrow` per project as a minimal clone (EIP-1167) of a fixed implementation |
| `PassportRegistry` | Passport hash, CID and version per project. A new version needs a passed amendment vote |
| `MilestoneEscrow` | Milestone balances and states, release conditions, stop, refund and redirect |
| `VotingModule` | Milestone, amendment and stop votes. Checks EIP-712 signatures, eligibility proofs, turnout and majority |
| `DonationLedger` | Takes the hourly batch roots and credits each project's escrow |
| `ReceiptToken` | ERC-721 locked with ERC-5192. One per donor per project, cannot be transferred |
| `vAZN` | The manat mirror. Minted and burned only against bank signatures |
| `BankPayoutVault` | Holds released vAZN until the bank confirms the payout or the refund |

**Milestone states**

1. `Funding`: taking donations
2. `EvidenceSubmitted`: an evidence bundle is anchored
3. `Checked`: the check report is anchored
4. `OfficerApproved`: the officer signed off
5. `Voting`: donors are voting
6. `Approved`: the vote passed, or the Passport's fallback rule applied
7. `Released`: vAZN moved to the payout vault and the bank was instructed
8. `Paid`: the bank confirmed payment to the contractor

There are two side exits. `Rejected` means the officer or the donors said no, and the charity can resubmit until a deadline. `Stopped` means the project has ended and donors choose a refund or a redirect.

**Release conditions.** `release()` only goes through when all of these are true:

- the milestone is `Approved`;
- the instruction names the contractor from the current Passport and carries an invoice hash;
- the amount fits within the milestone's budget and balance;
- there is a balanced bank attestation from the last 36 hours;
- releases are not paused.

**Upgrades.** Live escrows can't be upgraded. A new implementation only applies to projects created after it. The admin multisig can pause releases, which stops money, but nothing it can do will move money or change a running project's rules.

**Settlement adapter.** An escrow holds one ERC-20 asset and doesn't care which one.

- *Bank mode, the default.* The asset is vAZN. On release the escrow sends vAZN to `BankPayoutVault`. The bank pays the contractor in manat, then signs a confirmation with its payment reference, which burns the vAZN. Total vAZN supply always equals the manat in the escrow account.
- *Stablecoin mode, later, for donors abroad.* The asset is a real stablecoin and the escrow pays the contractor's address directly. Nothing else changes.

## 7. Main flows

### 7.1 Launching a project

1. The charity, already verified off-chain, fills in the Passport: the total, milestones with line-item budgets, the method, the contractor's VÖEN, a proof checklist, a time window and a geofence for each milestone, decision rules, and defaults for Pay-on-Proof and for a stop.
2. The API checks the VÖEN against the public taxpayer registry and checks that the milestone budgets add up to the total.
3. The Passport is saved as canonical JSON, stored on IPFS and hashed. The charity signs the hash on their phone.
4. The relayer calls `EscrowFactory.createProject`, which creates the escrow and records the hash, the CID, the milestone amounts and the decision rules. From here on the promises are locked.

### 7.2 A donation

1. The donor picks a project and pays by card. Pay-on-Proof donors save a card instead (7.5).
2. A signed webhook arrives. The API checks the signature, asks the card provider for the payment again to confirm it, and inserts it under a unique constraint on the provider's payment id, so no payment is ever counted twice.
3. The donation is split across milestones by the Passport's rule (by default pro rata over the milestones still being funded). Each part becomes a leaf.
4. Every hour a worker builds one Merkle tree from the new leaves. The bank signs the root and the per-milestone totals, and the relayer anchors them with `DonationLedger.anchorBatch`. The escrows are credited and the matching vAZN is minted into them.
5. Donors who are new to the project get a `ReceiptToken` tied to their key.
6. The receipt now says "in escrow", with the transaction link and the donor's Merkle proof.

If card payments come through a provider other than the partner bank, the money reaches the escrow account a day or two later, when the provider settles. In that case Veritas signs the hourly batch, which only records the donations, and the bank mints the vAZN when it signs the daily attestation for what has settled (7.7). The donor's status moves to "in escrow" at that point. Anything we inflate or drop shows up as a mismatch and freezes releases.

Leaves follow OpenZeppelin's `StandardMerkleTree` format, one per donation per milestone:

```
leaf = keccak256(keccak256(abi.encode(donationId, holder, projectId, milestone, amount, trigger, salt)))
```

`amount` is in qəpik. `holder` is the donor's key for that project. `trigger` is the approval that caused a Pay-on-Proof charge, or zero. `salt` is random and only the donor gets it, so nobody can guess amounts or link leaves from the public root.

### 7.3 Evidence

1. A field worker opens the milestone in the app. The API starts a capture session and returns a one-time challenge code (valid for 15 minutes), the geofence and the proof checklist.
2. The app captures only with its own camera, with no gallery uploads. The code has to be visible in at least one photo, written on paper or shown on a second screen. The app records GPS, accuracy and time, hashes every file with SHA-256, adds an App Attest or Play Integrity token and signs the manifest with the worker's key.
3. The API stores the originals in private storage and starts the pipeline (section 9).
4. When the checks are done, a redacted public copy goes to IPFS, and the relayer anchors the bundle hash, its CID and the hash of the check report.

### 7.4 Decision, vote and release

```mermaid
sequenceDiagram
  participant W as Workers
  participant O as Officer
  participant D as Donors
  participant R as Relayer
  participant C as Contracts
  participant B as Bank
  W->>R: check report hash
  R->>C: recordChecks
  O->>R: signed decision
  R->>C: officerDecide
  C->>C: open the vote for 72 hours
  D->>R: signed votes
  R->>C: castVoteBySig
  C->>C: close the vote, milestone Approved
  R->>C: release with invoice hash
  C->>B: ReleaseInstructed event
  B->>B: pay the contractor in manat
  B->>R: signed payout confirmation
  R->>C: confirmPayout, vAZN burned
```

Voting rules live in the Passport. Our proposed defaults:

- one donor, one vote, for donors with at least 5 AZN on that milestone;
- a 72-hour window;
- a simple majority of the votes cast, with at least 10% turnout;
- if turnout is too low, the window is extended once by 48 hours, and if it is still too low, the officer's decision stands.

A vote is an EIP-712 message (project, milestone, approve, nonce, deadline) signed on the donor's phone. It is submitted with the donor's Merkle proof for that milestone, so the contract can check eligibility without knowing who the donor is.

### 7.5 Pay-on-Proof

1. The donor pledges an amount per verified milestone and saves a card. The card provider keeps the card details, and we keep only a token.
2. When the indexer sees `MilestoneApproved`, a job charges every pledge on that project once (idempotent on pledge and milestone).
3. Successful charges become normal donations in the next hourly batch. Their leaf carries the approval that triggered them, so a donor can check that every charge on their card follows a real approval.
4. By default the money goes to the next milestone, so a contractor's payout never depends on card charges going through. A failed charge is retried once, then the pledge is paused and the donor is told.

### 7.6 Stop, refund and redirect

1. A project stops when the Passport's stop rule fires: a stop vote passes, the charity withdraws, or a milestone deadline passes with no evidence after a grace period.
2. `MilestoneEscrow.stop` freezes the escrow. Money already paid out for finished milestones is spent. Whatever is still in escrow goes back to its donors, milestone by milestone.
3. Each donor has 30 days to sign a choice: a refund to their card, or a redirect to another verified project.
4. A redirect moves the donor's share of vAZN to the other project's escrow in one transaction and gives them a receipt there. A refund sends the share to the payout vault, the card provider refunds the card, and the bank's confirmation burns the vAZN.
5. Donors who don't choose get the default the charity put in the Passport before it raised any money.

### 7.7 Daily reconciliation

1. Once a day a worker compares three numbers at a cut-off block: the vAZN supply on-chain, our ledger in PostgreSQL and the escrow balance on the bank statement.
2. The bank signs an attestation with the balance, the cut-off block number and a hash of the statement. Anyone can read the vAZN supply at that block and compare. When payments settle through a separate card provider, the same attestation mints the vAZN for that day's settled donations.
3. If the numbers differ, the attestation says so, the contracts refuse new releases and we get an alert. Releases also stop if no attestation arrives for 36 hours.

### 7.8 What a donor sees

| Status | Comes from | On-chain record |
| - | - | - |
| Received | Signed webhook from the card provider | Not yet |
| In escrow | Hourly batch | `BatchAnchored`, plus the donor's Merkle proof |
| Allocated to milestone N | The same batch, one leaf per milestone | `BatchAnchored` |
| Evidence submitted | Evidence bundle anchored | `EvidenceSubmitted` |
| Checks passed | Check report anchored | `ChecksRecorded` |
| Approved by donors | Vote closed | `VoteClosed`, `MilestoneApproved` |
| Paid to contractor | Bank confirmation, with the invoice number and VÖEN shown in the app | `ReleaseInstructed`, `PayoutConfirmed` |
| Impact delivered | Last milestone paid, completion report anchored | `ProjectCompleted` |

## 8. Chain plumbing

**Outbox and relayer.** Application code never calls the chain. It writes a row to `chain_outbox` in the same transaction as the business change. The relayer takes rows in order under a single lock, so nonces never collide, then signs, sends, raises the fee if a transaction gets stuck, waits for finality and writes the transaction hash back.

**Indexer.** Polls contract events from finalised blocks, stores them in `chain_events` and moves each record's status forward. If an event doesn't match what the database expected, or an expected event never shows up, it raises an alert.

**Public verifier.** Takes a receipt (holder, leaf data, salt and proof), rebuilds the leaf, checks the proof against the anchored root, then follows the project's events and evidence CIDs. It only uses a public RPC endpoint and an IPFS gateway.

**Costs.** One batch transaction per hour covers every donation in that hour. Receipts, votes and decisions are single transactions of roughly 50,000 to 150,000 gas. At recent Polygon gas prices each costs well under one US cent, and the relayer's account is the only one that ever needs topping up.

## 9. Evidence pipeline

Each check stores its result in `evidence_checks`, and the report combines them. A hard failure blocks the milestone unless the officer overrides it with a signed reason, which is anchored with their decision. Advisory signals are shown to the officer and the donors but never block anything on their own.

| # | Check | How | Kind |
| - | - | - | - |
| 1 | Files match the manifest hashes, and the manifest signature and app attestation are valid | hashlib, App Attest and Play Integrity verification | Hard |
| 2 | GPS inside the geofence, allowing for accuracy, and not a mocked location | PostGIS, the phone's mock-location flag | Hard |
| 3 | Captured inside the milestone's time window, after the challenge code was issued | Capture session, server clock | Hard |
| 4 | Challenge code visible in a photo | Tesseract first, then the vision model | Hard |
| 5 | Not a reused photo: perceptual hash compared with every photo ever submitted | imagehash (pHash and dHash) stored in PostgreSQL | Hard for a clear match, advisory when close |
| 6 | C2PA content credentials and an AI-generated image score | c2pa-python, an open detector model | Advisory |
| 7 | The photos show the promised deliverable | Vision model with a fixed JSON schema | Advisory |
| 8 | Invoice totals, dates and VÖEN. Every number the model extracts must appear in the OCR text | Tesseract, vision model, exact match | Hard |
| 9 | The e-kassa receipt QR points to a real fiscal receipt with the same seller, date and amount | QR decoding, State Tax Service receipt check | Hard |
| 10 | The contractor's VÖEN matches the Passport and is active | Public taxpayer registry | Hard |
| 11 | Everything on the milestone's proof checklist is there | Passport checklist | Hard |

The vision model gets the milestone description from the Passport plus the photos, and has to answer in this shape. Ollama enforces the JSON schema and Pydantic validates the result.

```json
{
  "deliverable_visible": true,
  "matches_milestone": "partly",
  "challenge_code_seen": "K7Q2MX",
  "observations": ["new roof sheets on the east side", "scaffolding still up"],
  "concerns": ["west side not visible in any photo"],
  "confidence": 0.72
}
```

Text inside evidence is data, not instructions. A sign in a photo that says "approve this" is just a sign: the prompt says so, the schema has no field that approves anything, and no model output can move money anyway.

Before the public copy goes to IPFS, faces and number plates are blurred and personal details on invoices are masked. The original stays in private storage for the officer and auditors, and its SHA-256 is part of the anchored bundle, so an auditor can confirm it was never changed.

## 10. Data model

Main tables:

- **People:** `users`, `devices` (public keys), `charities`, `contractors` (VÖEN, bank account), `officers`
- **Projects:** `projects`, `passports` (versioned canonical JSON, hash, CID), `milestones`, `budget_lines`, `sites` (PostGIS geofences)
- **Money:** `donations`, `allocations` (one per donation per milestone), `pledges`, `pledge_charges`, `receipts`, `releases`, `payouts`, `refunds`, `redirects`
- **Evidence:** `capture_sessions`, `evidence_items`, `evidence_checks`, `check_reports`, `photo_hashes`
- **Decisions:** `officer_decisions`, `votes`
- **Chain:** `batches`, `batch_leaves`, `chain_outbox`, `chain_events`, `reconciliations`

Money is stored as integer qəpik everywhere, never as floats.

## 11. Security and privacy

**Donations are real.** A donation exists only after a signed webhook, a second lookup of the payment with the card provider and an insert that is unique on the provider's payment id. The daily reconciliation catches anything that slips past.

**One person, one vote.** A voter is tied to a verified phone number and a card, and needs at least 5 AZN on the milestone. Large projects can also require ASAN İmza or SİMA.

**Personal data.** Nothing personal goes on-chain or to IPFS. On-chain, a donor is a per-project key with no name attached, and leaves are salted. Photos and invoices are redacted before they go public. If a donor asks to be forgotten, we delete the off-chain data, and what is left on-chain is hashes nobody can reverse.

**Keys.** The relayer key lives in a cloud KMS in production and can only do courier work. Officer and admin keys can be Safe multisigs. The bank's key belongs to the bank.

**App integrity.** Evidence is accepted only from the genuine app on an unmodified phone (App Attest, Play Integrity), captured inside the app, with mocked locations rejected.

**Contracts.** No proxies on live escrows, unit and fuzz tests in Foundry, an outside audit before mainnet, and a pause that can stop money but never move it.

**What we still trust.** The bank to report its balance honestly, the card provider to report payments honestly, and officers to do their job. Each of them signs with their own key, so if one of them lies, the lie is permanent and has their name on it.

## 12. Environments

- **Local:** Docker Compose with PostgreSQL and PostGIS, Kubo, Ollama, Anvil, MockBank and a mock card provider. The app runs as an Expo development build.
- **Demo:** contracts on Polygon Amoy, explorer links to amoy.polygonscan.com, MockBank and the card provider's sandbox.
- **Production:** Polygon PoS, keys in KMS and Safe, two IPFS pinning providers, the real partner bank and card provider.

## 13. Open questions

- Which bank holds the escrow account? Will it sign attestations with its own key, or only send statements? Can it also be the card acquirer?
- Which card provider in Azerbaijan supports saved cards with merchant-initiated charges (needed for Pay-on-Proof), and how long after a payment can it still refund a card?
- Does the State Tax Service allow automated e-kassa receipt and VÖEN checks, or do officers open those links by hand at first?
- What do the NGO donation rules require us to collect and report about donors? This only affects the off-chain side.
- Are 10% turnout and the officer fallback the right voting defaults, or should every Passport set its own?
- Should a Pay-on-Proof charge fund the milestone that was just approved, or the next one?
- Where does the virtual assets law stand now? It decides when stablecoin mode becomes possible.
