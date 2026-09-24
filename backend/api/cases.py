"""HTTP route that lists exam cases."""

from __future__ import annotations

from fastapi import APIRouter

from backend.data import load_case_pack
from backend.models.case_pack import CasePackItem

router = APIRouter()


@router.get("/cases", response_model=list[CasePackItem])
def list_cases() -> list[CasePackItem]:
    return load_case_pack()
