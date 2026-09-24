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


def test_account_takeover_does_not_cite_confirm_policy() -> None:
    docs = retrieve_documents(load_case_facts("HHG-020"), FraudPattern.ACCOUNT_TAKEOVER)
    refs = [item.ref for item in docs]
    assert "document:policy:R3" not in refs
    assert any(ref in {"document:policy:R2", "document:policy:R6", "document:policy:R10"} for ref in refs)


def test_missing_billing_region_does_not_dump_card_history() -> None:
    answer = compose_answer(load_case_facts("HHG-011"))
    assert all(len(item.entity_ids) <= 12 for item in answer.case.evidence)
    region = next(item for item in answer.case.evidence if "no billing region" in item.claim)
    assert region.entity_ids == ["3583368"]
