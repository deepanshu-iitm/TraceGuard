"""Load investigation facts for a case-pack id from the exported graph."""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path

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

    def prior(self) -> tuple[TxnFact, ...]:
        return tuple(txn for txn in self.history if txn.ts < self.flagged.ts)

    def prior_in_region(self, region: str | None = None) -> tuple[TxnFact, ...]:
        target = self.flagged.billing_region if region is None else region
        return tuple(txn for txn in self.prior() if txn.billing_region == target)


def load_case_facts(case_id: str, processed_dir: Path | None = None) -> CaseFacts:
    item = _case_pack_item(case_id)
    index = _graph_index(processed_dir or PROCESSED_DIR)
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
    return CaseFacts(
        case=item,
        flagged=flagged,
        card=card,
        customer_card_ids=tuple(sorted(index.owns.get(item.customer_id, ()))),
        history=history,
        closed_cases=closed,
        device_profile_id=index.device.get(item.flagged_txn_id, ""),
    )


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

    involves_by_case = {case_id: tuple(txn_ids) for case_id, txn_ids in involves.items()}
    closed = {
        case_id: replace(fact, txn_ids=involves_by_case.get(case_id, ()))
        for case_id, fact in closed.items()
    }
    return _GraphIndex(
        txns=txns,
        cards=cards,
        closed=closed,
        made={card_id: tuple(txn_ids) for card_id, txn_ids in made.items()},
        owns={customer_id: tuple(card_ids) for customer_id, card_ids in owns.items()},
        on_card={card_id: tuple(case_ids) for card_id, case_ids in on_card.items()},
        device=device,
    )


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _float(value: str) -> float:
    return float(value) if value else 0.0
