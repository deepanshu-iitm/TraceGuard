"""Hashed embeddings on RagDocument vertices. GraphRAG search via vectorSearch."""

from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache
from typing import Any

from backend.config import settings
from backend.models.enums import FraudPattern
from backend.models.evidence import Evidence, EvidenceSource

VECTOR_DIM = 32
_BATCH = 80
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
    """32-dim embedding: OpenAI projected down when a key is set, else hashed tokens."""
    if settings.openai_api_key.strip():
        from backend.llm import embed_texts

        return _project(embed_texts([text])[0])
    return _hash_embed(text)


def _hash_embed(text: str) -> list[float]:
    vec = [0.0] * VECTOR_DIM
    for token in sorted(_tokens(text)):
        digest = hashlib.md5(token.encode("utf-8")).digest()
        bucket = digest[0] % VECTOR_DIM
        sign = 1.0 if digest[1] % 2 == 0 else -1.0
        weight = 1.0 + digest[2] / 255.0
        vec[bucket] += sign * weight
    return _normalize(vec)


def _project(source: list[float]) -> list[float]:
    out = [0.0] * VECTOR_DIM
    for index, value in enumerate(source):
        digest = hashlib.md5(f"proj-{index}".encode("utf-8")).digest()
        for dim in range(VECTOR_DIM):
            bit = (digest[dim % 16] >> (dim % 8)) & 1
            out[dim] += value if bit else -value
    return _normalize(out)


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vec)) or 1.0
    return [value / norm for value in vec]


def rag_rows() -> list[tuple[str, dict[str, Any]]]:
    from backend.retrieve.search import all_corpus_docs

    docs = all_corpus_docs(full_bank_notes=True)
    texts = [f"{doc.title} {doc.text[:8000]} {doc.pattern}" for doc in docs]
    vectors = _embed_many(texts)
    rows: list[tuple[str, dict[str, Any]]] = []
    for doc, text, vector in zip(docs, texts, vectors):
        stored = doc.text[:8000]
        rows.append(
            (
                vertex_id(doc.doc_id),
                {
                    "title": doc.title[:200],
                    "text": stored,
                    "kind": _doc_kind(doc.doc_id),
                    "embedding": vector,
                },
            )
        )
    return rows


def _embed_many(texts: list[str]) -> list[list[float]]:
    if not settings.openai_api_key.strip():
        return [_hash_embed(text) for text in texts]
    from backend.llm import embed_texts

    out: list[list[float]] = []
    for start in range(0, len(texts), 64):
        out.extend(_project(item) for item in embed_texts(texts[start : start + 64]))
    return out


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


def repair_closed_case_notes() -> int:
    """Write every closed-case history row onto ClosedCase vertices."""
    if not settings.tg_host.strip():
        raise RuntimeError("TG_HOST is empty")
    from backend.mcp.client import add_nodes

    rows = _closed_case_vertices()
    written = 0
    for start in range(0, len(rows), _BATCH):
        batch = rows[start : start + _BATCH]
        add_nodes(
            "ClosedCase",
            [{key: value for key, value in row.items() if key != "card_id"} for row in batch],
        )
        written += len(batch)
    return written


def _closed_case_vertices() -> list[dict[str, Any]]:
    import csv

    from backend.graph.export import RAW_DIR

    path = RAW_DIR / "closed_cases_history.csv"
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            vid = (row.get("case_id") or "").strip()
            if not vid:
                continue
            rows.append(
                {
                    "id": vid,
                    "card_id": (row.get("card_id") or "").strip(),
                    "opened_at": row.get("opened_at") or "",
                    "closed_at": row.get("closed_at") or "",
                    "outcome": row.get("outcome") or "",
                    "pattern": row.get("pattern") or "",
                    "exposure_usd": float(row.get("exposure_usd") or 0),
                    "n_txns": int(float(row.get("n_txns") or 0)),
                    "report_filed": str(row.get("report_filed") or "").strip().lower()
                    in {"true", "1", "yes"},
                    "analyst_notes": (row.get("analyst_notes") or "")[:8000],
                }
            )
    return rows


def retrieve_from_graph(facts: Any, pattern: FraudPattern, limit: int = 4) -> list[Evidence] | None:
    from backend.graph.tools import get_graph_tools
    from backend.retrieve.search import allowed_policies, query_text

    query_vec = embed_text(query_text(facts, pattern))
    try:
        payload = get_graph_tools().run_installed_query(
            "rag_search", {"query_vec": query_vec, "k": max(limit * 16, 64)}
        )
    except Exception:
        return None
    hits = _hits_from_payload(payload)
    if not hits:
        return None
    picked: list[Evidence] = []
    seen_kind: set[str] = set()
    allowed = allowed_policies(pattern)
    want_pattern = (
        f"pattern:{pattern.value}"
        if pattern not in {FraudPattern.NONE, FraudPattern.UNDOCUMENTED}
        else ""
    )
    for hit in hits:
        doc_id = doc_id_from_vertex(hit["v_id"])
        kind = str(hit["attributes"].get("kind") or "")
        if kind == "policy" and doc_id not in allowed:
            continue
        if kind == "pattern" and (not want_pattern or doc_id != want_pattern):
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
                ref=f"query:rag_search({doc_id})",
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
    if not doc_id.startswith("closed_case/"):
        return []
    case_id = doc_id.split("/", 1)[1]
    return [case_id] if case_id in _known_closed_ids() else []


@lru_cache(maxsize=1)
def _known_closed_ids() -> frozenset[str]:
    from backend.graph.export import PROCESSED_DIR
    from backend.retrieve.search import _load_closed_notes

    path = PROCESSED_DIR / "vertices_closed_case.csv"
    return frozenset(doc.entity_ids[0] for doc in _load_closed_notes(path) if doc.entity_ids)


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def _tokens(text: str) -> set[str]:
    return {token for token in _TOKEN.findall(text.lower()) if token not in _STOP and len(token) > 1}


if __name__ == "__main__":
    notes = repair_closed_case_notes()
    count = upsert_rag_documents()
    print(f"repaired {notes} ClosedCase notes; upserted {count} RagDocument vertices")
