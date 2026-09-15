from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
import unittest

import yaml

from evidence_writer.capabilities import (
    CAPABILITY_REGISTRY,
    CAPABILITY_REGISTRY_VERSION,
)
from evidence_writer.canonical import canonical_sha256
from evidence_writer.contracts import (
    ArtifactEnvelope,
    AuthorIntent,
    CapabilityRegistrySnapshot,
    WriterHandoff,
    WriterInput,
)
from evidence_writer.llm_stages import AdapterHandler, RunContext, WriterHandler
from evidence_writer.providers import FakeProvider


ROOT = Path(__file__).resolve().parents[1]

FROZEN_DEFINITIONS = [
    {
        "capability_id": "CAP-JUDGMENT-ON-MATERIAL",
        "objective": "避免先抛抽象结论，再用材料装饰。",
        "trigger": "现实评论、文化评论、产业/政策题；安全包中已有可观察对象、制度、关系、文本或数据。",
        "execution_directive": "重要判断尽量先落在已授权的具体对象、关系或材料上，再向外延伸；不要新增例子来支撑判断。",
        "skip_if": "安全包没有足够具体材料；文章本身是纯个人感受。",
        "success_check": "判断所指对象清楚；没有新增事实；没有变成“多写细节”。",
        "fact_authority": "NONE",
    },
    {
        "capability_id": "CAP-REDUCE-EXPLANATION",
        "objective": "减少“事实后再解释一遍”的 AI 逻辑水印。",
        "trigger": "facts/judgments already illuminate each other; Writer tends to append summaries/mechanisms/meaning.",
        "execution_directive": "when authorized material already carries judgment, do not add same-meaning explanation; preserve necessary logic, don’t close every paragraph.",
        "skip_if": "medical/policy/professional explanation if omission causes substantive misunderstanding.",
        "success_check": "information intact, logic intact, author judgment still visible.",
        "fact_authority": "NONE",
    },
    {
        "capability_id": "CAP-EMOTION-DELAYED-NAMING",
        "objective": "real emotion without immediately naming/defending/uplifting it.",
        "trigger": "personal experience/memorial/controlled emotion; Author Intent has real emotion; authorized actions/relations/objects/experience position exist.",
        "execution_directive": "let authorized action/relation/waiting/friction/hesitation carry emotion first; direct feeling later if needed; do not justify why feeling is correct.",
        "skip_if": "no real experience; industry/professional explainer; risk key misunderstanding.",
        "success_check": "emotion perceptible but not managed; no fabricated life detail; direct emotion not sterilized.",
        "fact_authority": "NONE",
    },
    {
        "capability_id": "CAP-OPEN-QUESTION",
        "objective": "allow unresolved question; avoid “困境—领悟—升华”.",
        "trigger": "CENTRAL_TENSION lacks sufficient answer; author wants incompleteness.",
        "execution_directive": "if material lacks full answer, leave real unresolved question; do not fabricate conclusion for structural completeness.",
        "skip_if": "explicit explanation/operational guidance/clear judgment required.",
        "success_check": "openness comes from material resistance, not faux profundity; reader still knows topic.",
        "fact_authority": "NONE",
    },
    {
        "capability_id": "CAP-QUIET-ENDING",
        "objective": "avoid summary/uplift/gold-line ending.",
        "trigger": "ENDING_DESTINATION = QUIET_STOP or OPEN_REMAINDER; main judgment done.",
        "execution_directive": "stop near last still-pressurized fact/action/judgment/question; no repeat conclusion; no higher abstraction.",
        "skip_if": "knowledge article needs explicit conclusion/steps/boundary.",
        "success_check": "natural stop; no second uplift.",
        "fact_authority": "NONE",
    },
    {
        "capability_id": "CAP-KNOWLEDGE-AS-PROCESS",
        "objective": "professional knowledge without textbook/terminology display.",
        "trigger": "medicine/tech/consumer/professional explanation; safe package has real phenomena/process/verifiable sequence.",
        "execution_directive": "enter terms/explanation from authorized phenomenon/process/problem, preserving accuracy; knowledge serves current problem.",
        "skip_if": "definition must precede; no process material.",
        "success_check": "object understood before term; no unauthorized “accessible” analogy facts.",
        "fact_authority": "NONE",
    },
    {
        "capability_id": "CAP-BOUNDED-AUTHOR-POSITION",
        "objective": "author judgment/emotion present without expanding fact authority.",
        "trigger": "viewpoint/value judgment; Author Intent has clear stance.",
        "execution_directive": "first-person care/doubt/dislike/delight/irony/respect allowed; external assertions still only from handoff.",
        "skip_if": "pure explainer and author position adds no value.",
        "success_check": "distinguish “作者怎么看” from “外部世界是什么”; “我觉得” not used to package new facts.",
        "fact_authority": "NONE",
    },
    {
        "capability_id": "CAP-FACTS-ON-ACTION-LINE",
        "objective": "dense facts not background manual.",
        "trigger": "safe package has real verified timeline/action/event process.",
        "execution_directive": "attach authorized facts to real action/timeline; institutions/numbers/rules enter with process.",
        "skip_if": "no real action line; only statistical aggregation; requires fabricated scene.",
        "success_check": "facts have position/rhythm; no fabricated scene/interview/dialogue/actions.",
        "fact_authority": "NONE",
    },
]


