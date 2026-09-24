from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_graph_neighborhood_returns_hhg001_timeline() -> None:
    response = client.get("/graph/HHG-001")
    assert response.status_code == 200
    payload = response.json()
    assert payload["case_id"] == "HHG-001"
    assert payload["nodes"]
    assert payload["edges"]
    assert any(row["flagged"] for row in payload["timeline"])
    assert payload["policy"]["verdict"] == "legitimate"
