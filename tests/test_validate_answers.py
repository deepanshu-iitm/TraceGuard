import pytest

from backend.graph.export import PROCESSED_DIR
from backend.validate import format_report, validate_answers


pytestmark = pytest.mark.skipif(
    not (PROCESSED_DIR / "edges.csv").is_file(),
    reason="export graph CSVs into data/processed first",
)


def test_all_twenty_answers_pass_the_local_validator() -> None:
    report = validate_answers()
    assert report.issues == [], format_report(report)
    assert report.schema == 20
    assert report.ids == 20
    assert report.exposure == 20
    assert report.policy == 20
    assert report.routes == 20
    assert report.sar == 20
    assert report.graph == 20
    assert report.evidence == 20
    assert report.actions == 20
    text = format_report(report)
    assert "JSON schema:            20/20" in text
    assert "SAR consistency:        20/20" in text
