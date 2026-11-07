# Veritas

Donations that move only when the work is proven.

Veritas is a donation platform for Azerbaijan. Before a registered charity raises any money, it publishes a Project Passport: the total amount, a line-item budget for each milestone, how the work will be done, the contractor doing it (identified by VÖEN), the proof each milestone needs, and who has the right to decide. Donations wait in milestone escrow. For each milestone the charity submits evidence captured inside the Veritas app, automated checks and an AI review go through it, and the donors who paid for that milestone vote on releasing the money. Approved funds go straight to the verified contractor against an invoice. Every step is recorded on a public blockchain, so nobody can quietly change the record or move the money, Veritas included.

AI advises, humans decide, the blockchain enforces.

## How it works

1. **Passport.** The charity publishes its Project Passport. Its hash is locked on-chain at launch, so changing a promise later takes a donor vote.
2. **Donate.** Donors pay by card in manat. A licensed partner bank holds the money, and the donation is recorded on-chain against the project's milestones.
3. **Prove.** The charity captures photos, video and invoices in the app. Each capture carries a one-time code, GPS and a timestamp, and is hashed on the spot.
4. **Check.** Automated checks look at location, timing, reused photos, invoice numbers, the e-kassa receipt and the contractor's VÖEN. A vision model running on our own servers writes a short structured report.
5. **Decide.** A Verification Officer signs a decision, and the donors of that milestone vote, each with their own key.
6. **Pay.** When the Passport's rules are met, the contract issues a release. The bank pays the contractor against the invoice and confirms it on-chain.

## For donors

- Track each donation like a parcel: received, in escrow, allocated to milestone N, evidence submitted, checks passed, approved by donors, paid to contractor, impact delivered. Every status links to its public transaction.
- Vote on the milestones you paid for.
- **Pay-on-Proof:** pledge an amount per milestone, and your card is charged only when a milestone is verified.
- **Failure-to-Redirect:** if a project stops, take a refund or move your money to another verified project.
- A personal proof timeline, an impact map and receipts for tax or CSR reporting.

No wallet, no gas, no crypto. The app handles all of that.

## Stack

| Part | Choice |
| - | - |
| App | Expo (React Native, TypeScript) for iOS, Android and web |
| Backend | Python 3.12, FastAPI, SQLAlchemy, Procrastinate |
| Database | PostgreSQL 17 with PostGIS |
| Evidence checks | Tesseract, OpenCV, imagehash, c2pa-python |
| AI | Ollama with local vision and text models |
| Storage | Private S3-compatible bucket, IPFS |
| Contracts | Solidity, OpenZeppelin, Foundry |
| Chain | web3.py, Polygon Amoy testnet for the demo |

The full design, including exactly what goes on-chain and why, is in [ARCHITECTURE.md](ARCHITECTURE.md).

## Repository layout

Planned:

```
apps/client      Expo app for iOS, Android and web
apps/verifier    static page that checks a receipt against the chain directly
backend/         Python: API, workers, relayer and indexer
contracts/       Solidity contracts and Foundry tests
infra/           Docker Compose and example environment files
```

## Status

Design stage, no code yet.
