from backend.policy.actions import ApprovalRoute, PolicyAction
from backend.policy.permissions import approval_route


def test_auto_actions_do_not_need_a_human() -> None:
    assert approval_route(PolicyAction.VERIFY_WITH_CUSTOMER) is ApprovalRoute.AUTO
    assert approval_route(PolicyAction.CREATE_CASE) is ApprovalRoute.AUTO
    assert approval_route(PolicyAction.CLOSE_NO_FRAUD) is ApprovalRoute.AUTO


def test_decline_and_small_block_are_l1() -> None:
    assert approval_route(PolicyAction.DECLINE_TRANSACTION) is ApprovalRoute.L1
    assert approval_route(PolicyAction.BLOCK_CARD, exposure_usd=2500) is ApprovalRoute.L1


def test_large_block_all_cards_and_file_report_are_l2() -> None:
    assert approval_route(PolicyAction.BLOCK_CARD, exposure_usd=2500.01) is ApprovalRoute.L2
    assert approval_route(PolicyAction.BLOCK_ALL_CARDS) is ApprovalRoute.L2
    assert approval_route(PolicyAction.FILE_REPORT) is ApprovalRoute.L2
