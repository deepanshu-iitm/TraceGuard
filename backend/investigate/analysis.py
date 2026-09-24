"""Deterministic graph pattern, episode, and probability analysis."""

from __future__ import annotations

from datetime import datetime, timedelta
from math import exp

from backend.investigate.facts import CaseFacts, TxnFact
from backend.models.enums import FraudPattern, TriggerType


def parse_ts(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")


def card_testing(facts: CaseFacts) -> tuple[bool, bool]:
    flagged = facts.flagged
    start = parse_ts(flagged.ts) - timedelta(hours=1)
    small = [
        txn
        for txn in facts.prior()
        if txn.channel == "online" and txn.amount < 5 and parse_ts(txn.ts) >= start
    ]
    if len(small) >= 3 and flagged.channel == "online" and flagged.amount >= 5:
        return True, flagged.amount > 100
    return False, False


def specific_device(profile: str) -> bool:
    info = profile.split("|", 1)[0].strip() if profile else ""
    if info in {"", "Windows", "iOS Device", "MacOS", "Linux", "Trident/7.0"}:
        return False
    return any(char.isdigit() for char in info)


def new_device(facts: CaseFacts) -> bool:
    profile = facts.flagged.device_profile_id
    if not profile:
        return False
    prior = facts.prior()
    seen = {txn.device_profile_id for txn in prior if txn.device_profile_id}
    if seen:
        return profile not in seen
    return not prior


def known_spend(facts: CaseFacts) -> bool:
    prior = facts.prior()
    if not prior:
        return False
    same_channel = [txn for txn in prior if txn.channel == facts.flagged.channel]
    if len(same_channel) < 3 or len(same_channel) < 0.1 * len(prior):
        return False
    peers = facts.prior_in_region() if facts.flagged.billing_region else tuple(same_channel)
    return amount_matches(facts, peers)


def amount_matches(facts: CaseFacts, prior: tuple[TxnFact, ...] | None = None) -> bool:
    pool = facts.prior_in_region() if prior is None else prior
    if not pool:
        return False
    amount = facts.flagged.amount
    tolerance = max(20.0, 0.25 * amount)
    return any(abs(txn.amount - amount) <= tolerance for txn in pool)


def shared_origin(facts: CaseFacts) -> bool:
    if facts.case.trigger_type is TriggerType.ANALYST_REQUEST and facts.device_profile_id:
        return True
    if specific_device(facts.device_profile_id):
        if any(card_id != facts.card.card_id for card_id in facts.device_card_ids):
            return True
    return bool(rare_email_cards(facts))


def rare_email_cards(facts: CaseFacts) -> tuple[str, ...]:
    """Gmail-scale domains are not a shared origin. A tight cluster is."""
    others = tuple(
        card_id for card_id in facts.email_card_ids if card_id != facts.card.card_id
    )
    if 1 <= len(others) <= 6:
        return others
    return ()


def connected_card_ids(facts: CaseFacts) -> list[str]:
    cards = {
        card_id for card_id in facts.device_card_ids if card_id != facts.card.card_id
    }
    cards.update(rare_email_cards(facts))
    return sorted(cards)


def account_takeover(facts: CaseFacts) -> bool:
    if facts.flagged.channel != "online" or not new_device(facts):
        return False
    flagged_at = parse_ts(facts.flagged.ts)
    recent_present = [
        txn
        for txn in facts.prior()
        if txn.channel == "in_person" and flagged_at - parse_ts(txn.ts) <= timedelta(days=14)
    ]
    return bool(recent_present)


def undocumented_coordinated(facts: CaseFacts) -> bool:
    if card_testing(facts)[0] or account_takeover(facts) or new_device(facts):
        return False
    if facts.flagged.channel == "in_person" and not facts.prior_in_region():
        return False
    return bool(rare_email_cards(facts)) and not known_spend(facts)


def detect_pattern(facts: CaseFacts) -> FraudPattern:
    testing, _cleared = card_testing(facts)
    if testing:
        return FraudPattern.CARD_TESTING
    if account_takeover(facts):
        return FraudPattern.ACCOUNT_TAKEOVER
    if shared_origin(facts) and facts.flagged.channel == "online":
        if new_device(facts):
            return FraudPattern.CARD_NOT_PRESENT_NEW_DEVICE
        return FraudPattern.CARD_NOT_PRESENT_FRAUD
    if known_spend(facts):
        return FraudPattern.NONE
    if undocumented_coordinated(facts):
        return FraudPattern.UNDOCUMENTED
    if facts.flagged.channel == "online" and new_device(facts):
        return FraudPattern.CARD_NOT_PRESENT_NEW_DEVICE
    if facts.flagged.channel == "in_person" and not facts.prior_in_region():
        return FraudPattern.OUT_OF_REGION_USE
    if facts.flagged.channel == "online":
        return FraudPattern.CARD_NOT_PRESENT_FRAUD
    return FraudPattern.NONE


def calibrated_probability(facts: CaseFacts, pattern: FraudPattern) -> float:
    score = max(0.0, min(1.0, facts.flagged.risk_score))
    z = -1.35 + 1.15 * score
    if shared_origin(facts):
        z += 1.45
    if pattern is FraudPattern.CARD_TESTING:
        z += 1.55
    elif pattern is FraudPattern.ACCOUNT_TAKEOVER:
        z += 1.35
    elif pattern is FraudPattern.CARD_NOT_PRESENT_NEW_DEVICE:
        z += 1.05
    elif pattern is FraudPattern.OUT_OF_REGION_USE:
        z += 0.65
    elif pattern is FraudPattern.UNDOCUMENTED:
        z += 1.1
    elif pattern is FraudPattern.CARD_NOT_PRESENT_FRAUD:
        z += 0.55
    if known_spend(facts) and pattern is FraudPattern.NONE:
        z -= 2.15
    if facts.case.trigger_type is TriggerType.CUSTOMER_REPORT:
        z += 0.35
    closed_fraud = sum(1 for case in facts.closed_cases if case.outcome == "confirmed_fraud")
    z += min(0.4, 0.04 * closed_fraud)
    probability = 1.0 / (1.0 + exp(-z))
    return round(min(0.97, max(0.04, probability)), 2)


def episode_txns(facts: CaseFacts, pattern: FraudPattern) -> list[TxnFact]:
    if pattern is FraudPattern.NONE:
        return []
    flagged = facts.flagged
    flagged_at = parse_ts(flagged.ts)
    chosen = {flagged.txn_id: flagged}
    if pattern is FraudPattern.CARD_TESTING:
        start = flagged_at - timedelta(hours=1)
        for txn in facts.prior():
            if txn.channel == "online" and txn.amount < 5 and parse_ts(txn.ts) >= start:
                chosen[txn.txn_id] = txn
    elif pattern is FraudPattern.OUT_OF_REGION_USE:
        for txn in facts.history:
            if txn.billing_region != flagged.billing_region or txn.channel != "in_person":
                continue
            if abs(parse_ts(txn.ts) - flagged_at) <= timedelta(days=2):
                chosen[txn.txn_id] = txn
    else:
        window = timedelta(hours=48)
        median = _median([abs(txn.amount) for txn in facts.prior()] or [flagged.amount])
        for txn in facts.history:
            if abs(parse_ts(txn.ts) - flagged_at) > window:
                continue
            if txn.txn_id == flagged.txn_id:
                continue
            same_device = bool(
                flagged.device_profile_id
                and txn.device_profile_id == flagged.device_profile_id
            )
            outlier = abs(txn.amount) >= max(2 * median, flagged.amount * 0.75)
            if txn.channel == "online" and (same_device or outlier):
                chosen[txn.txn_id] = txn
    for txn in facts.history:
        if txn.txn_id in facts.next_txn_ids:
            chosen[txn.txn_id] = txn
    return sorted(chosen.values(), key=lambda txn: (txn.ts, txn.txn_id))


def episode_exposure(txns: list[TxnFact]) -> float:
    return round(sum(abs(txn.amount) for txn in txns), 2)


def pattern_description(facts: CaseFacts, pattern: FraudPattern) -> str:
    if pattern is FraudPattern.UNDOCUMENTED:
        others = rare_email_cards(facts)
        email = facts.flagged.recipient_email or facts.flagged.purchaser_email
        return (
            f"Coordinated activity on email domain {email or 'unknown'} linking card "
            f"{facts.card.card_id} to {', '.join(others) or 'another card'}. "
            "The episode does not match card testing, new-device CNP, out-of-region use, or account takeover. "
            "It was discovered by expanding PURCHASER_EMAIL/RECIPIENT_EMAIL neighbors on FraudGraph."
        )
    if pattern is FraudPattern.ACCOUNT_TAKEOVER:
        return (
            f"Online purchase {facts.flagged.txn_id} used a device not seen on this card, "
            "shortly after in-person activity. That mixed-channel shift is treated as stolen "
            "credentials rather than a stolen card number alone."
        )
    return ""


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2
