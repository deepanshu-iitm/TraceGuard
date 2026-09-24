from backend.investigate.facts import CaseFacts, load_case_facts

__all__ = [
    "CaseFacts",
    "compose_answer",
    "investigate",
    "load_case_facts",
    "persist_investigation_cases",
    "write_investigation_case",
    "write_answer",
]


def __getattr__(name: str):
    if name == "investigate":
        from backend.investigate.agent import investigate as fn

        return fn
    if name in {"compose_answer", "write_answer"}:
        from backend.investigate import compose

        return getattr(compose, name)
    if name in {"persist_investigation_cases", "write_investigation_case"}:
        from backend.investigate import persist

        return getattr(persist, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
