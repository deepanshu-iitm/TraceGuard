import csv
import tempfile
from pathlib import Path

import pytest

from backend.data import load_case_pack
from backend.graph.export import GRAPH_FILES, RAW_DIR, export_graph


pytestmark = pytest.mark.skipif(
    not (RAW_DIR / "transactions.csv").is_file(),
    reason="copy transactions.csv, identity.csv, and closed_cases_history.csv into data/raw",
)


def _ids(path: Path, column: str = "id") -> set[str]:
    with path.open(encoding="utf-8", newline="") as handle:
        return {row[column] for row in csv.DictReader(handle)}


def _edge_pairs(path: Path, edge_type: str) -> set[tuple[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return {
            (row["from_id"], row["to_id"])
            for row in csv.DictReader(handle)
            if row["edge_type"] == edge_type
        }


def test_export_includes_case_pack_customers_cards_and_flagged_txns() -> None:
    cases = load_case_pack()
    with tempfile.TemporaryDirectory() as raw:
        out = Path(raw)
        export_graph(out_dir=out, customer_ids={item.customer_id for item in cases})

        assert {path.name for path in out.glob("*.csv")} == GRAPH_FILES
        customers = _ids(out / "vertices_customer.csv")
        cards = _ids(out / "vertices_card.csv")
        txns = _ids(out / "vertices_transaction.csv")
        made = _edge_pairs(out / "edges.csv", "made")
        owns = _edge_pairs(out / "edges.csv", "owns")
        for item in cases:
            assert item.customer_id in customers
            assert item.card_id in cards
            assert item.flagged_txn_id in txns
            assert (item.card_id, item.flagged_txn_id) in made
            assert (item.customer_id, item.card_id) in owns
