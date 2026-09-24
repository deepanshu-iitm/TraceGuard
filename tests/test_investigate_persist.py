import csv
import json
from pathlib import Path

from backend.investigate.persist import export_investigation_cases, persist_investigation_cases


def test_export_writes_hhg001_customer_card_and_flagged_txn(tmp_path: Path) -> None:
    export_investigation_cases(out_dir=tmp_path)

    with (tmp_path / "vertices_investigation_case.csv").open(encoding="utf-8", newline="") as handle:
        ids = [row["id"] for row in csv.DictReader(handle)]
    assert ids == [f"HHG-{i:03d}" for i in range(1, 21)]

    with (tmp_path / "case_edges.csv").open(encoding="utf-8", newline="") as handle:
        edges = {(row["edge_type"], row["from_id"], row["to_id"]) for row in csv.DictReader(handle)}
    assert ("case_for_customer", "HHG-001", "C12382") in edges
    assert ("case_on_card", "HHG-001", "C12382-K1") in edges
    assert ("case_involves", "HHG-001", "3514030") in edges
    assert ("case_matches", "HHG-001", "CC-1066") in edges

    with (tmp_path / "vertices_investigation_case.csv").open(encoding="utf-8") as handle:
        next(handle)
        hhg001 = next(handle)
    assert hhg001.startswith("HHG-001,")
    assert hhg001.count(",") == 8


def test_persist_marks_answer_files_written(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1] / "cases" / "HHG-001.json"
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    (cases_dir / "HHG-001.json").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    persist_investigation_cases(cases_dir=cases_dir, out_dir=tmp_path / "processed")

    payload = json.loads((cases_dir / "HHG-001.json").read_text(encoding="utf-8"))
    assert payload["case"]["written_to_graph"] is True
    assert payload["case"]["graph_case_id"] == "HHG-001"
