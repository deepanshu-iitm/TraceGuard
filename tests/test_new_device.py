from datetime import datetime

from backend.investigate.compose import _new_device
from backend.investigate.facts import CardFact, CaseFacts, TxnFact
from backend.models.case_pack import CasePackItem
from backend.models.enums import TriggerType


def _item() -> CasePackItem:
    return CasePackItem(
        case_id="HHG-099",
        opened_at=datetime(2016, 12, 4),
        trigger_type=TriggerType.RISK_SCORE,
        trigger_text="score",
        flagged_txn_id="2",
        card_id="C1",
        customer_id="U1",
    )


def _txn(txn_id: str, ts: str, device: str = "") -> TxnFact:
    return TxnFact(
        txn_id=txn_id,
        ts=ts,
        amount=10.0,
        product_cd="W",
        channel="online",
        risk_score=0.5,
        billing_region="1.0",
        billing_country="87.0",
        device_profile_id=device,
    )


def _facts(flagged: TxnFact, history: tuple[TxnFact, ...]) -> CaseFacts:
    return CaseFacts(
        case=_item(),
        flagged=flagged,
        card=CardFact(card_id="C1", card1="", network="visa", card_type="debit"),
        customer_card_ids=("C1",),
        history=history,
        closed_cases=(),
        device_profile_id=flagged.device_profile_id,
        device_card_ids=("C1",),
    )


def test_new_device_is_false_when_history_omits_device_ids() -> None:
    flagged = _txn("2", "2016-12-04 00:00:00", "SM-G935F | Android")
    prior = _txn("1", "2016-11-01 00:00:00")
    assert _new_device(_facts(flagged, (prior, flagged))) is False


def test_new_device_is_true_when_prior_used_a_different_device() -> None:
    flagged = _txn("2", "2016-12-04 00:00:00", "SM-G935F | Android")
    prior = _txn("1", "2016-11-01 00:00:00", "iPhone | iOS")
    assert _new_device(_facts(flagged, (prior, flagged))) is True


def test_new_device_is_true_when_there_is_no_prior_history() -> None:
    flagged = _txn("2", "2016-12-04 00:00:00", "SM-G935F | Android")
    assert _new_device(_facts(flagged, (flagged,))) is True
