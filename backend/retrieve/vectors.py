"""Hashed embeddings on RagDocument vertices. GraphRAG search via vectorSearch."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

from backend.config import settings
from backend.models.enums import FraudPattern
from backend.models.evidence import Evidence, EvidenceSource

VECTOR_DIM = 32
_BATCH = 80
_NONE_POLICY = frozenset({"policy:R1", "policy:R3", "policy:R7"})
_ID_PREFIXES = (
    ("policy_", "policy:"),
    ("pattern_", "pattern:"),
    ("reg_", "reg:"),
    ("closed_case_", "closed_case/"),
)
_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    {
        "a",
        "an",
        "and",
        "the",
        "to",
        "of",
        "in",
        "on",
        "for",
        "or",
        "is",
        "this",
        "that",
        "with",
        "from",
        "was",
        "were",
        "usd",
        "case",
    }
)


def vertex_id(doc_id: str) -> str:
    """Savanna primary ids cannot use ':' in this loading path."""
    return doc_id.replace(":", "_").replace("/", "_")


def doc_id_from_vertex(vid: str) -> str:
    for prefix, original in _ID_PREFIXES:
        if vid.startswith(prefix):
            return original + vid[len(prefix) :]
    return vid


def embed_text(text: str) -> list[float]:
    """Deterministic 32-dim hashed bag-of-tokens, L2-normalized."""
    vec = [0.0] * VECTOR_DIM
    for token in sorted(_tokens(text)):
        digest = hashlib.md5(token.encode("utf-8")).digest()
        bucket = digest[0] % VECTOR_DIM
        sign = 1.0 if digest[1] % 2 == 0 else -1.0
        weight = 1.0 + digest[2] / 255.0
        vec[bucket] += sign * weight
    norm = math.sqrt(sum(value * value for value in vec)) or 1.0
    return [value / norm for value in vec]


def rag_rows() -> list[tuple[str, dict[str, Any]]]:
    from backend.retrieve.search import all_corpus_docs

    rows: list[tuple[str, dict[str, Any]]] = []
    for doc in all_corpus_docs():
        text = doc.text[:8000]
        rows.append(
            (
                vertex_id(doc.doc_id),
                {
                    "title": doc.title[:200],
                    "text": text,
                    "kind": _doc_kind(doc.doc_id),
                    "embedding": embed_text(f"{doc.title} {text} {doc.pattern}"),
                },
            )
        )
    return rows


def upsert_rag_documents() -> int:
    """Write policy, pattern, regulatory, and closed-case notes onto RagDocument."""
    if not settings.tg_host.strip():
        raise RuntimeError("TG_HOST is empty")
    from backend.graph.tools import _connection

    conn = _connection()
    rows = rag_rows()
    written = 0
    for start in range(0, len(rows), _BATCH):
        batch = rows[start : start + _BATCH]
        try:
            conn.upsertVertices("RagDocument", batch)
            written += len(batch)
        except Exception:
            for vertex_id, attrs in batch:
                conn.upsertVertex("RagDocument", vertex_id, attrs)
                written += 1
    return written


def retrieve_from_graph(facts: Any, pattern: FraudPattern, limit: int = 4) -> list[Evidence] | None:
    from backend.graph.tools import get_graph_tools
    from backend.retrieve.search import query_text

    query_vec = embed_text(query_text(facts, pattern))
    try:
        payload = get_graph_tools().run_installed_query(
            "rag_search", {"query_vec": query_vec, "k": max(limit * 4, 16)}
        )
    except Exception:
        return None
    hits = _hits_from_payload(payload)
    if not hits:
        return None
    picked: list[Evidence] = []
    seen_kind: set[str] = set()
    for hit in hits:
        doc_id = doc_id_from_vertex(hit["v_id"])
        kind = str(hit["attributes"].get("kind") or "")
        if pattern is FraudPattern.NONE and kind == "policy" and doc_id not in _NONE_POLICY:
            continue
        if kind in seen_kind:
            continue
        seen_kind.add(kind)
        title = str(hit["attributes"].get("title") or doc_id)
        text = str(hit["attributes"].get("text") or "")
        picked.append(
            Evidence(
                claim=f"{title}: {text}",
                source=EvidenceSource.DOCUMENT,
                ref=f"document:{doc_id}",
                entity_ids=_entity_ids(doc_id),
            )
        )
        if len(picked) >= limit:
            break
    return picked or None


def local_rag_search(query_vec: list[float], k: int) -> list[dict[str, Any]]:
    from backend.retrieve.search import all_corpus_docs

    scored: list[tuple[float, Any]] = []
    for doc in all_corpus_docs():
        vec = embed_text(f"{doc.title} {doc.text} {doc.pattern}")
        scored.append((_cosine(query_vec, vec), doc))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    hits = []
    distances: dict[str, float] = {}
    for score, doc in scored[: max(k, 1)]:
        hits.append(
            {
                "v_id": doc.doc_id,
                "v_type": "RagDocument",
                "attributes": {
                    "title": doc.title,
                    "text": doc.text,
                    "kind": _doc_kind(doc.doc_id),
                },
            }
        )
        distances[doc.doc_id] = round(1.0 - score, 6)
    return [{"v": hits}, {"distances": distances}]


def _doc_kind(doc_id: str) -> str:
    if doc_id.startswith("policy:"):
        return "policy"
    if doc_id.startswith("pattern:"):
        return "pattern"
    if doc_id.startswith("closed_case/"):
        return "closed_case"
    if doc_id.startswith("reg:"):
        return "regulatory"
    return "other"


def _hits_from_payload(payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from backend.graph.parse import vertices

    rows = vertices(payload, "v")
    if rows:
        return rows
    return vertices(payload, "hits")


def _entity_ids(doc_id: str) -> list[str]:
    if doc_id.startswith("closed_case/"):
        return [doc_id.split("/", 1)[1]]
    return []


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def _tokens(text: str) -> set[str]:
    return {token for token in _TOKEN.findall(text.lower()) if token not in _STOP and len(token) > 1}


if __name__ == "__main__":
    count = upsert_rag_documents()
    print(f"upserted {count} RagDocument vertices")
