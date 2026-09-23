"""Export graph CSVs for the TigerGraph loading job."""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from backend.data.case_pack import DATA_DIR
from backend.graph.cards import (
    CardTuple,
    assign_card_ids,
    card_tuple,
    labeled_txn_card_ids,
)

RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
GRAPH_FILES = frozenset(
    {
        "vertices_customer.csv",
        "vertices_card.csv",
        "vertices_transaction.csv",
        "vertices_device.csv",
        "vertices_email.csv",
        "vertices_region.csv",
        "vertices_closed_case.csv",
        "edges.csv",
    }
)


@dataclass(frozen=True)
class _Txn:
    txn_id: str
    customer_id: str
    ts: str
    amount: str
    product_cd: str
    channel: str
    risk_score: str
    billing_region: str
    billing_country: str
    purchaser_email: str
    recipient_email: str
    card: CardTuple


def device_profile_id(row: dict[str, str]) -> str:
    return " | ".join(
        [
            row.get("DeviceInfo", ""),
            row.get("id_30", ""),
            row.get("id_31", ""),
            row.get("id_33", ""),
        ]
    )


def export_graph(
    out_dir: Path | None = None,
    data_dir: Path | None = None,
    customer_ids: set[str] | None = None,
) -> Path:
    root = data_dir or DATA_DIR
    dest = out_dir or PROCESSED_DIR
    dest.mkdir(parents=True, exist_ok=True)
    raw = root / "raw"

    labeled = labeled_txn_card_ids(root)
    txns, tuples_by_customer, labeled_tuples = _read_transactions(
        raw / "transactions.csv", labeled, customer_ids
    )
    identity = _read_identity(raw / "identity.csv", {txn.txn_id for txn in txns})
    card_ids = assign_card_ids(tuples_by_customer, labeled_tuples)
    closed_cases = _read_closed_cases(raw / "closed_cases_history.csv", customer_ids)

    customers = {txn.customer_id for txn in txns}
    customers.update(case["customer_id"] for case in closed_cases)
    cards = _card_vertices(card_ids, closed_cases)
    emails: set[str] = set()
    regions: dict[str, str] = {}
    devices: dict[str, dict[str, str]] = {}
    made: list[tuple[str, str]] = []
    owns: set[tuple[str, str]] = set()
    purchaser: list[tuple[str, str]] = []
    recipient: list[tuple[str, str]] = []
    billed: list[tuple[str, str]] = []
    from_device: list[tuple[str, str]] = []
    by_card: dict[str, list[tuple[str, str]]] = defaultdict(list)

    for txn in txns:
        card_id = card_ids[(txn.customer_id, txn.card)]
        owns.add((txn.customer_id, card_id))
        made.append((card_id, txn.txn_id))
        by_card[card_id].append((txn.ts, txn.txn_id))
        if txn.purchaser_email:
            emails.add(txn.purchaser_email)
            purchaser.append((txn.txn_id, txn.purchaser_email))
        if txn.recipient_email:
            emails.add(txn.recipient_email)
            recipient.append((txn.txn_id, txn.recipient_email))
        if txn.billing_region:
            regions[txn.billing_region] = txn.billing_country
            billed.append((txn.txn_id, txn.billing_region))
        ident = identity.get(txn.txn_id)
        if ident:
            profile_id = device_profile_id(ident)
            if profile_id.strip(" |"):
                devices[profile_id] = ident
                from_device.append((txn.txn_id, profile_id))

    next_edges: list[tuple[str, str]] = []
    for pairs in by_card.values():
        pairs.sort()
        for (_, left), (_, right) in zip(pairs, pairs[1:]):
            next_edges.append((left, right))

    involves: list[tuple[str, str]] = []
    on_card: list[tuple[str, str]] = []
    connected: list[tuple[str, str]] = []
    exported_txns = {txn.txn_id for txn in txns}
    for case in closed_cases:
        on_card.append((case["case_id"], case["card_id"]))
        for card_id in case["connected_card_ids"].split("|"):
            if card_id:
                connected.append((case["case_id"], card_id))
        for txn_id in case["txn_ids"].split("|"):
            if txn_id and txn_id in exported_txns:
                involves.append((case["case_id"], txn_id))
        if case["first_fraud_txn_id"] and case["first_fraud_txn_id"] in exported_txns:
            involves.append((case["case_id"], case["first_fraud_txn_id"]))

    _write(dest / "vertices_customer.csv", ["id"], [(cid,) for cid in sorted(customers)])
    _write(
        dest / "vertices_card.csv",
        ["id", "card1", "network", "card_type"],
        [
            (card_id, card1, network, card_type)
            for card_id, (card1, network, card_type) in sorted(cards.items())
        ],
    )
    _write(
        dest / "vertices_transaction.csv",
        [
            "id",
            "ts",
            "amount",
            "product_cd",
            "channel",
            "risk_score",
            "billing_region",
            "billing_country",
        ],
        [
            (
                txn.txn_id,
                txn.ts,
                txn.amount,
                txn.product_cd,
                txn.channel,
                txn.risk_score,
                txn.billing_region,
                txn.billing_country,
            )
            for txn in txns
        ],
    )
    _write(
        dest / "vertices_device.csv",
        ["id", "device_type", "device_info", "os", "browser", "screen"],
        [
            (
                profile_id,
                row.get("DeviceType", ""),
                row.get("DeviceInfo", ""),
                row.get("id_30", ""),
                row.get("id_31", ""),
                row.get("id_33", ""),
            )
            for profile_id, row in sorted(devices.items())
        ],
    )
    _write(dest / "vertices_email.csv", ["id"], [(email,) for email in sorted(emails)])
    _write(
        dest / "vertices_region.csv",
        ["id", "country"],
        [(region, country) for region, country in sorted(regions.items())],
    )
    _write(
        dest / "vertices_closed_case.csv",
        [
            "id",
            "opened_at",
            "closed_at",
            "outcome",
            "pattern",
            "exposure_usd",
            "n_txns",
            "report_filed",
            "analyst_notes",
        ],
        [
            (
                case["case_id"],
                case["opened_at"],
                case["closed_at"],
                case["outcome"],
                case["pattern"],
                case["exposure_usd"],
                case["n_txns"],
                "true" if case["report_filed"] == "Yes" else "false",
                case["analyst_notes"],
            )
            for case in closed_cases
        ],
    )

    edges: list[tuple[str, str, str]] = []
    for kind, pairs in (
        ("owns", sorted(owns)),
        ("made", made),
        ("from_device", from_device),
        ("purchaser_email", purchaser),
        ("recipient_email", recipient),
        ("billed_in", billed),
        ("next", next_edges),
        ("involves", involves),
        ("on_card", on_card),
        ("connected_to", connected),
    ):
        edges.extend((kind, src, dst) for src, dst in pairs)
    _write(dest / "edges.csv", ["edge_type", "from_id", "to_id"], edges)

    for path in dest.glob("*.csv"):
        if path.name not in GRAPH_FILES:
            path.unlink()
    return dest


