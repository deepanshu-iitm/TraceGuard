"""Answer JSON submitted for each exam case."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.models.enums import CaseStatus, FraudPattern
from backend.models.evidence import Evidence
from backend.models.verdict import Verdict
from backend.policy.actions import ApprovalRoute, PolicyAction


class EvidenceRequestType(str, Enum):
    """Kinds of extra evidence the investigation may request."""

    CUSTOMER_VALIDATION = "customer_validation"
    STEP_UP_AUTH = "step_up_auth"
    ANALYST_INFO = "analyst_info"


class ActionRecommendation(BaseModel):
    """One next-best action with its approval route and policy citation."""

    model_config = ConfigDict(extra="forbid")

    action: PolicyAction
    route: ApprovalRoute
    reason: str


class EvidenceRequest(BaseModel):
    """An evidence request and the response assumed for this run."""

    model_config = ConfigDict(extra="forbid")

    type: EvidenceRequestType
    asked_after_step: int = Field(ge=0)
    assumed_response: str


class NextBestActions(BaseModel):
    """Recommendations before and after any assumed evidence."""

    model_config = ConfigDict(extra="forbid")

    initial: list[ActionRecommendation]
    final: list[ActionRecommendation]
    what_changed: str


class SAR(BaseModel):
    """Suspicious activity report section of an answer file."""

    model_config = ConfigDict(extra="forbid")

    file: bool
    reason: str
    narrative: str
    subjects: list[str]
    total_amount_usd: float = Field(ge=0)
    activity_dates: list[str]

    @model_validator(mode="after")
    def empty_when_not_filed(self) -> SAR:
        if not self.file:
            if self.narrative or self.subjects or self.total_amount_usd != 0 or self.activity_dates:
                raise ValueError("unfiled SAR must have empty narrative, subjects, amount, and dates")
            return self
        if len(self.activity_dates) != 2:
            raise ValueError("filed SAR requires two activity dates")
        if not self.narrative:
            raise ValueError("filed SAR requires a narrative")
        return self


class AnswerCase(BaseModel):
    """Internal investigation record stored in the answer file."""

    model_config = ConfigDict(extra="forbid")

    status: CaseStatus
    verdict: Verdict
    fraud_probability: float = Field(ge=0, le=1)
    pattern: FraudPattern
    pattern_description: str
    affected_txn_ids: list[str]
    first_suspicious_txn_id: str
    connected_card_ids: list[str]
    connected_device_profiles: list[str]
    exposure_usd: float = Field(ge=0)
    evidence: list[Evidence]
    similar_prior_cases: list[str]
    summary: str
    written_to_graph: bool
    graph_case_id: str

    @model_validator(mode="after")
    def consistent_with_verdict_and_pattern(self) -> AnswerCase:
        if self.pattern is FraudPattern.UNDOCUMENTED and not self.pattern_description:
            raise ValueError("undocumented pattern requires a description")
        if self.verdict is Verdict.LEGITIMATE:
            if self.affected_txn_ids or self.exposure_usd != 0:
                raise ValueError("legitimate cases have no affected transactions and zero exposure")
        if self.written_to_graph and not self.graph_case_id:
            raise ValueError("written_to_graph requires graph_case_id")
        return self


class Answer(BaseModel):
    """One scored answer file for a case-pack investigation."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    case: AnswerCase
    evidence_requests: list[EvidenceRequest]
    next_best_actions: NextBestActions
    sar: SAR
    stop_reason: str
    tool_calls: int = Field(ge=0)
    tokens: int = Field(ge=0)
    latency_s: float = Field(ge=0)

    @model_validator(mode="after")
    def actions_and_sar_agree(self) -> Answer:
        if self.case.verdict is Verdict.LEGITIMATE and self.sar.file:
            raise ValueError("legitimate cases must not file a SAR")
        filed = any(
            item.action is PolicyAction.FILE_REPORT for item in self.next_best_actions.final
        )
        if self.sar.file != filed:
            raise ValueError("sar.file must match FILE_REPORT in final actions")
        if not self.evidence_requests:
            if self.next_best_actions.final != self.next_best_actions.initial:
                raise ValueError("final actions must equal initial when no evidence was requested")
            if self.next_best_actions.what_changed != "nothing":
                raise ValueError("what_changed must be nothing when no evidence was requested")
        return self
