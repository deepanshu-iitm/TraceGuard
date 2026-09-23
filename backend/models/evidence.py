"""Investigation evidence domain model."""

from enum import Enum

from pydantic import BaseModel


class EvidenceSource(str, Enum):
    """Sources from which investigation evidence can originate."""

    GRAPH = "graph"
    DOCUMENT = "document"
    CUSTOMER = "customer"
    EXTERNAL = "external"


class Evidence(BaseModel):
    """Represents a traceable piece of investigation evidence."""

    claim: str
    source: EvidenceSource
    ref: str
    entity_ids: list[str]