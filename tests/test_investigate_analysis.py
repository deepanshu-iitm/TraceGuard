import pytest

from backend.graph.export import PROCESSED_DIR
from backend.investigate.analysis import calibrated_probability, detect_pattern
from backend.investigate.facts import load_case_facts
from backend.investigate.local_queries import LocalGraphTools
from backend.models.enums import FraudPattern


pytestmark = pytest.mark.skipif(
    not (PROCESSED_DIR / "edges.csv").is_file(),
    reason="export graph CSVs into data/processed first",
)


def test_hhg001_stays_none_with_calibrated_probability() -> None:
    facts = load_case_facts("HHG-001")
    pattern = detect_pattern(facts)
    assert pattern is FraudPattern.NONE
    assert calibrated_probability(facts, pattern) < 0.20


def test_email_fanout_returns_cards_for_a_known_domain() -> None:
    facts = load_case_facts("HHG-001")
    domain = facts.flagged.recipient_email or facts.flagged.purchaser_email
    if not domain:
        pytest.skip("HHG-001 has no email domain on the flagged transaction")
    payload = LocalGraphTools().run_installed_query("email_fanout", {"e": domain})
    assert payload[0]["e"][0]["v_id"] == domain
    assert "cards" in payload[2]


def test_region_and_next_queries_are_installed_locally() -> None:
    tools = LocalGraphTools()
    region = tools.run_installed_query("region_fanout", {"r": "444.0"})
    assert region[0]["r"][0]["v_id"] == "444.0"
    nxt = tools.run_installed_query("next_chain", {"t": "3514030"})
    assert nxt[0]["t"][0]["v_id"] == "3514030"
    component = tools.run_installed_query("card_component", {"c": "C12382-K1"})
    assert component[0]["c"][0]["v_id"] == "C12382-K1"
