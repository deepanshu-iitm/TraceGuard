"""Investigation verdict domain model."""

from enum import StrEnum

from pydantic import BaseModel


class Verdict(StrEnum):
    """Possible investigation outcomes."""

    FRAUD = "fraud"
    NOT_FRAUD = "not_fraud"
    UNCERTAIN = "uncertain"


class InvestigationVerdict(BaseModel):
    """Represents the analytical conclusion of an investigation."""

    verdict: Verdict
    fraud_probability: float
    pattern: str
    pattern_description: str