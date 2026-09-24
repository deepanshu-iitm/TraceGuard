import json
from pathlib import Path

from backend.models.answer import Answer

CASES_DIR = Path(__file__).resolve().parents[1] / "cases"


def test_all_twenty_answer_files_match_the_schema() -> None:
    paths = sorted(CASES_DIR.glob("HHG-*.json"))
    assert [path.stem for path in paths] == [f"HHG-{i:03d}" for i in range(1, 21)]
    for path in paths:
        answer = Answer.model_validate(json.loads(path.read_text(encoding="utf-8")))
        assert answer.case_id == path.stem
        assert answer.case.written_to_graph is True
        assert answer.case.graph_case_id == path.stem
