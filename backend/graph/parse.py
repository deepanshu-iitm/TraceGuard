"""Parse installed-query JSON from TigerGraph into case-fact payloads."""

from __future__ import annotations

from typing import Any


def vertices(payload: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    for block in payload:
        if key in block:
            raw = block[key]
            if isinstance(raw, list):
                return [_normalize_vertex(item) for item in raw]
            if raw:
                return [_normalize_vertex(raw)]
            return []
    return []


def flagged_vertex(payload: list[dict[str, Any]]) -> dict[str, Any]:
    """Savanna PRINT of a VERTEX param may be only the id; take attributes from history."""
    rows = vertices(payload, "t")
    if not rows:
        raise KeyError("get_case_facts did not return the flagged transaction")
    flagged = rows[0]
    if flagged["attributes"]:
        return flagged
    for item in vertices(payload, "history"):
        if item["v_id"] == flagged["v_id"] and item["attributes"]:
            return item
    return flagged


def accum(payload: list[dict[str, Any]], key: str) -> Any:
    for block in payload:
        if key in block:
            return block[key]
    return None


def _normalize_vertex(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"v_id": str(item), "attributes": {}}
    vertex_id = str(item.get("v_id") or item.get("id") or "")
    attrs = item.get("attributes") or {
        key: value for key, value in item.items() if key not in {"v_id", "v_type", "id"}
    }
    return {"v_id": vertex_id, "v_type": item.get("v_type", ""), "attributes": attrs}
