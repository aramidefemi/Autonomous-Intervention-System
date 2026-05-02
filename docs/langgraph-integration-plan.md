# LangGraph integration plan — AI flow, specialized agents, Watchtower persistence

This plan describes how to add **LangGraph** to orchestrate multi-step / multi-agent watchtower reasoning while **keeping the system of record** the existing **`WatchtowerDecision`** path (append-only `watchtower_decisions` in Mongo, same API fields clients already use).

---

## 1. Goals

| Goal | Outcome |
|------|--------|
| **Managed AI flow** | Explicit graph: nodes, edges, conditional routes, optional checkpointing—no ad-hoc nested if/LLM calls. |
| **Specialized agents** | Small, testable units (rules gate, signal analyst, risk synthesizer, tool nodes) instead of one monolithic prompt. |
| **Cost / latency** | Route to LLM subgraphs only when rules are ambiguous or risk is borderline. |
| **Traceability** | Every graph step (agent name, inputs summary, output, model/tool usage) is **persisted with the same watchtower row** the pipeline already writes. |
| **Non-breaking API** | `risk`, `reason`, `action`, `actionReason`, `signals`, `source`, `decidedAt` remain the **authoritative** fields; rich trace is additive. |

---

## 2. Current baseline (for alignment)

- **Today:** `run_watchtower` → one `WatchtowerEvaluator` (`RulesEvaluator` or `NvidiaWatchtowerEvaluator` single completion) → `append_watchtower_decision`.
- **Idempotency:** `ingest_idempotency_key` + unique index on `(delivery_id, ingest_idempotency_key)` must continue to dedupe **one final decision per ingest**.

LangGraph must **not** bypass that: the graph’s **terminal node** produces exactly one `WatchtowerDecision` (or returns an existing one early).

---

## 3. Target architecture

### 3.1 Graph topology (conceptual)

```text
                    ┌─────────────────┐
                    │  load_context   │  (delivery + events from repo — not an LLM)
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  rules_gate     │  deterministic: same as today’s `decide_from_rules`
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │ clear_low    │ ambiguous    │ high_risk_rules
              ▼              ▼              ▼
         ┌─────────┐   ┌───────────┐   ┌──────────────┐
         │ END     │   │ subgraph  │   │ synthesizer  │
         │ (rules  │   │ "deep     │   │ (may merge   │
         │ only)   │   │  eval"    │   │  rules+LLM)  │
         └─────────┘   └─────┬─────┘   └──────┬───────┘
                             └───────────────┘
                                      │
                              ┌───────▼────────┐
                              │ merge_finalize │
                              │ → WatchtowerDecision
                              └────────────────┘
```

- **Specialized “agents”** = **graph nodes** with narrow contracts (inputs/outputs typed), not separate HTTP services.
- **Subgraph** can itself be a small LangGraph (e.g. *signal_analyst* → *policy_hint* → *risk_synthesizer*) or a single LLM node initially (tracer bullet).

### 3.2 Optional patterns to add later

- **Parallel fan-out:** e.g. run “ETA drift scorer” and “intervention history scorer” in parallel, then merge—LangGraph supports this when you need lower latency on independent subscores.
- **Tool nodes:** read-only calls (`get_delivery`, `list_events`, policy lookup) as LangChain tools bound to nodes; **writes** still only through `EventRepository` in finalize or dedicated persistence hooks (keep side effects at the edges).
- **Human-in-the-loop:** interrupt/resume via LangGraph checkpointer only if product requires it; otherwise defer.

---

## 4. Persistence: “everything in the Watchtower model”

### 4.1 Principle

The **final** user-facing decision stays **`WatchtowerDecision`**. Add **one structured place** for the full graph trace so Mongo and OpenAPI stay coherent.

**Recommended approach:**

1. **Extend `WatchtowerDecision`** with an **optional** field, e.g. `graph_trace` (or `watchtowerRun`), typed in Pydantic:
   - `graph_name`, `graph_version`
   - `thread_id` / `run_id` (for correlation with LangGraph checkpointer if enabled)
   - `steps`: ordered list of `{ node_name, agent_name?, started_at, ended_at, input_summary, output_summary, source: "rules" | "llm" | "tool", extra?: dict }`
   - Optional: `route_taken` (list of edge labels) for debugging

