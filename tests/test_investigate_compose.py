import pytest

from backend.graph.export import PROCESSED_DIR
from backend.investigate import compose_answer, load_case_facts
from backend.models.enums import CaseStatus, FraudPattern
from backend.models.verdict import Verdict
from backend.policy.actions import PolicyAction


pytestmark = pytest.mark.skipif(
    not (PROCESSED_DIR / "edges.csv").is_file(),
    reason="export graph CSVs into data/processed first",
)


def test_composer_matches_hhg001_verdict_and_actions() -> None:
    answer = compose_answer(load_case_facts("HHG-001"))

    assert answer.case_id == "HHG-001"
    assert answer.case.status is CaseStatus.CLOSED_LEGITIMATE
    assert answer.case.verdict is Verdict.LEGITIMATE
    assert answer.case.pattern is FraudPattern.NONE
    assert answer.case.affected_txn_ids == []
    assert answer.case.exposure_usd == 0
    assert answer.case.fraud_probability < 0.20
    assert answer.sar.file is False
    assert answer.case.written_to_graph is True
    assert answer.case.graph_case_id == "HHG-001"
    assert [item.action for item in answer.next_best_actions.initial] == [
        PolicyAction.VERIFY_WITH_CUSTOMER,
        PolicyAction.CREATE_CASE,
    ]
    assert [item.action for item in answer.next_best_actions.final] == [
        PolicyAction.CLOSE_NO_FRAUD,
    ]
    assert answer.stop_reason.startswith("A verification response settled")


def test_composer_returns_schema_valid_answer_for_a_customer_report() -> None:
    answer = compose_answer(load_case_facts("HHG-003"))
    assert answer.case_id == "HHG-003"
    assert answer.sar.file is (
        any(item.action is PolicyAction.FILE_REPORT for item in answer.next_best_actions.final)
    )


def test_composer_treats_hhg014_shared_device_as_fraud() -> None:
    answer = compose_answer(load_case_facts("HHG-014"))
    assert answer.case.verdict is Verdict.FRAUD
    assert PolicyAction.FILE_REPORT in [item.action for item in answer.next_best_actions.final]
    assert PolicyAction.MONITOR_CONNECTED_CARDS in [
        item.action for item in answer.next_best_actions.final
    ]
