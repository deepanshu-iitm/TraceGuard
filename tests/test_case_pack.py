from backend.data import load_case_pack
from backend.models.enums import TriggerType


def test_case_pack_loads_twenty_exam_cases() -> None:
    cases = load_case_pack()
    by_id = {item.case_id: item for item in cases}

    assert list(by_id) == [f"HHG-{index:03d}" for index in range(1, 21)]
    assert by_id["HHG-001"].trigger_type is TriggerType.RISK_SCORE
    assert by_id["HHG-001"].risk_score == 0.61
    assert by_id["HHG-003"].trigger_type is TriggerType.CUSTOMER_REPORT
    assert by_id["HHG-003"].risk_score is None
    assert by_id["HHG-014"].trigger_type is TriggerType.ANALYST_REQUEST
    assert by_id["HHG-014"].flagged_txn_id == "3478561"
