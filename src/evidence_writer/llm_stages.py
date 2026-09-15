"""Authorized real-model implementations for the four frozen stages."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from .canonical import canonical_sha256
from .contracts import (
    ArtifactEnvelope,
    ArtifactType,
    AuthorIntent,
    CapabilityPlan,
    CapabilityRegistrySnapshot,
    DraftArtifact,
    ResearchPackage,
    ReviewResult,
    Stage,
    StageResult,
    WriterHandoff,
    WriterInput,
)
from .providers import LLMProvider
from .serialization import to_contract_json


def _object(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _envelope(artifact_type: ArtifactType, artifact: Any) -> ArtifactEnvelope:
    data = to_contract_json(artifact)
    return ArtifactEnvelope.model_validate(
        {
            "artifact_type": artifact_type.value,
            "artifact_schema_version": data["schema_version"],
            "canonical_json_sha256": canonical_sha256(data),
            "artifact": data,
        }
    )


def _pass(stage: Stage, envelope: ArtifactEnvelope) -> StageResult:
    return StageResult(stage=stage, stage_status="PASS", artifact_envelope=envelope)


def _prompt(provider: LLMProvider, model: str, system: str, value: Any, schema: dict[str, Any]):
    response = provider.generate(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(to_contract_json(value), ensure_ascii=False)},
        ],
        model=model,
        temperature=0,
        response_schema=schema,
    )
    return response


@dataclass
class RunContext:
    writer_input: WriterInput | None = None


class AuditorHandler:
    def __init__(self, provider: LLMProvider, model: str) -> None:
        self.provider, self.model = provider, model

    def run(self, input_artifact: ArtifactEnvelope) -> StageResult:
        research = ResearchPackage.model_validate(input_artifact.artifact)
        schema = _object(
            {
                "authorized_claim_ids": {"type": "array", "items": {"type": "string"}},
                "boundary_claim_ids": {"type": "array", "items": {"type": "string"}},
            },
            ["authorized_claim_ids", "boundary_claim_ids"],
        )
        response = _prompt(
            self.provider,
            self.model,
            "Audit only the supplied ResearchPackage. Put FACT/SIGNAL/HYPOTHESIS IDs in authorized_claim_ids and LIMIT/FORBIDDEN IDs in boundary_claim_ids. Include every claim exactly once. Never alter or invent evidence.",
            research,
            schema,
        )
        result = response.structured
        by_id = {claim.id: claim for claim in research.claims}
        authorized_ids = result["authorized_claim_ids"]
        boundary_ids = result["boundary_claim_ids"]
        if set(authorized_ids) | set(boundary_ids) != set(by_id) or set(authorized_ids) & set(boundary_ids):
            raise ValueError("auditor did not partition the supplied claims")
        handoff = WriterHandoff(
            schema_version="writer-handoff/0.1.3",
            input_artifact_digest=input_artifact.canonical_json_sha256,
            evidence_authority="WRITER_HANDOFF_ONLY",
            sources=research.sources,
            authorized_claims=[by_id[item] for item in authorized_ids],
            boundary_claims=[by_id[item] for item in boundary_ids],
        )
        return _pass(Stage.AUDITOR, _envelope(ArtifactType.HANDOFF, handoff))


class AdapterHandler:
    def __init__(self, provider: LLMProvider, model: str, intent: AuthorIntent, registry: CapabilityRegistrySnapshot) -> None:
        self.provider, self.model, self.intent, self.registry = provider, model, intent, registry

    def run(self, input_artifact: ArtifactEnvelope) -> StageResult:
        handoff = WriterHandoff.model_validate(input_artifact.artifact)
        selection = _object(
            {key: {"type": "string"} for key in ("capability_id", "objective", "execution_directive", "skip_if", "success_check")},
            ["capability_id", "objective", "execution_directive", "skip_if", "success_check"],
        )
        schema = _object({"selected": {"type": "array", "items": selection, "maxItems": 3}}, ["selected"])
        response = _prompt(
            self.provider,
            self.model,
            "Adapt the supplied handoff and author intent into at most three writing capabilities. Select only IDs in capability_ids. Intent has no fact authority; do not add evidence.",
            {"writer_handoff": handoff, "author_intent": self.intent, "capability_ids": self.registry.capability_ids},
            schema,
        )
        if any(item["capability_id"] not in self.registry.capability_ids for item in response.structured["selected"]):
            raise ValueError("adapter selected an unregistered capability")
        plan = CapabilityPlan(
            schema_version="capability-plan/0.1.3",
            registry_version=self.registry.registry_version,
            fact_authority="NONE",
            selected=response.structured["selected"],
        )
        writer_input = WriterInput(
            schema_version="writer-input/0.1.3",
            input_artifact_digest=input_artifact.canonical_json_sha256,
            evidence_handoff=handoff,
            author_intent=self.intent,
            capability_plan=plan,
        )
        return _pass(Stage.ADAPTER, _envelope(ArtifactType.INPUT, writer_input))


class WriterHandler:
    def __init__(self, provider: LLMProvider, model: str, context: RunContext) -> None:
        self.provider, self.model, self.context = provider, model, context

    def run(self, input_artifact: ArtifactEnvelope) -> StageResult:
        writer_input = WriterInput.model_validate(input_artifact.artifact)
        self.context.writer_input = writer_input
        schema = _object({"draft_markdown": {"type": "string", "minLength": 1}}, ["draft_markdown"])
        response = _prompt(
            self.provider,
            self.model,
            "Write a concise nonfiction article in Markdown. Your entire and only input is this WriterInput. Use only authorized_claims as factual material, obey boundary_claims, clearly qualify hypotheses, and do not invent facts, scenes, quotations, people, actions, motives, or causality.",
            writer_input,
            schema,
        )
        draft = DraftArtifact(
            schema_version="draft-artifact/0.1.3",
            input_artifact_digest=input_artifact.canonical_json_sha256,
            draft_markdown=response.structured["draft_markdown"],
            generation_metadata={"provider": response.provider, "model": response.model},
        )
        return _pass(Stage.WRITER, _envelope(ArtifactType.DRAFT, draft))


class FinalReviewHandler:
    def __init__(self, provider: LLMProvider, model: str, context: RunContext) -> None:
        self.provider, self.model, self.context = provider, model, context

    def run(self, input_artifact: ArtifactEnvelope) -> StageResult:
        draft = DraftArtifact.model_validate(input_artifact.artifact)
        if self.context.writer_input is None:
            raise ValueError("writer input unavailable")
        finding = _object(
            {
                "finding_type": {"type": "string", "enum": ["EXTERNAL_FACT", "NUMBER_TIME_PLACE", "ACTION", "SCENE", "QUOTE", "GROUP_TRAIT", "PSYCHOLOGY", "MOTIVE", "CAUSALITY", "PROFESSIONAL_JUDGMENT"]},
                "location": _object({"start_line": {"type": "integer", "minimum": 1}, "end_line": {"type": "integer", "minimum": 1}}, ["start_line", "end_line"]),
                "original_text": {"type": "string", "minLength": 1},
                "evidence_claim_ids": {"type": "array", "items": {"type": "string"}},
                "action": {"type": "string", "enum": ["FLAG", "LOCAL_REPAIR", "RETURN_TO_WRITER"]},
                "repaired_text": {"type": "string"},
                "reason": {"type": "string", "minLength": 1},
            },
            ["finding_type", "location", "original_text", "evidence_claim_ids", "action", "repaired_text", "reason"],
        )
        schema = _object(
            {
                "review_verdict": {"type": "string", "enum": ["PASS", "LOCAL_REPAIR", "RETURN_TO_WRITER"]},
                "findings": {"type": "array", "items": finding},
                "final_text": {"type": "string"},
                "return_reason": {"type": "string"},
            },
            ["review_verdict", "findings", "final_text", "return_reason"],
        )
        response = _prompt(
            self.provider,
            self.model,
            "Review the draft only against its WriterInput evidence. You may PASS, make strictly local repairs, or RETURN_TO_WRITER. Never introduce evidence. For PASS use unchanged draft as final_text. Empty strings mean an absent optional field; every LOCAL_REPAIR finding needs repaired_text and every RETURN_TO_WRITER needs a reason.",
            {"writer_input": self.context.writer_input, "draft": draft},
            schema,
        )
        data = dict(response.structured)
        findings = data["findings"]
        for item in findings:
            if not item.get("repaired_text"):
                item.pop("repaired_text", None)
        if not data.get("final_text"):
            data.pop("final_text", None)
        if not data.get("return_reason"):
            data.pop("return_reason", None)
        data.update(schema_version="review-result/0.1.3", reviewed_draft_digest=input_artifact.canonical_json_sha256)
        review = ReviewResult.model_validate(data)
        return _pass(Stage.FINAL_REVIEW, _envelope(ArtifactType.REVIEW, review))
