from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

import yaml

from evidence_writer.policies import validate_contract_data

from test_contract_core import finding, load_fixture


ROOT = Path(__file__).resolve().parents[1]


def codes(data: dict) -> set[str]:
    return {item.code for item in validate_contract_data(data)}


def mutate(case_id: str, data: dict) -> str:
    research = data["research_artifact_envelope"]["artifact"]
    handoff = data["auditor_result"]["artifact_envelope"]["artifact"]
    writer_input = data["adapter_result"]["artifact_envelope"]["artifact"]
    review = data["final_review_result"]["artifact_envelope"]["artifact"]
    if case_id == "V012-01-dangling-claim":
        research["claims"][2]["supporting_claim_ids"] = ["C-404"]; return "DANGLING_CLAIM_REF"
    if case_id == "V012-02-cyclic-claim":
        research["claims"][0]["supporting_claim_ids"] = ["C-02"]; research["claims"][1]["supporting_claim_ids"] = ["C-01"]; return "CLAIM_DEPENDENCY_CYCLE"
    if case_id == "V012-03-capability-over-three":
        writer_input["capability_plan"]["selected"] *= 4; return "CAPABILITY_OVER_MAX"
    if case_id == "V012-04-intent-fact-authority":
        writer_input["author_intent"]["fact_authority"] = "FACTS_ALLOWED"; return "INTENT_FACT_AUTHORITY"
    if case_id in {"V012-05-forbidden-authorized", "V013-06-forbidden-matrix-bypass"}:
        handoff["authorized_claims"].append(deepcopy(research["claims"][4])); return "FORBIDDEN_AUTHORIZED"
    if case_id == "V012-06-fake-sha256":
        data["writer_result"]["artifact_envelope"]["canonical_json_sha256"] = "sha256:" + "0" * 64; return "DIGEST_INVALID"
    if case_id == "V012-07-return-without-reason":
        review["review_verdict"] = "RETURN_TO_WRITER"; review["findings"] = [finding("RETURN_TO_WRITER")]; return "RETURN_MISSING_REASON"
    if case_id == "V013-01-top-level-stage-mismatch":
        data["auditor_result"]["stage"] = "WRITER"; return "TOP_LEVEL_STAGE_MISMATCH"
    if case_id == "V013-02-unverified-fact-state":
        research["claims"][0]["verification_status"] = "UNVERIFIED"; return "CLAIM_AUTHORIZATION_MATRIX"
    if case_id == "V013-03-hypothesis-state":
        research["claims"][2]["allowed_use"] = ["state"]; return "CLAIM_AUTHORIZATION_MATRIX"
    if case_id == "V013-04-source-backed-no-source":
        research["claims"][0]["source_ids"] = []; return "CLAIM_AUTHORIZATION_MATRIX"
    if case_id == "V013-05-derived-no-support":
        research["claims"][2]["supporting_claim_ids"] = []; return "CLAIM_AUTHORIZATION_MATRIX"
    if case_id == "V013-07-envelope-schema-version-mismatch":
        data["writer_result"]["artifact_envelope"]["artifact_schema_version"] = "draft-artifact/9.9.9"; return "SCHEMA_VERSION_MISMATCH"
    if case_id == "V013-08-pass-return-finding":
        review["findings"] = [finding("RETURN_TO_WRITER")]; return "REVIEW_VERDICT_CONFLICT"
    if case_id == "V013-09-local-repair-no-text":
        review["review_verdict"] = "LOCAL_REPAIR"; review["findings"] = [finding("LOCAL_REPAIR")]; return "LOCAL_REPAIR_TEXT_REQUIRED"
    if case_id == "V013-10-review-wrong-draft-digest":
        review["reviewed_draft_digest"] = "sha256:" + "0" * 64; return "PROVENANCE_DIGEST_MISMATCH"
    raise AssertionError(f"unhandled fixture: {case_id}")


class NegativeFixtureTests(unittest.TestCase):
    def test_all_declared_negative_fixtures_fail_closed(self) -> None:
        suite = yaml.safe_load((ROOT / "contract_fixtures" / "negative_cases.yaml").read_text())
        cases = suite["cases"]
        self.assertEqual(len(cases), 17)
        for fixture in cases:
            with self.subTest(fixture=fixture["id"]):
                data = deepcopy(load_fixture())
                expected = mutate(fixture["id"], data)
                self.assertEqual(expected, fixture["expect"])
                self.assertIn(expected, codes(data))
