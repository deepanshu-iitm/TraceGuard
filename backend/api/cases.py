"""HTTP routes that list exam cases and return saved answers."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.data import load_case_pack
from backend.investigate.compose import CASES_DIR
from backend.models.answer import Answer
from backend.models.case_pack import CasePackItem

router = APIRouter()


@router.get("/cases", response_model=list[CasePackItem])
def list_cases() -> list[CasePackItem]:
    return load_case_pack()


@router.get("/cases/{case_id}", response_model=Answer)
def saved_answer(case_id: str) -> Answer:
    if not any(item.case_id == case_id for item in load_case_pack()):
        raise HTTPException(status_code=404, detail=f"unknown case_id: {case_id}")
    path = CASES_DIR / f"{case_id}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"no saved answer for {case_id}")
    return Answer.model_validate_json(path.read_text(encoding="utf-8"))
