"""Investigation evidence domain model."""

from enum import StrEnum

from pydantic import BaseModel


class EvidenceSource(StrEnum):
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