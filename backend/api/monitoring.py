"""HTTP routes for optional exam-period monitoring answers."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from backend.investigate.monitor import MONITOR_DIR
from backend.models.answer import Answer
from backend.models.case_pack import CasePackItem
from backend.models.enums import TriggerType

router = APIRouter()


@router.get("/monitoring", response_model=list[CasePackItem])
def list_monitoring() -> list[CasePackItem]:
    items: list[CasePackItem] = []
    for path in sorted(MONITOR_DIR.glob("MON-*.json")):
        answer = Answer.model_validate_json(path.read_text(encoding="utf-8"))
        items.append(
            CasePackItem(
                case_id=answer.case_id,
                opened_at=datetime(2016, 11, 1),
                trigger_type=TriggerType.RISK_SCORE,
                trigger_text="Autonomous risk-score monitor",
                flagged_txn_id="",
                card_id="",
                customer_id="monitor",
                risk_score=None,
            )
        )
    return items


@router.get("/monitoring/{case_id}", response_model=Answer)
def saved_monitoring_answer(case_id: str) -> Answer:
    path = MONITOR_DIR / f"{case_id}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"unknown monitoring case_id: {case_id}")
    return Answer.model_validate_json(path.read_text(encoding="utf-8"))
