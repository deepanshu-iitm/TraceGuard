"""Load investigation facts for a case-pack id from the exported graph."""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path

from backend.config import settings
from backend.data import load_case_pack
from backend.graph.export import PROCESSED_DIR
from backend.models.case_pack import CasePackItem


@dataclass(frozen=True)
class TxnFact:
    """One CardTransaction vertex."""

    txn_id: str
    ts: str
    amount: float
    product_cd: str
    channel: str
    risk_score: float
    billing_region: str
    billing_country: str
    device_profile_id: str = ""
    purchaser_email: str = ""
    recipient_email: str = ""


@dataclass(frozen=True)
class CardFact:
    """One PaymentCard vertex."""

    card_id: str
    card1: str
    network: str
    card_type: str


@dataclass(frozen=True)
class ClosedCaseFact:
    """One ClosedCase vertex on the flagged card."""

    case_id: str
    opened_at: str
    closed_at: str
    outcome: str
    pattern: str
    exposure_usd: float
    n_txns: int
    report_filed: bool
    analyst_notes: str
    txn_ids: tuple[str, ...]


@dataclass(frozen=True)
class CaseFacts:
    """Graph facts needed to investigate one exam case."""

    case: CasePackItem
    flagged: TxnFact
    card: CardFact
    customer_card_ids: tuple[str, ...]
    history: tuple[TxnFact, ...]
    closed_cases: tuple[ClosedCaseFact, ...]
    device_profile_id: str
    device_card_ids: tuple[str, ...]
    email_card_ids: tuple[str, ...] = ()
    region_card_ids: tuple[str, ...] = ()
    next_txn_ids: tuple[str, ...] = ()

    def prior(self) -> tuple[TxnFact, ...]:
        return tuple(txn for txn in self.history if txn.ts < self.flagged.ts)

    def prior_in_region(self, region: str | None = None) -> tuple[TxnFact, ...]:
        target = self.flagged.billing_region if region is None else region
        if not target:
            return ()
        return tuple(txn for txn in self.prior() if txn.billing_region == target)


def load_case_facts(case_id: str, processed_dir: Path | None = None) -> CaseFacts:
    item = _case_pack_item(case_id)
    if settings.tg_host.strip():
        from backend.graph.tools import get_graph_tools

        payload = get_graph_tools().run_installed_query(
            "get_case_facts", {"t": item.flagged_txn_id}
        )
        return _facts_from_payload(item, payload)
    return load_local_case_facts(case_id, processed_dir)


def load_local_case_facts(case_id: str, processed_dir: Path | None = None) -> CaseFacts:
    """Neighborhood from exported CSVs, even when TG_HOST is set."""
    return _facts_from_csv(_case_pack_item(case_id), processed_dir or PROCESSED_DIR)


def load_alert_facts(
    case_id: str, txn_id: str, processed_dir: Path | None = None
) -> CaseFacts:
    """Build investigation facts for a monitored transaction that is not in the exam pack."""
    from datetime import datetime

    from backend.models.enums import TriggerType

    dest = processed_dir or PROCESSED_DIR
    index = _graph_index(dest)
    flagged = index.txn(txn_id)
    card_id = index.card_for_txn(txn_id)
    customer_id = index.customer_for_card(card_id)
    opened = flagged.ts.replace(" ", "T")
    item = CasePackItem(
        case_id=case_id,
        opened_at=datetime.fromisoformat(opened),
        trigger_type=TriggerType.RISK_SCORE,
        trigger_text=(
            f"Autonomous monitor scored transaction {txn_id} "
            f"(${flagged.amount:.2f}, {flagged.channel}) at {flagged.risk_score:.2f}."
        ),
        flagged_txn_id=txn_id,
        card_id=card_id,
        customer_id=customer_id or "UNKNOWN",
        risk_score=flagged.risk_score,
    )
    return _facts_from_csv(item, dest)


