import pytest

from backend.graph.export import PROCESSED_DIR
from backend.investigate import compose_answer, load_case_facts
from backend.models.enums import FraudPattern
from backend.models.evidence import EvidenceSource
from backend.retrieve import retrieve_documents


pytestmark = pytest.mark.skipif(
    not (PROCESSED_DIR / "edges.csv").is_file(),
    reason="export graph CSVs into data/processed first",
)


def test_hhg001_retrieves_policy_pattern_and_closed_case_notes() -> None:
    facts = load_case_facts("HHG-001")
    docs = retrieve_documents(facts, FraudPattern.NONE)
    refs = [item.ref for item in docs]
    sources = {item.source for item in docs}
    assert EvidenceSource.DOCUMENT in sources
    assert "document:policy:R1" in refs
    assert any(ref.startswith("document:pattern:") for ref in refs)
    assert any("closed_case/" in ref for ref in refs)


def test_composer_adds_document_evidence() -> None:
    answer = compose_answer(load_case_facts("HHG-001"))
    assert any(item.source is EvidenceSource.DOCUMENT for item in answer.case.evidence)
