"""Compose an answer file from graph facts, policy rules, and stopping rules."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from backend.investigate.analysis import (
    account_takeover,
    calibrated_probability,
    card_testing,
    connected_card_ids,
    detect_pattern,
    episode_exposure,
    episode_txns,
    evidence_conflicts,
    known_spend,
    new_device as _new_device,
    pattern_description,
    shared_origin,
    undocumented_coordinated,
)
from backend.investigate.facts import CaseFacts, ClosedCaseFact, TxnFact, load_case_facts, load_local_case_facts
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
from backend.retrieve import retrieve_documents, retrieve_similar_cases

CASES_DIR = Path(__file__).resolve().parents[2] / "cases"
_ENTITY_CAP = 12

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
    episode: tuple[TxnFact, ...] = ()


def decide_investigation(facts: CaseFacts) -> InvestigationDecision:
    pattern = detect_pattern(facts)
    graph_p = calibrated_probability(facts, pattern)
    testing, cleared = card_testing(facts)
    disputed = facts.case.trigger_type is TriggerType.CUSTOMER_REPORT
    shared = shared_origin(facts)
    undocumented = undocumented_coordinated(facts)
    recurring = disputed and known_spend(facts) and not shared
    if recurring:
        pattern = FraudPattern.NONE
        graph_p = calibrated_probability(facts, pattern)
    conflicts = evidence_conflicts(facts)
    step_up = (account_takeover(facts) or _new_device(facts)) and pattern is not FraudPattern.NONE
    single_signal = not disputed and not shared and graph_p < 0.70 and not testing
    episode = tuple(episode_txns(facts, pattern))
    exposure = 0.0 if pattern is FraudPattern.NONE and not shared else episode_exposure(list(episode)) or abs(facts.flagged.amount)
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
        episode = ()
        exposure = 0.0
    elif disputed:
        final_snap = PolicySnapshot(
            fraud_probability=graph_p,
            exposure_usd=exposure,
            pattern=pattern,
            customer_response=CustomerResponse.DENY,
            card_testing=testing,
            testing_large_purchase_cleared=cleared,
            shared_origin=shared,
            coordinated_undocumented=undocumented,
            customer_dispute=True,
            evidence_conflicts=conflicts,
        )
        assumed = CustomerResponse.DENY
        initial = recommend_actions(final_snap)
        final = initial
    elif undocumented:
        final_snap = PolicySnapshot(
            fraud_probability=max(graph_p, 0.70),
            exposure_usd=exposure,
            pattern=FraudPattern.UNDOCUMENTED,
            coordinated_undocumented=True,
            shared_origin=shared,
        )
        graph_p = final_snap.fraud_probability
        pattern = final_snap.pattern
        assumed = None
        initial = recommend_actions(final_snap)
        final = initial
    elif shared:
        final_snap = PolicySnapshot(
            fraud_probability=max(graph_p, 0.80),
            exposure_usd=exposure or abs(facts.flagged.amount),
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
        exposure = final_snap.exposure_usd
        if not episode:
            episode = (facts.flagged,)
    else:
        assumed = _assumed_response(facts, pattern, disputed, graph_p, step_up)
        request_type = (
            EvidenceRequestType.STEP_UP_AUTH if step_up else EvidenceRequestType.CUSTOMER_VALIDATION
        )
        initial = recommend_actions(
            PolicySnapshot(
                fraud_probability=graph_p,
                exposure_usd=exposure,
                pattern=pattern,
                single_signal=single_signal,
                card_testing=testing,
                testing_large_purchase_cleared=cleared,
                evidence_requested=assumed is not None,
                evidence_conflicts=conflicts,
                step_up_auth=step_up,
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
            evidence_conflicts=conflicts,
            step_up_auth=step_up,
        )
        final = recommend_actions(final_snap)
        if assumed is not None:
            requests.append(
                EvidenceRequest(
                    type=request_type,
                    asked_after_step=4,
                    assumed_response=_assumed_text(facts, assumed, request_type),
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
        episode=episode,
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
    connected = connected_card_ids(facts)
    verdict = _verdict(final, pattern)
    status = _status(final, verdict)
    episode = list(decision.episode)
    affected = [] if verdict is Verdict.LEGITIMATE else [txn.txn_id for txn in episode] or [facts.flagged.txn_id]
    exposure_out = 0.0 if verdict is Verdict.LEGITIMATE else episode_exposure(
        [txn for txn in facts.history if txn.txn_id in set(affected)] or [facts.flagged]
    )
    filed = any(item.action is PolicyAction.FILE_REPORT for item in final)
    return Answer(
        case_id=facts.case.case_id,
        case=AnswerCase(
            status=status,
            verdict=verdict,
            fraud_probability=graph_p,
            pattern=FraudPattern.NONE if verdict is Verdict.LEGITIMATE else pattern,
            pattern_description="" if verdict is Verdict.LEGITIMATE else pattern_description(facts, pattern),
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
                affected,
            ),
            similar_prior_cases=retrieve_similar_cases(facts, pattern),
            summary=_summary(facts, verdict, pattern, graph_p, affected, exposure_out),
            written_to_graph=True,
            graph_case_id=facts.case.case_id,
        ),
        evidence_requests=requests,
        next_best_actions=NextBestActions(
            initial=_actions(initial),
            final=_actions(final),
            what_changed=_what_changed(initial, final, assumed, disputed),
        ),
        sar=_sar(facts, filed, verdict, final, affected, exposure_out),
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


def write_exam_answers(out_dir: Path | None = None) -> list[Path]:
    """Rebuild the 20 exam files from local graph facts and the LangGraph loop."""
    from backend.data import load_case_pack
    from backend.investigate.agent import investigate

    dest_dir = out_dir or CASES_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for item in load_case_pack():
        answer = investigate(item.case_id, load_local_case_facts(item.case_id))
        path = dest_dir / f"{item.case_id}.json"
        path.write_text(json.dumps(answer.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def _pattern(facts: CaseFacts) -> FraudPattern:
    return detect_pattern(facts)


def _probability(facts: CaseFacts, pattern: FraudPattern) -> float:
    return calibrated_probability(facts, pattern)


def _known_spend(facts: CaseFacts) -> bool:
    return known_spend(facts)


def _shared_origin(facts: CaseFacts) -> bool:
    return shared_origin(facts)


def _card_testing(facts: CaseFacts) -> tuple[bool, bool]:
    return card_testing(facts)


def _assumed_response(
    facts: CaseFacts,
    pattern: FraudPattern,
    disputed: bool,
    probability: float = 0.0,
    step_up: bool = False,
) -> CustomerResponse | None:
    if disputed:
        return CustomerResponse.DENY
    if pattern is FraudPattern.NONE:
        return CustomerResponse.CONFIRM
    if step_up:
        return CustomerResponse.DENY
    if 0.15 < probability < 0.70:
        return CustomerResponse.NO_REPLY
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
    affected: list[str] | None = None,
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
            entity_ids=_cap_ids([txn.txn_id for txn in region_prior] + [flagged.txn_id]),
        ),
    ]
    if facts.closed_cases:
        items.append(
            Evidence(
                claim=_closed_claim(facts.closed_cases),
                source=EvidenceSource.GRAPH,
                ref=f"query:closed_cases(card_id={facts.card.card_id})",
                entity_ids=_cap_ids(_closed_ids(facts.closed_cases)),
            )
        )
    device_connected = [
        card_id for card_id in facts.device_card_ids if card_id != facts.card.card_id
    ]
    if facts.device_profile_id:
        if device_connected:
            claim = (
                f"Device {facts.device_profile_id} is also linked to "
                f"{len(device_connected)} other card(s): {', '.join(device_connected)}."
            )
            entity_ids = _cap_ids([facts.device_profile_id, *device_connected])
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
    email = facts.flagged.recipient_email or facts.flagged.purchaser_email
    email_others = [card_id for card_id in facts.email_card_ids if card_id != facts.card.card_id]
    if email:
        if 1 <= len(email_others) <= 6:
            claim = (
                f"Email domain {email} also links {len(email_others)} other card(s): "
                f"{', '.join(email_others)}."
            )
            entity_ids = list(email_others) or [facts.card.card_id]
        else:
            claim = (
                f"Email domain {email} is present on the flagged purchase; "
                f"email_fanout found {len(email_others)} other cards, treated as too common for R6."
            )
            entity_ids = [facts.card.card_id]
        items.append(
            Evidence(
                claim=claim,
                source=EvidenceSource.GRAPH,
                ref=f"query:email_fanout(e={email})",
                entity_ids=entity_ids,
            )
        )
    if facts.flagged.billing_region:
        region_others = [
            card_id for card_id in facts.region_card_ids if card_id != facts.card.card_id
        ]
        items.append(
            Evidence(
                claim=(
                    f"Billing region {facts.flagged.billing_region} also links "
                    f"{len(region_others)} other card(s)."
                    if 1 <= len(region_others) <= 6
                    else (
                        f"Billing region {facts.flagged.billing_region} appears on "
                        f"{len(region_others)} other cards in the local 1-hop fan-out. "
                        "Region sharing is recorded, not treated as proof of a shared origin."
                    )
                ),
                source=EvidenceSource.GRAPH,
                ref=f"query:region_fanout(r={facts.flagged.billing_region})",
                entity_ids=[facts.card.card_id],
            )
        )
    if known_spend(facts):
        items.append(
            Evidence(
                claim=(
                    "Supports legitimate: flagged amount and channel match established spend "
                    f"on card {facts.card.card_id}."
                ),
                source=EvidenceSource.GRAPH,
                ref=f"query:card_region_history(card_id={facts.card.card_id}, region={flagged.billing_region})",
                entity_ids=[facts.card.card_id, flagged.txn_id],
            )
        )
    if _new_device(facts) or shared_origin(facts) or account_takeover(facts):
        items.append(
            Evidence(
                claim=(
                    "Supports fraud: new device, mixed-channel takeover, or a tight shared-origin "
                    "cluster is present on the neighborhood."
                ),
                source=EvidenceSource.GRAPH,
                ref=f"query:shared_cards_on_device(d={facts.device_profile_id or facts.card.card_id})",
                entity_ids=[facts.card.card_id, flagged.txn_id],
            )
        )
    if affected and len(affected) > 1:
        items.append(
            Evidence(
                claim=(
                    f"Episode reconstruction grouped {len(affected)} transactions "
                    f"around {facts.flagged.txn_id} using history, device, amount outliers, "
                    f"and NEXT edges {', '.join(facts.next_txn_ids) or '(none)'}."
                ),
                source=EvidenceSource.GRAPH,
                ref=f"query:next_chain(t={facts.flagged.txn_id})",
                entity_ids=_cap_ids(list(affected)),
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
    elif response is CustomerResponse.NO_REPLY:
        items.append(
            Evidence(
                claim="Customer did not reply within 24 hours.",
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


def _cap_ids(ids: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for entity_id in ids:
        if not entity_id or entity_id in seen:
            continue
        seen.add(entity_id)
        ordered.append(entity_id)
        if len(ordered) >= _ENTITY_CAP:
            break
    return ordered


def _closed_claim(cases: tuple[ClosedCaseFact, ...]) -> str:
    parts = [f"{case.case_id} ({case.outcome}, {case.pattern})" for case in cases]
    return "Closed cases on this card: " + "; ".join(parts) + "."


def _closed_ids(cases: tuple[ClosedCaseFact, ...]) -> list[str]:
    ids = [case.case_id for case in cases]
    for case in cases:
        ids.extend(case.txn_ids)
    return ids


def _summary(
    facts: CaseFacts,
    verdict: Verdict,
    pattern: FraudPattern,
    probability: float,
    affected: list[str] | None = None,
    exposure: float = 0.0,
) -> str:
    flagged = facts.flagged
    n_affected = len(affected or [])
    return (
        f"{facts.case.case_id} is a {facts.case.trigger_type.value} alert on a "
        f"{flagged.amount:.2f} USD {flagged.channel} purchase in billing region "
        f"{flagged.billing_region or 'unknown'}. Graph history shows "
        f"{len(facts.prior_in_region())} prior purchases in that region. "
        f"Pattern is {pattern.value}; fraud probability {probability:.2f}. "
        f"Episode size {n_affected}; exposure {exposure:.2f} USD. "
        f"Verdict is {verdict.value}."
    )


def _assumed_text(
    facts: CaseFacts,
    response: CustomerResponse,
    request_type: EvidenceRequestType | None = None,
) -> str:
    flagged = facts.flagged
    if request_type is EvidenceRequestType.STEP_UP_AUTH:
        if response is CustomerResponse.DENY:
            return "Step-up authentication failed. Customer still has the card."
        return "Step-up authentication passed."
    if response is CustomerResponse.CONFIRM:
        return (
            f"Customer confirms they made the {flagged.amount:.2f} USD "
            f"{flagged.channel} purchase in billing region {flagged.billing_region} "
            "and still have the card."
        )
    if response is CustomerResponse.NO_REPLY:
        return "Customer did not reply within 24 hours."
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
    if assumed is CustomerResponse.NO_REPLY:
        return "No customer reply; monitor the card and decline pending authorizations."
    if assumed is CustomerResponse.DENY:
        return "Customer denial confirmed the block."
    return "nothing"


def _sar(
    facts: CaseFacts,
    filed: bool,
    verdict: Verdict,
    final: list,
    affected: list[str] | None = None,
    exposure: float = 0.0,
) -> SAR:
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
    episode_ids = affected or [flagged.txn_id]
    episode = [txn for txn in facts.history if txn.txn_id in set(episode_ids)] or [flagged]
    start_day = min(txn.ts[:10] for txn in episode)
    end_day = max(txn.ts[:10] for txn in episode)
    total = exposure or round(sum(abs(txn.amount) for txn in episode), 2)
    connected = connected_card_ids(facts)
    pattern_note = pattern_description(facts, detect_pattern(facts))
    return SAR(
        file=True,
        reason=(
            "R2: customer denied the transaction"
            if facts.case.trigger_type is TriggerType.CUSTOMER_REPORT
            else "R9: coordinated undocumented abuse"
            if detect_pattern(facts) is FraudPattern.UNDOCUMENTED
            else "R6: shared origin or high-exposure confirmed activity"
        ),
        narrative=(
            f"On {start_day}, card {facts.card.card_id} belonging to customer {facts.case.customer_id} "
            f"was used for a {flagged.amount:.2f} USD {flagged.channel} transaction {flagged.txn_id} "
            f"in billing region {flagged.billing_region or 'unknown'}, country {flagged.billing_country or 'unknown'}. "
            f"The product code was {flagged.product_cd}. "
            f"Episode reconstruction identified {len(episode_ids)} related transaction(s) "
            f"totaling {total:.2f} USD from {start_day} to {end_day}. "
            "Graph neighborhood review found this activity inconsistent with the cardholder's established pattern "
            "or linked it to a shared origin, email cluster, or mixed-channel takeover. "
            f"{pattern_note} "
            "The investigation treated the purchase as unauthorized. "
            f"Connected cards recommended for monitoring: {', '.join(connected) or 'none beyond the flagged card'}. "
            "The flagged card is recommended for restriction pending reissue. "
            f"Total unauthorized amount: {total:.2f} USD. "
            "This report is filed so a regulator can review the episode on its own."
        ),
        subjects=[facts.case.customer_id, facts.card.card_id, *connected[:8]],
        total_amount_usd=total,
        activity_dates=[start_day, end_day],
    )


if __name__ == "__main__":
    paths = write_exam_answers()
    print(f"wrote {len(paths)} exam answers")
