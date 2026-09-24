"""Export investigation cases for the TigerGraph loading job."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from backend.data import load_case_pack
from backend.graph.export import PROCESSED_DIR
from backend.models.answer import Answer

CASES_DIR = Path(__file__).resolve().parents[2] / "cases"

CASE_FILES = frozenset(
    {
        "vertices_investigation_case.csv",
        "case_edges.csv",
    }
)


def persist_investigation_cases(
    cases_dir: Path | None = None,
    out_dir: Path | None = None,
) -> Path:
    """Write case vertices/edges and mark each answer as stored in the graph."""

    answers = _load_answers(cases_dir or CASES_DIR)
    dest = export_investigation_cases(answers, out_dir=out_dir)
    _mark_written(answers, cases_dir or CASES_DIR)
    return dest


def export_investigation_cases(
    answers: list[Answer] | None = None,
    out_dir: Path | None = None,
) -> Path:
    dest = out_dir or PROCESSED_DIR
    dest.mkdir(parents=True, exist_ok=True)
    records = answers if answers is not None else _load_answers(CASES_DIR)
    pack = {item.case_id: item for item in load_case_pack()}

    vertices: list[tuple] = []
    edges: list[tuple[str, str, str]] = []
    for answer in records:
        item = pack[answer.case_id]
        case = answer.case
        vertices.append(
            (
                answer.case_id,
                case.status.value,
                case.verdict.value,
                case.fraud_probability,
                case.pattern.value,
                case.pattern_description,
                case.exposure_usd,
                _csv_text(case.summary),
                _csv_text(answer.stop_reason),
            )
        )
        edges.append(("case_for_customer", answer.case_id, item.customer_id))
        edges.append(("case_on_card", answer.case_id, item.card_id))
        txn_ids = list(case.affected_txn_ids)
        if item.flagged_txn_id not in txn_ids:
            txn_ids.append(item.flagged_txn_id)
        for txn_id in txn_ids:
            edges.append(("case_involves", answer.case_id, txn_id))
        for card_id in case.connected_card_ids:
            if card_id != item.card_id:
                edges.append(("case_connected_to", answer.case_id, card_id))
        for closed_id in case.similar_prior_cases:
            edges.append(("case_matches", answer.case_id, closed_id))

    _write(
        dest / "vertices_investigation_case.csv",
        [
            "id",
            "status",
            "verdict",
            "fraud_probability",
            "pattern",
            "pattern_description",
            "exposure_usd",
            "summary",
            "stop_reason",
        ],
        vertices,
    )
    _write(dest / "case_edges.csv", ["edge_type", "from_id", "to_id"], edges)
    return dest


def _load_answers(cases_dir: Path) -> list[Answer]:
    paths = sorted(cases_dir.glob("HHG-*.json"))
    return [Answer.model_validate_json(path.read_text(encoding="utf-8")) for path in paths]


def _mark_written(answers: list[Answer], cases_dir: Path) -> None:
    for answer in answers:
        payload = json.loads((cases_dir / f"{answer.case_id}.json").read_text(encoding="utf-8"))
        payload["case"]["written_to_graph"] = True
        payload["case"]["graph_case_id"] = answer.case_id
        (cases_dir / f"{answer.case_id}.json").write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )


def _csv_text(value: str) -> str:
    return value.replace(",", ";").replace('"', "").replace("\n", " ").strip()


def _write(path: Path, header: list[str], rows: list[tuple]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
