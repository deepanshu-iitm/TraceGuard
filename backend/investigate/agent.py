"""LangGraph investigation loop: facts, policy, retrieve, compose."""

from __future__ import annotations

from operator import add
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.graph.tools import get_graph_tools
from backend.investigate.compose import compose_answer, decide_investigation
from backend.investigate.explain import explain_answer
from backend.investigate.facts import CaseFacts, load_case_facts
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
    answer: Answer
    steps: Annotated[list[str], add]


def investigate(case_id: str) -> Answer:
    """Run the investigation graph and return the exam answer."""
    return investigate_state(case_id)["answer"]


def investigate_state(case_id: str) -> InvestigateState:
    return investigation_graph.invoke({"case_id": case_id})


def _facts(state: InvestigateState) -> dict:
    facts = load_case_facts(state["case_id"])
    tools = get_graph_tools()
    tools.run_installed_query("get_case_facts", {"t": facts.flagged.txn_id})
    tools.run_installed_query("investigate_txn", {"t": facts.flagged.txn_id})
    if facts.device_profile_id:
        tools.run_installed_query("shared_cards_on_device", {"d": facts.device_profile_id})
    return {"facts": facts, "steps": ["facts"]}


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
    return {
        "answer": compose_answer(state["facts"], documents=state["documents"]),
        "steps": ["compose"],
    }


def _explain(state: InvestigateState) -> dict:
    return {
        "answer": explain_answer(state["answer"]),
        "steps": ["explain"],
    }


def _build_graph():
    graph = StateGraph(InvestigateState)
    graph.add_node("facts", _facts)
    graph.add_node("policy", _policy)
    graph.add_node("retrieve", _retrieve)
    graph.add_node("compose", _compose)
    graph.add_node("explain", _explain)
    graph.add_edge(START, "facts")
    graph.add_edge("facts", "policy")
    graph.add_edge("policy", "retrieve")
    graph.add_edge("retrieve", "compose")
    graph.add_edge("compose", "explain")
    graph.add_edge("explain", END)
    return graph.compile()


investigation_graph = _build_graph()
