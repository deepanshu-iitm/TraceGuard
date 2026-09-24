import pytest

from backend.graph.export import PROCESSED_DIR
from backend.graph.parse import vertices
from backend.graph.tools import get_graph_tools
from backend.investigate.local_queries import LocalGraphTools


pytestmark = pytest.mark.skipif(
    not (PROCESSED_DIR / "edges.csv").is_file(),
    reason="export graph CSVs into data/processed first",
)


def test_get_case_facts_returns_hhg001_neighborhood() -> None:
    payload = LocalGraphTools().run_installed_query("get_case_facts", {"t": "3514030"})
    flagged = vertices(payload, "t")[0]
    cards = vertices(payload, "cards")
    closed = vertices(payload, "closed")
    assert flagged["v_id"] == "3514030"
    assert flagged["attributes"]["amount"] == 77.07
    assert cards[0]["v_id"] == "C12382-K1"
    assert {item["v_id"] for item in closed} == {"CC-1066", "CC-1673", "CC-2964", "CC-3587"}


def test_graph_tools_default_to_local_without_host() -> None:
    tools = get_graph_tools()
    payload = tools.run_installed_query("investigate_txn", {"t": "3514030"})
    assert payload[-1]["@@n_history"] >= 10


def test_unknown_query_is_rejected() -> None:
    with pytest.raises(KeyError, match="unknown installed query"):
        LocalGraphTools().run_installed_query("not_a_query", {})
