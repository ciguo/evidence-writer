from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
import unittest

from pydantic import ValidationError

from evidence_writer.canonical import CanonicalizationError, canonical_json, canonical_sha256
from evidence_writer.contracts import (
    AuthorIntent,
    CapabilityPlan,
    CapabilityRegistrySnapshot,
    ReviewFinding,
    Source,
)

from test_contract_core import load_fixture, violations


ROOT = Path(__file__).resolve().parents[1]


class PolicyInvariantTests(unittest.TestCase):
    def test_frozen_schema_document_is_valid_json_and_version_aligned(self) -> None:
        schema = json.loads((ROOT / "schema_examples" / "contracts.schema.json").read_text())
        self.assertEqual(schema["$id"], "https://example.invalid/evidence-writer/contracts/0.1.3")
        self.assertIn("v0.1.3", schema["title"])
        self.assertNotIn("0.1.2", json.dumps(schema))

    def test_canonical_json_is_order_independent_and_rejects_float(self) -> None:
        self.assertEqual(canonical_json({"b": 1, "a": "x"}), canonical_json({"a": "x", "b": 1}))
        self.assertEqual(canonical_sha256({"b": 1, "a": "x"}), canonical_sha256({"a": "x", "b": 1}))
        with self.assertRaises(CanonicalizationError):
            canonical_json({"not_in_contract": 1.5})

    def test_unique_ids_and_dangling_source_fail_closed(self) -> None:
        data = load_fixture()
        data["research_artifact_envelope"]["artifact"]["sources"].append(
            data["research_artifact_envelope"]["artifact"]["sources"][0].copy()
        )
        self.assertIn("SOURCE_ID_NOT_UNIQUE", violations(data))
        data = load_fixture()
        data["research_artifact_envelope"]["artifact"]["claims"][0]["source_ids"] = ["S-404"]
        self.assertIn("DANGLING_SOURCE_REF", violations(data))

    def test_capability_registry_and_fact_authority_fail_closed(self) -> None:
        data = load_fixture()
        data["adapter_result"]["artifact_envelope"]["artifact"]["capability_plan"]["selected"][0]["capability_id"] = "unknown"
        self.assertIn("UNKNOWN_CAPABILITY_ID", violations(data))
        data = load_fixture()
        data["adapter_result"]["artifact_envelope"]["artifact"]["capability_plan"]["fact_authority"] = "FACTS_ALLOWED"
        self.assertIn("CAPABILITY_FACT_AUTHORITY", violations(data))

    def test_stage_transition_fails_after_upstream_failure(self) -> None:
        data = load_fixture()
        data["auditor_result"] = {
            "stage": "AUDITOR",
            "stage_status": "FAIL",
            "error_code": "AUDIT_FAILED",
            "reason": "synthetic",
        }
        self.assertIn("INVALID_STAGE_TRANSITION", violations(data))

    def test_review_finding_claim_id_and_line_range_fail_closed(self) -> None:
        data = load_fixture()
        review = data["final_review_result"]["artifact_envelope"]["artifact"]
        review["findings"] = [{
            "finding_type": "EXTERNAL_FACT",
            "location": {"start_line": 4, "end_line": 2},
            "original_text": "x",
            "evidence_claim_ids": ["C-404", "C-404"],
            "action": "FLAG",
            "repaired_text": None,
            "reason": "synthetic",
        }]
        self.assertIn("REVIEW_FINDING_CLAIM_IDS", violations(data))

        data = load_fixture()
        review = data["final_review_result"]["artifact_envelope"]["artifact"]
        review["findings"] = [{
            "finding_type": "EXTERNAL_FACT",
            "location": {"start_line": 4, "end_line": 2},
            "original_text": "x",
            "evidence_claim_ids": ["C-01"],
            "action": "FLAG",
            "repaired_text": None,
            "reason": "synthetic",
        }]
        self.assertIn("REVIEW_FINDING_LINE_RANGE", violations(data))

    def test_embedded_handoff_tampering_fails_closed(self) -> None:
        data = load_fixture()
        upstream = data["auditor_result"]["artifact_envelope"]
        input_envelope = data["adapter_result"]["artifact_envelope"]
        embedded = deepcopy(upstream["artifact"])
        embedded["authorized_claims"][0]["text"] = "tampered but structurally valid claim"
        input_envelope["artifact"]["evidence_handoff"] = embedded
        self.assertEqual(
            input_envelope["artifact"]["input_artifact_digest"],
            upstream["canonical_json_sha256"],
        )
        input_envelope["canonical_json_sha256"] = canonical_sha256(input_envelope["artifact"])
        data["writer_result"] = {
            "stage": "WRITER",
            "stage_status": "BLOCKED",
            "error_code": "STOPPED_FOR_TEST",
            "reason": "adapter output is under test",
        }
        data["final_review_result"] = {
            "stage": "FINAL_REVIEW",
            "stage_status": "BLOCKED",
            "error_code": "UPSTREAM_BLOCKED",
            "reason": "writer was blocked",
        }
        self.assertIn("EMBEDDED_HANDOFF_MISMATCH", violations(data))

    def test_invalid_pass_artifact_is_checked_before_downstream_block(self) -> None:
        data = load_fixture()
        research_claims = data["research_artifact_envelope"]["artifact"]["claims"]
        handoff_envelope = data["auditor_result"]["artifact_envelope"]
        handoff_envelope["artifact"] = deepcopy(handoff_envelope["artifact"])
        handoff_envelope["artifact"]["authorized_claims"].append(deepcopy(research_claims[4]))
        handoff_envelope["canonical_json_sha256"] = canonical_sha256(handoff_envelope["artifact"])
        data["adapter_result"] = {
            "stage": "ADAPTER",
            "stage_status": "BLOCKED",
            "error_code": "UPSTREAM_INVALID",
            "reason": "auditor artifact is invalid",
        }
        data["writer_result"] = {
            "stage": "WRITER",
            "stage_status": "BLOCKED",
            "error_code": "UPSTREAM_BLOCKED",
            "reason": "adapter was blocked",
        }
        data["final_review_result"] = {
            "stage": "FINAL_REVIEW",
            "stage_status": "BLOCKED",
            "error_code": "UPSTREAM_BLOCKED",
            "reason": "writer was blocked",
        }
        self.assertIn("FORBIDDEN_AUTHORIZED", violations(data))

    def test_source_schema_model_parity(self) -> None:
        valid = {
            "id": "S-01",
            "title": "Synthetic",
            "url": "https://example.invalid/source",
            "published_at": "2026-09-13",
            "accessed_at": "2026-09-14",
            "rights_status": "SYNTHETIC",
        }
        Source.model_validate(valid)
        for field, value in (
            ("rights_status", "INVENTED"),
            ("url", "not a uri"),
            ("published_at", "2026-13-99"),
            ("accessed_at", "yesterday"),
        ):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                Source.model_validate({**valid, field: value})

    def test_review_finding_schema_model_parity(self) -> None:
        valid = {
            "finding_type": "EXTERNAL_FACT",
            "location": {"start_line": 1, "end_line": 1},
            "original_text": "x",
            "evidence_claim_ids": ["C-01"],
            "action": "FLAG",
            "reason": "synthetic",
        }
        ReviewFinding.model_validate(valid)
        invalid_cases = [
            {**valid, "finding_type": "OTHER"},
            {**valid, "location": {"start_line": 1}},
            {**valid, "location": {"start_line": 1, "end_line": 1, "column": 2}},
            {**valid, "evidence_claim_ids": ["bad-id"]},
            {**valid, "evidence_claim_ids": ["C-01", "C-01"]},
        ]
        for index, invalid in enumerate(invalid_cases):
            with self.subTest(case=index), self.assertRaises(ValidationError):
                ReviewFinding.model_validate(invalid)

    def test_authority_capability_and_registry_schema_model_parity(self) -> None:
        intent = load_fixture()["adapter_result"]["artifact_envelope"]["artifact"]["author_intent"]
        with self.assertRaises(ValidationError):
            AuthorIntent.model_validate({**intent, "fact_authority": "FACTS_ALLOWED"})

        plan = load_fixture()["adapter_result"]["artifact_envelope"]["artifact"]["capability_plan"]
        with self.assertRaises(ValidationError):
            CapabilityPlan.model_validate({**plan, "fact_authority": "FACTS_ALLOWED"})
        with self.assertRaises(ValidationError):
            CapabilityPlan.model_validate({**plan, "selected": plan["selected"] * 4})

        registry = load_fixture()["capability_registry_snapshot"]
        with self.assertRaises(ValidationError):
            CapabilityRegistrySnapshot.model_validate(
                {**registry, "capability_ids": ["duplicate", "duplicate"]}
            )
