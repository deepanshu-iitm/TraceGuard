"""MCP server exposing TraceGuard investigation queries.

Run: python -m backend.mcp.server

When TG_HOST is set, tools hit Savanna through pyTigerGraph. Otherwise they
run the same installed-query names against the exported graph CSVs.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from tigergraph_mcp.tool_names import TigerGraphToolName

from backend.graph.tools import get_graph_tools

mcp = FastMCP("traceguard-tigergraph")


@mcp.tool(name=TigerGraphToolName.RUN_QUERY.value)
def run_query(queryName: str, params: dict[str, Any] | None = None) -> list:
    """Official tigergraph-mcp name, mapped to installed FraudGraph queries."""
    return get_graph_tools().run_installed_query(queryName, params or {})


@mcp.tool(name=TigerGraphToolName.RUN_INSTALLED_QUERY.value)
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


@mcp.tool(name="email_fanout")
def email_fanout(e: str) -> list:
    """Payment cards that share a purchaser or recipient email domain."""
    return get_graph_tools().run_installed_query("email_fanout", {"e": e})


@mcp.tool(name="region_fanout")
def region_fanout(r: str) -> list:
    """Payment cards billed in the same region. Informational, not automatic R6."""
    return get_graph_tools().run_installed_query("region_fanout", {"r": r})


@mcp.tool(name="next_chain")
def next_chain(t: str) -> list:
    """Follow NEXT edges from a CardTransaction for episode reconstruction."""
    return get_graph_tools().run_installed_query("next_chain", {"t": t})


@mcp.tool(name="device_degree")
def device_degree(d: str) -> list:
    """Degree centrality of a DeviceProfile: transaction count and unique cards."""
    return get_graph_tools().run_installed_query("device_degree", {"d": d})


@mcp.tool(name="device_fanout")
def device_fanout(d: str) -> list:
    """Cards reached by expanding FROM_DEVICE neighbors of a DeviceProfile."""
    return get_graph_tools().run_installed_query("device_fanout", {"d": d})


@mcp.tool(name="card_component")
def card_component(c: str) -> list:
    """Two-hop component around a PaymentCard: devices, emails, linked cards."""
    return get_graph_tools().run_installed_query("card_component", {"c": c})


@mcp.tool(name="rag_search")
def rag_search(query: str, k: int = 8) -> list:
    """GraphRAG vector search over RagDocument embeddings on FraudGraph."""
    from backend.retrieve.vectors import embed_text

    return get_graph_tools().run_installed_query(
        "rag_search", {"query_vec": embed_text(query), "k": k}
    )


@mcp.tool(name=TigerGraphToolName.SEARCH_TOP_K_SIMILARITY.value)
def search_top_k_similarity(
    query_vector: list[float],
    top_k: int = 8,
    vertex_type: str = "RagDocument",
    vector_attribute: str = "embedding",
) -> list:
    """Official tigergraph-mcp vector search, mapped to FraudGraph rag_search."""
    return get_graph_tools().run_installed_query(
        "rag_search", {"query_vec": query_vector, "k": top_k}
    )


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
