"""Retrieve policy, pattern, and closed-case text for an investigation."""

from __future__ import annotations

import csv
import re
from pathlib import Path

from backend.graph.export import PROCESSED_DIR
from backend.investigate.facts import CaseFacts
from backend.models.enums import FraudPattern
from backend.models.evidence import Evidence, EvidenceSource
from backend.retrieve.corpus import PATTERN_DOCS, POLICY_DOCS, CorpusDoc

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
_NOTES: list[CorpusDoc] | None = None


def retrieve_documents(
    facts: CaseFacts, pattern: FraudPattern, limit: int = 3
) -> list[Evidence]:
    query = _query_tokens(facts, pattern)
    policy_pool = POLICY_DOCS
    if pattern is FraudPattern.NONE:
        policy_pool = tuple(
            doc for doc in POLICY_DOCS if doc.doc_id in {"policy:R1", "policy:R3", "policy:R7"}
        )
    hits = [
        _as_evidence(doc)
        for doc in (
            _best(query, policy_pool),
            _best(query, PATTERN_DOCS),
            _best(query, _closed_case_docs()),
        )
        if doc is not None
    ]
    return hits[:limit]


def _best(query: set[str], docs: tuple[CorpusDoc, ...] | list[CorpusDoc]) -> CorpusDoc | None:
    ranked = sorted(((_score(query, doc), doc) for doc in docs), key=lambda pair: pair[0], reverse=True)
    if not ranked or ranked[0][0] <= 0:
        return None
    return ranked[0][1]


def _as_evidence(doc: CorpusDoc) -> Evidence:
    return Evidence(
        claim=f"{doc.title}: {doc.text}",
        source=EvidenceSource.DOCUMENT,
        ref=f"document:{doc.doc_id}",
        entity_ids=list(doc.entity_ids),
    )


def _closed_case_docs() -> list[CorpusDoc]:
    global _NOTES
    if _NOTES is None:
        _NOTES = _load_closed_notes(PROCESSED_DIR / "vertices_closed_case.csv")
    return _NOTES


def _load_closed_notes(path: Path) -> list[CorpusDoc]:
    if not path.is_file():
        return []
    docs: list[CorpusDoc] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            notes = row.get("analyst_notes", "").strip()
            if not notes:
                continue
            docs.append(
                CorpusDoc(
                    doc_id=f"closed_case/{row['id']}",
                    title=f"Closed case {row['id']}",
                    text=notes,
                    pattern=row.get("pattern", ""),
                    entity_ids=(row["id"],),
                )
            )
    return docs


def _query_tokens(facts: CaseFacts, pattern: FraudPattern) -> set[str]:
    parts = [
        pattern.value,
        facts.flagged.channel,
        facts.flagged.product_cd,
        facts.case.trigger_type.value,
        facts.flagged.billing_region or "",
    ]
    for case in facts.closed_cases:
        parts.append(case.pattern)
        parts.append(case.outcome)
    if facts.device_profile_id:
        parts.append("device")
        parts.append("new")
    return _tokens(" ".join(parts))


def _score(query: set[str], doc: CorpusDoc) -> int:
    text_tokens = _tokens(f"{doc.title} {doc.text} {doc.pattern}")
    overlap = len(query & text_tokens)
    if doc.pattern and doc.pattern in query:
        overlap += 3
    return overlap


def _tokens(text: str) -> set[str]:
    return {token for token in _TOKEN.findall(text.lower()) if token not in _STOP and len(token) > 1}
