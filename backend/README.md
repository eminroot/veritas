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
