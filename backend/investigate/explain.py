"""Optional LLM rewrite of analyst-facing text. Policy and verdict stay in Python."""

from __future__ import annotations

import json
import time
import urllib.error
from typing import Any

from backend.config import settings
from backend.llm import complete as llm_complete
from backend.models.answer import Answer

_SYSTEM = """You are the analyst-facing writer for a finished fraud investigation.
Use only the JSON. That JSON already contains graph evidence, policy text, pattern notes, and closed-case notes (GraphRAG).
Do not invent IDs, amounts, dates, regions, or outcomes.
Do not change the verdict, pattern, probability, or actions.
Reply with JSON: {"summary": "...", "sar_narrative": "..."}.
summary is 2-4 sentences: what happened, which graph evidence mattered, which policy applies.
If sar_file is false, sar_narrative must be an empty string.
If sar_file is true, rewrite sar_narrative using the same subjects, amount, and dates, grounded in the evidence list."""


def explain_answer(answer: Answer) -> Answer:
    if not settings.openai_api_key.strip():
        return answer
    started = time.perf_counter()
    try:
        data, tokens = complete(_prompt(answer))
    except (OSError, urllib.error.URLError, json.JSONDecodeError, KeyError, ValueError):
        return answer
    elapsed = time.perf_counter() - started
    summary = data.get("summary")
    narrative = data.get("sar_narrative")
    case = answer.case
    if isinstance(summary, str) and summary.strip():
        case = case.model_copy(update={"summary": summary.strip()})
    sar = answer.sar
    if answer.sar.file and isinstance(narrative, str) and narrative.strip():
        sar = sar.model_copy(update={"narrative": narrative.strip()})
    return answer.model_copy(
        update={
            "case": case,
            "sar": sar,
            "tokens": answer.tokens + max(tokens, 0),
            "latency_s": round(answer.latency_s + elapsed, 2),
        }
    )


def complete(user: str) -> tuple[dict[str, Any], int]:
    return llm_complete(_SYSTEM, user)


def _prompt(answer: Answer) -> str:
    return json.dumps(
        {
            "case_id": answer.case_id,
            "verdict": answer.case.verdict.value,
            "pattern": answer.case.pattern.value,
            "fraud_probability": answer.case.fraud_probability,
            "exposure_usd": answer.case.exposure_usd,
            "status": answer.case.status.value,
            "summary": answer.case.summary,
            "evidence": [
                {"claim": item.claim, "source": item.source.value, "ref": item.ref}
                for item in answer.case.evidence
            ],
            "final_actions": [item.action.value for item in answer.next_best_actions.final],
            "sar_file": answer.sar.file,
            "sar_reason": answer.sar.reason,
            "sar_narrative": answer.sar.narrative,
            "sar_subjects": answer.sar.subjects,
            "sar_amount": answer.sar.total_amount_usd,
            "sar_dates": answer.sar.activity_dates,
            "stop_reason": answer.stop_reason,
        },
        indent=2,
    )
