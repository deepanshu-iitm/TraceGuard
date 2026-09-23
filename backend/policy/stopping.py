"""When an investigation must stop."""

from __future__ import annotations

from dataclasses import dataclass

from backend.policy.rules import CustomerResponse

_SETTLED = frozenset({CustomerResponse.DENY, CustomerResponse.CONFIRM})


@dataclass(frozen=True)
class StopSnapshot:
    """Facts the stopping rule is allowed to use."""

    fraud_probability: float
    independent_evidence_count: int = 0
    customer_response: CustomerResponse | None = None
    further_steps_unlikely: bool = False


@dataclass(frozen=True)
class StopDecision:
    """Whether to stop, and the reason written into the answer file."""

    stop: bool
    reason: str
    condition: str | None = None


def stop_decision(snapshot: StopSnapshot) -> StopDecision:
    if snapshot.customer_response in _SETTLED:
        reply = snapshot.customer_response.value
        return StopDecision(
            stop=True,
            reason=f"A verification response settled the question ({reply}).",
            condition="B",
        )
    if snapshot.independent_evidence_count >= 2 and (
        snapshot.fraud_probability >= 0.85 or snapshot.fraud_probability <= 0.15
    ):
        return StopDecision(
            stop=True,
            reason=(
                f"Fraud probability {snapshot.fraud_probability:.2f} is supported "
                f"by {snapshot.independent_evidence_count} independent pieces of evidence."
            ),
            condition="A",
        )
    if snapshot.further_steps_unlikely:
        return StopDecision(
            stop=True,
            reason="Further steps are unlikely to change the decision.",
            condition="C",
        )
    return StopDecision(stop=False, reason="", condition=None)
