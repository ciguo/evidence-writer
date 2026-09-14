"""Deterministic validation for Architecture/Contracts v0.1.3."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .canonical import canonical_sha256
from .contracts import (
    AllowedUse, ArtifactEnvelope, ArtifactType, Claim, ClaimOrigin, ClaimType,
    EvidenceWriterBundle, ReviewAction, ReviewVerdict, Stage, StageStatus,
    VerificationStatus,
)


@dataclass(frozen=True)
class PolicyViolation:
    code: str
    path: str
    message: str


def _issue(out: list[PolicyViolation], code: str, path: str, message: str) -> None:
    out.append(PolicyViolation(code, path, message))


def _claim_matrix(claim: Claim, path: str, out: list[PolicyViolation]) -> None:
    uses = set(claim.allowed_use)
    invalid = (
        (claim.origin is ClaimOrigin.SOURCE_BACKED and not claim.source_ids)
        or (claim.origin is ClaimOrigin.DERIVED and not claim.supporting_claim_ids)
        or (claim.origin is ClaimOrigin.AUTHOR_HYPOTHESIS and (claim.claim_type is not ClaimType.HYPOTHESIS or uses != {AllowedUse.QUALIFY}))
        or (claim.claim_type is ClaimType.FACT and AllowedUse.STATE in uses and claim.verification_status is not VerificationStatus.VERIFIED)
        or (claim.claim_type is ClaimType.FACT and claim.verification_status is VerificationStatus.PARTIAL and uses != {AllowedUse.QUALIFY})
        or (claim.claim_type is ClaimType.HYPOTHESIS and uses != {AllowedUse.QUALIFY})
        or (claim.claim_type is ClaimType.LIMIT and uses != {AllowedUse.LIMIT})
        or (claim.claim_type is ClaimType.FORBIDDEN and (uses != {AllowedUse.FORBID} or claim.verification_status is not VerificationStatus.FORBIDDEN))
    )
    if invalid:
        _issue(out, "CLAIM_AUTHORIZATION_MATRIX", path, "claim violates frozen authorization matrix")


def _validate_claim_graph(claims: list[Claim], source_ids: set[str], path: str, out: list[PolicyViolation]) -> None:
    ids = [claim.id for claim in claims]
    if len(ids) != len(set(ids)):
        _issue(out, "CLAIM_ID_NOT_UNIQUE", path, "claim IDs must be unique")
    known = set(ids)
    graph: dict[str, list[str]] = {}
    for claim in claims:
        _claim_matrix(claim, f"{path}.{claim.id}", out)
        graph[claim.id] = claim.supporting_claim_ids
        if not set(claim.source_ids) <= source_ids:
            _issue(out, "DANGLING_SOURCE_REF", f"{path}.{claim.id}", "unknown source reference")
        if not set(claim.supporting_claim_ids) <= known:
            _issue(out, "DANGLING_CLAIM_REF", f"{path}.{claim.id}", "unknown supporting claim")
        if claim.id in claim.supporting_claim_ids:
            _issue(out, "CLAIM_SELF_REFERENCE", f"{path}.{claim.id}", "claim supports itself")
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        cyclic = any(visit(n) for n in graph[node] if n in graph)
        visiting.remove(node)
        visited.add(node)
        return cyclic
    if any(visit(node) for node in graph):
        _issue(out, "CLAIM_DEPENDENCY_CYCLE", path, "supporting_claim graph contains a cycle")


def _expected_type(envelope: ArtifactEnvelope) -> tuple[ArtifactType, str]:
    mapping = {
        ArtifactType.RESEARCH: (ArtifactType.RESEARCH, "research-package/0.1.3"),
        ArtifactType.HANDOFF: (ArtifactType.HANDOFF, "writer-handoff/0.1.3"),
        ArtifactType.INPUT: (ArtifactType.INPUT, "writer-input/0.1.3"),
        ArtifactType.DRAFT: (ArtifactType.DRAFT, "draft-artifact/0.1.3"),
        ArtifactType.REVIEW: (ArtifactType.REVIEW, "review-result/0.1.3"),
    }
    return mapping[envelope.artifact_type]


def _validate_envelope(envelope: ArtifactEnvelope, expected_type: ArtifactType, path: str, out: list[PolicyViolation]) -> None:
    _, expected_version = _expected_type(envelope)
    if envelope.artifact_type is not expected_type:
        _issue(out, "ARTIFACT_TYPE_MISMATCH", path, "artifact type does not match stage")
    if envelope.artifact_schema_version != expected_version or envelope.artifact.get("schema_version") != expected_version:
        _issue(out, "SCHEMA_VERSION_MISMATCH", path, "envelope and artifact schema versions differ")
    if canonical_sha256(envelope.artifact) != envelope.canonical_json_sha256:
        _issue(out, "DIGEST_INVALID", path, "artifact digest does not match canonical JSON")


def validate_bundle(bundle: EvidenceWriterBundle) -> list[PolicyViolation]:
    out: list[PolicyViolation] = []
    research_env = bundle.research_artifact_envelope
    _validate_envelope(research_env, ArtifactType.RESEARCH, "research_artifact_envelope", out)
    research = research_env.artifact
    # Pydantic models are deliberately reconstituted here, so data exchanged
    # between stages has no hidden context and only Contract data is consumed.
    from .contracts import ResearchPackage, WriterHandoff, WriterInput, DraftArtifact, ReviewResult
    research_model = ResearchPackage.model_validate(research)
    sources = [source.id for source in research_model.sources]
    if len(sources) != len(set(sources)):
        _issue(out, "SOURCE_ID_NOT_UNIQUE", "research.sources", "source IDs must be unique")
    _validate_claim_graph(research_model.claims, set(sources), "research.claims", out)

    results = [
        (bundle.auditor_result, Stage.AUDITOR, ArtifactType.HANDOFF, "auditor_result"),
        (bundle.adapter_result, Stage.ADAPTER, ArtifactType.INPUT, "adapter_result"),
        (bundle.writer_result, Stage.WRITER, ArtifactType.DRAFT, "writer_result"),
        (bundle.final_review_result, Stage.FINAL_REVIEW, ArtifactType.REVIEW, "final_review_result"),
    ]
    prior_pass = True
    for result, expected_stage, expected, path in results:
        if result.stage is not expected_stage:
            _issue(out, "TOP_LEVEL_STAGE_MISMATCH", path, "top-level result is bound to a different stage")
        if result.stage_status is StageStatus.PASS:
            if result.artifact_envelope is None:
                _issue(out, "PASS_MISSING_ARTIFACT", path, "PASS requires an artifact envelope")
            else:
                _validate_envelope(result.artifact_envelope, expected, path, out)
        else:
            if result.artifact_envelope is not None:
                _issue(out, "FAILED_STAGE_HAS_ARTIFACT", path, "FAIL/BLOCKED cannot carry an artifact")
            if not result.error_code or not result.reason:
                _issue(out, "FAILED_STAGE_MISSING_REASON", path, "FAIL/BLOCKED requires error_code and reason")
            prior_pass = False
        if not prior_pass and result.stage_status is StageStatus.PASS:
            _issue(out, "INVALID_STAGE_TRANSITION", path, "a later stage cannot PASS after an earlier failure")

    if any(result.stage_status is not StageStatus.PASS for result, _, _, _ in results):
        return out

    handoff = WriterHandoff.model_validate(bundle.auditor_result.artifact_envelope.artifact)
    writer_input = WriterInput.model_validate(bundle.adapter_result.artifact_envelope.artifact)
    draft = DraftArtifact.model_validate(bundle.writer_result.artifact_envelope.artifact)
    review = ReviewResult.model_validate(bundle.final_review_result.artifact_envelope.artifact)
    if handoff.input_artifact_digest != research_env.canonical_json_sha256:
        _issue(out, "PROVENANCE_DIGEST_MISMATCH", "writer_handoff.input_artifact_digest", "must equal research envelope digest")
    if writer_input.input_artifact_digest != bundle.auditor_result.artifact_envelope.canonical_json_sha256:
        _issue(out, "PROVENANCE_DIGEST_MISMATCH", "writer_input.input_artifact_digest", "must equal handoff envelope digest")
    if draft.input_artifact_digest != bundle.adapter_result.artifact_envelope.canonical_json_sha256:
        _issue(out, "PROVENANCE_DIGEST_MISMATCH", "draft.input_artifact_digest", "must equal writer input envelope digest")
    if review.reviewed_draft_digest != bundle.writer_result.artifact_envelope.canonical_json_sha256:
        _issue(out, "PROVENANCE_DIGEST_MISMATCH", "review.reviewed_draft_digest", "must equal draft envelope digest")
    h_sources = {source.id for source in handoff.sources}
    all_h_claims = handoff.authorized_claims + handoff.boundary_claims
    _validate_claim_graph(all_h_claims, h_sources, "writer_handoff.claims", out)
    authorized_ids = {claim.id for claim in handoff.authorized_claims}
    boundary_ids = {claim.id for claim in handoff.boundary_claims}
    if authorized_ids & boundary_ids:
        _issue(out, "AUTHORIZED_BOUNDARY_OVERLAP", "writer_handoff", "claim cannot be both authorized and boundary")
    if any(claim.claim_type not in {ClaimType.FACT, ClaimType.SIGNAL, ClaimType.HYPOTHESIS} for claim in handoff.authorized_claims):
        _issue(out, "FORBIDDEN_AUTHORIZED", "writer_handoff.authorized_claims", "only FACT/SIGNAL/HYPOTHESIS may be authorized")
    if any(claim.claim_type not in {ClaimType.LIMIT, ClaimType.FORBIDDEN} for claim in handoff.boundary_claims):
        _issue(out, "INVALID_BOUNDARY_CLAIM", "writer_handoff.boundary_claims", "boundary may only contain LIMIT/FORBIDDEN")
    registry = set(bundle.capability_registry_snapshot.capability_ids)
    if writer_input.capability_plan.registry_version != bundle.capability_registry_snapshot.registry_version:
        _issue(out, "CAPABILITY_REGISTRY_VERSION_MISMATCH", "capability_plan", "registry version differs")
    for item in writer_input.capability_plan.selected:
        if item.capability_id not in registry:
            _issue(out, "UNKNOWN_CAPABILITY_ID", "capability_plan.selected", "capability absent from registry")
    if len(writer_input.capability_plan.selected) > 3:
        _issue(out, "CAPABILITY_OVER_MAX", "capability_plan.selected", "at most three capabilities are allowed")
    if writer_input.author_intent.fact_authority != "NONE":
        _issue(out, "INTENT_FACT_AUTHORITY", "author_intent.fact_authority", "Author Intent has no fact authority")
    if writer_input.capability_plan.fact_authority != "NONE":
        _issue(out, "CAPABILITY_FACT_AUTHORITY", "capability_plan.fact_authority", "Capability Plan has no fact authority")
    findings = review.findings
    known_claims = authorized_ids | boundary_ids
    for finding in findings:
        if len(finding.evidence_claim_ids) != len(set(finding.evidence_claim_ids)) or not set(finding.evidence_claim_ids) <= known_claims:
            _issue(out, "REVIEW_FINDING_CLAIM_IDS", "review.findings", "finding claim references must be unique and known")
        start = finding.location.get("start_line", 0)
        end = finding.location.get("end_line", 0)
        if start < 1 or end < start:
            _issue(out, "REVIEW_FINDING_LINE_RANGE", "review.findings", "invalid line range")
        if finding.action is ReviewAction.LOCAL_REPAIR and not finding.repaired_text:
            _issue(out, "LOCAL_REPAIR_TEXT_REQUIRED", "review.findings", "LOCAL_REPAIR requires repaired_text")
    if review.review_verdict is ReviewVerdict.PASS:
        if not review.final_text:
            _issue(out, "REVIEW_MISSING_FINAL_TEXT", "review", "PASS requires final_text")
        if any(finding.action is ReviewAction.RETURN_TO_WRITER for finding in findings):
            _issue(out, "REVIEW_VERDICT_CONFLICT", "review", "PASS cannot have RETURN_TO_WRITER finding")
    elif review.review_verdict is ReviewVerdict.LOCAL_REPAIR:
        if not review.final_text:
            _issue(out, "REVIEW_MISSING_FINAL_TEXT", "review", "LOCAL_REPAIR requires final_text")
        if not any(finding.action is ReviewAction.LOCAL_REPAIR for finding in findings):
            _issue(out, "LOCAL_REPAIR_FINDING_REQUIRED", "review", "LOCAL_REPAIR requires repair finding")
    else:
        if not review.return_reason:
            _issue(out, "RETURN_MISSING_REASON", "review", "RETURN_TO_WRITER requires return_reason")
        if not any(finding.action is ReviewAction.RETURN_TO_WRITER for finding in findings):
            _issue(out, "RETURN_FINDING_REQUIRED", "review", "RETURN_TO_WRITER requires matching finding")
    return out


def ensure_bundle_valid(bundle: EvidenceWriterBundle) -> None:
    violations = validate_bundle(bundle)
    if violations:
        formatted = "; ".join(f"{item.code}@{item.path}" for item in violations)
        raise ValueError(formatted)
