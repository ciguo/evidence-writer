from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

import yaml

from evidence_writer.canonical import canonical_sha256
from evidence_writer.contracts import EvidenceWriterBundle
from evidence_writer.policies import validate_bundle


ROOT = Path(__file__).resolve().parents[1]


def load_fixture() -> dict:
    return yaml.safe_load((ROOT / "schema_examples" / "complete_chain.valid.yaml").read_text())


def violations(data: dict) -> set[str]:
    bundle = EvidenceWriterBundle.model_validate(data)
    return {item.code for item in validate_bundle(bundle)}


def finding(action: str) -> dict:
    return {
        "finding_type": "EXTERNAL_FACT",
        "location": {"start_line": 1, "end_line": 1},
        "original_text": "synthetic text",
        "evidence_claim_ids": ["C-01"],
        "action": action,
        "repaired_text": None,
        "reason": "synthetic fixture",
    }


class ContractCoreTests(unittest.TestCase):
    def test_valid_fixture_passes(self) -> None:
        self.assertEqual(violations(load_fixture()), set())

    def test_empty_boundary_passes_after_chain_recalculation(self) -> None:
        data = load_fixture()
        research = data["research_artifact_envelope"]
        handoff = data["auditor_result"]["artifact_envelope"]
        writer_input = data["adapter_result"]["artifact_envelope"]
        draft = data["writer_result"]["artifact_envelope"]
        review = data["final_review_result"]["artifact_envelope"]
        handoff["artifact"]["boundary_claims"] = []
        handoff["canonical_json_sha256"] = canonical_sha256(handoff["artifact"])
        writer_input["artifact"]["input_artifact_digest"] = handoff["canonical_json_sha256"]
        writer_input["artifact"]["evidence_handoff"] = handoff["artifact"]
        writer_input["canonical_json_sha256"] = canonical_sha256(writer_input["artifact"])
        draft["artifact"]["input_artifact_digest"] = writer_input["canonical_json_sha256"]
        draft["canonical_json_sha256"] = canonical_sha256(draft["artifact"])
        review["artifact"]["reviewed_draft_digest"] = draft["canonical_json_sha256"]
        review["canonical_json_sha256"] = canonical_sha256(review["artifact"])
        self.assertEqual(violations(data), set())
        self.assertTrue(research["canonical_json_sha256"].startswith("sha256:"))

    def test_failure_stage_without_artifact_is_allowed(self) -> None:
        data = load_fixture()
        data["writer_result"] = {
            "stage": "WRITER",
            "stage_status": "FAIL",
            "error_code": "MODEL_DOWN",
            "reason": "synthetic provider failure",
        }
        # Later result is deliberately blocked, which is the only legal
        # transition after a stage failure.
        data["final_review_result"] = {
            "stage": "FINAL_REVIEW",
            "stage_status": "BLOCKED",
            "error_code": "UPSTREAM_FAILED",
            "reason": "writer did not produce a draft",
        }
        self.assertEqual(violations(data), set())

    def test_failure_stage_with_artifact_fails_closed(self) -> None:
        data = load_fixture()
        data["writer_result"]["stage_status"] = "FAIL"
        data["writer_result"]["error_code"] = "MODEL_DOWN"
        data["writer_result"]["reason"] = "synthetic provider failure"
        self.assertIn("FAILED_STAGE_HAS_ARTIFACT", violations(data))
