"""MCP-shaped graph tools: TigerGraph when configured, local CSVs otherwise."""

from __future__ import annotations

from typing import Any, Protocol

from backend.config import settings


class GraphTools(Protocol):
    def run_installed_query(self, name: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Run an installed GSQL query. Same contract as tigergraph__run_installed_query."""

    def upsert_investigation_case(
        self,
        case_id: str,
        attributes: dict[str, Any],
        edges: list[tuple[str, str, str]],
    ) -> None:
        """Write an InvestigationCase vertex and its CASE_* edges."""


def get_graph_tools() -> GraphTools:
    if settings.tg_host.strip():
        return TigerGraphTools()
    from backend.investigate.local_queries import LocalGraphTools

    return LocalGraphTools()


class TigerGraphTools:
    """Installed queries through official tigergraph-mcp tools."""

    def run_installed_query(self, name: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        from backend.mcp.client import run_installed_query

        return run_installed_query(name, params)

    def upsert_investigation_case(
        self,
        case_id: str,
        attributes: dict[str, Any],
        edges: list[tuple[str, str, str]],
    ) -> None:
        from backend.mcp.client import add_edge, add_nodes

        add_nodes("InvestigationCase", [{"id": case_id, **attributes}])
        for edge_type, target_type, target_id in edges:
            try:
                add_edge("InvestigationCase", case_id, edge_type, target_type, target_id)
            except Exception:
                continue


def _connection():
    try:
        from pyTigerGraph import TigerGraphConnection
    except ImportError as exc:
        raise RuntimeError("pyTigerGraph is required when TG_HOST is set") from exc
    conn = TigerGraphConnection(
        host=settings.tg_host,
        graphname=settings.tg_graphname,
        username=settings.tg_username or "tigergraph",
        password=settings.tg_password or "tigergraph",
        gsqlSecret=settings.tg_secret or None,
        tgCloud=settings.tg_tgcloud,
    )
    if settings.tg_api_token:
        conn.apiToken = settings.tg_api_token
    elif settings.tg_secret:
        conn.getToken(settings.tg_secret)
    return conn
