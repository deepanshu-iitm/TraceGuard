"""Watch the exam period for high risk-score alerts beyond the 20 scored cases."""

from __future__ import annotations

import json
from pathlib import Path

from backend.data import load_case_pack
from backend.investigate.compose import compose_answer
from backend.investigate.facts import load_alert_facts, _graph_index
from backend.investigate.persist import write_investigation_case
from backend.graph.export import PROCESSED_DIR

MONITOR_DIR = Path(__file__).resolve().parents[2] / "optional_monitoring"
_EXAM_START = "2016-11-01"
_MIN_SCORE = 0.70
_LIMIT = 8


def high_risk_alerts(processed_dir: Path | None = None, limit: int = _LIMIT) -> list[tuple[str, str]]:
    """Txn ids in Nov–Dec with risk_score >= 0.70 that are not in the exam pack."""
    dest = processed_dir or PROCESSED_DIR
    flagged = {item.flagged_txn_id for item in load_case_pack()}
    index = _graph_index(dest)
    ranked = sorted(
        (
            txn
            for txn in index.txns.values()
            if txn.risk_score >= _MIN_SCORE
            and txn.ts >= _EXAM_START
            and txn.txn_id not in flagged
        ),
        key=lambda txn: (-txn.risk_score, txn.ts, txn.txn_id),
    )
    alerts: list[tuple[str, str]] = []
    for offset, txn in enumerate(ranked[:limit], start=1):
        alerts.append((f"MON-{offset:03d}", txn.txn_id))
    return alerts


def write_monitoring_answers(
    out_dir: Path | None = None, processed_dir: Path | None = None
) -> list[Path]:
    dest = out_dir or MONITOR_DIR
    dest.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for case_id, txn_id in high_risk_alerts(processed_dir):
        facts = load_alert_facts(case_id, txn_id, processed_dir)
        answer = write_investigation_case(compose_answer(facts), item=facts.case)
        path = dest / f"{case_id}.json"
        path.write_text(json.dumps(answer.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


if __name__ == "__main__":
    paths = write_monitoring_answers()
    print(f"wrote {len(paths)} monitoring answers")
