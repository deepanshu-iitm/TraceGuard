import pytest

from backend.graph.export import PROCESSED_DIR
from backend.investigate import compose_answer, investigate, load_case_facts
from backend.investigate.agent import investigate_state
from backend.models.enums import CaseStatus
from backend.models.evidence import EvidenceSource
from backend.models.verdict import Verdict
from backend.policy.actions import PolicyAction


pytestmark = pytest.mark.skipif(
    not (PROCESSED_DIR / "edges.csv").is_file(),
    reason="export graph CSVs into data/processed first",
)


def test_agent_runs_facts_policy_retrieve_compose_for_hhg001() -> None:
    state = investigate_state("HHG-001")
    composed = compose_answer(
        load_case_facts("HHG-001"),
        tool_calls=state["answer"].tool_calls,
    )

    assert state["steps"] == ["facts", "policy", "retrieve", "compose", "explain"]
    assert state["answer"] == composed
    assert investigate("HHG-001") == composed
    assert state["answer"].tool_calls >= 2
    assert any(item.source is EvidenceSource.DOCUMENT for item in state["documents"])
    assert PolicyAction.CLOSE_NO_FRAUD.value in state["final_actions"]
    assert state["answer"].case.status is CaseStatus.CLOSED_LEGITIMATE


def test_agent_matches_composer_for_shared_device_fraud() -> None:
    answer = investigate("HHG-014")
    composed = compose_answer(load_case_facts("HHG-014"), tool_calls=answer.tool_calls)
    assert answer.case.verdict is Verdict.FRAUD
    assert answer.tool_calls >= 3
    assert any("shared_cards_on_device" in item.ref for item in answer.case.evidence)
    assert answer == composed
