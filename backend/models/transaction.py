"""Transaction domain model."""

from pydantic import BaseModel


class Transaction(BaseModel):
    """Represents a transaction under investigation."""

    transaction_id: str
    customer_id: str
    card_id: str
    amount: float
    timestamp: str
    channel: str