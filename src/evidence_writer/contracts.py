"""Pydantic representations of frozen Architecture/Contracts v0.1.3."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError


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


class RightsStatus(StrEnum):
    SYNTHETIC = "SYNTHETIC"
    PUBLIC_DOMAIN = "PUBLIC_DOMAIN"
    LICENSED = "LICENSED"
    LINK_ONLY = "LINK_ONLY"
    UNKNOWN = "UNKNOWN"


SourceId = Annotated[str, Field(pattern=r"^S-[A-Za-z0-9_-]+$")]
ClaimId = Annotated[str, Field(pattern=r"^C-[A-Za-z0-9_-]+$")]


class Source(ContractModel):
    id: SourceId
    title: str = Field(min_length=1)
    url: AnyUrl
    accessed_at: date
    rights_status: RightsStatus
    published_at: date | None = None

    @model_validator(mode="before")
    @classmethod
    def published_at_cannot_be_null(cls, data: Any) -> Any:
        if isinstance(data, dict) and "published_at" in data and data["published_at"] is None:
            raise PydanticCustomError("schema_null_not_allowed", "published_at cannot be null")
        return data


class Claim(ContractModel):
    id: ClaimId
    claim_type: ClaimType
    text: str = Field(min_length=1)
    source_ids: list[SourceId]
    supporting_claim_ids: list[ClaimId]
    origin: ClaimOrigin
    evidence_level: EvidenceLevel
    scope: str = Field(min_length=1)
    allowed_use: list[AllowedUse] = Field(min_length=1)
    verification_status: VerificationStatus
    as_of: date | None = None

    @model_validator(mode="before")
    @classmethod
    def as_of_cannot_be_null(cls, data: Any) -> Any:
        if isinstance(data, dict) and "as_of" in data and data["as_of"] is None:
            raise PydanticCustomError("schema_null_not_allowed", "as_of cannot be null")
        return data

    @model_validator(mode="after")
    def enforce_authorization_matrix(self) -> Claim:
        uses = set(self.allowed_use)
        invalid = (
            (self.origin is ClaimOrigin.SOURCE_BACKED and not self.source_ids)
            or (self.origin is ClaimOrigin.DERIVED and not self.supporting_claim_ids)
            or (
                self.origin is ClaimOrigin.AUTHOR_HYPOTHESIS
                and (self.claim_type is not ClaimType.HYPOTHESIS or uses != {AllowedUse.QUALIFY})
            )
            or (
                self.claim_type is ClaimType.FACT
                and AllowedUse.STATE in uses
                and self.verification_status is not VerificationStatus.VERIFIED
            )
            or (
                self.claim_type is ClaimType.FACT
                and self.verification_status is VerificationStatus.PARTIAL
                and uses != {AllowedUse.QUALIFY}
            )
            or (self.claim_type is ClaimType.HYPOTHESIS and uses != {AllowedUse.QUALIFY})
            or (self.claim_type is ClaimType.LIMIT and uses != {AllowedUse.LIMIT})
            or (
                self.claim_type is ClaimType.FORBIDDEN
                and (uses != {AllowedUse.FORBID} or self.verification_status is not VerificationStatus.FORBIDDEN)
            )
        )
        if invalid:
            raise PydanticCustomError(
                "claim_authorization_matrix",
                "claim violates the frozen authorization matrix",
            )
        return self


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
    boundary_claims: list[Claim]

    @model_validator(mode="after")
    def enforce_claim_lanes(self) -> WriterHandoff:
        if any(
            claim.claim_type not in {ClaimType.FACT, ClaimType.SIGNAL, ClaimType.HYPOTHESIS}
            for claim in self.authorized_claims
        ):
            raise PydanticCustomError(
                "forbidden_authorized",
                "authorized_claims may contain only FACT, SIGNAL, or HYPOTHESIS",
            )
        if any(
            claim.claim_type not in {ClaimType.LIMIT, ClaimType.FORBIDDEN}
            for claim in self.boundary_claims
        ):
            raise PydanticCustomError(
                "invalid_boundary_claim",
                "boundary_claims may contain only LIMIT or FORBIDDEN",
            )
        return self


class AuthorIntent(ContractModel):
    schema_version: Literal["author-intent/0.1.3"]
    fact_authority: Literal["NONE"]
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
    fact_authority: Literal["NONE"]
    selected: list[CapabilitySelection] = Field(max_length=3)


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
    generation_metadata: dict[str, Any]


class ReviewAction(StrEnum):
    FLAG = "FLAG"
    LOCAL_REPAIR = "LOCAL_REPAIR"
    RETURN_TO_WRITER = "RETURN_TO_WRITER"


class ReviewFindingType(StrEnum):
    EXTERNAL_FACT = "EXTERNAL_FACT"
    NUMBER_TIME_PLACE = "NUMBER_TIME_PLACE"
    ACTION = "ACTION"
    SCENE = "SCENE"
    QUOTE = "QUOTE"
    GROUP_TRAIT = "GROUP_TRAIT"
    PSYCHOLOGY = "PSYCHOLOGY"
    MOTIVE = "MOTIVE"
    CAUSALITY = "CAUSALITY"
    PROFESSIONAL_JUDGMENT = "PROFESSIONAL_JUDGMENT"


class ReviewLocation(ContractModel):
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


class ReviewFinding(ContractModel):
    finding_type: ReviewFindingType
    location: ReviewLocation
    original_text: str = Field(min_length=1)
    evidence_claim_ids: list[ClaimId]
    action: ReviewAction
    repaired_text: str | None = None
    reason: str = Field(min_length=1)

    @field_validator("evidence_claim_ids")
    @classmethod
    def claim_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise PydanticCustomError(
                "review_finding_claim_ids",
                "evidence_claim_ids must be unique",
            )
        return value

    @model_validator(mode="after")
    def local_repair_requires_text(self) -> ReviewFinding:
        if self.action is ReviewAction.LOCAL_REPAIR and not self.repaired_text:
            raise PydanticCustomError(
                "local_repair_text_required",
                "LOCAL_REPAIR requires non-empty repaired_text",
            )
        return self


class ReviewVerdict(StrEnum):
    PASS = "PASS"
    LOCAL_REPAIR = "LOCAL_REPAIR"
    RETURN_TO_WRITER = "RETURN_TO_WRITER"


class ReviewResult(ContractModel):
    schema_version: Literal["review-result/0.1.3"]
    reviewed_draft_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    review_verdict: ReviewVerdict
    findings: list[ReviewFinding]
    final_text: str | None = Field(default=None, min_length=1)
    return_reason: str | None = Field(default=None, min_length=1)

    @model_validator(mode="before")
    @classmethod
    def optional_strings_cannot_be_null(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for field_name in ("final_text", "return_reason"):
                if field_name in data and data[field_name] is None:
                    raise PydanticCustomError(
                        "schema_null_not_allowed",
                        f"{field_name} cannot be null",
                    )
        return data

    @model_validator(mode="after")
    def enforce_verdict_conditions(self) -> ReviewResult:
        if self.review_verdict is ReviewVerdict.PASS:
            if not self.final_text:
                raise PydanticCustomError("review_missing_final_text", "PASS requires final_text")
            if any(finding.action is ReviewAction.RETURN_TO_WRITER for finding in self.findings):
                raise PydanticCustomError(
                    "review_verdict_conflict",
                    "PASS cannot contain a RETURN_TO_WRITER finding",
                )
        elif self.review_verdict is ReviewVerdict.LOCAL_REPAIR:
            if not self.final_text:
                raise PydanticCustomError(
                    "review_missing_final_text",
                    "LOCAL_REPAIR requires final_text",
                )
            if not any(finding.action is ReviewAction.LOCAL_REPAIR for finding in self.findings):
                raise PydanticCustomError(
                    "local_repair_finding_required",
                    "LOCAL_REPAIR requires at least one repair finding",
                )
        else:
            if not self.return_reason:
                raise PydanticCustomError(
                    "return_missing_reason",
                    "RETURN_TO_WRITER requires return_reason",
                )
            if not any(finding.action is ReviewAction.RETURN_TO_WRITER for finding in self.findings):
                raise PydanticCustomError(
                    "return_finding_required",
                    "RETURN_TO_WRITER requires a matching finding",
                )
        return self


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

    @model_validator(mode="after")
    def enforce_artifact_contract(self) -> ArtifactEnvelope:
        model_by_type = {
            ArtifactType.RESEARCH: ResearchPackage,
            ArtifactType.HANDOFF: WriterHandoff,
            ArtifactType.INPUT: WriterInput,
            ArtifactType.DRAFT: DraftArtifact,
            ArtifactType.REVIEW: ReviewResult,
        }
        version_by_type = {
            ArtifactType.RESEARCH: "research-package/0.1.3",
            ArtifactType.HANDOFF: "writer-handoff/0.1.3",
            ArtifactType.INPUT: "writer-input/0.1.3",
            ArtifactType.DRAFT: "draft-artifact/0.1.3",
            ArtifactType.REVIEW: "review-result/0.1.3",
        }
        expected_version = version_by_type[self.artifact_type]
        if self.artifact_schema_version != expected_version:
            raise PydanticCustomError(
                "schema_version_mismatch",
                "artifact_schema_version does not match artifact_type",
            )
        model_by_type[self.artifact_type].model_validate(self.artifact)
        return self


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
    error_code: str | None = Field(default=None, min_length=1)
    reason: str | None = Field(default=None, min_length=1)
    diagnostic: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def optional_non_null_fields_match_schema(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for field_name in ("artifact_envelope", "error_code", "reason"):
                if field_name in data and data[field_name] is None:
                    raise PydanticCustomError(
                        "schema_null_not_allowed",
                        f"{field_name} cannot be null",
                    )
        return data

    @model_validator(mode="after")
    def enforce_stage_result(self) -> StageResult:
        expected_type = {
            Stage.AUDITOR: ArtifactType.HANDOFF,
            Stage.ADAPTER: ArtifactType.INPUT,
            Stage.WRITER: ArtifactType.DRAFT,
            Stage.FINAL_REVIEW: ArtifactType.REVIEW,
        }[self.stage]
        if self.stage_status is StageStatus.PASS:
            if self.artifact_envelope is None:
                raise PydanticCustomError("pass_missing_artifact", "PASS requires artifact_envelope")
            if self.artifact_envelope.artifact_type is not expected_type:
                raise PydanticCustomError(
                    "artifact_type_mismatch",
                    "PASS artifact type does not match stage",
                )
        else:
            if self.artifact_envelope is not None:
                raise PydanticCustomError(
                    "failed_stage_has_artifact",
                    "FAIL/BLOCKED cannot carry artifact_envelope",
                )
            if not self.error_code or not self.reason:
                raise PydanticCustomError(
                    "failed_stage_missing_reason",
                    "FAIL/BLOCKED requires error_code and reason",
                )
        return self


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

    @field_validator("capability_ids")
    @classmethod
    def capability_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise PydanticCustomError(
                "capability_registry_ids_not_unique",
                "capability_ids must be unique",
            )
        return value


class EvidenceWriterBundle(ContractModel):
    research_artifact_envelope: ArtifactEnvelope
    capability_registry_snapshot: CapabilityRegistrySnapshot
    auditor_result: AuditorStageResult
    adapter_result: AdapterStageResult
    writer_result: WriterStageResult
    final_review_result: FinalReviewStageResult

    @model_validator(mode="after")
    def research_envelope_must_contain_research(self) -> EvidenceWriterBundle:
        if self.research_artifact_envelope.artifact_type is not ArtifactType.RESEARCH:
            raise PydanticCustomError(
                "artifact_type_mismatch",
                "research_artifact_envelope must contain ResearchPackage",
            )
        return self
