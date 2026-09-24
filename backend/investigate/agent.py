"""LangGraph investigation loop: facts, policy, retrieve, compose."""

from __future__ import annotations

import json
import time
from operator import add
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.config import settings
from backend.graph.tools import get_graph_tools
from backend.investigate.compose import compose_answer, decide_investigation
from backend.investigate.explain import explain_answer
from backend.investigate.facts import (
    CaseFacts,
    load_case_facts,
    merge_email_cards,
    merge_next_txns,
    merge_region_cards,
    merge_shared_cards,
)
from backend.investigate.persist import write_investigation_case
from backend.models.answer import Answer
from backend.models.enums import FraudPattern
from backend.models.evidence import Evidence
from backend.retrieve import retrieve_documents


class InvestigateState(TypedDict, total=False):
    case_id: str
    facts: CaseFacts
    pattern: str
    documents: list[Evidence]
    initial_actions: list[str]
    final_actions: list[str]
    tool_calls: int
    tokens: int
    answer: Answer
    steps: Annotated[list[str], add]


def investigate(case_id: str) -> Answer:
    """Run the investigation graph and return the exam answer."""
    started = time.perf_counter()
    answer = investigate_state(case_id)["answer"]
    elapsed = round(time.perf_counter() - started, 2)
    return answer.model_copy(update={"latency_s": elapsed})


def investigate_state(case_id: str) -> InvestigateState:
    return investigation_graph.invoke({"case_id": case_id})


def _facts(state: InvestigateState) -> dict:
    facts = load_case_facts(state["case_id"])
    tools = get_graph_tools()
    live = bool(settings.tg_host.strip())
    calls = 1 if live else 0
    tokens = 0
    selected = _selected_tools(facts)
    extra_tokens = 0
    selected, extra_tokens = _maybe_llm_tools(facts, selected)
    tokens += extra_tokens
    for name, params in selected:
        if live and name == "get_case_facts":
            continue
        payload = _try_query(tools, name, params)
        if payload is None:
            continue
        facts = _apply_tool(facts, name, payload)
        calls += 1
    return {"facts": facts, "tool_calls": calls, "tokens": tokens, "steps": ["facts"]}


def _selected_tools(facts: CaseFacts) -> list[tuple[str, dict[str, str]]]:
    """Choose graph algorithms from the neighborhood, not a fixed three-hop path."""
    selected: list[tuple[str, dict[str, str]]] = [
        ("get_case_facts", {"t": facts.flagged.txn_id}),
        ("investigate_txn", {"t": facts.flagged.txn_id}),
        ("next_chain", {"t": facts.flagged.txn_id}),
        ("card_component", {"c": facts.card.card_id}),
    ]
    if facts.device_profile_id:
        selected.append(("shared_cards_on_device", {"d": facts.device_profile_id}))
        selected.append(("device_fanout", {"d": facts.device_profile_id}))
        selected.append(("device_degree", {"d": facts.device_profile_id}))
    email = facts.flagged.recipient_email or facts.flagged.purchaser_email
    if email:
        selected.append(("email_fanout", {"e": email}))
    if facts.flagged.billing_region:
        selected.append(("region_fanout", {"r": facts.flagged.billing_region}))
    return selected


_TOOL_SYSTEM = """Choose graph investigation tools. Reply JSON {"tools": ["name", ...]}.
Only use names from the offered list. Always keep get_case_facts and investigate_txn.
Do not invent IDs. Prefer fan-out and NEXT when a device, email, or region exists."""


def _maybe_llm_tools(
    facts: CaseFacts, selected: list[tuple[str, dict[str, str]]]
) -> tuple[list[tuple[str, dict[str, str]]], int]:
    if not settings.openai_api_key.strip():
        return selected, 0
    catalog = {name: params for name, params in selected}
    try:
        from backend.llm import complete

        data, tokens = complete(
            _TOOL_SYSTEM,
            json.dumps(
                {
                    "case_id": facts.case.case_id,
                    "channel": facts.flagged.channel,
                    "device": facts.device_profile_id,
                    "email": facts.flagged.recipient_email or facts.flagged.purchaser_email,
                    "region": facts.flagged.billing_region,
                    "offered": list(catalog),
                }
            ),
        )
    except Exception:
        return selected, 0
    names = data.get("tools")
    if not isinstance(names, list):
        return selected, tokens
    kept = [
        (name, catalog[name])
        for name in names
        if isinstance(name, str) and name in catalog
    ]
    for required in ("get_case_facts", "investigate_txn"):
        if required in catalog and required not in {name for name, _params in kept}:
            kept.insert(0, (required, catalog[required]))
    return kept or selected, tokens


def _try_query(tools: Any, name: str, params: dict[str, str]) -> list | None:
    try:
        return tools.run_installed_query(name, params)
    except Exception:
        return None


def _apply_tool(facts: CaseFacts, name: str, payload: list) -> CaseFacts:
    if name in {"shared_cards_on_device", "device_fanout", "device_degree"}:
        return merge_shared_cards(facts, payload)
    if name == "email_fanout":
        return merge_email_cards(facts, payload)
    if name == "region_fanout":
        return merge_region_cards(facts, payload)
    if name == "next_chain":
        return merge_next_txns(facts, payload)
    return facts


def _policy(state: InvestigateState) -> dict:
    decision = decide_investigation(state["facts"])
    return {
        "pattern": decision.pattern.value,
        "initial_actions": [item.action.value for item in decision.initial],
        "final_actions": [item.action.value for item in decision.final],
        "steps": ["policy"],
    }


def _retrieve(state: InvestigateState) -> dict:
    pattern = FraudPattern(state["pattern"])
    return {
        "documents": retrieve_documents(state["facts"], pattern),
        "steps": ["retrieve"],
    }


def _compose(state: InvestigateState) -> dict:
    answer = compose_answer(
        state["facts"],
        documents=state["documents"],
        tool_calls=state.get("tool_calls", 6),
    )
    tokens = state.get("tokens") or 0
    if tokens:
        answer = answer.model_copy(update={"tokens": tokens})
    return {
        "answer": answer,
        "steps": ["compose"],
    }


def _explain(state: InvestigateState) -> dict:
    return {
        "answer": explain_answer(state["answer"]),
        "steps": ["explain"],
    }


def _persist(state: InvestigateState) -> dict:
    return {
        "answer": write_investigation_case(state["answer"]),
        "steps": ["persist"],
    }


def _build_graph():
    graph = StateGraph(InvestigateState)
    graph.add_node("facts", _facts)
    graph.add_node("policy", _policy)
    graph.add_node("retrieve", _retrieve)
    graph.add_node("compose", _compose)
    graph.add_node("explain", _explain)
    graph.add_node("persist", _persist)
    graph.add_edge(START, "facts")
    graph.add_edge("facts", "policy")
    graph.add_edge("policy", "retrieve")
    graph.add_edge("retrieve", "compose")
    graph.add_edge("compose", "explain")
    graph.add_edge("explain", "persist")
    graph.add_edge("persist", END)
    return graph.compile()


investigation_graph = _build_graph()
