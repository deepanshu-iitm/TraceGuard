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


def test_card_testing_detector_matches_the_one_hour_signature() -> None:
    from datetime import datetime

    from backend.investigate.analysis import card_testing
    from backend.investigate.facts import CardFact, CaseFacts, TxnFact
    from backend.models.case_pack import CasePackItem
    from backend.models.enums import TriggerType

    def txn(txn_id: str, ts: str, amount: float) -> TxnFact:
        return TxnFact(
            txn_id=txn_id,
            ts=ts,
            amount=amount,
            product_cd="H",
            channel="online",
            risk_score=0.4,
            billing_region="1.0",
            billing_country="87.0",
        )

    flagged = txn("5", "2016-12-04 01:00:00", 120.0)
    history = (
        txn("1", "2016-12-04 00:10:00", 1.1),
        txn("2", "2016-12-04 00:20:00", 1.2),
        txn("3", "2016-12-04 00:30:00", 1.3),
        flagged,
    )
    facts = CaseFacts(
        case=CasePackItem(
            case_id="HHG-099",
            opened_at=datetime(2016, 12, 4),
            trigger_type=TriggerType.RISK_SCORE,
            trigger_text="score",
            flagged_txn_id="5",
            card_id="C1",
            customer_id="U1",
        ),
        flagged=flagged,
        card=CardFact(card_id="C1", card1="", network="visa", card_type="debit"),
        customer_card_ids=("C1",),
        history=history,
        closed_cases=(),
        device_profile_id="",
        device_card_ids=("C1",),
    )
    testing, cleared = card_testing(facts)
    assert testing is True
    assert cleared is True


def test_similar_prior_cases_mix_card_memory_and_notes() -> None:
    from backend.investigate import compose_answer, load_case_facts

    answer = compose_answer(load_case_facts("HHG-001"))
    assert 1 <= len(answer.case.similar_prior_cases) <= 8
    assert all(item.startswith("CC-") for item in answer.case.similar_prior_cases)


def test_region_and_next_queries_are_installed_locally() -> None:
    tools = LocalGraphTools()
    region = tools.run_installed_query("region_fanout", {"r": "444.0"})
    assert region[0]["r"][0]["v_id"] == "444.0"
    nxt = tools.run_installed_query("next_chain", {"t": "3514030"})
    assert nxt[0]["t"][0]["v_id"] == "3514030"
    component = tools.run_installed_query("card_component", {"c": "C12382-K1"})
    assert component[0]["c"][0]["v_id"] == "C12382-K1"
