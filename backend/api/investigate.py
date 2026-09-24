"""HTTP route that runs one exam-case investigation."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.data import load_case_pack
from backend.investigate import investigate
from backend.models.answer import Answer

router = APIRouter()


@router.post("/investigate/{case_id}", response_model=Answer)
def investigate_case(case_id: str) -> Answer:
    if not _is_exam_case(case_id):
        raise HTTPException(status_code=404, detail=f"unknown case_id: {case_id}")
    try:
        return investigate(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="graph export is not available") from exc


def _is_exam_case(case_id: str) -> bool:
    return any(item.case_id == case_id for item in load_case_pack())
