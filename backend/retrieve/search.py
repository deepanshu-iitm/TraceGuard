"""Retrieve policy, pattern, closed-case, and regulatory text for an investigation."""

from __future__ import annotations

import csv
import math
import re
from collections import Counter
from pathlib import Path

from backend.graph.export import PROCESSED_DIR
from backend.investigate.facts import CaseFacts
from backend.models.enums import FraudPattern
from backend.models.evidence import Evidence, EvidenceSource
from backend.retrieve.corpus import PATTERN_DOCS, POLICY_DOCS, REGULATORY_DOCS, CorpusDoc

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
    facts: CaseFacts, pattern: FraudPattern, limit: int = 4
) -> list[Evidence]:
    from backend.config import settings

    if settings.tg_host.strip():
        from backend.retrieve.vectors import retrieve_from_graph

        hits = retrieve_from_graph(facts, pattern, limit)
        if hits:
            return hits
    query = _query_tokens(facts, pattern)
    policy_pool = POLICY_DOCS
    if pattern is FraudPattern.NONE:
        policy_pool = tuple(
            doc for doc in POLICY_DOCS if doc.doc_id in {"policy:R1", "policy:R3", "policy:R7"}
        )
    hits = [
        _as_evidence(doc)
        for doc in (
            _best(query, policy_pool, pattern),
            _best(query, PATTERN_DOCS, pattern),
            _best(query, _closed_case_docs(), pattern),
            _best(query, REGULATORY_DOCS, pattern),
        )
        if doc is not None
    ]
    return hits[:limit]


def retrieve_similar_cases(
    facts: CaseFacts, pattern: FraudPattern, limit: int = 8
) -> list[str]:
    """Closed-case memory: a few cases on this card, then similar notes graph-wide."""
    ordered: list[str] = []
    seen: set[str] = set()
    for case in facts.closed_cases[:4]:
        seen.add(case.case_id)
        ordered.append(case.case_id)
    query = _query_tokens(facts, pattern)
    ranked = sorted(
        (
            (_score(query, doc, pattern), doc)
            for doc in _closed_case_docs()
            if doc.entity_ids and doc.entity_ids[0] not in seen
        ),
        key=lambda pair: pair[0],
        reverse=True,
    )
    for score, doc in ranked:
        if score <= 0 or len(ordered) >= limit:
            break
        case_id = doc.entity_ids[0]
        if case_id in seen:
            continue
        seen.add(case_id)
        ordered.append(case_id)
    for case in facts.closed_cases:
        if len(ordered) >= limit:
            break
        if case.case_id in seen:
            continue
        seen.add(case.case_id)
        ordered.append(case.case_id)
    return ordered[:limit]


def _best(
    query: set[str],
    docs: tuple[CorpusDoc, ...] | list[CorpusDoc],
    pattern: FraudPattern,
) -> CorpusDoc | None:
    ranked = sorted(
        ((_score(query, doc, pattern), doc) for doc in docs),
        key=lambda pair: pair[0],
        reverse=True,
    )
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


def all_corpus_docs() -> list[CorpusDoc]:
    return list(POLICY_DOCS) + list(PATTERN_DOCS) + list(REGULATORY_DOCS) + _closed_case_docs()


def query_text(facts: CaseFacts, pattern: FraudPattern) -> str:
    parts = [
        pattern.value,
        facts.flagged.channel,
        facts.flagged.product_cd,
        facts.case.trigger_type.value,
        facts.flagged.billing_region or "",
        "verify" if pattern is FraudPattern.NONE else "fraud",
        "device" if facts.device_profile_id else "",
        "email" if facts.flagged.recipient_email or facts.flagged.purchaser_email else "",
        "sar" if pattern is not FraudPattern.NONE else "signal",
    ]
    for case in facts.closed_cases:
        parts.append(case.pattern)
        parts.append(case.outcome)
    if facts.device_profile_id:
        parts.extend(["device", "new"])
    return " ".join(part for part in parts if part)


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
    return _tokens(query_text(facts, pattern))


def _score(query: set[str], doc: CorpusDoc, pattern: FraudPattern) -> float:
    doc_tokens = _tokens(f"{doc.title} {doc.text} {doc.pattern}")
    if not doc_tokens:
        return 0.0
    overlap = query & doc_tokens
    tf = sum(1.0 for token in overlap)
    idf = math.log(1.0 + len(doc_tokens))
    score = tf / math.sqrt(len(doc_tokens)) * idf
    if doc.pattern and doc.pattern == pattern.value:
        score += 4.0
    elif doc.pattern and doc.pattern in query:
        score += 2.0
    counts = Counter(doc_tokens)
    weighted = sum((1.0 + math.log(counts[token])) for token in overlap)
    return score + 0.15 * weighted


def _tokens(text: str) -> set[str]:
    return {token for token in _TOKEN.findall(text.lower()) if token not in _STOP and len(token) > 1}
