"""Fraud policy rules R1–R10."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.models.enums import FraudPattern
from backend.policy.actions import ApprovalRoute, PolicyAction
from backend.policy.permissions import approval_route


class CustomerResponse(str, Enum):
    """Assumed customer reply for this investigation step."""

    DENY = "deny"
    CONFIRM = "confirm"
    NO_REPLY = "no_reply"


@dataclass(frozen=True)
class PolicySnapshot:
    """Facts the policy engine is allowed to use."""

    fraud_probability: float
    exposure_usd: float
    pattern: FraudPattern = FraudPattern.NONE
    single_signal: bool = False
    customer_response: CustomerResponse | None = None
    card_testing: bool = False
    testing_large_purchase_cleared: bool = False
    shared_origin: bool = False
    linked_other_card_fraud: bool = False
    disputed_but_recurring: bool = False
    evidence_conflicts: bool = False
    coordinated_undocumented: bool = False
    n_confirmed_fraud_cards: int = 0
    credentials_compromised: bool = False
    evidence_requested: bool = False
    customer_dispute: bool = False


@dataclass(frozen=True)
class RecommendedAction:
    """One policy action with its approval route and rule citation."""

    action: PolicyAction
    route: ApprovalRoute
    reason: str


def recommend_actions(snapshot: PolicySnapshot) -> list[RecommendedAction]:
    actions: list[RecommendedAction] = []

    if snapshot.disputed_but_recurring:
        _add(actions, PolicyAction.CREATE_CASE, "R7", snapshot)
        _add(actions, PolicyAction.VERIFY_WITH_CUSTOMER, "R7", snapshot)
        _add(actions, PolicyAction.WARN_CUSTOMER, "R7", snapshot)
        return actions

    if snapshot.customer_response is CustomerResponse.CONFIRM:
        _add(actions, PolicyAction.CLOSE_NO_FRAUD, "R3", snapshot)
        return actions

    if snapshot.customer_response is CustomerResponse.DENY:
        _add(actions, PolicyAction.BLOCK_CARD, "R2", snapshot)
        _add(actions, PolicyAction.CREATE_CASE, "R2", snapshot)
        if snapshot.exposure_usd > 1000 or snapshot.shared_origin or snapshot.linked_other_card_fraud:
            _add(actions, PolicyAction.FILE_REPORT, "R2", snapshot)
        if snapshot.shared_origin:
            _add(actions, PolicyAction.MONITOR_CONNECTED_CARDS, "R6", snapshot)
        if snapshot.n_confirmed_fraud_cards >= 2 or snapshot.credentials_compromised:
            _add(actions, PolicyAction.BLOCK_ALL_CARDS, "R10", snapshot)
        return _apply_r10(actions, snapshot)

    if snapshot.customer_response is CustomerResponse.NO_REPLY:
        _add(actions, PolicyAction.MONITOR_CARD, "R4", snapshot)
        _add(actions, PolicyAction.DECLINE_TRANSACTION, "R4", snapshot)
        if snapshot.exposure_usd > 500:
            _add(actions, PolicyAction.ESCALATE_TO_ANALYST, "R4", snapshot)
        return actions

    if snapshot.card_testing or snapshot.pattern is FraudPattern.CARD_TESTING:
        _add(actions, PolicyAction.DECLINE_TRANSACTION, "R5", snapshot)
        _add(actions, PolicyAction.STEP_UP_AUTH, "R5", snapshot)
        if snapshot.testing_large_purchase_cleared:
            _add(actions, PolicyAction.BLOCK_CARD, "R5", snapshot)
        _maybe_create_case(actions, snapshot)
        return _apply_r10(actions, snapshot)

    if snapshot.coordinated_undocumented:
        _add(actions, PolicyAction.CREATE_CASE, "R9", snapshot)
        _add(actions, PolicyAction.FILE_REPORT, "R9", snapshot)
        _add(actions, PolicyAction.ESCALATE_TO_ANALYST, "R9", snapshot)
        return _apply_r10(actions, snapshot)

    if snapshot.shared_origin:
        _add(actions, PolicyAction.CREATE_CASE, "R6", snapshot)
        _add(actions, PolicyAction.FILE_REPORT, "R6", snapshot)
        _add(actions, PolicyAction.MONITOR_CONNECTED_CARDS, "R6", snapshot)
        return _apply_r10(actions, snapshot)

    if snapshot.single_signal and snapshot.fraud_probability < 0.70:
        _add(actions, PolicyAction.VERIFY_WITH_CUSTOMER, "R1", snapshot)
        _maybe_create_case(actions, snapshot)
        return actions

    if _uncertain(snapshot) and (snapshot.exposure_usd > 500 or snapshot.evidence_conflicts):
        _add(actions, PolicyAction.ESCALATE_TO_ANALYST, "R8", snapshot)
        _maybe_create_case(actions, snapshot)
        return actions

    _maybe_create_case(actions, snapshot)
    return _apply_r10(actions, snapshot)


def _uncertain(snapshot: PolicySnapshot) -> bool:
    return 0.15 < snapshot.fraud_probability < 0.85


def _maybe_create_case(actions: list[RecommendedAction], snapshot: PolicySnapshot) -> None:
    if (
        snapshot.fraud_probability >= 0.30
        or snapshot.evidence_requested
        or snapshot.customer_dispute
    ):
        _add(actions, PolicyAction.CREATE_CASE, "3a", snapshot)


def _apply_r10(
    actions: list[RecommendedAction], snapshot: PolicySnapshot
) -> list[RecommendedAction]:
    allowed = snapshot.n_confirmed_fraud_cards >= 2 or snapshot.credentials_compromised
    if allowed:
        return actions
    return [item for item in actions if item.action is not PolicyAction.BLOCK_ALL_CARDS]


def _add(
    actions: list[RecommendedAction],
    action: PolicyAction,
    rule: str,
    snapshot: PolicySnapshot,
) -> None:
    if any(item.action is action for item in actions):
        return
    actions.append(
        RecommendedAction(
            action=action,
            route=approval_route(action, snapshot.exposure_usd),
            reason=rule,
        )
    )
