"""HTTP route that returns the investigation neighborhood for the console."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.data import load_case_pack
from backend.investigate.monitor import MONITOR_DIR
from backend.investigate.neighborhood import investigation_view


router = APIRouter()


@router.get("/graph/{case_id}")
def case_graph(case_id: str) -> dict:
    exam = any(item.case_id == case_id for item in load_case_pack())
    monitored = (MONITOR_DIR / f"{case_id}.json").is_file()
    if not exam and not monitored:
        raise HTTPException(status_code=404, detail=f"unknown case_id: {case_id}")
    try:
        return investigation_view(case_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
