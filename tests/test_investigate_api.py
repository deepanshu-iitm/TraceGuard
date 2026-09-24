import pytest
from fastapi.testclient import TestClient

from backend.graph.export import PROCESSED_DIR
from backend.main import app
from backend.models.enums import CaseStatus
from backend.models.verdict import Verdict


client = TestClient(app)


@pytest.mark.skipif(
    not (PROCESSED_DIR / "edges.csv").is_file(),
    reason="export graph CSVs into data/processed first",
)
def test_investigate_hhg001_returns_answer_json() -> None:
    response = client.post("/investigate/HHG-001")
    assert response.status_code == 200
    payload = response.json()
    assert payload["case_id"] == "HHG-001"
    assert payload["case"]["status"] == CaseStatus.CLOSED_LEGITIMATE.value
    assert payload["case"]["verdict"] == Verdict.LEGITIMATE.value
    assert payload["sar"]["file"] is False


def test_investigate_unknown_case_returns_404() -> None:
    response = client.post("/investigate/HHG-999")
    assert response.status_code == 404
    assert response.json()["detail"] == "unknown case_id: HHG-999"
