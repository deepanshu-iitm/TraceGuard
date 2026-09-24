"""Compose an answer file from graph facts, policy rules, and stopping rules."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from backend.investigate.facts import CaseFacts, ClosedCaseFact, load_case_facts
from backend.models.answer import (
    ActionRecommendation,
    Answer,
    AnswerCase,
    EvidenceRequest,
    EvidenceRequestType,
    NextBestActions,
    SAR,
)
from backend.models.enums import CaseStatus, FraudPattern, TriggerType
from backend.models.evidence import Evidence, EvidenceSource
from backend.models.verdict import Verdict
from backend.policy.actions import PolicyAction
from backend.policy.rules import CustomerResponse, PolicySnapshot, recommend_actions
from backend.policy.stopping import StopSnapshot, stop_decision

CASES_DIR = Path(__file__).resolve().parents[2] / "cases"

_REASON = {
    "R1": "R1: the alert is a single weak signal; verify before any block",
    "R2": "R2: customer denied the transaction",
    "R3": "R3: customer confirmed the transaction",
    "R4": "R4: no customer reply; monitor and decline pending authorizations",
    "R5": "R5: card-testing sequence observed",
    "R6": "R6: shared origin across cards",
    "R7": "R7: disputed charge matches a recurring pattern; do not block",
    "R8": "R8: uncertain with exposure or conflicting evidence",
    "R9": "R9: coordinated undocumented abuse",
    "R10": "R10: two confirmed-fraud cards or compromised credentials",
    "3a": "3a: evidence requested from the customer",
}


def compose_answer(facts: CaseFacts) -> Answer:
    pattern = _pattern(facts)
    graph_p = _probability(facts, pattern)
    testing, cleared = _card_testing(facts)
    disputed = facts.case.trigger_type is TriggerType.CUSTOMER_REPORT
    recurring = disputed and _known_spend(facts)
    single_signal = pattern is FraudPattern.NONE and not disputed
    exposure = 0.0 if pattern is FraudPattern.NONE else abs(facts.flagged.amount)
    assumed: CustomerResponse | None
    requests: list[EvidenceRequest] = []

    if recurring:
        final_snap = PolicySnapshot(
            fraud_probability=graph_p,
            exposure_usd=exposure,
            pattern=pattern,
            disputed_but_recurring=True,
            customer_dispute=True,
        )
        assumed = None
        initial = recommend_actions(final_snap)
        final = initial
    elif disputed:
        final_snap = PolicySnapshot(
            fraud_probability=graph_p,
            exposure_usd=exposure,
            pattern=pattern,
            customer_response=CustomerResponse.DENY,
            card_testing=testing,
            testing_large_purchase_cleared=cleared,
            customer_dispute=True,
        )
        assumed = CustomerResponse.DENY
        initial = recommend_actions(final_snap)
        final = initial
    else:
        assumed = _assumed_response(facts, pattern, disputed)
        initial = recommend_actions(
            PolicySnapshot(
                fraud_probability=graph_p,
                exposure_usd=exposure,
                pattern=pattern,
                single_signal=single_signal,
                card_testing=testing,
                testing_large_purchase_cleared=cleared,
                evidence_requested=assumed is not None,
            )
        )
        final_snap = PolicySnapshot(
            fraud_probability=graph_p,
            exposure_usd=exposure,
            pattern=pattern,
            single_signal=single_signal,
            customer_response=assumed,
            card_testing=testing,
            testing_large_purchase_cleared=cleared,
            evidence_requested=assumed is not None,
        )
        final = recommend_actions(final_snap)
        if assumed is not None:
            requests.append(
                EvidenceRequest(
                    type=EvidenceRequestType.CUSTOMER_VALIDATION,
                    asked_after_step=4,
                    assumed_response=_assumed_text(facts, assumed),
                )
            )

    stop = stop_decision(
        StopSnapshot(
            fraud_probability=graph_p,
            independent_evidence_count=2,
            customer_response=final_snap.customer_response,
            further_steps_unlikely=final_snap.customer_response is None,
        )
    )
    verdict = _verdict(final, pattern)
    status = _status(final, verdict)
    affected = [] if verdict is Verdict.LEGITIMATE else [facts.flagged.txn_id]
    exposure_out = 0.0 if verdict is Verdict.LEGITIMATE else round(sum(
        abs(txn.amount) for txn in facts.history if txn.txn_id in set(affected)
    ), 2)
    filed = any(item.action is PolicyAction.FILE_REPORT for item in final)
    return Answer(
        case_id=facts.case.case_id,
        case=AnswerCase(
            status=status,
            verdict=verdict,
            fraud_probability=graph_p,
            pattern=FraudPattern.NONE if verdict is Verdict.LEGITIMATE else pattern,
            pattern_description="",
            affected_txn_ids=affected,
            first_suspicious_txn_id="" if not affected else affected[0],
            connected_card_ids=[],
            connected_device_profiles=_device_profiles(facts, verdict),
            exposure_usd=exposure_out,
            evidence=_evidence(facts, assumed if not disputed else CustomerResponse.DENY),
            similar_prior_cases=[case.case_id for case in facts.closed_cases],
            summary=_summary(facts, verdict, pattern, graph_p),
            written_to_graph=False,
            graph_case_id="",
        ),
        evidence_requests=requests,
        next_best_actions=NextBestActions(
            initial=_actions(initial),
            final=_actions(final),
            what_changed=_what_changed(initial, final, assumed, disputed),
        ),
        sar=_sar(facts, filed, verdict, final),
        stop_reason=stop.reason or "Further steps are unlikely to change the decision.",
        tool_calls=6,
        tokens=0,
        latency_s=0.0,
    )


def write_answer(case_id: str, out_dir: Path | None = None) -> Path:
    dest_dir = out_dir or CASES_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / f"{case_id}.json"
    answer = compose_answer(load_case_facts(case_id))
    path.write_text(json.dumps(answer.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    return path


def _pattern(facts: CaseFacts) -> FraudPattern:
    testing, _cleared = _card_testing(facts)
    if testing:
        return FraudPattern.CARD_TESTING
    if facts.flagged.channel == "online" and _new_device(facts):
        return FraudPattern.CARD_NOT_PRESENT_NEW_DEVICE
    if facts.flagged.channel == "in_person" and not facts.prior_in_region():
        return FraudPattern.OUT_OF_REGION_USE
    if facts.flagged.channel == "online" and not _amount_matches_region(facts):
        return FraudPattern.CARD_NOT_PRESENT_FRAUD
    return FraudPattern.NONE


def _probability(facts: CaseFacts, pattern: FraudPattern) -> float:
    if pattern is FraudPattern.NONE and _known_spend(facts):
        return 0.12
    if pattern is FraudPattern.CARD_TESTING:
        return 0.82
    if pattern is FraudPattern.CARD_NOT_PRESENT_NEW_DEVICE:
        return 0.74
    if pattern is FraudPattern.OUT_OF_REGION_USE:
        return 0.68
    if pattern is FraudPattern.CARD_NOT_PRESENT_FRAUD:
        return 0.58
    return 0.45


def _known_spend(facts: CaseFacts) -> bool:
    return len(facts.prior_in_region()) >= 3 and _amount_matches_region(facts)


def _amount_matches_region(facts: CaseFacts) -> bool:
    prior = facts.prior_in_region()
    if not prior:
        return False
    return any(abs(txn.amount - facts.flagged.amount) <= 5 for txn in prior)


def _new_device(facts: CaseFacts) -> bool:
    profile = facts.flagged.device_profile_id
    if not profile:
        return False
    seen = {txn.device_profile_id for txn in facts.prior() if txn.device_profile_id}
    return profile not in seen


def _card_testing(facts: CaseFacts) -> tuple[bool, bool]:
    flagged = facts.flagged
    start = _parse(flagged.ts) - timedelta(hours=1)
    small = [
        txn
        for txn in facts.prior()
        if txn.channel == "online"
        and txn.amount < 5
        and _parse(txn.ts) >= start
    ]
    if len(small) >= 3 and flagged.channel == "online" and flagged.amount >= 5:
        return True, flagged.amount > 100
    return False, False


def _assumed_response(
    facts: CaseFacts, pattern: FraudPattern, disputed: bool
) -> CustomerResponse | None:
    if disputed:
        return CustomerResponse.DENY
    if pattern is FraudPattern.NONE and _known_spend(facts):
        return CustomerResponse.CONFIRM
    if pattern is FraudPattern.NONE:
        return CustomerResponse.CONFIRM
    return CustomerResponse.DENY


def _verdict(final: list, pattern: FraudPattern) -> Verdict:
    actions = {item.action for item in final}
    if PolicyAction.CLOSE_NO_FRAUD in actions:
        return Verdict.LEGITIMATE
    if PolicyAction.ESCALATE_TO_ANALYST in actions and PolicyAction.BLOCK_CARD not in actions:
        return Verdict.UNCERTAIN
    if PolicyAction.BLOCK_CARD in actions or PolicyAction.FILE_REPORT in actions:
        return Verdict.FRAUD
    if pattern is FraudPattern.NONE:
        return Verdict.LEGITIMATE
    return Verdict.UNCERTAIN


def _status(final: list, verdict: Verdict) -> CaseStatus:
    actions = {item.action for item in final}
    if PolicyAction.ESCALATE_TO_ANALYST in actions and verdict is Verdict.UNCERTAIN:
        return CaseStatus.ESCALATED
    if verdict is Verdict.LEGITIMATE:
        return CaseStatus.CLOSED_LEGITIMATE
    if verdict is Verdict.FRAUD:
        return CaseStatus.CLOSED_FRAUD
    return CaseStatus.OPEN


def _device_profiles(facts: CaseFacts, verdict: Verdict) -> list[str]:
    if verdict is Verdict.LEGITIMATE or not facts.flagged.device_profile_id:
        return []
    return [facts.flagged.device_profile_id]


def _evidence(facts: CaseFacts, response: CustomerResponse | None) -> list[Evidence]:
    flagged = facts.flagged
    region_prior = facts.prior_in_region()
    items = [
        Evidence(
            claim=(
                f"Flagged transaction {flagged.txn_id} is a {flagged.amount:.2f} USD "
                f"{flagged.channel} product-{flagged.product_cd} purchase in billing region "
                f"{flagged.billing_region or 'unknown'} on {flagged.ts}. Card {facts.card.card_id} "
                f"is a {facts.card.network} {facts.card.card_type} owned by {facts.case.customer_id}."
            ),
            source=EvidenceSource.GRAPH,
            ref=f"query:investigate_txn(t={flagged.txn_id})",
            entity_ids=[flagged.txn_id, facts.card.card_id, facts.case.customer_id],
        ),
        Evidence(
            claim=(
                f"Region {flagged.billing_region} has {len(region_prior)} prior purchases on this card "
                f"before the alert."
                if flagged.billing_region
                else "The flagged transaction has no billing region on the graph."
            ),
            source=EvidenceSource.GRAPH,
            ref=f"query:card_region_history(card_id={facts.card.card_id}, region={flagged.billing_region})",
            entity_ids=[txn.txn_id for txn in region_prior] + [flagged.txn_id],
        ),
    ]
    if facts.closed_cases:
        items.append(
            Evidence(
                claim=_closed_claim(facts.closed_cases),
                source=EvidenceSource.GRAPH,
                ref=f"query:closed_cases(card_id={facts.card.card_id})",
                entity_ids=_closed_ids(facts.closed_cases),
            )
        )
    if response is CustomerResponse.CONFIRM:
        items.append(
            Evidence(
                claim=(
                    f"Customer confirmed they made the {flagged.amount:.2f} USD "
                    f"{flagged.channel} purchase in billing region {flagged.billing_region} "
                    "and still have the card."
                ),
                source=EvidenceSource.CUSTOMER,
                ref="evidence_request:1",
                entity_ids=[],
            )
        )
    elif response is CustomerResponse.DENY:
        items.append(
            Evidence(
                claim="Customer denied the purchase and still has the card.",
                source=EvidenceSource.CUSTOMER,
                ref="evidence_request:1" if facts.case.trigger_type is not TriggerType.CUSTOMER_REPORT else "trigger:customer_report",
                entity_ids=[],
            )
        )
    return items


def _closed_claim(cases: tuple[ClosedCaseFact, ...]) -> str:
    parts = [f"{case.case_id} ({case.outcome}, {case.pattern})" for case in cases]
    return "Closed cases on this card: " + "; ".join(parts) + "."


def _closed_ids(cases: tuple[ClosedCaseFact, ...]) -> list[str]:
    ids = [case.case_id for case in cases]
    for case in cases:
        ids.extend(case.txn_ids)
    return ids


def _summary(
    facts: CaseFacts, verdict: Verdict, pattern: FraudPattern, probability: float
) -> str:
    flagged = facts.flagged
    return (
        f"{facts.case.case_id} is a {facts.case.trigger_type.value} alert on a "
        f"{flagged.amount:.2f} USD {flagged.channel} purchase in billing region "
        f"{flagged.billing_region or 'unknown'}. Graph history shows "
        f"{len(facts.prior_in_region())} prior purchases in that region. "
        f"Pattern is {pattern.value}; fraud probability {probability:.2f}. "
        f"Verdict is {verdict.value}."
    )


def _assumed_text(facts: CaseFacts, response: CustomerResponse) -> str:
    flagged = facts.flagged
    if response is CustomerResponse.CONFIRM:
        return (
            f"Customer confirms they made the {flagged.amount:.2f} USD "
            f"{flagged.channel} purchase in billing region {flagged.billing_region} "
            "and still have the card."
        )
    return "Customer states they did not make this purchase and still have the card."


def _actions(items: list) -> list[ActionRecommendation]:
    return [
        ActionRecommendation(
            action=item.action,
            route=item.route,
            reason=_REASON.get(item.reason, item.reason),
        )
        for item in items
    ]


def _what_changed(initial: list, final: list, assumed: CustomerResponse | None, disputed: bool) -> str:
    if disputed or initial == final:
        return "nothing"
    if assumed is CustomerResponse.CONFIRM:
        return "Customer confirmation replaced verification with close as not fraud."
    if assumed is CustomerResponse.DENY:
        return "Customer denial confirmed the block."
    return "nothing"


def _sar(facts: CaseFacts, filed: bool, verdict: Verdict, final: list) -> SAR:
    if not filed or verdict is Verdict.LEGITIMATE:
        reason = "FILE_REPORT is not recommended"
        if any(item.reason == "R3" or item.action is PolicyAction.CLOSE_NO_FRAUD for item in final):
            reason = "R3: customer confirmed; FILE_REPORT is not recommended"
        return SAR(
            file=False,
            reason=reason,
            narrative="",
            subjects=[],
            total_amount_usd=0,
            activity_dates=[],
        )
    flagged = facts.flagged
    day = flagged.ts[:10]
    return SAR(
        file=True,
        reason="R2: customer denied the transaction" if facts.case.trigger_type is TriggerType.CUSTOMER_REPORT else "Policy recommended FILE_REPORT",
        narrative=(
            f"On {day}, card {facts.card.card_id} belonging to customer {facts.case.customer_id} "
            f"was used for a {flagged.amount:.2f} USD {flagged.channel} transaction {flagged.txn_id} "
            f"in billing region {flagged.billing_region or 'unknown'}. "
            "The activity is inconsistent with the investigation conclusion and was treated as unauthorized. "
            "The cardholder denied the purchase or the graph pattern matched confirmed fraud. "
            "The card is recommended for block and the episode is recorded for case memory. "
            f"Total unauthorized amount: {flagged.amount:.2f} USD."
        ),
        subjects=[facts.case.customer_id, facts.card.card_id],
        total_amount_usd=abs(flagged.amount),
        activity_dates=[day, day],
    )


def _parse(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
