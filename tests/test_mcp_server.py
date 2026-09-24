import pytest

from backend.mcp.server import get_investigation_case, investigate_case, upsert_investigation_case
from backend.models.answer import Answer
from tests.test_answer import EXAMPLE


def test_mcp_upsert_writes_saved_hhg001(monkeypatch) -> None:
    captured: dict = {}

    def fake_write(answer: Answer, out_dir=None) -> Answer:
        captured["case_id"] = answer.case_id
        captured["verdict"] = answer.case.verdict.value
        return answer

    monkeypatch.setattr(
        "backend.investigate.persist.write_investigation_case", fake_write
    )
    result = upsert_investigation_case("HHG-001")
    assert captured["case_id"] == "HHG-001"
    assert captured["verdict"] == "legitimate"
    assert result["written_to_graph"] is True
    assert result["graph_case_id"] == "HHG-001"


def test_mcp_get_investigation_case_uses_installed_query(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.mcp.server.get_graph_tools",
        lambda: type(
            "Tools",
            (),
            {
                "run_installed_query": staticmethod(
                    lambda name, params: [
                        {
                            "c": [
                                {
                                    "v_id": params["c"],
                                    "attributes": {"verdict": "legitimate"},
                                }
                            ]
                        }
                    ]
                )
            },
        )(),
    )
    payload = get_investigation_case("HHG-001")
    assert payload[0]["c"][0]["v_id"] == "HHG-001"


def test_mcp_investigate_case_runs_the_agent(monkeypatch) -> None:
    answer = Answer.model_validate(EXAMPLE)
    monkeypatch.setattr(
        "backend.investigate.investigate", lambda case_id: answer
    )
    payload = investigate_case("HHG-001")
    assert payload["case_id"] == "HHG-017"
    assert payload["case"]["verdict"] == "fraud"


def test_mcp_investigate_case_rejects_unknown_ids() -> None:
    with pytest.raises(ValueError, match="unknown case_id"):
        investigate_case("HHG-999")