def _read_transactions(
    path: Path,
    labeled: dict[str, str],
    customer_ids: set[str] | None,
) -> tuple[list[_Txn], dict[str, set[CardTuple]], dict[tuple[str, CardTuple], str]]:
    txns: list[_Txn] = []
    tuples_by_customer: dict[str, set[CardTuple]] = defaultdict(set)
    labeled_tuples: dict[tuple[str, CardTuple], str] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            customer_id = row["customer_id"]
            if customer_ids is not None and customer_id not in customer_ids:
                continue
            tuple_ = card_tuple(row)
            txn = _Txn(
                txn_id=row["TransactionID"],
                customer_id=customer_id,
                ts=row["ts"],
                amount=row["TransactionAmt"],
                product_cd=row["ProductCD"],
                channel=row["channel"],
                risk_score=row["risk_score"],
                billing_region=row["addr1"],
                billing_country=row["addr2"],
                purchaser_email=row["P_emaildomain"],
                recipient_email=row["R_emaildomain"],
                card=tuple_,
            )
            txns.append(txn)
            tuples_by_customer[customer_id].add(tuple_)
            if txn.txn_id in labeled:
                labeled_tuples[(customer_id, tuple_)] = labeled[txn.txn_id]
    return txns, tuples_by_customer, labeled_tuples


def _read_identity(path: Path, txn_ids: set[str]) -> dict[str, dict[str, str]]:
    records: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            txn_id = row["TransactionID"]
            if txn_id in txn_ids:
                records[txn_id] = row
    return records


def _read_closed_cases(
    path: Path, customer_ids: set[str] | None
) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if customer_ids is None:
        return rows
    return [row for row in rows if row["customer_id"] in customer_ids]


def _card_vertices(
    card_ids: dict[tuple[str, CardTuple], str],
    closed_cases: list[dict[str, str]],
) -> dict[str, tuple[str, str, str]]:
    cards: dict[str, tuple[str, str, str]] = {}
    for (_customer_id, tuple_), card_id in card_ids.items():
        cards[card_id] = (tuple_[0], tuple_[3], tuple_[5])
    for case in closed_cases:
        cards.setdefault(case["card_id"], ("", "", ""))
        for card_id in case["connected_card_ids"].split("|"):
            if card_id:
                cards.setdefault(card_id, ("", "", ""))
    return cards


def _write(path: Path, header: list[str], rows: list[tuple]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


if __name__ == "__main__":
    from backend.data import load_case_pack

    output = export_graph(customer_ids={item.customer_id for item in load_case_pack()})
    print(f"wrote {output}")
