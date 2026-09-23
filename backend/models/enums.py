"""TraceGuard domain enumerations."""

from enum import Enum


class CaseStatus(str, Enum):
    """Investigation case lifecycle states."""

    OPEN = "open"
    CLOSED_FRAUD = "closed_fraud"
    CLOSED_LEGITIMATE = "closed_legitimate"
    ESCALATED = "escalated"


class TriggerType(str, Enum):
    """Reasons an investigation case is opened."""

    RISK_SCORE = "risk_score"
    CUSTOMER_REPORT = "customer_report"
    ANALYST_REQUEST = "analyst_request"


class FraudPattern(str, Enum):
    """Fraud patterns recognized in the answer format."""

    CARD_TESTING = "card_testing"
    CARD_NOT_PRESENT_FRAUD = "card_not_present_fraud"
    CARD_NOT_PRESENT_NEW_DEVICE = "card_not_present_new_device"
    OUT_OF_REGION_USE = "out_of_region_use"
    ACCOUNT_TAKEOVER = "account_takeover"
    UNDOCUMENTED = "undocumented"
    NONE = "none"
