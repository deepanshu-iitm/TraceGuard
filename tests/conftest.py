from pathlib import Path

import pytest

from backend.config import settings


@pytest.fixture(autouse=True)
def disable_remote_services(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "tg_host", "")
    dest = tmp_path / "investigation_export"
    dest.mkdir()
    monkeypatch.setattr("backend.investigate.persist.PROCESSED_DIR", dest)
