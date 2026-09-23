"""Investigation verdict domain model."""

from enum import StrEnum

from pydantic import BaseModel

from backend.models.enums import FraudPattern


class Verdict(StrEnum):
    """Possible investigation outcomes."""

    FRAUD = "fraud"
    LEGITIMATE = "legitimate"
    UNCERTAIN = "uncertain"


class InvestigationVerdict(BaseModel):
    """Represents the analytical conclusion of an investigation."""

    verdict: Verdict
    fraud_probability: float
    pattern: FraudPattern
    pattern_description: str