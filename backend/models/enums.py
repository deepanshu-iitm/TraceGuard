"""TraceGuard domain enumerations."""

from enum import StrEnum


class CaseStatus(StrEnum):
    """Investigation case lifecycle states."""

    OPEN = "open"
    CLOSED = "closed"
    