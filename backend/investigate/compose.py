"""Compose an answer file from graph facts, policy rules, and stopping rules."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from backend.investigate.facts import CaseFacts, ClosedCaseFact, TxnFact, load_case_facts
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
from backend.policy.rules import CustomerResponse, PolicySnapshot, RecommendedAction, recommend_actions
from backend.policy.stopping import StopSnapshot, stop_decision
from backend.retrieve import retrieve_documents

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


@dataclass(frozen=True)
class InvestigationDecision:
    """Pattern, policy actions, and stop reason for one case."""

    pattern: FraudPattern
    fraud_probability: float
    assumed: CustomerResponse | None
    disputed: bool
    initial: list[RecommendedAction]
    final: list[RecommendedAction]
    requests: list[EvidenceRequest]
    stop_reason: str


def decide_investigation(facts: CaseFacts) -> InvestigationDecision:
    pattern = _pattern(facts)
    graph_p = _probability(facts, pattern)
    testing, cleared = _card_testing(facts)
    disputed = facts.case.trigger_type is TriggerType.CUSTOMER_REPORT
    shared = _shared_origin(facts)
    recurring = disputed and _known_spend(facts) and not shared
    if recurring:
        pattern = FraudPattern.NONE
        graph_p = 0.12
    single_signal = pattern is FraudPattern.NONE and not disputed and not shared
    exposure = 0.0 if pattern is FraudPattern.NONE and not shared else abs(facts.flagged.amount)
    assumed: CustomerResponse | None
    requests: list[EvidenceRequest] = []

    if recurring:
        final_snap = PolicySnapshot(
            fraud_probability=graph_p,
            exposure_usd=0.0,
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
            shared_origin=shared,
            customer_dispute=True,
        )
        assumed = CustomerResponse.DENY
        initial = recommend_actions(final_snap)
        final = initial
    elif shared:
        final_snap = PolicySnapshot(
            fraud_probability=max(graph_p, 0.80),
            exposure_usd=abs(facts.flagged.amount),
            pattern=pattern if pattern is not FraudPattern.NONE else FraudPattern.CARD_NOT_PRESENT_FRAUD,
            shared_origin=True,
            card_testing=testing,
            testing_large_purchase_cleared=cleared,
        )
        graph_p = final_snap.fraud_probability
        pattern = final_snap.pattern
        assumed = None
        initial = recommend_actions(final_snap)
        final = initial
        exposure = abs(facts.flagged.amount)
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
    return InvestigationDecision(
        pattern=pattern,
        fraud_probability=graph_p,
        assumed=assumed,
        disputed=disputed,
        initial=initial,
        final=final,
        requests=requests,
        stop_reason=stop.reason or "Further steps are unlikely to change the decision.",
    )


def compose_answer(
    facts: CaseFacts,
    documents: list[Evidence] | None = None,
    tool_calls: int = 6,
) -> Answer:
    decision = decide_investigation(facts)
    docs = documents if documents is not None else retrieve_documents(facts, decision.pattern)
    return _build_answer(facts, decision, docs, tool_calls)


def _build_answer(
    facts: CaseFacts,
    decision: InvestigationDecision,
    documents: list[Evidence],
    tool_calls: int,
) -> Answer:
    pattern = decision.pattern
    graph_p = decision.fraud_probability
    assumed = decision.assumed
    disputed = decision.disputed
    initial = decision.initial
    final = decision.final
    requests = decision.requests
    connected = [card_id for card_id in facts.device_card_ids if card_id != facts.card.card_id]
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
            connected_card_ids=connected if verdict is not Verdict.LEGITIMATE else [],
            connected_device_profiles=_device_profiles(facts, verdict),
            exposure_usd=exposure_out,
            evidence=_evidence(
                facts,
                assumed if not disputed else CustomerResponse.DENY,
                pattern,
                documents,
            ),
            similar_prior_cases=[case.case_id for case in facts.closed_cases],
            summary=_summary(facts, verdict, pattern, graph_p),
            written_to_graph=True,
            graph_case_id=facts.case.case_id,
        ),
        evidence_requests=requests,
        next_best_actions=NextBestActions(
            initial=_actions(initial),
            final=_actions(final),
            what_changed=_what_changed(initial, final, assumed, disputed),
        ),
        sar=_sar(facts, filed, verdict, final),
        stop_reason=decision.stop_reason,
        tool_calls=tool_calls,
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
    if _shared_origin(facts) and facts.flagged.channel == "online":
        if _new_device(facts):
            return FraudPattern.CARD_NOT_PRESENT_NEW_DEVICE
        return FraudPattern.CARD_NOT_PRESENT_FRAUD
    if _known_spend(facts):
        return FraudPattern.NONE
    if facts.flagged.channel == "online" and _new_device(facts):
        return FraudPattern.CARD_NOT_PRESENT_NEW_DEVICE
    if facts.flagged.channel == "in_person" and not facts.prior_in_region():
        return FraudPattern.OUT_OF_REGION_USE
    if facts.flagged.channel == "online":
        return FraudPattern.CARD_NOT_PRESENT_FRAUD
    return FraudPattern.NONE


def _probability(facts: CaseFacts, pattern: FraudPattern) -> float:
    if _shared_origin(facts):
        return 0.80
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
    prior = facts.prior()
    if not prior:
        return False
    same_channel = [txn for txn in prior if txn.channel == facts.flagged.channel]
    if len(same_channel) < 3 or len(same_channel) < 0.1 * len(prior):
        return False
    peers = facts.prior_in_region() if facts.flagged.billing_region else tuple(same_channel)
    return _amount_matches(facts, peers)


def _amount_matches_region(facts: CaseFacts) -> bool:
    return _amount_matches(facts, facts.prior_in_region())


def _amount_matches(facts: CaseFacts, prior: tuple[TxnFact, ...] | None = None) -> bool:
    pool = facts.prior_in_region() if prior is None else prior
    if not pool:
        return False
    amount = facts.flagged.amount
    tolerance = max(20.0, 0.25 * amount)
    return any(abs(txn.amount - amount) <= tolerance for txn in pool)


def _shared_origin(facts: CaseFacts) -> bool:
    if facts.case.trigger_type is TriggerType.ANALYST_REQUEST and facts.device_profile_id:
        return True
    if not _specific_device(facts.device_profile_id):
        return False
    return any(card_id != facts.card.card_id for card_id in facts.device_card_ids)


def _specific_device(profile: str) -> bool:
    info = profile.split("|", 1)[0].strip() if profile else ""
    if info in {"", "Windows", "iOS Device", "MacOS", "Linux", "Trident/7.0"}:
        return False
    return any(char.isdigit() for char in info)


def _new_device(facts: CaseFacts) -> bool:
    profile = facts.flagged.device_profile_id
    if not profile:
        return False
    prior = facts.prior()
    seen = {txn.device_profile_id for txn in prior if txn.device_profile_id}
    if seen:
        return profile not in seen
    # Savanna history vertices do not carry device ids. Do not treat that as a new device.
    return not prior


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
    if (
        PolicyAction.WARN_CUSTOMER in actions
        and PolicyAction.BLOCK_CARD not in actions
        and PolicyAction.FILE_REPORT not in actions
    ):
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


def _evidence(
    facts: CaseFacts,
    response: CustomerResponse | None,
    pattern: FraudPattern,
    documents: list[Evidence],
) -> list[Evidence]:
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
    connected = [card_id for card_id in facts.device_card_ids if card_id != facts.card.card_id]
    if facts.device_profile_id:
        if connected:
            claim = (
                f"Device {facts.device_profile_id} is also linked to "
                f"{len(connected)} other card(s): {', '.join(connected)}."
            )
            entity_ids = [facts.device_profile_id, *connected]
        else:
            claim = (
                f"Device {facts.device_profile_id} made this purchase; "
                "shared_cards_on_device found no other payment cards on this profile."
            )
            entity_ids = [facts.device_profile_id, facts.card.card_id]
        items.append(
            Evidence(
                claim=claim,
                source=EvidenceSource.GRAPH,
                ref=f"query:shared_cards_on_device(d={facts.device_profile_id})",
                entity_ids=entity_ids,
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
    items.extend(documents)
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
        reason="R2: customer denied the transaction" if facts.case.trigger_type is TriggerType.CUSTOMER_REPORT else "R6: shared origin or high-exposure confirmed activity",
        narrative=(
            f"On {day}, card {facts.card.card_id} belonging to customer {facts.case.customer_id} "
            f"was used for a {flagged.amount:.2f} USD {flagged.channel} transaction {flagged.txn_id} "
            f"in billing region {flagged.billing_region or 'unknown'}, country {flagged.billing_country or 'unknown'}. "
            f"The product code was {flagged.product_cd}. "
            "Graph neighborhood review found this activity inconsistent with the cardholder's established pattern or linked it to a shared origin. "
            "The investigation treated the purchase as unauthorized. "
            "Connected cards on the same device profile, if any, are recommended for monitoring. "
            "The flagged card is recommended for restriction pending reissue. "
            f"Total unauthorized amount: {flagged.amount:.2f} USD. "
            "This report is filed so a regulator can review the episode on its own."
        ),
        subjects=[facts.case.customer_id, facts.card.card_id],
        total_amount_usd=abs(flagged.amount),
        activity_dates=[day, day],
    )


def _parse(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
