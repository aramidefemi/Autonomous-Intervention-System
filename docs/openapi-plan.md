# API documentation plan (OpenAPI / Swagger)

FastAPI already publishes **OpenAPI 3** at **`GET /openapi.json`** and interactive UIs at **`GET /docs`** (Swagger UI) and **`GET /redoc`** (ReDoc). No extra framework is required for the baseline.

## Baseline (ship first)

| Deliverable | Action |
|-------------|--------|
| **Stable metadata** | Set `title`, `version`, `description` on `FastAPI()` (already started); add `openapi_tags` when routes grow. |
| **Tagged routes** | Use `tags=` on routers (e.g. `health`, `ingest`, `admin`) so `/docs` stays navigable. |
| **Request/response models** | Every route uses Pydantic models or `response_model=` so the schema stays accurate. |
| **Summaries** | Short `summary=` / `description=` on non-obvious endpoints. |

## Next (when HTTP surface grows)

| Option | When to use |
|--------|-------------|
| **Export OpenAPI in CI** | Add a step that boots the app and writes `openapi.json` to the repo or artifact for diff review on PRs. |
| **Alternative UI** | If Swagger UI feels dated, serve **Scalar** or **Stoplight Elements** as static assets pointing at `/openapi.json`. |
| **Versioning** | Prefix paths (`/v1/...`) or document breaking changes in release notes; keep one OpenAPI doc per major version if needed. |
| **Auth** | Document `securitySchemes` (e.g. API key header) when ingest is protected. |

## What we are *not* doing yet

- Separate **Swagger Editor** host unless we need collaborative editing of specs outside the repo.
- **Code generation** from OpenAPI for clients until there is a stable consumer; Pydantic remains the source of truth server-side.