def _facts_from_csv(item: CasePackItem, processed_dir: Path) -> CaseFacts:
    index = _graph_index(processed_dir)
    flagged = index.txn(item.flagged_txn_id)
    card = index.card(item.card_id)
    history = tuple(
        sorted(
            (index.txn(txn_id) for txn_id in index.made.get(item.card_id, ())),
            key=lambda txn: (txn.ts, txn.txn_id),
        )
    )
    closed = tuple(
        index.closed[closed_id]
        for closed_id in sorted(index.on_card.get(item.card_id, ()))
    )
    profile = flagged.device_profile_id
    device_cards = index.cards_by_device.get(profile, ())
    if item.card_id not in device_cards:
        device_cards = device_cards + (item.card_id,)
    email_key = flagged.recipient_email or flagged.purchaser_email
    email_cards = index.cards_by_email.get(email_key, ()) if email_key else ()
    region_cards = (
        index.cards_by_region.get(flagged.billing_region, ()) if flagged.billing_region else ()
    )
    return CaseFacts(
        case=item,
        flagged=flagged,
        card=card,
        customer_card_ids=tuple(sorted(index.owns.get(item.customer_id, ()))),
        history=history,
        closed_cases=closed,
        device_profile_id=profile,
        device_card_ids=tuple(sorted(device_cards)),
        email_card_ids=tuple(sorted(email_cards)),
        region_card_ids=tuple(sorted(region_cards)),
        next_txn_ids=_neighbors(index.next_txn, item.flagged_txn_id),
    )


def _facts_from_payload(item: CasePackItem, payload: list) -> CaseFacts:
    from backend.graph.parse import flagged_vertex, vertices

    flagged_row = flagged_vertex(payload)
    card_row = vertices(payload, "cards")[0]
    attrs = flagged_row["attributes"]
    devices = vertices(payload, "devices")
    profile = devices[0]["v_id"] if devices else ""
    owned = tuple(sorted(row["v_id"] for row in vertices(payload, "owned")))
    device_cards = tuple(sorted(row["v_id"] for row in vertices(payload, "device_cards")))
    if item.card_id not in device_cards:
        device_cards = device_cards + (item.card_id,)
    purchaser = vertices(payload, "purchaser")
    recipient = vertices(payload, "recipient")
    flagged = TxnFact(
        txn_id=flagged_row["v_id"],
        ts=str(attrs.get("ts", "")),
        amount=float(attrs.get("amount") or 0),
        product_cd=str(attrs.get("product_cd", "")),
        channel=str(attrs.get("channel", "")),
        risk_score=float(attrs.get("risk_score") or 0),
        billing_region=str(attrs.get("billing_region") or ""),
        billing_country=str(attrs.get("billing_country") or ""),
        device_profile_id=profile,
        purchaser_email=purchaser[0]["v_id"] if purchaser else "",
        recipient_email=recipient[0]["v_id"] if recipient else "",
    )
    card_attrs = card_row["attributes"]
    history = tuple(
        sorted(
            (
                TxnFact(
                    txn_id=row["v_id"],
                    ts=str(row["attributes"].get("ts", "")),
                    amount=float(row["attributes"].get("amount") or 0),
                    product_cd=str(row["attributes"].get("product_cd", "")),
                    channel=str(row["attributes"].get("channel", "")),
                    risk_score=float(row["attributes"].get("risk_score") or 0),
                    billing_region=str(row["attributes"].get("billing_region") or ""),
                    billing_country=str(row["attributes"].get("billing_country") or ""),
                    device_profile_id=(
                        profile if row["v_id"] == flagged_row["v_id"] else ""
                    ),
                )
                for row in vertices(payload, "history")
            ),
            key=lambda txn: (txn.ts, txn.txn_id),
        )
    )
    closed = tuple(
        sorted(
            (
                ClosedCaseFact(
                    case_id=row["v_id"],
                    opened_at=str(row["attributes"].get("opened_at", "")),
                    closed_at=str(row["attributes"].get("closed_at", "")),
                    outcome=str(row["attributes"].get("outcome", "")),
                    pattern=str(row["attributes"].get("pattern", "")),
                    exposure_usd=float(row["attributes"].get("exposure_usd") or 0),
                    n_txns=int(row["attributes"].get("n_txns") or 0),
                    report_filed=bool(row["attributes"].get("report_filed")),
                    analyst_notes=str(row["attributes"].get("analyst_notes", "")),
                    txn_ids=tuple(row["attributes"].get("txn_ids") or ()),
                )
                for row in vertices(payload, "closed")
            ),
            key=lambda case: case.case_id,
        )
    )
    return CaseFacts(
        case=item,
        flagged=flagged,
        card=CardFact(
            card_id=card_row["v_id"],
            card1=str(card_attrs.get("card1", "")),
            network=str(card_attrs.get("network", "")),
            card_type=str(card_attrs.get("card_type", "")),
        ),
        customer_card_ids=owned,
        history=history,
        closed_cases=closed,
        device_profile_id=profile,
        device_card_ids=tuple(sorted(device_cards)),
        email_card_ids=(),
        region_card_ids=(),
        next_txn_ids=(),
    )


