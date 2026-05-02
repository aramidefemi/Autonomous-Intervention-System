"""LangGraph watchtower: rules gate, optional LLM chain, one persisted decision."""

from __future__ import annotations

import operator
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from ais.models import (
    Delivery,
    GraphTraceStep,
    RiskLevel,
    WatchtowerDecision,
    WatchtowerGraphTrace,
)
from ais.watchtower.evaluator import RulesEvaluator, WatchtowerEvaluator
from ais.watchtower.rules import decide_from_rules
from ais.watchtower.signals import WatchtowerSignals

GRAPH_NAME = "watchtower"
GRAPH_VERSION = "1"
_SUMMARY_MAX = 500


def _clip(text: str, n: int = _SUMMARY_MAX) -> str:
    if len(text) <= n:
        return text
    return text[: n - 3] + "..."


def _summarize_signals(signals: WatchtowerSignals) -> str:
    return _clip(
        f"staleness_s={signals.staleness_seconds}, eta_delta_min={signals.eta_delta_minutes}"
    )


def _compress_events(events: list[dict]) -> str:
    if not events:
        return "events=0"
    tail = events[-10:]
    parts: list[str] = []
    for e in tail:
        et = e.get("event_type") or e.get("eventType") or "?"
        parts.append(str(et))
    return _clip(f"n={len(events)} tail_types=[{','.join(parts)}]")


class WatchtowerGraphState(TypedDict, total=False):
    delivery_id: str
    delivery: Delivery
    signals: WatchtowerSignals
    events: list[dict]
    evaluator_kind: Literal["rules", "nvidia"]
    thread_id: str
    run_id: str
    rules_decision: WatchtowerDecision
    candidate_decision: WatchtowerDecision
    decision: WatchtowerDecision
    next_route: Literal["finalize", "llm"]
    llm_path_taken: bool
    compressed_events_summary: str
    trace_steps: Annotated[list[GraphTraceStep], operator.add]
    route_labels: Annotated[list[str], operator.add]


def _step(
    *,
    node_name: str,
    source: str,
    started: datetime,
    ended: datetime,
    input_summary: str,
    output_summary: str,
    agent_name: str | None = None,
    extra: dict[str, Any] | None = None,
) -> GraphTraceStep:
    return GraphTraceStep(
        nodeName=node_name,
        agentName=agent_name,
        startedAt=started,
        endedAt=ended,
        inputSummary=_clip(input_summary),
        outputSummary=_clip(output_summary),
        source=source,
        extra=extra,
    )


def _evaluator_kind(ev: WatchtowerEvaluator) -> Literal["rules", "nvidia"]:
    if isinstance(ev, RulesEvaluator):
        return "rules"
    from ais.llm.nvidia import NvidiaWatchtowerEvaluator

    if isinstance(ev, NvidiaWatchtowerEvaluator):
        return "nvidia"
    return "rules"