2. **Map into Mongo** in `_watchtower_doc`: serialize `graph_trace` as a nested document (or omit if null for backward compatibility).

3. **Keep `signals`** as the **numeric/context snapshot** for analytics (staleness, eta_delta, etc.); do **not** overload `signals` with the full trace unless you want a single field—prefer **`graph_trace`** for clarity.

4. **`source`** field semantics:
   - `rules` — graph exited early at rules gate with no LLM.
   - `langgraph` — graph ran at least one LLM/tool subgraph (or set `langgraph+rules` if you want to stress hybrid).

### 4.2 Idempotency

- Graph invocation must be keyed by the same **`ingest_idempotency_key`** as today.
- On replay: either short-circuit before graph (existing row) or LangGraph **deterministic** thread id = `f"{delivery_id}:{ingest_idempotency_key}"` so checkpoints do not fork duplicates.

### 4.3 What not to do

- Do **not** store only in LangGraph memory without writing Mongo—ops and audits need **`watchtower_decisions`** as today.
- Avoid a second “truth” for risk/action; **specialized agents** contribute to **one** merged `WatchtowerDecision`.

---

## 5. Implementation phases (tracer bullets)

### Phase A — Dependency + skeleton (no behavior change)

- Add `langgraph` (and compatible `langchain-core` stack) to `pyproject.toml`; pin versions.
- Introduce `ais.watchtower.graph` with a **`StateGraph`** definition that currently has **two nodes**: `rules_gate` → `finalize` that wraps existing `RulesEvaluator` / `NvidiaWatchtowerEvaluator` behavior **unchanged**.
- **Unit tests:** graph compiles; single run produces same `WatchtowerDecision` as current evaluator for fixed fixtures.

### Phase B — Trace plumbing

- Add `graph_trace` (or chosen name) to **`WatchtowerDecision`** + Mongo mapping + API schema if exposed.
- Each node appends to state; **finalize** copies trace into `WatchtowerDecision`.
- **Tests:** Mongo document contains nested trace; GET delivery detail still works.

### Phase C — Split specialized nodes (first real split)

- Replace monolithic LLM node with:
  - **`signal_compressor`** (optional cheap model or heuristic: summarize events → short text)
  - **`risk_synthesizer`** (existing JSON schema prompt, tightened)
- **Router:** if `rules_gate` confidence is “clear”, skip LLM subgraph (trace shows `route: early_exit`).

### Phase D — Planner alignment (optional, same doc contract)

- If intervention planner later uses LLM, mirror this pattern: **`InterventionPlan`** remains the stored row; optional `graph_trace` on that model **or** a shared `agent_run_id` linking plans to watchtower rows—only if needed.

### Phase E — Ops hardening

- Metrics: per-node latency, token usage (attach to `steps[].extra`).
- Feature flag: `AIS_WATCHTOWER_GRAPH=1` to toggle graph vs legacy evaluator class.

---

## 6. Testing strategy

| Layer | What to test |
|-------|----------------|
| **Pure** | Router thresholds, merge of rules + LLM output (existing `merge_watchtower_risk_with_rules` style). |
| **Graph** | Deterministic fixtures: same input → same `WatchtowerDecision` + trace shape. |
| **Integration** | Existing `POST /v1/events` → Mongo row includes `graph_trace` when flag on; idempotency unchanged. |

---

## 7. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Version drift LangGraph/LangChain | Pin deps; thin adapter module `ais.watchtower.graph` only. |
| Larger Mongo documents | Cap `input_summary`/`output_summary` length; truncate tool payloads; optional TTL or separate collection **only** if size becomes an issue (still link via `run_id`). |
| Debugging complexity | `graph_trace.route_taken` + structured `steps`; keep **one** finalize node that builds the persisted model. |

---

## 8. Summary

- **LangGraph** becomes the **orchestration layer** for watchtower; **specialized agents** are **nodes** with narrow IO.
- **All traces and final actions** land in **`WatchtowerDecision`** (extended with **`graph_trace`**) and the existing **`watchtower_decisions`** collection, preserving append-only history and idempotency.
- Roll out in **phases**: skeleton parity → trace persistence → split nodes → routing optimizations.

When this plan is approved, the next concrete step is **Phase A** (dependency + graph skeleton mirroring current behavior) plus a short ADR note on the exact `graph_trace` JSON schema for OpenAPI consumers.
