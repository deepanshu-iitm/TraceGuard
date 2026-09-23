"""Investigation request domain model."""

from pydantic import BaseModel


class InvestigationRequest(BaseModel):
    """Represents a request to investigate a transaction."""

    case_id: str
    transaction_id: str