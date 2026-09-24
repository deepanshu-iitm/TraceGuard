"""Sync wrappers around official tigergraph-mcp tools."""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

from backend.config import settings


_VERTEX_PARAMS = {
    "get_case_facts": ("t",),
    "investigate_txn": ("t",),
    "next_chain": ("t",),
    "shared_cards_on_device": ("d",),
    "device_fanout": ("d",),
    "device_degree": ("d",),
    "email_fanout": ("e",),
    "region_fanout": ("r",),
    "card_component": ("c",),
    "get_investigation_case": ("c",),
}


def run_installed_query(query_name: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Official tigergraph__run_installed_query, used by the investigation agent."""
    from tigergraph_mcp.tools import run_installed_query as mcp_run_installed_query

    _ensure_env()
    payload = _parse(
        _await(
            mcp_run_installed_query(
                query_name, _query_params(query_name, params or {}), graph_name=settings.tg_graphname
            )
        )
    )
    result = payload.get("result", payload) if isinstance(payload, dict) else payload
    if not isinstance(result, list):
        raise TypeError(f"{query_name} MCP result was {type(result).__name__}, expected a list")
    return result


def _query_params(query_name: str, params: dict[str, Any]) -> dict[str, Any]:
    out = dict(params)
    for key in _VERTEX_PARAMS.get(query_name, ()):
        value = out.get(key)
        if value is not None and not isinstance(value, (tuple, list)):
            out[key] = (value,)
    return out


def add_nodes(vertex_type: str, vertices: list[dict[str, Any]]) -> dict[str, Any]:
    """Official tigergraph-mcp add_nodes."""
    from tigergraph_mcp.tools import add_nodes as mcp_add_nodes

    _ensure_env()
    payload = _parse(_await(mcp_add_nodes(vertex_type, vertices, graph_name=settings.tg_graphname)))
    return payload if isinstance(payload, dict) else {"result": payload}


def add_edge(
    from_type: str,
    from_id: str,
    edge_type: str,
    to_type: str,
    to_id: str,
) -> None:
    """Official tigergraph-mcp add_edge."""
    from tigergraph_mcp.tools import add_edge as mcp_add_edge

    _ensure_env()
    _parse(
        _await(
            mcp_add_edge(
                source_vertex_type=from_type,
                source_vertex_id=from_id,
                edge_type=edge_type,
                target_vertex_type=to_type,
                target_vertex_id=to_id,
                graph_name=settings.tg_graphname,
            )
        )
    )


def _ensure_env() -> None:
    import os
    from pathlib import Path

    from tigergraph_mcp.connection_manager import _load_env_file

    env_path = Path(__file__).resolve().parents[2] / ".env"
    _load_env_file(str(env_path) if env_path.is_file() else None)
    mapping = {
        "TG_HOST": settings.tg_host,
        "TG_GRAPHNAME": settings.tg_graphname,
        "TG_USERNAME": settings.tg_username,
        "TG_PASSWORD": settings.tg_password,
        "TG_SECRET": settings.tg_secret,
        "TG_API_TOKEN": settings.tg_api_token,
        "TG_TGCLOUD": "true" if settings.tg_tgcloud else "false",
    }
    for key, value in mapping.items():
        if value and not os.environ.get(key):
            os.environ[key] = str(value)


_LOOP: asyncio.AbstractEventLoop | None = None


def _await(coro: Any) -> Any:
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is not None and running.is_running():
        box: list[Any] = []
        error: list[BaseException] = []

        def worker() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                box.append(loop.run_until_complete(coro))
            except BaseException as exc:
                error.append(exc)
            finally:
                loop.close()

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        if error:
            raise error[0]
        return box[0]
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP.run_until_complete(coro)


def _parse(contents: list[Any]) -> Any:
    if not contents:
        raise RuntimeError("empty tigergraph-mcp response")
    raw = contents[0].text if hasattr(contents[0], "text") else str(contents[0])
    raw = raw.strip()
    start = raw.find("{")
    if start < 0:
        raise RuntimeError(raw[:240])
    decoder = json.JSONDecoder()
    try:
        parsed, _offset = decoder.raw_decode(raw, start)
    except json.JSONDecodeError as exc:
        raise RuntimeError(raw[:240]) from exc
    if parsed.get("success") is False:
        raise RuntimeError(parsed.get("error") or parsed.get("summary") or raw[:240])
    return parsed.get("data") or {}
