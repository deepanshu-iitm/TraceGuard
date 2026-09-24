from backend.config import settings
from backend.graph.tools import TigerGraphTools


def test_tigergraph_tools_call_official_mcp(monkeypatch) -> None:
    monkeypatch.setattr(settings, "tg_host", "https://example.invalid")
    monkeypatch.setattr(
        "backend.mcp.client.run_installed_query",
        lambda name, params: [{"query": name, **params}],
    )
    payload = TigerGraphTools().run_installed_query("investigate_txn", {"t": "3514030"})
    assert payload == [{"query": "investigate_txn", "t": "3514030"}]
