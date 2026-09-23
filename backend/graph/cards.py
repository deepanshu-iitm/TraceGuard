"""Assign dataset card IDs to card-attribute tuples."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

CardTuple = tuple[str, str, str, str, str, str]


def card_tuple(row: dict[str, str]) -> CardTuple:
    return (
        row.get("card1", ""),
        row.get("card2", ""),
        row.get("card3", ""),
        row.get("card4", ""),
        row.get("card5", ""),
        row.get("card6", ""),
    )


def labeled_txn_card_ids(data_dir: Path) -> dict[str, str]:
    labeled: dict[str, str] = {}
    case_pack = data_dir / "case_pack.csv"
    if case_pack.is_file():
        with case_pack.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                labeled[row["flagged_txn_id"]] = row["card_id"]
    closed = data_dir / "raw" / "closed_cases_history.csv"
    if closed.is_file():
        with closed.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                card_id = row["card_id"]
                if row.get("first_fraud_txn_id"):
                    labeled.setdefault(row["first_fraud_txn_id"], card_id)
                for txn_id in row.get("txn_ids", "").split("|"):
                    if txn_id:
                        labeled.setdefault(txn_id, card_id)
    return labeled


def assign_card_ids(
    tuples_by_customer: dict[str, set[CardTuple]],
    labeled_tuples: dict[tuple[str, CardTuple], str],
) -> dict[tuple[str, CardTuple], str]:
    assigned = dict(labeled_tuples)
    used_ks: dict[str, set[int]] = defaultdict(set)
    for (customer_id, _tuple), card_id in assigned.items():
        used_ks[customer_id].add(_k_number(card_id))
    for customer_id, tuples in tuples_by_customer.items():
        next_k = 1
        for tuple_ in sorted(tuples):
            key = (customer_id, tuple_)
            if key in assigned:
                continue
            while next_k in used_ks[customer_id]:
                next_k += 1
            assigned[key] = f"{customer_id}-K{next_k}"
            used_ks[customer_id].add(next_k)
            next_k += 1
    return assigned


def _k_number(card_id: str) -> int:
    _, _, suffix = card_id.partition("-K")
    return int(suffix) if suffix.isdigit() else 0
