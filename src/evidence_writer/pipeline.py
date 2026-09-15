"""Thin, fail-closed orchestration for the frozen Contract stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from pydantic import ValidationError

from .contracts import (
    ArtifactEnvelope,
    ArtifactType,
    CapabilityRegistrySnapshot,
    DraftArtifact,
    ReviewResult,
    ReviewVerdict,
    Stage,
    StageResult,
    StageStatus,
)
from .policies import PolicyViolation, validate_contract_data
from .providers.base import ProviderError
from .review_acceptance import validate_review_acceptance
from .serialization import to_contract_json
from .storage import FilesystemStorage, StorageError


class StageHandler(Protocol):
    def run(self, input_artifact: ArtifactEnvelope) -> StageResult:
        ...


@dataclass(frozen=True)
class PipelineRunResult:
    status: str
    stage: str | None
    error_code: str | None
    stage_results: Mapping[Stage, StageResult]
    artifact_paths: Mapping[str, str] = field(default_factory=dict)


_STAGE_ORDER = (Stage.AUDITOR, Stage.ADAPTER, Stage.WRITER, Stage.FINAL_REVIEW)
_RESULT_KEYS = {
    Stage.AUDITOR: "auditor_result",
    Stage.ADAPTER: "adapter_result",
    Stage.WRITER: "writer_result",
    Stage.FINAL_REVIEW: "final_review_result",
}
_FILENAMES = {
    Stage.AUDITOR: "01_writer_handoff.json",
    Stage.ADAPTER: "02_writer_input.json",
    Stage.WRITER: "03_draft.json",
    Stage.FINAL_REVIEW: "04_review.json",
}


def _blocked(stage: Stage, upstream_status: str = "NOT_EXECUTED") -> StageResult:
    return StageResult.model_validate(
        {
            "stage": stage.value,
            "stage_status": "BLOCKED",
            "error_code": f"UPSTREAM_{upstream_status}",
            "reason": "an upstream stage did not produce a validated PASS artifact",
        }
    )


def _failed(
    stage: Stage,
    code: str,
    reason: str,
    *,
    violations: list[PolicyViolation] | None = None,
) -> StageResult:
    data: dict[str, Any] = {
        "stage": stage.value,
        "stage_status": "FAIL",
        "error_code": code,
        "reason": reason,
    }
    if violations:
        data["diagnostic"] = {
            "violations": [
                {"code": item.code, "path": item.path, "message": item.message}
                for item in violations
            ]
        }
    return StageResult.model_validate(data)


def _bundle_data(
    research: ArtifactEnvelope,
    registry: CapabilityRegistrySnapshot,
    results: Mapping[Stage, StageResult],
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "research_artifact_envelope": to_contract_json(research),
        "capability_registry_snapshot": to_contract_json(registry),
    }
    for stage in _STAGE_ORDER:
        data[_RESULT_KEYS[stage]] = to_contract_json(
            results.get(stage, _blocked(stage))
        )
    return data


class PipelineRunner:
    """Orchestrate injected handlers without owning stage business rules."""

    def __init__(
        self,
        handlers: Mapping[Stage, StageHandler],
        storage: FilesystemStorage,
    ) -> None:
        self.handlers = dict(handlers)
        self.storage = storage

    def run(
        self,
        research_artifact_envelope: ArtifactEnvelope | dict[str, Any],
        capability_registry_snapshot: CapabilityRegistrySnapshot | dict[str, Any],
    ) -> PipelineRunResult:
        try:
            research = ArtifactEnvelope.model_validate(
                to_contract_json(research_artifact_envelope)
            )
            registry = CapabilityRegistrySnapshot.model_validate(
                to_contract_json(capability_registry_snapshot)
            )
        except (ValidationError, TypeError, ValueError):
            return PipelineRunResult("FAIL", "INPUT", "INPUT_CONTRACT_INVALID", {})

        if research.artifact_type is not ArtifactType.RESEARCH:
            return PipelineRunResult("FAIL", "INPUT", "INPUT_CONTRACT_INVALID", {})

        initial = {stage: _blocked(stage) for stage in _STAGE_ORDER}
        input_violations = validate_contract_data(
            _bundle_data(research, registry, initial)
        )
        if input_violations:
            return PipelineRunResult("FAIL", "INPUT", "INPUT_CONTRACT_INVALID", {})

        results: dict[Stage, StageResult] = {}
        paths: dict[str, str] = {}
        current_input = research
        terminal_status: StageStatus | None = None
        terminal_stage: Stage | None = None
        terminal_code: str | None = None

        for stage in _STAGE_ORDER:
            final_review: ReviewResult | None = None
            if terminal_status is not None:
                result = _blocked(stage, terminal_status.value)
                results[stage] = result
                continue

            handler = self.handlers.get(stage)
            if handler is None:
                result = _failed(
                    stage,
                    "MISSING_STAGE_HANDLER",
                    "no handler was injected for the stage",
                )
            else:
                try:
                    raw_result = handler.run(current_input)
                    result = StageResult.model_validate(
                        to_contract_json(raw_result)
                    )
                    if result.stage is not stage:
                        result = _failed(
                            stage,
                            "STAGE_RESULT_MISMATCH",
                            "handler returned a result for another stage",
                        )
                except ProviderError as error:
                    result = _failed(stage, error.code, str(error))
                except Exception:
                    result = _failed(
                        stage,
                        "HANDLER_EXCEPTION",
                        "stage handler raised an exception",
                    )

            if result.stage_status is StageStatus.PASS:
                candidate = dict(results)
                candidate[stage] = result
                violations = validate_contract_data(
                    _bundle_data(research, registry, candidate)
                )
                if stage is Stage.FINAL_REVIEW:
                    assert result.artifact_envelope is not None
                    final_review = ReviewResult.model_validate(
                        result.artifact_envelope.artifact
                    )
                    draft = DraftArtifact.model_validate(current_input.artifact)
                    violations.extend(
                        validate_review_acceptance(draft, final_review)
                    )
                if violations:
                    result = _failed(
                        stage,
                        "CONTRACT_POLICY_VIOLATION",
                        "PASS artifact failed Contract or deterministic policy validation",
                        violations=violations,
                    )
                else:
                    assert result.artifact_envelope is not None
                    try:
                        stored = self.storage.write_envelope(
                            _FILENAMES[stage],
                            result.artifact_envelope,
                        )
                        paths[_FILENAMES[stage]] = str(stored.path)
                        if stage is Stage.FINAL_REVIEW:
                            assert final_review is not None
                            if (
                                final_review.review_verdict
                                in {ReviewVerdict.PASS, ReviewVerdict.LOCAL_REPAIR}
                                and final_review.final_text is not None
                            ):
                                final_path = self.storage.write_final(
                                    "final.md", final_review.final_text
                                )
                                paths["final.md"] = str(final_path)
                    except (StorageError, ValidationError, ValueError):
                        result = _failed(
                            stage,
                            "STORAGE_VERIFICATION_FAILED",
                            "artifact persistence or read-back verification failed",
                        )

            results[stage] = result
            if result.stage_status is StageStatus.PASS:
                assert result.artifact_envelope is not None
                current_input = result.artifact_envelope
                if (
                    stage is Stage.FINAL_REVIEW
                    and final_review is not None
                    and final_review.review_verdict is ReviewVerdict.RETURN_TO_WRITER
                ):
                    terminal_status = StageStatus.BLOCKED
                    terminal_stage = stage
                    terminal_code = "FINAL_REVIEW_RETURN_TO_WRITER"
            else:
                terminal_status = result.stage_status
                terminal_stage = stage
                terminal_code = result.error_code

        if terminal_status is None:
            return PipelineRunResult(
                "COMPLETE",
                Stage.FINAL_REVIEW.value,
                None,
                results,
                paths,
            )
        return PipelineRunResult(
            terminal_status.value,
            terminal_stage.value if terminal_stage else None,
            terminal_code,
            results,
            paths,
        )
