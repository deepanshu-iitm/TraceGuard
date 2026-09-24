import pytest

from backend.graph.export import PROCESSED_DIR
from backend.investigate import load_case_facts
from backend.investigate.facts import merge_shared_cards


pytestmark = pytest.mark.skipif(
    not (PROCESSED_DIR / "edges.csv").is_file(),
    reason="export graph CSVs into data/processed first",
)


def test_hhg001_flagged_txn_card_and_closed_cases() -> None:
    facts = load_case_facts("HHG-001")

    assert facts.flagged.txn_id == "3514030"
    assert facts.flagged.amount == 77.07
    assert facts.flagged.channel == "in_person"
    assert facts.flagged.billing_region == "444.0"
    assert facts.card.card_id == "C12382-K1"
    assert facts.card.network == "visa"
    assert facts.customer_card_ids == ("C12382-K1",)
    assert facts.device_profile_id == ""
    assert [case.case_id for case in facts.closed_cases] == [
        "CC-1066",
        "CC-1673",
        "CC-2964",
        "CC-3587",
    ]
    assert [txn.txn_id for txn in facts.prior_in_region()] == [
        "3264155",
        "3275900",
        "3276102",
        "3320680",
        "3356278",
        "3376974",
        "3400970",
        "3441958",
        "3471020",
        "3490282",
    ]


def test_unknown_case_is_rejected() -> None:
    with pytest.raises(KeyError, match="HHG-999"):
        load_case_facts("HHG-999")


def test_merge_shared_cards_unions_cards_from_the_query() -> None:
    facts = load_case_facts("HHG-014")
    merged = merge_shared_cards(
        facts, [{"cards": [{"v_id": "SHARED-CARD", "v_type": "PaymentCard", "attributes": {}}]}]
    )
    assert "SHARED-CARD" in merged.device_card_ids
    assert facts.card.card_id in merged.device_card_ids
