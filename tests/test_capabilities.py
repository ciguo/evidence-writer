from __future__ import annotations

import json
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
