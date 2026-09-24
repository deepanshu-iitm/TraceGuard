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


def test_graph_neighborhood_returns_monitoring_case() -> None:
    import pytest

    from backend.graph.export import PROCESSED_DIR
    from backend.investigate.monitor import MONITOR_DIR

    if not (MONITOR_DIR / "MON-001.json").is_file():
        pytest.skip("monitoring answers not written")
    if not (PROCESSED_DIR / "vertices_transaction.csv").is_file():
        pytest.skip("processed transaction export missing")
    response = client.get("/graph/MON-001")
    assert response.status_code == 200
    payload = response.json()
    assert payload["case_id"] == "MON-001"
    assert payload["nodes"]
    assert payload["edges"]
    assert any(row["flagged"] for row in payload["timeline"])
    assert payload["policy"]["verdict"] in {"fraud", "legitimate", "uncertain"}


def test_unknown_graph_case_returns_404() -> None:
    response = client.get("/graph/MON-999")
    assert response.status_code == 404
