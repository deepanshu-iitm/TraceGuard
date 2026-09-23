import json
from pathlib import Path

from backend.models.answer import Answer
from backend.models.enums import CaseStatus, FraudPattern
from backend.models.verdict import Verdict
from backend.policy.actions import PolicyAction

ANSWER_PATH = Path(__file__).resolve().parents[1] / "cases" / "HHG-001.json"


def test_hhg001_is_a_valid_legitimate_answer() -> None:
    payload = json.loads(ANSWER_PATH.read_text(encoding="utf-8"))
    answer = Answer.model_validate(payload)

    assert answer.case_id == "HHG-001"
    assert answer.case.status is CaseStatus.CLOSED_LEGITIMATE
    assert answer.case.verdict is Verdict.LEGITIMATE
    assert answer.case.pattern is FraudPattern.NONE
    assert answer.case.affected_txn_ids == []
    assert answer.case.exposure_usd == 0
    assert answer.sar.file is False
    assert answer.next_best_actions.final[0].action is PolicyAction.CLOSE_NO_FRAUD
    assert "3514030" in answer.case.evidence[0].entity_ids
