"""Benchmark case pack domain model."""

from datetime import datetime

from pydantic import BaseModel

from backend.models.enums import TriggerType


class CasePackItem(BaseModel):
    """Represents one exam case from the benchmark case pack."""

    case_id: str
    opened_at: datetime
    trigger_type: TriggerType
    trigger_text: str
    flagged_txn_id: str
    card_id: str
    customer_id: str
    risk_score: float | None = None
