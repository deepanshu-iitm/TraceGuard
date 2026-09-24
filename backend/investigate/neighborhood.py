"""Neighborhood, timeline, and approval views for the investigation console."""

from __future__ import annotations

from typing import Any

from backend.investigate.analysis import connected_card_ids
from backend.investigate.compose import CASES_DIR
from backend.investigate.facts import CaseFacts, load_case_facts
from backend.models.answer import Answer


def investigation_view(case_id: str) -> dict[str, Any]:
    facts = load_case_facts(case_id)
    answer = _saved_answer(case_id)
    return {
        "case_id": case_id,
        "nodes": _nodes(facts, answer),
        "edges": _edges(facts, answer),
        "timeline": _timeline(facts, answer),
        "approvals": _approvals(answer),
        "policy": _policy(answer),
    }


def _saved_answer(case_id: str) -> Answer | None:
    path = CASES_DIR / f"{case_id}.json"
    if not path.is_file():
        return None
    return Answer.model_validate_json(path.read_text(encoding="utf-8"))


def _nodes(facts: CaseFacts, answer: Answer | None) -> list[dict[str, Any]]:
    flagged = facts.flagged
    nodes = [
        _node(facts.case.case_id, "case", facts.case.case_id),
        _node(facts.card.card_id, "card", facts.card.card_id),
        _node(facts.case.customer_id, "customer", facts.case.customer_id),
        _node(flagged.txn_id, "txn", f"{flagged.txn_id} · {flagged.amount:.2f}"),
    ]
    if facts.device_profile_id:
        nodes.append(_node(facts.device_profile_id, "device", facts.device_profile_id))
    email = flagged.recipient_email or flagged.purchaser_email
    if email:
        nodes.append(_node(email, "email", email))
    if flagged.billing_region:
        nodes.append(_node(flagged.billing_region, "region", flagged.billing_region))
    for card_id in connected_card_ids(facts)[:12]:
        nodes.append(_node(card_id, "card", card_id))
    if answer:
        for txn_id in answer.case.affected_txn_ids[:12]:
            if txn_id != flagged.txn_id:
                nodes.append(_node(txn_id, "txn", txn_id))
        for case_id in answer.case.similar_prior_cases[:6]:
            nodes.append(_node(case_id, "closed", case_id))
    return _dedupe(nodes)


def _edges(facts: CaseFacts, answer: Answer | None) -> list[dict[str, str]]:
    flagged = facts.flagged
    edges = [
        _edge(facts.case.customer_id, facts.card.card_id, "OWNS"),
        _edge(facts.card.card_id, flagged.txn_id, "MADE"),
        _edge(facts.case.case_id, facts.card.card_id, "CASE_ON_CARD"),
        _edge(facts.case.case_id, flagged.txn_id, "CASE_INVOLVES"),
    ]
    if facts.device_profile_id:
        edges.append(_edge(flagged.txn_id, facts.device_profile_id, "FROM_DEVICE"))
    email = flagged.recipient_email or flagged.purchaser_email
    if email:
        edges.append(_edge(flagged.txn_id, email, "EMAIL"))
    if flagged.billing_region:
        edges.append(_edge(flagged.txn_id, flagged.billing_region, "BILLED_IN"))
    for card_id in connected_card_ids(facts)[:12]:
        if facts.device_profile_id:
            edges.append(_edge(facts.device_profile_id, card_id, "SHARED_DEVICE"))
        else:
            edges.append(_edge(email or facts.card.card_id, card_id, "SHARED"))
    if answer:
        for txn_id in answer.case.affected_txn_ids[:12]:
            edges.append(_edge(facts.card.card_id, txn_id, "MADE"))
        for case_id in answer.case.similar_prior_cases[:6]:
            edges.append(_edge(facts.case.case_id, case_id, "CASE_MATCHES"))
    return _dedupe(edges)


def _timeline(facts: CaseFacts, answer: Answer | None) -> list[dict[str, Any]]:
    affected = set(answer.case.affected_txn_ids) if answer else {facts.flagged.txn_id}
    rows = []
    for txn in facts.history:
        rows.append(
            {
                "txn_id": txn.txn_id,
                "ts": txn.ts,
                "amount": txn.amount,
                "channel": txn.channel,
                "region": txn.billing_region,
                "flagged": txn.txn_id == facts.flagged.txn_id,
                "episode": txn.txn_id in affected,
            }
        )
    flagged_at = next(
        (index for index, row in enumerate(rows) if row["flagged"]),
        max(len(rows) - 1, 0),
    )
    start = max(0, flagged_at - 20)
    return rows[start : start + 40]


def _approvals(answer: Answer | None) -> list[dict[str, str]]:
    if answer is None:
        return []
    return [
        {
            "action": item.action.value,
            "route": item.route.value,
            "reason": item.reason,
            "stage": "final",
        }
        for item in answer.next_best_actions.final
    ]


def _policy(answer: Answer | None) -> dict[str, Any]:
    if answer is None:
        return {}
    return {
        "verdict": answer.case.verdict.value,
        "status": answer.case.status.value,
        "pattern": answer.case.pattern.value,
        "fraud_probability": answer.case.fraud_probability,
        "exposure_usd": answer.case.exposure_usd,
        "stop_reason": answer.stop_reason,
        "what_changed": answer.next_best_actions.what_changed,
    }


def _node(node_id: str, kind: str, label: str) -> dict[str, str]:
    return {"id": node_id, "type": kind, "label": label}


def _edge(src: str, dst: str, kind: str) -> dict[str, str]:
    return {"from": src, "to": dst, "type": kind}


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        key = tuple(sorted(item.items()))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique
