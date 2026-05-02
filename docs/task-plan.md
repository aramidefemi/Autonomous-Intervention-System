# AI Delivery Watchtower — Task Plan

This document aligns delivery work with ideas from *The Pragmatic Programmer* (tracer bullets, orthogonality, DRY, design by contract, good-enough software, time-boxed spikes) and breaks work into **phases** with **unit tests per task** and **integration tests per phase**.

---

## Principles we lean on

| Idea | How we use it |
|------|----------------|
| **Tracer bullets** | Ship a thin end-to-end slice early (event → persist → one decision → visible outcome), then widen—not layers of empty “perfect” code. |
| **Orthogonality** | API, worker, agents, DB, and voice each behind clear contracts; swap mocks ↔ real services without rewiring everything. |
| **DRY** | One event schema, one decision log shape, one Mongo access layer—agents never invent parallel models. |
| **Good-enough** | Rules + cheap heuristics before fancy prompts; one voice path that works in the demo. |
| **Prototypes & spikes** | Time-box spikes for LiveKit and LLM reliability; fold in only what proves out. |
| **Design by contract** | Inputs/outputs documented (types + invariants); tests enforce contracts at boundaries. |

---

## Adjustments vs a generic plan

1. **Phase 1 must be a vertical tracer bullet**, not “finish Mongo, then SQS, then agents.”
2. **LLM and LiveKit come after** the pipeline is boring and tested—avoid debugging three moving parts at once.
3. **Integration tests per phase** assert phase outcomes (e.g. event in → expected Mongo state), not every internal function.
4. **Unit tests** focus on **pure** logic: normalization, idempotency keys, scoring helpers, planner policy—keep I/O at the edges.

---

## Phase 0 — Project skeleton and contracts

**What you can run/demonstrate:** `docker compose` (or scripts), API health responds, packages build, CI runs tests.

| Task | Unit tests |
|------|------------|
| Monorepo layout (`apps/api`, `apps/worker`, `packages/core`, `packages/db`, `packages/events`) | — |
| Shared types: `Delivery`, `NormalizedEvent`, `AgentDecision` in `packages/core` | Serialize/deserialize; reject invalid input |
| Event versioning strategy (e.g. `eventType` + `schemaVersion`) | Version compatibility helpers |
| Lint/format/CI script | — |

**Phase integration test:** Health checks for API (and worker if HTTP admin); full test suite green in CI.

---

## Phase 1 — Tracer bullet: webhook → Mongo

**What you can run/demonstrate:** POST a fake delivery event → stored in MongoDB with trace id; query/list proves it.

| Task | Unit tests |
|------|------------|
| Mongo connection + repository: append event, upsert delivery projection | Repo mocks or in-memory fake for query helpers |
| API route: validate payload → normalize → write | Normalizer pure functions; HTTP handler with injected repo |
| Idempotency key on ingest (header or body hash) | Key generation + “duplicate ignored” logic |

**Phase integration test:** HTTP POST → Mongo contains one event + updated delivery document; **duplicate POST → no duplicate side effects**.

---

## Phase 2 — LocalStack SQS: async boundary

**What you can run/demonstrate:** Same event via API enqueues to SQS; worker consumes and writes the same Mongo shape as Phase 1 (or an equivalent worker-only path).

| Task | Unit tests |
|------|------------|
| SQS client wrapper (send/receive/delete, visibility timeout) | Wrapper with mocked AWS client |
| Worker loop: parse message → same normalization path as API | Message parsing; poison-message handling |
| DLQ or retry policy (minimal) | Retry/backoff pure logic where applicable |

**Phase integration test:** Publish to queue → worker processes → Mongo matches expected; **invalid message → DLQ or dead-letter path**, no crash loop.

---

## Phase 3 — Watchtower (rules + optional LLM)

**What you can run/demonstrate:** After events, the system computes health/risk and appends `WatchtowerDecision` (first version can be rule-only).

| Task | Unit tests |
|------|------------|
| Pure “signals” from delivery state (staleness, ETA delta) | Table-driven cases |
| Watchtower: rules engine or LLM adapter behind an interface | Mock LLM; rules fully unit-tested |
| Persist decisions + link to `deliveryId` | Decision record shape |

**Phase integration test:** Seed Mongo with scripted events → processing runs → **decision row exists** with expected risk/reason fields.

---

## Phase 4 — Intervention planner

**What you can run/demonstrate:** From watchtower output, the system proposes call rider / wait / escalate and stores a planned intervention.

| Task | Unit tests |
|------|------------|
| Policy mapping: risk + context → `InterventionPlan` | Matrix of inputs → outputs |
| Cooldown / “don’t over-call” guard | Time-window logic |
| Write `interventions` collection | — |

**Phase integration test:** End-to-end from events → **planned intervention** with correct type; duplicate tick does not double-plan (cooldown).

---

## Phase 5 — Voice (LiveKit)

**What you can run/demonstrate:** Trigger creates a LiveKit session (or test room); transcript saved; structured extraction → Mongo.

| Task | Unit tests |
|------|------------|
| Spike: minimal LiveKit agent → transcript | Mock transport if needed |
| Package `voice`: session lifecycle hooks | State machine or pure transitions |
| NL → structured `issueType` (prompt + parser / JSON schema) | Parser + fixture transcripts |

**Phase integration test:** If full SFU is heavy for CI, use a **contract test**: mock LiveKit webhook/callback with a sample payload → Mongo has transcript + structured fields. Optional manual/nightly full LiveKit run.

---

## Phase 6 — Recovery and consistency

**What you can run/demonstrate:** Kill the worker mid-flow; on restart, processing **resumes** without duplicate intervention (idempotent recovery).

| Task | Unit tests |
|------|------------|
| Checkpoint fields (`lastProcessedSeq`, `openInterventionId`, etc.) | Pure helpers for state migration |
| Recovery job: scan stale “in progress” | Pure classification of rows |

**Phase integration test:** Stop worker after partial write → restart → **exactly-once effect** on intervention side effects, or documented at-least-once + dedupe behavior.

---

## Phase 7 — Demo scenario and hardening

**What you can run/demonstrate:** Scripted bike-breakdown flow end-to-end; basic metrics and logs.

| Task | Unit tests |
|------|------------|
| Simulation script: inject event sequence | Smoke-test the script if feasible |
| Concurrency: optimistic locking or version field on delivery | Conflict resolution logic |
| Structured logging; correlation id through API → worker → agents | — |

**Phase integration test:** Full **happy-path** script: events → risk → plan → (mock) voice outcome → recovery path; optional load smoke.

---

## Test summary

| Level | Scope |
|--------|--------|
| **Unit** | Per-task tables above: pure functions, policies, normalizers, repos behind fakes. |
| **Integration** | One phase gate per phase: real Mongo + LocalStack where relevant; LiveKit optional in CI. |

---

## Suggested execution order

Complete **Phase 0 → 1 → 2** in sequence (tracer + queue). Start **Phases 3–4** only after Phase 2 is green. Run a **LiveKit spike** in parallel if capacity allows, but **merge Phase 5** after Phase 4 contracts exist so voice does not own business rules.
