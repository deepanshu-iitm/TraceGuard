from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)
FRONTEND = Path(__file__).resolve().parents[1] / "frontend"


def test_api_root_points_to_next_ui() -> None:
    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "TraceGuard"
    assert payload["ui"] == "http://127.0.0.1:3000"


def test_exam_stats_counts_saved_answers() -> None:
    response = client.get("/stats")
    assert response.status_code == 200
    payload = response.json()
    assert payload["exam"] == 20
    assert payload["fraud"] + payload["legitimate"] + payload["uncertain"] == 20
    assert payload["sar"] >= 1


def test_analyst_console_is_nextjs() -> None:
    package = (FRONTEND / "package.json").read_text(encoding="utf-8")
    assert '"next"' in package
    source = "\n".join(path.read_text(encoding="utf-8") for path in (FRONTEND / "app").rglob("*.tsx"))
    assert "TraceGuard" in source
    assert "/investigate/" in source
    assert "Evidence requests" in source
    assert "Connected cards" in source
    assert "Graph write" in source
    assert "Neighborhood" in source
    assert "Timeline" in source
    assert "Approvals" in source
    assert "Policy trace" in source
    assert "Conflicts" in source
    assert "Approval queue" in source
    assert "/graph/" in source
    assert "/monitoring" in source
    assert 'id="mode"' in source or "id=\"mode\"" in source
    assert '"/health"' in source or "'/health'" in source


def test_cases_lists_twenty_exam_ids() -> None:
    response = client.get("/cases")
    assert response.status_code == 200
    payload = response.json()
    assert [item["case_id"] for item in payload] == [f"HHG-{index:03d}" for index in range(1, 21)]
    assert payload[0]["trigger_type"] == "risk_score"
    assert payload[0]["customer_id"] == "C12382"


def test_saved_answer_returns_hhg001() -> None:
    response = client.get("/cases/HHG-001")
    assert response.status_code == 200
    payload = response.json()
    assert payload["case_id"] == "HHG-001"
    assert payload["case"]["verdict"] == "legitimate"
    assert payload["sar"]["file"] is False


def test_saved_answer_unknown_case_returns_404() -> None:
    response = client.get("/cases/HHG-999")
    assert response.status_code == 404
    assert response.json()["detail"] == "unknown case_id: HHG-999"


def test_saved_fraud_answer_has_sar_fields_the_page_renders() -> None:
    response = client.get("/cases/HHG-014")
    assert response.status_code == 200
    payload = response.json()
    assert payload["case"]["verdict"] == "fraud"
    assert payload["sar"]["file"] is True
    assert payload["sar"]["narrative"]
    assert payload["case"]["written_to_graph"] is True
    assert payload["case"]["connected_device_profiles"]
