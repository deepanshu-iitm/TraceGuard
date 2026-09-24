from fastapi.testclient import TestClient

from backend.graph.export import PROCESSED_DIR
from backend.investigate.monitor import high_risk_alerts
from backend.main import app

client = TestClient(app)


def test_high_risk_alerts_are_outside_the_exam_pack() -> None:
    if not (PROCESSED_DIR / "vertices_transaction.csv").is_file():
        return
    from backend.data import load_case_pack

    flagged = {item.flagged_txn_id for item in load_case_pack()}
    alerts = high_risk_alerts()
    assert alerts
    assert all(case_id.startswith("MON-") for case_id, _txn in alerts)
    assert all(txn_id not in flagged for _case_id, txn_id in alerts)


def test_monitoring_list_is_empty_or_valid() -> None:
    response = client.get("/monitoring")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
