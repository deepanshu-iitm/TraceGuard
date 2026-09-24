"""Policy and pattern documents used for GraphRAG retrieval."""

from __future__ import annotations

from dataclasses import dataclass

from backend.models.enums import FraudPattern


@dataclass(frozen=True)
class CorpusDoc:
    """One retrievable text chunk."""

    doc_id: str
    title: str
    text: str
    pattern: str = ""
    entity_ids: tuple[str, ...] = ()


POLICY_DOCS: tuple[CorpusDoc, ...] = (
    CorpusDoc(
        "policy:R1",
        "R1 Verify before blocking on a weak signal",
        "If the case rests on a single signal, including a risk score alone, and fraud "
        "probability is below 0.70, recommend VERIFY_WITH_CUSTOMER or STEP_UP_AUTH before any block.",
    ),
    CorpusDoc(
        "policy:R2",
        "R2 Customer denies",
        "When the customer denies the transaction, recommend BLOCK_CARD and CREATE_CASE. "
        "Add FILE_REPORT when exposure exceeds 1000 USD, a shared device is present, or another card's fraud is connected.",
    ),
    CorpusDoc(
        "policy:R3",
        "R3 Customer confirms",
        "When the customer confirms the transaction, recommend CLOSE_NO_FRAUD and record the confirmation.",
    ),
    CorpusDoc(
        "policy:R5",
        "R5 Card testing",
        "Three or more small online authorizations within one hour followed by a larger purchase: "
        "DECLINE_TRANSACTION and STEP_UP_AUTH. If a purchase over 100 USD already cleared, BLOCK_CARD.",
        pattern=FraudPattern.CARD_TESTING.value,
    ),
    CorpusDoc(
        "policy:R6",
        "R6 Shared origin",
        "Several cards with fraud associated with the same device profile, billing region, or recipient "
        "email: CREATE_CASE, FILE_REPORT, and MONITOR_CONNECTED_CARDS for every affected card.",
    ),
    CorpusDoc(
        "policy:R7",
        "R7 Disputed but legitimate recurring pattern",
        "If a disputed charge matches the customer's normal recurring pattern: CREATE_CASE, "
        "VERIFY_WITH_CUSTOMER, WARN_CUSTOMER. Do not block.",
    ),
    CorpusDoc(
        "policy:R8",
        "R8 Uncertain and exposed",
        "If the case is uncertain with exposure above 500 USD, or evidence conflicts, ESCALATE_TO_ANALYST.",
    ),
    CorpusDoc(
        "policy:R10",
        "R10 BLOCK_ALL_CARDS",
        "Only recommend BLOCK_ALL_CARDS if at least two of the customer's cards show confirmed fraud "
        "or credentials are confirmed compromised.",
    ),
)

PATTERN_DOCS: tuple[CorpusDoc, ...] = (
    CorpusDoc(
        "pattern:card_testing",
        "Card testing",
        "Three or more small online authorizations, often under 5 USD, within about one hour, "
        "followed by a larger purchase.",
        pattern=FraudPattern.CARD_TESTING.value,
    ),
    CorpusDoc(
        "pattern:card_not_present_fraud",
        "Card-not-present fraud",
        "Online activity inconsistent with the cardholder's normal merchants, amounts, or product codes. "
        "A burst of a few transactions within 48 hours is common.",
        pattern=FraudPattern.CARD_NOT_PRESENT_FRAUD.value,
    ),
    CorpusDoc(
        "pattern:card_not_present_new_device",
        "Card-not-present new device",
        "Same as card-not-present fraud, but the identity record shows a device not previously seen "
        "on this account. Stronger evidence, not proof: legitimate customers also use new devices.",
        pattern=FraudPattern.CARD_NOT_PRESENT_NEW_DEVICE.value,
    ),
    CorpusDoc(
        "pattern:out_of_region_use",
        "Out-of-region use",
        "Card-present activity in a billing region with no prior history, while normal home activity "
        "may continue. One new region is not automatically fraud; travel can look the same.",
        pattern=FraudPattern.OUT_OF_REGION_USE.value,
    ),
    CorpusDoc(
        "pattern:account_takeover",
        "Account takeover",
        "Mixed-channel behavior inconsistent with the cardholder, often with device and match-flag "
        "anomalies. Stolen credentials, not only a stolen card number.",
        pattern=FraudPattern.ACCOUNT_TAKEOVER.value,
    ),
)
