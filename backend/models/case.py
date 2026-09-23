"""Investigation case domain model."""

from pydantic import BaseModel

from backend.models.enums import CaseStatus


class InvestigationCase(BaseModel):
    """Represents a fraud investigation case."""

    case_id: str
    transaction_id: str
    customer_id: str
    status: CaseStatus