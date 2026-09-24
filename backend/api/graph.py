"""HTTP route that returns the investigation neighborhood for the console."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.data import load_case_pack
from backend.investigate.neighborhood import investigation_view

router = APIRouter()


@router.get("/graph/{case_id}")
def case_graph(case_id: str) -> dict:
    if not any(item.case_id == case_id for item in load_case_pack()):
        raise HTTPException(status_code=404, detail=f"unknown case_id: {case_id}")
    return investigation_view(case_id)
