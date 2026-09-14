from __future__ import annotations

import json
from pathlib import Path
import unittest

from evidence_writer.canonical import CanonicalizationError, canonical_json, canonical_sha256

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
        self.assertIn("REVIEW_FINDING_LINE_RANGE", violations(data))
