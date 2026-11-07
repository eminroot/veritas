# Veritas backend

Python services for Veritas: the API, the background workers, the chain relayer and the indexer. The design they follow is in [ARCHITECTURE.md](../ARCHITECTURE.md).

## Setup

You need [uv](https://docs.astral.sh/uv/). It installs Python 3.12 by itself if you don't have it.

```bash
cd backend
uv sync
```

## Everyday commands

```bash
uv run pytest
uv run ruff check .
uv run ruff format .
```

## Layout

```
src/veritas/core/       money, hashing, canonical JSON, identifier checks
src/veritas/chain/      Merkle trees and leaf formats shared with the contracts
src/veritas/domain/     rules that don't depend on storage, such as allocation
src/veritas/passport/   the Project Passport schema
tests/                  pytest suite; fixtures/ holds vectors made with other tools
```

The Merkle vectors in `tests/fixtures/merkle_vectors.json` come from OpenZeppelin's JS library. `make_merkle_vectors.mjs` next to them rebuilds the file.
