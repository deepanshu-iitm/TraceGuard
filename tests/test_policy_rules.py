from backend.policy.actions import ApprovalRoute, PolicyAction
from backend.policy.rules import CustomerResponse, PolicySnapshot, recommend_actions


def _actions(snapshot: PolicySnapshot) -> list[PolicyAction]:
    return [item.action for item in recommend_actions(snapshot)]


def test_r1_weak_single_signal_verifies_before_block() -> None:
    out = recommend_actions(
        PolicySnapshot(fraud_probability=0.61, exposure_usd=77, single_signal=True)
    )
    assert [item.action for item in out] == [
        PolicyAction.VERIFY_WITH_CUSTOMER,
        PolicyAction.CREATE_CASE,
    ]
    assert PolicyAction.BLOCK_CARD not in _actions(
        PolicySnapshot(fraud_probability=0.61, exposure_usd=77, single_signal=True)
    )


def test_r2_shared_origin_files_and_monitors() -> None:
    assert _actions(
        PolicySnapshot(
            fraud_probability=0.8,
            exposure_usd=100,
            customer_response=CustomerResponse.DENY,
            shared_origin=True,
        )
    ) == [
        PolicyAction.BLOCK_CARD,
        PolicyAction.CREATE_CASE,
        PolicyAction.FILE_REPORT,
        PolicyAction.MONITOR_CONNECTED_CARDS,
    ]


def test_r2_deny_blocks_and_files_when_exposure_is_high() -> None:
    out = recommend_actions(
        PolicySnapshot(
            fraud_probability=0.9,
            exposure_usd=1500,
            customer_response=CustomerResponse.DENY,
        )
    )
    assert [item.action for item in out] == [
        PolicyAction.BLOCK_CARD,
        PolicyAction.CREATE_CASE,
        PolicyAction.FILE_REPORT,
    ]
    assert out[0].route is ApprovalRoute.L1
    assert out[2].route is ApprovalRoute.L2


def test_r3_confirm_closes_as_not_fraud() -> None:
    assert _actions(
        PolicySnapshot(
            fraud_probability=0.4,
            exposure_usd=200,
            customer_response=CustomerResponse.CONFIRM,
        )
    ) == [PolicyAction.CLOSE_NO_FRAUD]


def test_r4_no_reply_monitors_and_escalates_over_500() -> None:
    assert _actions(
        PolicySnapshot(
            fraud_probability=0.5,
            exposure_usd=600,
            customer_response=CustomerResponse.NO_REPLY,
        )
    ) == [
        PolicyAction.MONITOR_CARD,
        PolicyAction.DECLINE_TRANSACTION,
        PolicyAction.ESCALATE_TO_ANALYST,
    ]


def test_r5_testing_blocks_only_after_cleared_purchase() -> None:
    pending = _actions(
        PolicySnapshot(fraud_probability=0.8, exposure_usd=40, card_testing=True)
    )
    assert pending == [
        PolicyAction.DECLINE_TRANSACTION,
        PolicyAction.STEP_UP_AUTH,
        PolicyAction.CREATE_CASE,
    ]
    cleared = _actions(
        PolicySnapshot(
            fraud_probability=0.8,
            exposure_usd=140,
            card_testing=True,
            testing_large_purchase_cleared=True,
        )
    )
    assert PolicyAction.BLOCK_CARD in cleared


def test_r7_disputed_recurring_does_not_block() -> None:
    actions = _actions(
        PolicySnapshot(
            fraud_probability=0.55,
            exposure_usd=80,
            disputed_but_recurring=True,
        )
    )
    assert actions == [
        PolicyAction.CREATE_CASE,
        PolicyAction.VERIFY_WITH_CUSTOMER,
        PolicyAction.WARN_CUSTOMER,
    ]
    assert PolicyAction.BLOCK_CARD not in actions


def test_r10_blocks_all_cards_only_with_two_confirmed_cards() -> None:
    one = _actions(
        PolicySnapshot(
            fraud_probability=0.95,
            exposure_usd=2000,
            customer_response=CustomerResponse.DENY,
            n_confirmed_fraud_cards=1,
        )
    )
    assert PolicyAction.BLOCK_ALL_CARDS not in one
    two = _actions(
        PolicySnapshot(
            fraud_probability=0.95,
            exposure_usd=2000,
            customer_response=CustomerResponse.DENY,
            n_confirmed_fraud_cards=2,
        )
    )
    assert PolicyAction.BLOCK_ALL_CARDS in two
