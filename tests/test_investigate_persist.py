import csv
import json
from pathlib import Path

from backend.investigate.persist import (
    export_investigation_cases,
    persist_investigation_cases,
    write_investigation_case,
)
from backend.models.answer import Answer


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


def test_write_investigation_case_upserts_hhg001_csv(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1] / "cases" / "HHG-001.json"
    answer = Answer.model_validate_json(source.read_text(encoding="utf-8"))

    written = write_investigation_case(answer, out_dir=tmp_path)

    assert written.case.written_to_graph is True
    assert written.case.graph_case_id == "HHG-001"
    with (tmp_path / "vertices_investigation_case.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["id"] == "HHG-001"
    assert rows[0]["verdict"] == "legitimate"
    with (tmp_path / "case_edges.csv").open(encoding="utf-8", newline="") as handle:
        edges = {(row["edge_type"], row["from_id"], row["to_id"]) for row in csv.DictReader(handle)}
    assert ("case_on_card", "HHG-001", "C12382-K1") in edges
    assert ("case_involves", "HHG-001", "3514030") in edges


def test_write_investigation_case_calls_tigergraph_when_host_is_set(
    monkeypatch, tmp_path: Path
) -> None:
    from backend.config import settings

    calls: dict = {}

    class FakeTools:
        def run_installed_query(self, name, params):
            return []

        def upsert_investigation_case(self, case_id, attributes, edges):
            calls["case_id"] = case_id
            calls["attributes"] = attributes
            calls["edges"] = edges

    monkeypatch.setattr(settings, "tg_host", "https://example.i.tgcloud.io")
    monkeypatch.setattr("backend.graph.tools.get_graph_tools", lambda: FakeTools())
    source = Path(__file__).resolve().parents[1] / "cases" / "HHG-001.json"
    answer = Answer.model_validate_json(source.read_text(encoding="utf-8"))

    write_investigation_case(answer, out_dir=tmp_path)

    assert calls["case_id"] == "HHG-001"
    assert calls["attributes"]["verdict"] == "legitimate"
    assert ("CASE_ON_CARD", "PaymentCard", "C12382-K1") in calls["edges"]
    assert ("CASE_FOR_CUSTOMER", "Customer", "C12382") in calls["edges"]
    source = Path(__file__).resolve().parents[1] / "cases" / "HHG-001.json"
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    (cases_dir / "HHG-001.json").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    persist_investigation_cases(cases_dir=cases_dir, out_dir=tmp_path / "processed")

    payload = json.loads((cases_dir / "HHG-001.json").read_text(encoding="utf-8"))
    assert payload["case"]["written_to_graph"] is True
    assert payload["case"]["graph_case_id"] == "HHG-001"
