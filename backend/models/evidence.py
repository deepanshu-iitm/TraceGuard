"""Investigation evidence domain model."""

from enum import Enum

from pydantic import BaseModel, ConfigDict


class EvidenceSource(str, Enum):
    """Sources from which investigation evidence can originate."""

    GRAPH = "graph"
    DOCUMENT = "document"
    CUSTOMER = "customer"
    EXTERNAL = "external"


class Evidence(BaseModel):
    """Represents a traceable piece of investigation evidence."""

    model_config = ConfigDict(extra="forbid")

    claim: str
    source: EvidenceSource
    ref: str
    entity_ids: list[str]
