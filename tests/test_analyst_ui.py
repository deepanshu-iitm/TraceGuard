from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_analyst_page_is_served() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "TraceGuard" in response.text
    assert "/investigate/" in response.text


def test_cases_lists_twenty_exam_ids() -> None:
    response = client.get("/cases")
    assert response.status_code == 200
    payload = response.json()
    assert [item["case_id"] for item in payload] == [f"HHG-{index:03d}" for index in range(1, 21)]
    assert payload[0]["trigger_type"] == "risk_score"
    assert payload[0]["customer_id"] == "C12382"
