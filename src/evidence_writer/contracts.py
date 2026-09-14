"""Pydantic representations of frozen Architecture/Contracts v0.1.3."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    # JSON/YAML contracts represent enums as strings.  Extra fields remain
    # forbidden; enum coercion is required for standards-compliant wire input.
    model_config = ConfigDict(extra="forbid")


class ClaimType(StrEnum):
    FACT = "FACT"
    SIGNAL = "SIGNAL"
    HYPOTHESIS = "HYPOTHESIS"
    LIMIT = "LIMIT"
    FORBIDDEN = "FORBIDDEN"


class ClaimOrigin(StrEnum):
    SOURCE_BACKED = "SOURCE_BACKED"
    DERIVED = "DERIVED"
    AUTHOR_HYPOTHESIS = "AUTHOR_HYPOTHESIS"


class EvidenceLevel(StrEnum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    CONTEXTUAL = "CONTEXTUAL"
    NONE = "NONE"


class VerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    PARTIAL = "PARTIAL"
    UNVERIFIED = "UNVERIFIED"
    FORBIDDEN = "FORBIDDEN"


class AllowedUse(StrEnum):
    STATE = "state"
    QUALIFY = "qualify"
    LIMIT = "limit"
    FORBID = "forbid"


class Source(ContractModel):
    id: str = Field(pattern=r"^S-[A-Za-z0-9_-]+$")
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    accessed_at: str = Field(min_length=1)
    rights_status: str = Field(min_length=1)
    published_at: str | None = None


class Claim(ContractModel):
    id: str = Field(pattern=r"^C-[A-Za-z0-9_-]+$")
    claim_type: ClaimType
    text: str = Field(min_length=1)
    source_ids: list[str]
    supporting_claim_ids: list[str]
    origin: ClaimOrigin
    evidence_level: EvidenceLevel
    scope: str = Field(min_length=1)
    allowed_use: list[AllowedUse] = Field(min_length=1)
    verification_status: VerificationStatus
    as_of: str | None = None


class ResearchPackage(ContractModel):
    schema_version: Literal["research-package/0.1.3"]
    topic: str = Field(min_length=1)
    sources: list[Source] = Field(min_length=1)
    claims: list[Claim] = Field(min_length=1)


class WriterHandoff(ContractModel):
    schema_version: Literal["writer-handoff/0.1.3"]
    input_artifact_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    evidence_authority: Literal["WRITER_HANDOFF_ONLY"]
    sources: list[Source] = Field(min_length=1)
    authorized_claims: list[Claim] = Field(min_length=1)
    boundary_claims: list[Claim] = Field(default_factory=list)


class AuthorIntent(ContractModel):
    schema_version: Literal["author-intent/0.1.3"]
    fact_authority: str
    why_now: str
    central_tension: str
    core_position: str
    emotional_state: str = Field(min_length=1)
    distance_to_object: str
    do_not_become: str
    ending_destination: str


class CapabilitySelection(ContractModel):
    capability_id: str = Field(min_length=1)
    objective: str
    execution_directive: str
    skip_if: str
    success_check: str


class CapabilityPlan(ContractModel):
    schema_version: Literal["capability-plan/0.1.3"]
    registry_version: str = Field(min_length=1)
    fact_authority: str
    selected: list[CapabilitySelection]


class WriterInput(ContractModel):
    schema_version: Literal["writer-input/0.1.3"]
    input_artifact_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    evidence_handoff: WriterHandoff
    author_intent: AuthorIntent
    capability_plan: CapabilityPlan


class DraftArtifact(ContractModel):
    schema_version: Literal["draft-artifact/0.1.3"]
    input_artifact_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    draft_markdown: str
    generation_metadata: dict[str, str]


class ReviewAction(StrEnum):
    FLAG = "FLAG"
    LOCAL_REPAIR = "LOCAL_REPAIR"
    RETURN_TO_WRITER = "RETURN_TO_WRITER"


class ReviewFinding(ContractModel):
    finding_type: str = Field(min_length=1)
    location: dict[str, int]
    original_text: str = Field(min_length=1)
    evidence_claim_ids: list[str]
    action: ReviewAction
    repaired_text: str | None = None
    reason: str = Field(min_length=1)


class ReviewVerdict(StrEnum):
    PASS = "PASS"
    LOCAL_REPAIR = "LOCAL_REPAIR"
    RETURN_TO_WRITER = "RETURN_TO_WRITER"


class ReviewResult(ContractModel):
    schema_version: Literal["review-result/0.1.3"]
    reviewed_draft_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    review_verdict: ReviewVerdict
    findings: list[ReviewFinding]
    final_text: str | None = None
    return_reason: str | None = None


class ArtifactType(StrEnum):
    RESEARCH = "ResearchPackage"
    HANDOFF = "WriterHandoff"
    INPUT = "WriterInput"
    DRAFT = "DraftArtifact"
    REVIEW = "ReviewResult"


class ArtifactEnvelope(ContractModel):
    artifact_type: ArtifactType
    artifact_schema_version: str = Field(min_length=1)
    canonical_json_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    artifact: dict[str, Any]


class Stage(StrEnum):
    AUDITOR = "AUDITOR"
    ADAPTER = "ADAPTER"
    WRITER = "WRITER"
    FINAL_REVIEW = "FINAL_REVIEW"


class StageStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


class StageResult(ContractModel):
    stage: Stage
    stage_status: StageStatus
    artifact_envelope: ArtifactEnvelope | None = None
    error_code: str | None = None
    reason: str | None = None
    diagnostic: dict[str, Any] | None = None


class AuditorStageResult(StageResult):
    stage: Literal[Stage.AUDITOR]


class AdapterStageResult(StageResult):
    stage: Literal[Stage.ADAPTER]


class WriterStageResult(StageResult):
    stage: Literal[Stage.WRITER]


class FinalReviewStageResult(StageResult):
    stage: Literal[Stage.FINAL_REVIEW]


class CapabilityRegistrySnapshot(ContractModel):
    schema_version: Literal["capability-registry/0.1"]
    registry_version: str
    capability_ids: list[str]


class EvidenceWriterBundle(ContractModel):
    research_artifact_envelope: ArtifactEnvelope
    capability_registry_snapshot: CapabilityRegistrySnapshot
    auditor_result: StageResult
    adapter_result: StageResult
    writer_result: StageResult
    final_review_result: StageResult