def merge_shared_cards(facts: CaseFacts, payload: list) -> CaseFacts:
    """Union cards from shared_cards_on_device into the case neighborhood."""
    return _merge_id_tuple(facts, "device_card_ids", payload, "cards")


def merge_email_cards(facts: CaseFacts, payload: list) -> CaseFacts:
    """Union cards from email_fanout into the case neighborhood."""
    updated = _merge_id_tuple(facts, "email_card_ids", payload, "cards")
    return _merge_id_tuple(updated, "email_card_ids", payload, "cards2")


def merge_region_cards(facts: CaseFacts, payload: list) -> CaseFacts:
    """Union cards from region_fanout (informational, not an automatic R6)."""
    return _merge_id_tuple(facts, "region_card_ids", payload, "cards")


def merge_next_txns(facts: CaseFacts, payload: list) -> CaseFacts:
    """Union NEXT-chain transaction ids into the episode seed list."""
    updated = _merge_id_tuple(facts, "next_txn_ids", payload, "nxt")
    return _merge_id_tuple(updated, "next_txn_ids", payload, "prev")


def _merge_id_tuple(
    facts: CaseFacts, field: str, payload: list, key: str
) -> CaseFacts:
    from backend.graph.parse import vertices

    extra = {row["v_id"] for row in vertices(payload, key) if row.get("v_id")}
    if not extra:
        return facts
    current = set(getattr(facts, field))
    merged = tuple(sorted(current | extra))
    if merged == getattr(facts, field):
        return facts
    return replace(facts, **{field: merged})


def _case_pack_item(case_id: str) -> CasePackItem:
    for item in load_case_pack():
        if item.case_id == case_id:
            return item
    raise KeyError(f"unknown case_id: {case_id}")


@dataclass
class _GraphIndex:
    txns: dict[str, TxnFact]
    cards: dict[str, CardFact]
    closed: dict[str, ClosedCaseFact]
    made: dict[str, tuple[str, ...]]
    owns: dict[str, tuple[str, ...]]
    on_card: dict[str, tuple[str, ...]]
    device: dict[str, str]
    cards_by_device: dict[str, tuple[str, ...]]
    txn_to_card: dict[str, str]
    cards_by_email: dict[str, tuple[str, ...]]
    cards_by_region: dict[str, tuple[str, ...]]
    next_txn: dict[str, tuple[str, ...]]

    def txn(self, txn_id: str) -> TxnFact:
        try:
            return self.txns[txn_id]
        except KeyError as exc:
            raise KeyError(f"transaction {txn_id} is not in the graph") from exc

    def card(self, card_id: str) -> CardFact:
        try:
            return self.cards[card_id]
        except KeyError as exc:
            raise KeyError(f"card {card_id} is not in the graph") from exc

    def card_for_txn(self, txn_id: str) -> str:
        card_id = self.txn_to_card.get(txn_id)
        if not card_id:
            raise KeyError(f"no card for transaction {txn_id}")
        return card_id

    def customer_for_card(self, card_id: str) -> str:
        for customer_id, card_ids in self.owns.items():
            if card_id in card_ids:
                return customer_id
        return ""


_INDEX: dict[Path, _GraphIndex] = {}


def _graph_index(processed_dir: Path) -> _GraphIndex:
    key = processed_dir.resolve()
    cached = _INDEX.get(key)
    if cached is None:
        cached = _load_index(key)
        _INDEX[key] = cached
    return cached


