"""Installed GSQL queries executed against the exported graph CSVs."""

from __future__ import annotations

from typing import Any

from backend.graph.export import PROCESSED_DIR
from backend.investigate.facts import ClosedCaseFact, TxnFact, _graph_index


class LocalGraphTools:
    """Same query names as tigergraph/queries/*.gsql, over local CSVs."""

    def run_installed_query(self, name: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        if name == "get_case_facts":
            return local_case_facts(str(params["t"]))
        if name == "investigate_txn":
            return local_investigate_txn(str(params["t"]))
        if name == "shared_cards_on_device":
            return local_shared_cards(str(params["d"]))
        if name == "get_investigation_case":
            return [{"c": [{"v_id": str(params.get("c", "")), "attributes": {}}]}]
        raise KeyError(f"unknown installed query: {name}")


def local_case_facts(txn_id: str) -> list[dict[str, Any]]:
    index = _graph_index(PROCESSED_DIR)
    flagged = index.txn(txn_id)
    card_id = index.card_for_txn(txn_id)
    card = index.card(card_id)
    customer_id = index.customer_for_card(card_id)
    history = [index.txn(item) for item in index.made.get(card_id, ())]
    closed = [index.closed[case_id] for case_id in index.on_card.get(card_id, ())]
    profile = flagged.device_profile_id
    device_cards = index.cards_by_device.get(profile, ())
    return [
        {"t": [_txn_vertex(flagged)]},
        {"cards": [_card_vertex(card)]},
        {"customers": [{"v_id": customer_id, "attributes": {}}] if customer_id else []},
        {
            "owned": [
                _card_vertex(index.card(item)) for item in index.owns.get(customer_id, ())
            ]
        },
        {"history": [_txn_vertex(item) for item in history]},
        {"closed": [_closed_vertex(item) for item in closed]},
        {"devices": [{"v_id": profile, "attributes": {}}] if profile else []},
        {
            "device_cards": [
                _card_vertex(index.card(item))
                for item in device_cards
                if item in index.cards
            ]
        },
        {
            "purchaser": (
                [{"v_id": flagged.purchaser_email, "attributes": {}}]
                if flagged.purchaser_email
                else []
            )
        },
        {
            "recipient": (
                [{"v_id": flagged.recipient_email, "attributes": {}}]
                if flagged.recipient_email
                else []
            )
        },
        {
            "regions": (
                [{"v_id": flagged.billing_region, "attributes": {}}]
                if flagged.billing_region
                else []
            )
        },
    ]


def local_investigate_txn(txn_id: str) -> list[dict[str, Any]]:
    from backend.graph.parse import vertices

    facts = local_case_facts(txn_id)
    history = vertices(facts, "history")
    flagged = vertices(facts, "t")[0]
    return [
        {"t.amount": flagged["attributes"].get("amount")},
        {"cards": vertices(facts, "cards")},
        {"customers": vertices(facts, "customers")},
        {"closed": vertices(facts, "closed")},
        {"@@n_history": len(history)},
    ]


def local_shared_cards(profile: str) -> list[dict[str, Any]]:
    index = _graph_index(PROCESSED_DIR)
    card_ids = index.cards_by_device.get(profile, ())
    n_txns = sum(1 for txn in index.txns.values() if txn.device_profile_id == profile)
    return [
        {"d": [{"v_id": profile, "attributes": {}}]},
        {"@@n_txns": n_txns},
        {"cards": [_card_vertex(index.card(card_id)) for card_id in card_ids]},
    ]


def _txn_vertex(txn: TxnFact) -> dict[str, Any]:
    return {
        "v_id": txn.txn_id,
        "v_type": "CardTransaction",
        "attributes": {
            "ts": txn.ts,
            "amount": txn.amount,
            "product_cd": txn.product_cd,
            "channel": txn.channel,
            "risk_score": txn.risk_score,
            "billing_region": txn.billing_region,
            "billing_country": txn.billing_country,
        },
    }


def _card_vertex(card) -> dict[str, Any]:
    return {
        "v_id": card.card_id,
        "v_type": "PaymentCard",
        "attributes": {
            "card1": card.card1,
            "network": card.network,
            "card_type": card.card_type,
        },
    }


def _closed_vertex(case: ClosedCaseFact) -> dict[str, Any]:
    return {
        "v_id": case.case_id,
        "v_type": "ClosedCase",
        "attributes": {
            "opened_at": case.opened_at,
            "closed_at": case.closed_at,
            "outcome": case.outcome,
            "pattern": case.pattern,
            "exposure_usd": case.exposure_usd,
            "n_txns": case.n_txns,
            "report_filed": case.report_filed,
            "analyst_notes": case.analyst_notes,
            "txn_ids": list(case.txn_ids),
        },
    }
