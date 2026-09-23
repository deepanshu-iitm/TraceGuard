import pytest
from pydantic import ValidationError

from backend.models.answer import Answer
from backend.models.enums import FraudPattern
from backend.models.verdict import Verdict


EXAMPLE = {
    "case_id": "HHG-017",
    "case": {
        "status": "closed_fraud",
        "verdict": "fraud",
        "fraud_probability": 0.86,
        "pattern": "card_testing",
        "pattern_description": "",
        "affected_txn_ids": ["T0412877", "T0412878", "T0412879", "T0412883"],
        "first_suspicious_txn_id": "T0412877",
        "connected_card_ids": ["C00877-K1"],
        "connected_device_profiles": [
            "SAMSUNG SM-G892A Build/NRD90M | Android 7.0 | samsung browser 6.2 | 2220x1080"
        ],
        "exposure_usd": 268.43,
        "evidence": [
            {
                "claim": "Three online authorizations under $3 within 40 minutes, then a $259 purchase",
                "source": "graph",
                "ref": "query:card_window(card_id=C00377-K1, hours=2)",
                "entity_ids": ["T0412877", "T0412878", "T0412879", "T0412883"],
            }
        ],
        "similar_prior_cases": ["CC-0141"],
        "summary": "Textbook card testing on a new device, denied by the customer.",
        "written_to_graph": True,
        "graph_case_id": "CASE-2016-1187",
    },
    "evidence_requests": [
        {
            "type": "customer_validation",
            "asked_after_step": 4,
            "assumed_response": "Customer states they did not make these purchases and still has the card",
        }
    ],
    "next_best_actions": {
        "initial": [
            {
                "action": "DECLINE_TRANSACTION",
                "route": "L1",
                "reason": "R5: testing sequence observed, purchase already cleared",
            }
        ],
        "final": [
            {
                "action": "BLOCK_CARD",
                "route": "L1",
                "reason": "R2 and R5: customer denied; exposure $268 is under $2,500",
            },
            {"action": "CREATE_CASE", "route": "auto", "reason": "R2"},
            {
                "action": "FILE_REPORT",
                "route": "L2",
                "reason": "R2: shared device links this to another compromised card",
            },
        ],
        "what_changed": "Customer denial confirmed the block and the shared device triggered a report.",
    },
    "sar": {
        "file": True,
        "reason": "R2: confirmed unauthorized use linked by a shared device to a second compromised card",
        "narrative": "Card C00377-K1 was tested with three small online authorizations then a larger purchase.",
        "subjects": ["C00377", "C00377-K1", "C00877-K1"],
        "total_amount_usd": 268.43,
        "activity_dates": ["2016-11-14", "2016-11-14"],
    },
    "stop_reason": "Customer denial settled the verdict; connected card identified.",
    "tool_calls": 9,
    "tokens": 12480,
    "latency_s": 18.7,
}


def test_readme_example_matches_the_answer_schema() -> None:
    answer = Answer.model_validate(EXAMPLE)
    assert answer.case_id == "HHG-017"
    assert answer.case.verdict is Verdict.FRAUD
    assert answer.case.pattern is FraudPattern.CARD_TESTING
    assert answer.sar.file is True


def test_extra_fields_are_rejected() -> None:
    payload = {**EXAMPLE, "notes": "not in the schema"}
    with pytest.raises(ValidationError):
        Answer.model_validate(payload)


def test_legitimate_case_cannot_claim_exposure() -> None:
    payload = {
        **EXAMPLE,
        "case": {
            **EXAMPLE["case"],
            "verdict": "legitimate",
            "pattern": "none",
            "affected_txn_ids": ["3514030"],
            "exposure_usd": 77.07,
        },
        "next_best_actions": {
            "initial": EXAMPLE["next_best_actions"]["initial"],
            "final": EXAMPLE["next_best_actions"]["initial"],
            "what_changed": "nothing",
        },
        "sar": {
            "file": False,
            "reason": "R3: customer confirmed",
            "narrative": "",
            "subjects": [],
            "total_amount_usd": 0,
            "activity_dates": [],
        },
        "evidence_requests": [],
    }
    with pytest.raises(ValidationError):
        Answer.model_validate(payload)


def test_unfiled_sar_must_be_empty() -> None:
    payload = {
        **EXAMPLE,
        "sar": {**EXAMPLE["sar"], "file": False},
        "next_best_actions": {
            "initial": EXAMPLE["next_best_actions"]["initial"],
            "final": EXAMPLE["next_best_actions"]["initial"],
            "what_changed": "Customer reply did not change the action.",
        },
    }
    with pytest.raises(ValidationError):
        Answer.model_validate(payload)
