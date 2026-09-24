"""MCP server exposing TraceGuard investigation queries.

Run: python -m backend.mcp.server

When TG_HOST is set, tools hit Savanna through pyTigerGraph. Otherwise they
run the same installed-query names against the exported graph CSVs.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from backend.graph.tools import get_graph_tools

mcp = FastMCP("traceguard-tigergraph")


@mcp.tool(name="tigergraph__run_installed_query")
def run_installed_query(queryName: str, params: dict[str, Any] | None = None) -> list:
    """Run an installed GSQL query on FraudGraph."""
    return get_graph_tools().run_installed_query(queryName, params or {})


@mcp.tool(name="get_case_facts")
def get_case_facts(t: str) -> list:
    """Neighborhood of a flagged CardTransaction: card, customer, history, closed cases, device, emails."""
    return get_graph_tools().run_installed_query("get_case_facts", {"t": t})


@mcp.tool(name="investigate_txn")
def investigate_txn(t: str) -> list:
    """Card, customer, closed cases, and history count for a flagged transaction."""
    return get_graph_tools().run_installed_query("investigate_txn", {"t": t})


@mcp.tool(name="shared_cards_on_device")
def shared_cards_on_device(d: str) -> list:
    """Payment cards that share a DeviceProfile — shared-origin graph expansion."""
    return get_graph_tools().run_installed_query("shared_cards_on_device", {"d": d})


@mcp.tool(name="get_investigation_case")
def get_investigation_case(c: str) -> list:
    """Read a persisted InvestigationCase vertex and its graph links."""
    return get_graph_tools().run_installed_query("get_investigation_case", {"c": c})


@mcp.tool(name="upsert_investigation_case")
def upsert_investigation_case(c: str) -> dict:
    """Write a saved exam-case answer onto InvestigationCase vertices and CASE_* edges."""
    from backend.investigate.compose import CASES_DIR
    from backend.investigate.persist import write_investigation_case
    from backend.models.answer import Answer

    path = CASES_DIR / f"{c}.json"
    if not path.is_file():
        raise FileNotFoundError(f"no saved answer for {c}")
    answer = write_investigation_case(
        Answer.model_validate_json(path.read_text(encoding="utf-8"))
    )
    return {
        "case_id": answer.case_id,
        "written_to_graph": answer.case.written_to_graph,
        "graph_case_id": answer.case.graph_case_id,
    }


@mcp.tool(name="investigate_case")
def investigate_case(case_id: str) -> dict:
    """Run the LangGraph investigation for one exam case and persist InvestigationCase."""
    from backend.data import load_case_pack
    from backend.investigate import investigate

    if not any(item.case_id == case_id for item in load_case_pack()):
        raise ValueError(f"unknown case_id: {case_id}")
    return investigate(case_id).model_dump(mode="json")


if __name__ == "__main__":
    mcp.run()
