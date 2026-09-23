"""Approval routing from the fraud policy."""

from backend.policy.actions import ApprovalRoute, PolicyAction

_AUTO = frozenset(
    {
        PolicyAction.ALLOW_TRANSACTION,
        PolicyAction.MONITOR_CARD,
        PolicyAction.MONITOR_CONNECTED_CARDS,
        PolicyAction.WARN_CUSTOMER,
        PolicyAction.VERIFY_WITH_CUSTOMER,
        PolicyAction.STEP_UP_AUTH,
        PolicyAction.GENERATE_REPORT,
        PolicyAction.CREATE_CASE,
        PolicyAction.ESCALATE_TO_ANALYST,
        PolicyAction.CLOSE_NO_FRAUD,
    }
)


def approval_route(action: PolicyAction, exposure_usd: float = 0.0) -> ApprovalRoute:
    if action is PolicyAction.FILE_REPORT or action is PolicyAction.BLOCK_ALL_CARDS:
        return ApprovalRoute.L2
    if action is PolicyAction.BLOCK_CARD:
        return ApprovalRoute.L2 if exposure_usd > 2500 else ApprovalRoute.L1
    if action is PolicyAction.DECLINE_TRANSACTION:
        return ApprovalRoute.L1
    if action in _AUTO:
        return ApprovalRoute.AUTO
    raise ValueError(f"Unknown policy action: {action}")
