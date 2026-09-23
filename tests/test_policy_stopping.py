from backend.policy.rules import CustomerResponse
from backend.policy.stopping import StopSnapshot, stop_decision


def test_high_probability_stops_only_with_two_independent_evidence() -> None:
    continue_ = stop_decision(
        StopSnapshot(fraud_probability=0.90, independent_evidence_count=1)
    )
    assert continue_.stop is False
    done = stop_decision(StopSnapshot(fraud_probability=0.90, independent_evidence_count=2))
    assert done.stop is True
    assert done.condition == "A"
    assert "0.90" in done.reason


def test_low_probability_stops_only_with_two_independent_evidence() -> None:
    continue_ = stop_decision(
        StopSnapshot(fraud_probability=0.10, independent_evidence_count=1)
    )
    assert continue_.stop is False
    done = stop_decision(StopSnapshot(fraud_probability=0.10, independent_evidence_count=2))
    assert done.stop is True
    assert done.condition == "A"


def test_customer_reply_settles_even_when_probability_is_mid() -> None:
    deny = stop_decision(
        StopSnapshot(
            fraud_probability=0.55,
            independent_evidence_count=1,
            customer_response=CustomerResponse.DENY,
        )
    )
    assert deny.stop is True
    assert deny.condition == "B"
    confirm = stop_decision(
        StopSnapshot(
            fraud_probability=0.40,
            independent_evidence_count=0,
            customer_response=CustomerResponse.CONFIRM,
        )
    )
    assert confirm.stop is True
    assert confirm.condition == "B"


def test_no_reply_does_not_settle() -> None:
    out = stop_decision(
        StopSnapshot(
            fraud_probability=0.55,
            independent_evidence_count=1,
            customer_response=CustomerResponse.NO_REPLY,
        )
    )
    assert out.stop is False


def test_no_further_change_is_condition_c() -> None:
    out = stop_decision(
        StopSnapshot(
            fraud_probability=0.55,
            independent_evidence_count=1,
            further_steps_unlikely=True,
        )
    )
    assert out.stop is True
    assert out.condition == "C"
    assert out.reason == "Further steps are unlikely to change the decision."
