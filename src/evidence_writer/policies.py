"""Deterministic validation for Architecture/Contracts v0.1.3."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from .canonical import canonical_sha256
from .contracts import (
    AllowedUse, ArtifactEnvelope, ArtifactType, Claim, ClaimOrigin, ClaimType,
    EvidenceWriterBundle, Stage, StageStatus, VerificationStatus,
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


def _schema_violations(error: ValidationError) -> list[PolicyViolation]:
    """Translate strict Contract-model rejection into stable fail-closed codes."""
    code_by_error_type = {
        "claim_authorization_matrix": "CLAIM_AUTHORIZATION_MATRIX",
        "forbidden_authorized": "FORBIDDEN_AUTHORIZED",
        "invalid_boundary_claim": "INVALID_BOUNDARY_CLAIM",
        "review_finding_claim_ids": "REVIEW_FINDING_CLAIM_IDS",
        "local_repair_text_required": "LOCAL_REPAIR_TEXT_REQUIRED",
        "review_missing_final_text": "REVIEW_MISSING_FINAL_TEXT",
        "review_verdict_conflict": "REVIEW_VERDICT_CONFLICT",
        "local_repair_finding_required": "LOCAL_REPAIR_FINDING_REQUIRED",
        "return_missing_reason": "RETURN_MISSING_REASON",
        "return_finding_required": "RETURN_FINDING_REQUIRED",
        "schema_version_mismatch": "SCHEMA_VERSION_MISMATCH",
        "artifact_type_mismatch": "ARTIFACT_TYPE_MISMATCH",
        "pass_missing_artifact": "PASS_MISSING_ARTIFACT",
        "failed_stage_has_artifact": "FAILED_STAGE_HAS_ARTIFACT",
        "failed_stage_missing_reason": "FAILED_STAGE_MISSING_REASON",
        "capability_registry_ids_not_unique": "CAPABILITY_REGISTRY_IDS_NOT_UNIQUE",
    }
    out: list[PolicyViolation] = []
    for item in error.errors(include_url=False):
        path = ".".join(str(part) for part in item["loc"]) or "$"
        error_type = item["type"]
        code = code_by_error_type.get(error_type)
        if code is None and path.endswith("stage") and error_type == "literal_error":
            code = "TOP_LEVEL_STAGE_MISMATCH"
        elif code is None and path.endswith("author_intent.fact_authority"):
            code = "INTENT_FACT_AUTHORITY"
        elif code is None and path.endswith("capability_plan.fact_authority"):
            code = "CAPABILITY_FACT_AUTHORITY"
        elif code is None and path.endswith("capability_plan.selected") and error_type == "too_long":
            code = "CAPABILITY_OVER_MAX"
        if code is None:
            code = "SCHEMA_VALIDATION_FAILED"
        _issue(out, code, path, item["msg"])
    return out


def validate_contract_data(data: dict[str, Any]) -> list[PolicyViolation]:
    """Authoritative Contract ingress: strict model validation, then policy."""
    try:
        bundle = EvidenceWriterBundle.model_validate(data)
    except ValidationError as error:
        return _schema_violations(error)
    return validate_bundle(bundle)


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

    handoff = None
    writer_input = None
    draft = None
    review = None
    authorized_ids: set[str] = set()
    boundary_ids: set[str] = set()

    # Every PASS artifact is validated independently.  A downstream BLOCKED
    # result never suppresses validation of an upstream artifact that exists.
    if bundle.auditor_result.stage_status is StageStatus.PASS:
        handoff_env = bundle.auditor_result.artifact_envelope
        assert handoff_env is not None
        handoff = WriterHandoff.model_validate(handoff_env.artifact)
        if handoff.input_artifact_digest != research_env.canonical_json_sha256:
            _issue(out, "PROVENANCE_DIGEST_MISMATCH", "writer_handoff.input_artifact_digest", "must equal research envelope digest")
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

    if bundle.adapter_result.stage_status is StageStatus.PASS:
        input_env = bundle.adapter_result.artifact_envelope
        assert input_env is not None
        writer_input = WriterInput.model_validate(input_env.artifact)
        if handoff is not None:
            handoff_env = bundle.auditor_result.artifact_envelope
            assert handoff_env is not None
            if writer_input.input_artifact_digest != handoff_env.canonical_json_sha256:
                _issue(out, "PROVENANCE_DIGEST_MISMATCH", "writer_input.input_artifact_digest", "must equal handoff envelope digest")
            embedded_handoff = input_env.artifact["evidence_handoff"]
            if canonical_sha256(embedded_handoff) != handoff_env.canonical_json_sha256:
                _issue(
                    out,
                    "EMBEDDED_HANDOFF_MISMATCH",
                    "writer_input.evidence_handoff",
                    "embedded handoff must exactly match the upstream handoff artifact",
                )
        registry = set(bundle.capability_registry_snapshot.capability_ids)
        if writer_input.capability_plan.registry_version != bundle.capability_registry_snapshot.registry_version:
            _issue(out, "CAPABILITY_REGISTRY_VERSION_MISMATCH", "capability_plan", "registry version differs")
        for item in writer_input.capability_plan.selected:
            if item.capability_id not in registry:
                _issue(out, "UNKNOWN_CAPABILITY_ID", "capability_plan.selected", "capability absent from registry")

    if bundle.writer_result.stage_status is StageStatus.PASS:
        draft_env = bundle.writer_result.artifact_envelope
        assert draft_env is not None
        draft = DraftArtifact.model_validate(draft_env.artifact)
        input_env = bundle.adapter_result.artifact_envelope
        if input_env is not None and draft.input_artifact_digest != input_env.canonical_json_sha256:
            _issue(out, "PROVENANCE_DIGEST_MISMATCH", "draft.input_artifact_digest", "must equal writer input envelope digest")

    if bundle.final_review_result.stage_status is StageStatus.PASS:
        review_env = bundle.final_review_result.artifact_envelope
        assert review_env is not None
        review = ReviewResult.model_validate(review_env.artifact)
        draft_env = bundle.writer_result.artifact_envelope
        if draft_env is not None and review.reviewed_draft_digest != draft_env.canonical_json_sha256:
            _issue(out, "PROVENANCE_DIGEST_MISMATCH", "review.reviewed_draft_digest", "must equal draft envelope digest")
        findings = review.findings
        known_claims = authorized_ids | boundary_ids
        for finding in findings:
            if not set(finding.evidence_claim_ids) <= known_claims:
                _issue(out, "REVIEW_FINDING_CLAIM_IDS", "review.findings", "finding claim references must be unique and known")
            if finding.location.end_line < finding.location.start_line:
                _issue(out, "REVIEW_FINDING_LINE_RANGE", "review.findings", "invalid line range")
    return out


def ensure_bundle_valid(bundle: EvidenceWriterBundle) -> None:
    violations = validate_bundle(bundle)
    if violations:
        formatted = "; ".join(f"{item.code}@{item.path}" for item in violations)
        raise ValueError(formatted)


def ensure_contract_data_valid(data: dict[str, Any]) -> EvidenceWriterBundle:
    violations = validate_contract_data(data)
    if violations:
        formatted = "; ".join(f"{item.code}@{item.path}" for item in violations)
        raise ValueError(formatted)
    return EvidenceWriterBundle.model_validate(data)
