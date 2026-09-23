"""Load the benchmark case pack."""

from __future__ import annotations

import csv
from pathlib import Path

from backend.models.case_pack import CasePackItem

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load_case_pack(path: Path | None = None) -> list[CasePackItem]:
    csv_path = path or DATA_DIR / "case_pack.csv"
    with csv_path.open(encoding="utf-8", newline="") as handle:
        return [_parse_row(row) for row in csv.DictReader(handle)]


def _parse_row(row: dict[str, str]) -> CasePackItem:
    score = row.get("risk_score", "").strip()
    return CasePackItem.model_validate(
        {
            **row,
            "risk_score": score or None,
        }
    )