def _config() -> dict:
    return yaml.safe_load((ROOT / "examples" / "real_minimal.yaml").read_text(encoding="utf-8"))


def _handoff_envelope() -> ArtifactEnvelope:
    config = _config()
    research = config["research_package"]
    claims = {claim["id"]: claim for claim in research["claims"]}
    handoff = WriterHandoff.model_validate(
        {
            "schema_version": "writer-handoff/0.1.3",
            "input_artifact_digest": canonical_sha256(research),
            "evidence_authority": "WRITER_HANDOFF_ONLY",
            "sources": research["sources"],
            "authorized_claims": [claims[item] for item in ("C-01", "C-02", "C-03")],
            "boundary_claims": [claims[item] for item in ("C-04", "C-05")],
        }
    )
    data = handoff.model_dump(mode="json", exclude_none=True)
    return ArtifactEnvelope.model_validate(
        {
            "artifact_type": "WriterHandoff",
            "artifact_schema_version": handoff.schema_version,
            "canonical_json_sha256": canonical_sha256(data),
            "artifact": data,
        }
    )


def _adapter(selected: list[str], *, structured: dict | None = None, ids: list[str] | None = None):
    config = _config()
    intent = AuthorIntent.model_validate(config["author_intent"])
    snapshot_data = dict(config["capability_registry_snapshot"])
    if ids is not None:
        snapshot_data["capability_ids"] = ids
    snapshot = CapabilityRegistrySnapshot.model_validate(snapshot_data)
    provider = FakeProvider(
        structured=structured if structured is not None else {"selected_capability_ids": selected}
    )
    return AdapterHandler(provider, "offline", intent, snapshot).run(_handoff_envelope()), provider


class CapabilityRegistryTests(unittest.TestCase):
    def test_complete_registry_semantics_match_frozen_production_definitions(self) -> None:
        self.assertEqual(
            [asdict(definition) for definition in CAPABILITY_REGISTRY.values()],
            FROZEN_DEFINITIONS,
        )

    def test_registry_contains_exactly_the_eight_production_ids(self) -> None:
        self.assertEqual(
            set(CAPABILITY_REGISTRY),
            {
                "CAP-JUDGMENT-ON-MATERIAL",
                "CAP-REDUCE-EXPLANATION",
                "CAP-EMOTION-DELAYED-NAMING",
                "CAP-OPEN-QUESTION",
                "CAP-QUIET-ENDING",
                "CAP-KNOWLEDGE-AS-PROCESS",
                "CAP-BOUNDED-AUTHOR-POSITION",
                "CAP-FACTS-ON-ACTION-LINE",
            },
        )

    def test_registry_ids_are_unique(self) -> None:
        self.assertEqual(len(CAPABILITY_REGISTRY), len(set(CAPABILITY_REGISTRY)))

    def test_every_definition_has_no_fact_authority(self) -> None:
        self.assertTrue(all(item.fact_authority == "NONE" for item in CAPABILITY_REGISTRY.values()))

    def test_example_snapshot_has_runtime_version_and_all_ids(self) -> None:
        snapshot = _config()["capability_registry_snapshot"]
        self.assertEqual(snapshot["registry_version"], CAPABILITY_REGISTRY_VERSION)
        self.assertEqual(set(snapshot["capability_ids"]), set(CAPABILITY_REGISTRY))


