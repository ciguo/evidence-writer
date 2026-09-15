"""Authorized real-model implementations for the four frozen stages."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

from .capabilities import CAPABILITY_REGISTRY, CAPABILITY_REGISTRY_VERSION
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
from .review_acceptance import validate_review_acceptance
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
        runtime_ids = set(CAPABILITY_REGISTRY)
        snapshot_ids = set(self.registry.capability_ids)
        if self.registry.registry_version != CAPABILITY_REGISTRY_VERSION or not snapshot_ids <= runtime_ids:
            raise ValueError("capability snapshot is not supported by the runtime registry")
        allowed_ids = [item for item in self.registry.capability_ids if item in runtime_ids]
        schema = _object(
            {
                "selected_capability_ids": {
                    "type": "array",
                    "items": {"type": "string", "enum": allowed_ids},
                    "maxItems": 3,
                    "uniqueItems": True,
                }
            },
            ["selected_capability_ids"],
        )
        response = _prompt(
            self.provider,
            self.model,
            "Select zero to three capability IDs (one or two by default) from capability_ids. Return IDs only. Do not force a selection. Priority is Evidence Boundary, then Author Intent, then Capability. Respect each capability's trigger and skip_if. Capabilities have no fact authority.",
            {
                "writer_handoff": handoff,
                "author_intent": self.intent,
                "capabilities": [asdict(CAPABILITY_REGISTRY[item]) for item in allowed_ids],
                "capability_ids": allowed_ids,
            },
            schema,
        )
        result = response.structured
        if not isinstance(result, dict) or set(result) != {"selected_capability_ids"}:
            raise ValueError("adapter output must contain selected_capability_ids only")
        selected_ids = result["selected_capability_ids"]
        if (
            not isinstance(selected_ids, list)
            or any(not isinstance(item, str) for item in selected_ids)
            or len(selected_ids) > 3
            or len(set(selected_ids)) != len(selected_ids)
            or any(item not in snapshot_ids or item not in runtime_ids for item in selected_ids)
        ):
            raise ValueError("adapter returned an invalid capability selection")
        selected = []
        for capability_id in selected_ids:
            definition = CAPABILITY_REGISTRY[capability_id]
            selected.append(
                {
                    "capability_id": definition.capability_id,
                    "objective": definition.objective,
                    "execution_directive": definition.execution_directive,
                    "skip_if": definition.skip_if,
                    "success_check": definition.success_check,
                }
            )
        plan = CapabilityPlan(
            schema_version="capability-plan/0.1.3",
            registry_version=CAPABILITY_REGISTRY_VERSION,
            fact_authority="NONE",
            selected=selected,
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
            "Write a concise nonfiction article in Markdown. Your entire and only input is this WriterInput; never seek or use a ResearchPackage. Priority is Evidence Boundary, then Author Intent, then CapabilityPlan. Use only authorized_claims as factual material and obey boundary_claims. Treat execution_directive as a writing action, respect skip_if, and apply success_check silently. Capabilities may influence organization, explanation density, emotional timing, open endings, author stance, process presentation, and action-line placement. They never authorize new facts, numbers, scenes, fabricated actions, psychology or motive claims, causality, institutional intent, or unsupported professional judgments. Clearly qualify hypotheses. Do not expose capability IDs or internal control rules in the prose.",
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


def _normalize_review_output(structured: Any) -> dict[str, Any]:
    if not isinstance(structured, dict):
        raise ValueError("final review output must be an object")
    data = dict(structured)
    findings = data.get("findings")
    if not isinstance(findings, list) or any(
        not isinstance(item, dict) for item in findings
    ):
        raise ValueError("final review findings must be objects")
    data["findings"] = [dict(item) for item in findings]
    for item in data["findings"]:
        if not item.get("repaired_text"):
            item.pop("repaired_text", None)
    if not data.get("final_text"):
        data.pop("final_text", None)
    if not data.get("return_reason"):
        data.pop("return_reason", None)
    return data


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
            "Review the draft only against its WriterInput evidence. Never introduce evidence. PASS requires no findings and final_text exactly equal to the draft. LOCAL_REPAIR is deletion-only: repaired_text must be a non-empty exact substring of original_text, and final_text must equal the draft after applying every declared repair at its exact line location. If repair needs any new word or broader rewriting, RETURN_TO_WRITER. For RETURN_TO_WRITER use empty final_text and provide a matching finding and reason. Empty strings mean an absent optional field.",
            {"writer_input": self.context.writer_input, "draft": draft},
            schema,
        )
        data = _normalize_review_output(response.structured)
        data.update(schema_version="review-result/0.1.3", reviewed_draft_digest=input_artifact.canonical_json_sha256)
        review = ReviewResult.model_validate(data)
        violations = validate_review_acceptance(draft, review)
        if violations:
            raise ValueError(
                "; ".join(f"{item.code}: {item.message}" for item in violations)
            )
        return _pass(Stage.FINAL_REVIEW, _envelope(ArtifactType.REVIEW, review))
