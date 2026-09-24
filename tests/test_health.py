from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app


client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "graph": "local", "llm": "off"}


def test_health_reports_configured_backends(monkeypatch) -> None:
    monkeypatch.setattr(settings, "tg_host", "https://example.i.tgcloud.io")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    assert client.get("/health").json() == {
        "status": "ok",
        "graph": "tigergraph",
        "llm": "on",
    }