def build_watchtower_graph(evaluator: WatchtowerEvaluator) -> StateGraph:
    """Compile a graph that closes over ``evaluator`` (rules-only or NVIDIA LLM)."""

    async def rules_gate(state: WatchtowerGraphState) -> dict[str, Any]:
        t0 = datetime.now(UTC)
        did = state["delivery_id"]
        sig = state["signals"]
        rd = decide_from_rules(sig, delivery_id=did)
        t1 = datetime.now(UTC)
        step = _step(
            node_name="rules_gate",
            source="rules",
            started=t0,
            ended=t1,
            input_summary=_summarize_signals(sig),
            output_summary=f"risk={rd.risk.value} reason={rd.reason}",
        )
        kind = state["evaluator_kind"]
        out: dict[str, Any] = {
            "rules_decision": rd,
            "trace_steps": [step],
            "route_labels": ["rules_gate"],
        }
        if kind == "rules":
            out["candidate_decision"] = rd
            out["next_route"] = "finalize"
            return out
        if rd.risk == RiskLevel.LOW and rd.reason == "nominal":
            out["candidate_decision"] = rd
            out["next_route"] = "finalize"
            return out
        out["next_route"] = "llm"
        return out

    async def signal_compressor(state: WatchtowerGraphState) -> dict[str, Any]:
        t0 = datetime.now(UTC)
        summary = _compress_events(state["events"])
        t1 = datetime.now(UTC)
        step = _step(
            node_name="signal_compressor",
            source="rules",
            started=t0,
            ended=t1,
            input_summary=f"events_n={len(state['events'])}",
            output_summary=summary,
        )
        return {
            "compressed_events_summary": summary,
            "trace_steps": [step],
            "route_labels": ["signal_compressor"],
        }

    async def risk_synthesizer(state: WatchtowerGraphState) -> dict[str, Any]:
        t0 = datetime.now(UTC)
        d = await evaluator.evaluate(
            delivery_id=state["delivery_id"],
            delivery=state["delivery"],
            signals=state["signals"],
            events=state["events"],
        )
        t1 = datetime.now(UTC)
        step = _step(
            node_name="risk_synthesizer",
            source="llm",
            agent_name="nvidia_watchtower",
            started=t0,
            ended=t1,
            input_summary=state.get("compressed_events_summary", ""),
            output_summary=f"risk={d.risk.value} reason={_clip(d.reason, 120)}",
            extra={"source": d.source},
        )
        return {
            "candidate_decision": d,
            "llm_path_taken": True,
            "trace_steps": [step],
            "route_labels": ["risk_synthesizer"],
        }

    async def finalize(state: WatchtowerGraphState) -> dict[str, Any]:
        t0 = datetime.now(UTC)
        cand = state["candidate_decision"]
        steps = list(state.get("trace_steps", []))
        t_merge = datetime.now(UTC)
        steps.append(
            _step(
                node_name="merge_finalize",
                source="rules",
                started=t0,
                ended=t_merge,
                input_summary=f"steps={len(steps) - 1}",
                output_summary=f"risk={cand.risk.value} signal_source={cand.source}",
            )
        )
        trace = WatchtowerGraphTrace(
            graphName=GRAPH_NAME,
            graphVersion=GRAPH_VERSION,
            threadId=state.get("thread_id"),
            runId=state.get("run_id"),
            steps=steps,
            routeTaken=list(state.get("route_labels", [])) + ["merge_finalize"],
        )
        src = cand.source
        if state.get("llm_path_taken") and src == "llm":
            src = "langgraph"
        decision = cand.model_copy(update={"graph_trace": trace, "source": src})
        return {"decision": decision}

    g: StateGraph = StateGraph(WatchtowerGraphState)
    g.add_node("rules_gate", rules_gate)
    g.add_node("signal_compressor", signal_compressor)
    g.add_node("risk_synthesizer", risk_synthesizer)
    g.add_node("finalize", finalize)

    def route_after_rules(state: WatchtowerGraphState) -> str:
        return state.get("next_route", "finalize")

    g.add_edge(START, "rules_gate")
    g.add_conditional_edges(
        "rules_gate",
        route_after_rules,
        {"finalize": "finalize", "llm": "signal_compressor"},
    )
    g.add_edge("signal_compressor", "risk_synthesizer")
    g.add_edge("risk_synthesizer", "finalize")
    g.add_edge("finalize", END)
    return g


async def run_watchtower_graph(
    *,
    delivery_id: str,
    delivery: Delivery,
    signals: WatchtowerSignals,
    events: list[dict],
    evaluator: WatchtowerEvaluator,
    ingest_idempotency_key: str | None,
) -> WatchtowerDecision:
    """Run the compiled graph; returns a decision with ``graph_trace`` set."""
    graph = build_watchtower_graph(evaluator)
    app = graph.compile()
    thread = f"{delivery_id}:{ingest_idempotency_key or 'none'}"
    result = await app.ainvoke(
        {
            "delivery_id": delivery_id,
            "delivery": delivery,
            "signals": signals,
            "events": events,
            "evaluator_kind": _evaluator_kind(evaluator),
            "thread_id": thread,
            "run_id": str(uuid.uuid4()),
            "trace_steps": [],
            "route_labels": [],
            "llm_path_taken": False,
        }
    )
    return result["decision"]
