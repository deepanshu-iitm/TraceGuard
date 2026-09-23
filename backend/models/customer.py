"""Customer domain model."""

from pydantic import BaseModel


class Customer(BaseModel):
    """Represents a customer associated with transactions."""

    customer_id: str