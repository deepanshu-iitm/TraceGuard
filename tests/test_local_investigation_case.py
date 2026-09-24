from pathlib import Path

from backend.graph.parse import vertices
from backend.investigate.local_queries import local_investigation_case
from backend.investigate.persist import write_investigation_case
from backend.models.answer import Answer


def test_local_investigation_case_reads_persisted_vertex(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1] / "cases" / "HHG-001.json"
    answer = Answer.model_validate_json(source.read_text(encoding="utf-8"))
    write_investigation_case(answer, out_dir=tmp_path)

    payload = local_investigation_case("HHG-001", processed_dir=tmp_path)
    case = vertices(payload, "c")[0]
    cards = vertices(payload, "cards")
    customers = vertices(payload, "customers")
    prior = vertices(payload, "prior")

    assert case["v_id"] == "HHG-001"
    assert case["attributes"]["verdict"] == "legitimate"
    assert case["attributes"]["status"] == "closed_legitimate"
    assert cards[0]["v_id"] == "C12382-K1"
    assert customers[0]["v_id"] == "C12382"
    assert "CC-1066" in {item["v_id"] for item in prior}


def test_local_investigation_case_missing_vertex_has_empty_attributes(tmp_path: Path) -> None:
    payload = local_investigation_case("HHG-999", processed_dir=tmp_path)
    case = vertices(payload, "c")[0]
    assert case["v_id"] == "HHG-999"
    assert case["attributes"] == {}
    assert vertices(payload, "cards") == []
