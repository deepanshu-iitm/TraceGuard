"""Card domain model."""

from pydantic import BaseModel


class Card(BaseModel):
    """Represents a payment card associated with a customer."""

    card_id: str
    customer_id: str