def _load_index(processed_dir: Path) -> _GraphIndex:
    txns = {
        row["id"]: TxnFact(
            txn_id=row["id"],
            ts=row["ts"],
            amount=_float(row["amount"]),
            product_cd=row["product_cd"],
            channel=row["channel"],
            risk_score=_float(row["risk_score"]),
            billing_region=row["billing_region"],
            billing_country=row["billing_country"],
        )
        for row in _rows(processed_dir / "vertices_transaction.csv")
    }
    cards = {
        row["id"]: CardFact(
            card_id=row["id"],
            card1=row["card1"],
            network=row["network"],
            card_type=row["card_type"],
        )
        for row in _rows(processed_dir / "vertices_card.csv")
    }
    closed = {
        row["id"]: ClosedCaseFact(
            case_id=row["id"],
            opened_at=row["opened_at"],
            closed_at=row["closed_at"],
            outcome=row["outcome"],
            pattern=row["pattern"],
            exposure_usd=_float(row["exposure_usd"]),
            n_txns=int(row["n_txns"]),
            report_filed=row["report_filed"] == "true",
            analyst_notes=row["analyst_notes"],
            txn_ids=(),
        )
        for row in _rows(processed_dir / "vertices_closed_case.csv")
    }

    made: dict[str, list[str]] = defaultdict(list)
    owns: dict[str, list[str]] = defaultdict(list)
    on_card: dict[str, list[str]] = defaultdict(list)
    involves: dict[str, list[str]] = defaultdict(list)
    device: dict[str, str] = {}
    purchaser: dict[str, str] = {}
    recipient: dict[str, str] = {}
    billed: dict[str, str] = {}
    nxt: dict[str, list[str]] = defaultdict(list)
    for row in _rows(processed_dir / "edges.csv"):
        kind = row["edge_type"]
        src, dst = row["from_id"], row["to_id"]
        if kind == "made":
            made[src].append(dst)
        elif kind == "owns":
            owns[src].append(dst)
        elif kind == "on_card":
            on_card[dst].append(src)
        elif kind == "involves":
            involves[src].append(dst)
        elif kind == "from_device":
            device[src] = dst
        elif kind == "purchaser_email":
            purchaser[src] = dst
        elif kind == "recipient_email":
            recipient[src] = dst
        elif kind == "billed_in":
            billed[src] = dst
        elif kind == "next":
            nxt[src].append(dst)

    involves_by_case = {case_id: tuple(txn_ids) for case_id, txn_ids in involves.items()}
    closed = {
        case_id: replace(fact, txn_ids=involves_by_case.get(case_id, ()))
        for case_id, fact in closed.items()
    }
    txns = {
        txn_id: replace(
            txn,
            device_profile_id=device.get(txn_id, ""),
            purchaser_email=purchaser.get(txn_id, ""),
            recipient_email=recipient.get(txn_id, ""),
        )
        for txn_id, txn in txns.items()
    }
    txn_to_card = {
        txn_id: card_id for card_id, txn_ids in made.items() for txn_id in txn_ids
    }
    cards_by_device: dict[str, set[str]] = defaultdict(set)
    cards_by_email: dict[str, set[str]] = defaultdict(set)
    cards_by_region: dict[str, set[str]] = defaultdict(set)
    for txn_id, profile in device.items():
        card_id = txn_to_card.get(txn_id)
        if card_id:
            cards_by_device[profile].add(card_id)
    for txn_id, domain in {**purchaser, **recipient}.items():
        card_id = txn_to_card.get(txn_id)
        if card_id and domain:
            cards_by_email[domain].add(card_id)
    for txn_id, region in billed.items():
        card_id = txn_to_card.get(txn_id)
        if card_id and region:
            cards_by_region[region].add(card_id)
    for txn_id, txn in txns.items():
        card_id = txn_to_card.get(txn_id)
        if card_id and txn.billing_region:
            cards_by_region[txn.billing_region].add(card_id)
    return _GraphIndex(
        txns=txns,
        cards=cards,
        closed=closed,
        made={card_id: tuple(txn_ids) for card_id, txn_ids in made.items()},
        owns={customer_id: tuple(card_ids) for customer_id, card_ids in owns.items()},
        on_card={card_id: tuple(case_ids) for card_id, case_ids in on_card.items()},
        device=device,
        cards_by_device={
            profile: tuple(sorted(card_ids)) for profile, card_ids in cards_by_device.items()
        },
        txn_to_card=txn_to_card,
        cards_by_email={
            domain: tuple(sorted(card_ids)) for domain, card_ids in cards_by_email.items()
        },
        cards_by_region={
            region: tuple(sorted(card_ids)) for region, card_ids in cards_by_region.items()
        },
        next_txn={txn_id: tuple(dests) for txn_id, dests in nxt.items()},
    )


def _neighbors(forward: dict[str, tuple[str, ...]], txn_id: str) -> tuple[str, ...]:
    linked = set(forward.get(txn_id, ()))
    for src, dests in forward.items():
        if txn_id in dests:
            linked.add(src)
    return tuple(sorted(linked))


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _float(value: str) -> float:
    return float(value) if value else 0.0
