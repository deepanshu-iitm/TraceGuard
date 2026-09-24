"""Local submission checks for the 20 exam answer files."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from backend.data import load_case_pack
from backend.graph.export import PROCESSED_DIR
from backend.models.answer import Answer
from backend.models.verdict import Verdict
from backend.policy.actions import PolicyAction
from backend.policy.permissions import approval_route

CASES_DIR = Path(__file__).resolve().parents[2] / "cases"
EXPECTED_IDS = [f"HHG-{index:03d}" for index in range(1, 21)]


@dataclass(frozen=True)
class CheckIssue:
    """One failed check on one case file."""

    case_id: str
    check: str
    message: str


@dataclass
class QualityReport:
    """Counts and issues for the local quality report."""

    schema: int = 0
    ids: int = 0
    exposure: int = 0
    policy: int = 0
    routes: int = 0
    sar: int = 0
    graph: int = 0
    evidence: int = 0
    actions: int = 0
    issues: list[CheckIssue] = field(default_factory=list)

    @property
    def total(self) -> int:
        return 20


def validate_answers(
    cases_dir: Path | None = None,
    processed_dir: Path | None = None,
) -> QualityReport:
    root = cases_dir or CASES_DIR
    graph = processed_dir or PROCESSED_DIR
    report = QualityReport()
    catalog = _Catalog.load(graph)
    pack = {item.case_id: item for item in load_case_pack()}
    answers = _load_answers(root, report)
    if len(answers) != 20:
        return report

    for case_id, answer in answers.items():
        item = pack.get(case_id)
        _check_ids(answer, catalog, item, report)
        _check_exposure(answer, catalog, report)
        _check_policy(answer, report)
        _check_sar(answer, report)
        _check_graph(answer, report)
        _check_evidence(answer, catalog, report)
        _check_actions(answer, report)
    return report


def format_report(report: QualityReport) -> str:
    n = report.total
    lines = [
        "=================================================",
        "HACKER HOUSE GOA — LOCAL QUALITY REPORT",
        "=================================================",
        "",
        f"JSON schema:            {report.schema}/{n}",
        f"IDs valid:              {report.ids}/{n}",
        f"Exposure valid:         {report.exposure}/{n}",
        f"Policy valid:           {report.policy}/{n}",
        f"Approval routes:        {report.routes}/{n}",
        f"SAR consistency:        {report.sar}/{n}",
        f"Graph persistence:      {report.graph}/{n}",
        f"Evidence references:    {report.evidence}/{n}",
        f"Initial/final actions:  {report.actions}/{n}",
        "=================================================",
    ]
    if report.issues:
        lines.append("")
        for issue in report.issues:
            lines.append(f"{issue.case_id} [{issue.check}] {issue.message}")
    return "\n".join(lines) + "\n"


def _load_answers(root: Path, report: QualityReport) -> dict[str, Answer]:
    paths = sorted(root.glob("HHG-*.json"))
    found = [path.stem for path in paths]
    answers: dict[str, Answer] = {}
    if found != EXPECTED_IDS:
        report.issues.append(
            CheckIssue("pack", "schema", f"expected {EXPECTED_IDS}, found {found}")
        )
        return answers
    for path in paths:
        try:
            answer = Answer.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError as exc:
            report.issues.append(CheckIssue(path.stem, "schema", str(exc.errors()[0]["msg"])))
            continue
        if answer.case_id != path.stem:
            report.issues.append(
                CheckIssue(path.stem, "schema", f"case_id {answer.case_id} does not match file")
            )
            continue
        answers[path.stem] = answer
        report.schema += 1
    return answers


def _check_ids(answer: Answer, catalog: _Catalog, pack_item, report: QualityReport) -> None:
    missing: list[str] = []
    for txn_id in answer.case.affected_txn_ids:
        if txn_id not in catalog.txns:
            missing.append(txn_id)
    if answer.case.first_suspicious_txn_id and answer.case.first_suspicious_txn_id not in catalog.txns:
        missing.append(answer.case.first_suspicious_txn_id)
    for card_id in answer.case.connected_card_ids:
        if card_id not in catalog.cards:
            missing.append(card_id)
    for case_id in answer.case.similar_prior_cases:
        if case_id not in catalog.closed:
            missing.append(case_id)
    if pack_item is not None:
        if pack_item.card_id not in catalog.cards:
            missing.append(pack_item.card_id)
        if pack_item.customer_id not in catalog.customers:
            missing.append(pack_item.customer_id)
        if pack_item.flagged_txn_id not in catalog.txns:
            missing.append(pack_item.flagged_txn_id)
    for profile in answer.case.connected_device_profiles:
        if profile not in catalog.devices:
            missing.append(profile)
    if missing:
        report.issues.append(
            CheckIssue(answer.case_id, "ids", "unknown ids: " + ", ".join(missing))
        )
        return
    report.ids += 1


def _check_exposure(answer: Answer, catalog: _Catalog, report: QualityReport) -> None:
    if any(txn_id not in catalog.txns for txn_id in answer.case.affected_txn_ids):
        return
    expected = round(
        sum(abs(catalog.txns[txn_id]) for txn_id in answer.case.affected_txn_ids),
        2,
    )
    if round(answer.case.exposure_usd, 2) != expected:
        report.issues.append(
            CheckIssue(
                answer.case_id,
                "exposure",
                f"exposure {answer.case.exposure_usd} != sum of affected amounts {expected}",
            )
        )
        return
    report.exposure += 1


def _check_policy(answer: Answer, report: QualityReport) -> None:
    exposure = answer.case.exposure_usd
    ok = True
    for item in answer.next_best_actions.initial + answer.next_best_actions.final:
        expected = approval_route(item.action, exposure)
        if item.route is not expected:
            report.issues.append(
                CheckIssue(
                    answer.case_id,
                    "routes",
                    f"{item.action.value} route {item.route.value} != {expected.value}",
                )
            )
            ok = False
        if item.action is PolicyAction.BLOCK_ALL_CARDS:
            report.issues.append(
                CheckIssue(answer.case_id, "policy", "BLOCK_ALL_CARDS present; R10 must hold")
            )
            ok = False
    if not answer.next_best_actions.initial or not answer.next_best_actions.final:
        report.issues.append(CheckIssue(answer.case_id, "policy", "initial or final actions missing"))
        ok = False
    if ok:
        report.policy += 1
        report.routes += 1


def _check_sar(answer: Answer, report: QualityReport) -> None:
    filed = any(item.action is PolicyAction.FILE_REPORT for item in answer.next_best_actions.final)
    if answer.sar.file != filed:
        report.issues.append(CheckIssue(answer.case_id, "sar", "sar.file does not match FILE_REPORT"))
        return
    if answer.case.verdict is Verdict.LEGITIMATE and answer.sar.file:
        report.issues.append(CheckIssue(answer.case_id, "sar", "legitimate case filed a SAR"))
        return
    report.sar += 1


def _check_graph(answer: Answer, report: QualityReport) -> None:
    if not answer.case.written_to_graph or answer.case.graph_case_id != answer.case_id:
        report.issues.append(
            CheckIssue(answer.case_id, "graph", "written_to_graph/graph_case_id mismatch")
        )
        return
    report.graph += 1


def _check_evidence(answer: Answer, catalog: _Catalog, report: QualityReport) -> None:
    known = catalog.txns.keys() | catalog.cards | catalog.customers | catalog.closed | catalog.devices
    missing: list[str] = []
    for evidence in answer.case.evidence:
        for entity_id in evidence.entity_ids:
            if entity_id not in known:
                missing.append(entity_id)
    if missing:
        report.issues.append(
            CheckIssue(answer.case_id, "evidence", "unknown entity ids: " + ", ".join(missing))
        )
        return
    report.evidence += 1


def _check_actions(answer: Answer, report: QualityReport) -> None:
    actions = answer.next_best_actions
    if not actions.initial or not actions.final:
        report.issues.append(CheckIssue(answer.case_id, "actions", "missing initial or final"))
        return
    if not answer.evidence_requests and actions.what_changed != "nothing":
        report.issues.append(
            CheckIssue(answer.case_id, "actions", "what_changed must be nothing when no evidence requested")
        )
        return
    report.actions += 1


@dataclass
class _Catalog:
    txns: dict[str, float]
    cards: set[str]
    customers: set[str]
    closed: set[str]
    devices: set[str]

    @classmethod
    def load(cls, processed_dir: Path) -> _Catalog:
        return cls(
            txns=_amounts(processed_dir / "vertices_transaction.csv"),
            cards=_ids(processed_dir / "vertices_card.csv"),
            customers=_ids(processed_dir / "vertices_customer.csv"),
            closed=_ids(processed_dir / "vertices_closed_case.csv"),
            devices=_ids(processed_dir / "vertices_device.csv"),
        )


def _ids(path: Path) -> set[str]:
    with path.open(encoding="utf-8", newline="") as handle:
        return {row["id"] for row in csv.DictReader(handle)}


def _amounts(path: Path) -> dict[str, float]:
    with path.open(encoding="utf-8", newline="") as handle:
        return {row["id"]: abs(float(row["amount"])) for row in csv.DictReader(handle)}
