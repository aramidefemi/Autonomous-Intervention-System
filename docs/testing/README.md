# Testing guide

How we run tests, what we use, and how to add new ones. Aligns with [task-plan.md](../task-plan.md): **unit tests** next to pure logic; **integration tests** at phase boundaries (real Mongo, LocalStack when needed).

## Stack (target — matches [task-plan.md](../task-plan.md))

| Layer | Tool | Role |
|--------|------|------|
| Unit + integration runner | **pytest** + **pytest-asyncio** | FastAPI routes and async repos |
| HTTP API | **httpx** `AsyncClient` + `app = create_app()` | In-process ASGI tests; no separate server |
| Mocks | **pytest** `monkeypatch`, **`unittest.mock`**, or **respx** for outbound HTTP | Keep I/O at the edge; unit tests stay pure |
| Mongo / SQS in CI | **Docker Compose** (Mongo + LocalStack) or **Testcontainers** | Integration tests use real URLs from env |
| Coverage | **pytest-cov** | Track critical paths; do not chase 100% on glue code |

*If we add a JS/Deno worker later, use **Vitest** there and invoke both from CI.*

## Commands (once the repo is wired)

Use whatever the root **`pyproject.toml`** / **`Makefile`** defines; the intent is:

| Script | What runs |
|--------|-----------|
| `pytest` or `uv run pytest` | Default: unit tests (markers exclude integration if configured) |
| `pytest -m unit` | Only fast unit tests |
| `pytest -m integration` | Integration tests with `MONGO_URI`, `AWS_ENDPOINT_URL`, etc. |

Integration tests may need `docker compose up -d` first (document that in the phase README or CI job).

## Where to put files

| Kind | Location | Name pattern |
|------|-----------|----------------|
| Unit | Next to source or `tests/unit/` | `test_*.py` or `*_test.py` |
| Integration | `tests/integration/` | `test_*integration*.py` or marker `@pytest.mark.integration` |

Keep **integration** tests few and slow; keep **unit** tests many and fast.

## Adding a unit test

1. Put logic in a **pure function** or a class method that receives dependencies (no global singletons).
2. Add `thing.test.ts` beside `thing.ts` (or under `__tests__`).
3. Use `describe` / `it` / `expect`; inject fakes for DB/SQS.

```python
# example — adjust imports when packages exist
import pytest
from watchtower.normalize import normalize_event

def test_normalize_event_rejects_missing_delivery_id():
    with pytest.raises(ValueError):
        normalize_event({})
```

## Adding an integration test

1. Ensure env vars point at test Mongo/SQS (see `.env.test.example` when added).
2. Start dependencies or let CI start Testcontainers.
3. One test file per **boundary**: e.g. `ingest.integration.test.ts` = POST → Mongo row.
4. Use longer timeouts (`testTimeout` in Vitest config for integration project).
5. Clean collections or use a random DB name per run to avoid flakes.

## CI expectations

- **PR:** unit tests + optional lightweight integration (or Mongo service container).
- **Main / nightly:** full integration including LocalStack if we rely on it.

## Related docs

- [task-plan.md](../task-plan.md) — phases and which integration test proves each phase.
