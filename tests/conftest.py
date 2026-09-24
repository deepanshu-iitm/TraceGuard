import pytest

from backend.config import settings


@pytest.fixture(autouse=True)
def disable_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openai_api_key", "")
