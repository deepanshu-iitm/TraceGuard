"""Export investigation cases for the TigerGraph loading job."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from backend.config import settings
from backend.data import load_case_pack
from backend.graph.export import PROCESSED_DIR
from backend.models.answer import Answer
from backend.models.case_pack import CasePackItem

_VERTEX_FIELDS = (
    "id",
    "status",
    "verdict",
    "fraud_probability",
    "pattern",
    "pattern_description",
    "exposure_usd",
    "summary",
    "stop_reason",
)

_GRAPH_EDGES = {
    "case_for_customer": ("CASE_FOR_CUSTOMER", "Customer"),
    "case_on_card": ("CASE_ON_CARD", "PaymentCard"),
    "case_involves": ("CASE_INVOLVES", "CardTransaction"),
    "case_connected_to": ("CASE_CONNECTED_TO", "PaymentCard"),
    "case_matches": ("CASE_MATCHES", "ClosedCase"),
}

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


def write_investigation_case(
    answer: Answer,
    out_dir: Path | None = None,
    item: CasePackItem | None = None,
) -> Answer:
    """Upsert one finished investigation onto the local CSVs and, if configured, Savanna."""

    dest = out_dir or PROCESSED_DIR
    dest.mkdir(parents=True, exist_ok=True)
    pack = {row.case_id: row for row in load_case_pack()}
    resolved = item or pack[answer.case_id]
    _upsert_case_files(answer, resolved, dest)
    if settings.tg_host.strip():
        from backend.graph.tools import get_graph_tools

        get_graph_tools().upsert_investigation_case(
            answer.case_id,
            case_vertex_attrs(answer),
            case_graph_edges(answer, resolved),
        )
    case = answer.case.model_copy(
        update={"written_to_graph": True, "graph_case_id": answer.case_id}
    )
    return answer.model_copy(update={"case": case})


def case_vertex_attrs(answer: Answer) -> dict[str, object]:
    case = answer.case
    return {
        "status": case.status.value,
        "verdict": case.verdict.value,
        "fraud_probability": case.fraud_probability,
        "pattern": case.pattern.value,
        "pattern_description": case.pattern_description,
        "exposure_usd": case.exposure_usd,
        "summary": case.summary,
        "stop_reason": answer.stop_reason,
    }


def case_graph_edges(answer: Answer, item: CasePackItem) -> list[tuple[str, str, str]]:
    return [
        (_GRAPH_EDGES[kind][0], _GRAPH_EDGES[kind][1], target_id)
        for kind, _case_id, target_id in _csv_edges(answer, item)
    ]


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
        vertices.append(_csv_vertex(answer))
        edges.extend(_csv_edges(answer, item))

    _write(dest / "vertices_investigation_case.csv", list(_VERTEX_FIELDS), vertices)
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


def _csv_vertex(answer: Answer) -> tuple:
    case = answer.case
    return (
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


def _csv_edges(answer: Answer, item: CasePackItem) -> list[tuple[str, str, str]]:
    edges = [
        ("case_for_customer", answer.case_id, item.customer_id),
        ("case_on_card", answer.case_id, item.card_id),
    ]
    txn_ids = list(answer.case.affected_txn_ids)
    if item.flagged_txn_id not in txn_ids:
        txn_ids.append(item.flagged_txn_id)
    for txn_id in txn_ids:
        edges.append(("case_involves", answer.case_id, txn_id))
    for card_id in answer.case.connected_card_ids:
        if card_id != item.card_id:
            edges.append(("case_connected_to", answer.case_id, card_id))
    for closed_id in answer.case.similar_prior_cases:
        edges.append(("case_matches", answer.case_id, closed_id))
    return edges


def _upsert_case_files(answer: Answer, item: CasePackItem, dest: Path) -> None:
    vpath = dest / "vertices_investigation_case.csv"
    epath = dest / "case_edges.csv"
    vertices = [row for row in _read_rows(vpath) if row.get("id") != answer.case_id]
    vertices.append(dict(zip(_VERTEX_FIELDS, _csv_vertex(answer))))
    edges = [row for row in _read_rows(epath) if row.get("from_id") != answer.case_id]
    edges.extend(
        {"edge_type": kind, "from_id": src, "to_id": dst}
        for kind, src, dst in _csv_edges(answer, item)
    )
    _write(
        vpath,
        list(_VERTEX_FIELDS),
        [tuple(row[field] for field in _VERTEX_FIELDS) for row in vertices],
    )
    _write(
        epath,
        ["edge_type", "from_id", "to_id"],
        [(row["edge_type"], row["from_id"], row["to_id"]) for row in edges],
    )


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _csv_text(value: str) -> str:
    return value.replace(",", ";").replace('"', "").replace("\n", " ").strip()


def _write(path: Path, header: list[str], rows: list[tuple]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