class AdapterCapabilityTests(unittest.TestCase):
    def test_unknown_snapshot_id_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "snapshot"):
            _adapter([], ids=[*CAPABILITY_REGISTRY, "CAP-UNKNOWN"])

    def test_output_contract_requests_ids_only(self) -> None:
        _, provider = _adapter([])
        # FakeProvider accepts the schema but the adapter still validates the exact output shape.
        self.assertEqual(provider.call_count, 1)
        with self.assertRaisesRegex(ValueError, "ids only"):
            _adapter([], structured={"selected_capability_ids": [], "objective": "forbidden"})

    def test_zero_through_three_unique_selections_are_valid(self) -> None:
        ids = list(CAPABILITY_REGISTRY)
        for count in range(4):
            with self.subTest(count=count):
                result, _ = _adapter(ids[:count])
                writer_input = WriterInput.model_validate(result.artifact_envelope.artifact)
                self.assertEqual(len(writer_input.capability_plan.selected), count)

    def test_more_than_three_is_invalid(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid"):
            _adapter(list(CAPABILITY_REGISTRY)[:4])

    def test_duplicate_ids_are_invalid(self) -> None:
        capability_id = next(iter(CAPABILITY_REGISTRY))
        with self.assertRaisesRegex(ValueError, "invalid"):
            _adapter([capability_id, capability_id])

    def test_unknown_selected_id_is_invalid(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid"):
            _adapter(["CAP-UNKNOWN"])

    def test_plan_fields_are_copied_exactly_from_runtime_registry(self) -> None:
        selected_ids = list(CAPABILITY_REGISTRY)[:3]
        result, _ = _adapter(selected_ids)
        plan = WriterInput.model_validate(result.artifact_envelope.artifact).capability_plan
        self.assertEqual(plan.registry_version, CAPABILITY_REGISTRY_VERSION)
        self.assertEqual(plan.fact_authority, "NONE")
        for selection, capability_id in zip(plan.selected, selected_ids, strict=True):
            definition = CAPABILITY_REGISTRY[capability_id]
            self.assertEqual(
                selection.model_dump(),
                {
                    "capability_id": definition.capability_id,
                    "objective": definition.objective,
                    "execution_directive": definition.execution_directive,
                    "skip_if": definition.skip_if,
                    "success_check": definition.success_check,
                },
            )

    def test_model_generated_semantics_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "ids only"):
            _adapter([], structured={"selected": [{"capability_id": next(iter(CAPABILITY_REGISTRY))}]})


class RecordingProvider(FakeProvider):
    def generate(self, messages, **kwargs):
        self.messages = messages
        return super().generate(messages, **kwargs)


class WriterCapabilityTests(unittest.TestCase):
    def test_writer_input_carries_plan_and_is_writer_only_input(self) -> None:
        adapter_result, _ = _adapter([next(iter(CAPABILITY_REGISTRY))])
        provider = RecordingProvider(structured={"draft_markdown": "Bounded draft."})
        context = RunContext()
        WriterHandler(provider, "offline", context).run(adapter_result.artifact_envelope)
        self.assertIsNotNone(context.writer_input)
        self.assertEqual(len(context.writer_input.capability_plan.selected), 1)
        payload = json.loads(provider.messages[1]["content"])
        self.assertEqual(payload["schema_version"], "writer-input/0.1.3")
        self.assertIn("capability_plan", payload)
        self.assertNotIn("research_package", payload)
        self.assertNotIn("ResearchPackage", provider.messages[1]["content"])


if __name__ == "__main__":
    unittest.main()
