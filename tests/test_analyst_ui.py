from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_analyst_page_is_served() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html = response.text
    assert "TraceGuard" in html
    assert "/investigate/" in html
    assert "Evidence requests" in html
    assert "Connected cards" in html
    assert "Graph write" in html
    assert "Neighborhood" in html
    assert "Timeline" in html
    assert "Approvals" in html
    assert "/graph/" in html
    assert "function escapeHtml" in html
    assert "sarBlock" in html
    assert "id=\"mode\"" in html
    assert 'fetch("/health")' in html


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
