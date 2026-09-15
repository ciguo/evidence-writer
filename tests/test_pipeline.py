from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

import yaml

from evidence_writer.canonical import canonical_sha256
from evidence_writer.contracts import Stage, StageResult, StageStatus
from evidence_writer.pipeline import PipelineRunner
from evidence_writer.providers import ProviderError
from evidence_writer.storage import FilesystemStorage


ROOT = Path(__file__).resolve().parents[1]


def load_bundle() -> dict:
    return yaml.safe_load(
        (ROOT / "schema_examples" / "complete_chain.valid.yaml").read_text()
    )


class CountingHandler:
    def __init__(self, result: dict) -> None:
        self.result = deepcopy(result)
        self.calls = 0
        self.inputs = []

    def run(self, input_artifact) -> StageResult:
        self.calls += 1
        self.inputs.append(input_artifact.artifact_type)
        return StageResult.model_validate(deepcopy(self.result))


class RaisingHandler:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    def run(self, input_artifact) -> StageResult:
        self.calls += 1
        raise self.error


def handlers_for(bundle: dict):
    return {
        Stage.AUDITOR: CountingHandler(bundle["auditor_result"]),
        Stage.ADAPTER: CountingHandler(bundle["adapter_result"]),
        Stage.WRITER: CountingHandler(bundle["writer_result"]),
        Stage.FINAL_REVIEW: CountingHandler(bundle["final_review_result"]),
    }


def run_pipeline(bundle: dict, handlers):
    temporary = tempfile.TemporaryDirectory()
    runner = PipelineRunner(handlers, FilesystemStorage(temporary.name))
    result = runner.run(
        bundle["research_artifact_envelope"],
        bundle["capability_registry_snapshot"],
    )
    return temporary, result


class PipelineTests(unittest.TestCase):
    def test_happy_path_persists_all_artifacts_and_final(self) -> None:
        bundle = load_bundle()
        handlers = handlers_for(bundle)
        temporary, result = run_pipeline(bundle, handlers)
        with temporary:
            self.assertEqual(result.status, "COMPLETE")
            self.assertEqual(result.error_code, None)
            self.assertEqual(
                set(result.artifact_paths),
                {
                    "01_writer_handoff.json",
                    "02_writer_input.json",
                    "03_draft.json",
                    "04_review.json",
                    "final.md",
                },
            )
            for path in result.artifact_paths.values():
                self.assertTrue(Path(path).is_file())
            self.assertTrue(Path(result.artifact_paths["final.md"]).read_text())
            self.assertTrue(all(handler.calls == 1 for handler in handlers.values()))

    def test_auditor_fail_stops_all_downstream_handlers(self) -> None:
        bundle = load_bundle()
        bundle["auditor_result"] = {
            "stage": "AUDITOR",
            "stage_status": "FAIL",
            "error_code": "AUDIT_FAILED",
            "reason": "synthetic failure",
        }
        handlers = handlers_for(bundle)
        temporary, result = run_pipeline(bundle, handlers)
        with temporary:
            self.assertEqual(result.status, "FAIL")
            self.assertEqual(result.stage, "AUDITOR")
            self.assertEqual(handlers[Stage.ADAPTER].calls, 0)
            self.assertEqual(handlers[Stage.WRITER].calls, 0)
            self.assertEqual(handlers[Stage.FINAL_REVIEW].calls, 0)
            self.assertTrue(
                all(
                    result.stage_results[stage].stage_status is StageStatus.BLOCKED
                    for stage in (Stage.ADAPTER, Stage.WRITER, Stage.FINAL_REVIEW)
                )
            )

    def test_adapter_blocked_stops_writer_and_review(self) -> None:
        bundle = load_bundle()
        bundle["adapter_result"] = {
            "stage": "ADAPTER",
            "stage_status": "BLOCKED",
            "error_code": "NO_INPUT",
            "reason": "synthetic block",
        }
        handlers = handlers_for(bundle)
        temporary, result = run_pipeline(bundle, handlers)
        with temporary:
            self.assertEqual(result.status, "BLOCKED")
            self.assertEqual(result.stage, "ADAPTER")
            self.assertEqual(handlers[Stage.WRITER].calls, 0)
            self.assertEqual(handlers[Stage.FINAL_REVIEW].calls, 0)

    def test_writer_fail_stops_final_review(self) -> None:
        bundle = load_bundle()
        bundle["writer_result"] = {
            "stage": "WRITER",
            "stage_status": "FAIL",
            "error_code": "WRITE_FAILED",
            "reason": "synthetic failure",
        }
        handlers = handlers_for(bundle)
        temporary, result = run_pipeline(bundle, handlers)
        with temporary:
            self.assertEqual(result.status, "FAIL")
            self.assertEqual(result.stage, "WRITER")
            self.assertEqual(handlers[Stage.FINAL_REVIEW].calls, 0)

    def test_invalid_pass_artifact_stops_downstream(self) -> None:
        bundle = load_bundle()
        handoff = bundle["auditor_result"]["artifact_envelope"]
        handoff["artifact"]["input_artifact_digest"] = "sha256:" + "0" * 64
        handoff["canonical_json_sha256"] = canonical_sha256(handoff["artifact"])
        handlers = handlers_for(bundle)
        temporary, result = run_pipeline(bundle, handlers)
        with temporary:
            self.assertEqual(result.status, "FAIL")
            self.assertEqual(result.error_code, "CONTRACT_POLICY_VIOLATION")
            self.assertEqual(handlers[Stage.ADAPTER].calls, 0)
            codes = {
                item["code"]
                for item in result.stage_results[Stage.AUDITOR].diagnostic["violations"]
            }
            self.assertIn("PROVENANCE_DIGEST_MISMATCH", codes)

    def test_embedded_handoff_tampering_is_rejected_in_runner(self) -> None:
        bundle = load_bundle()
        writer_input = bundle["adapter_result"]["artifact_envelope"]
        embedded = deepcopy(writer_input["artifact"]["evidence_handoff"])
        embedded["authorized_claims"][0]["text"] = "tampered content"
        writer_input["artifact"]["evidence_handoff"] = embedded
        writer_input["canonical_json_sha256"] = canonical_sha256(
            writer_input["artifact"]
        )
        handlers = handlers_for(bundle)
        temporary, result = run_pipeline(bundle, handlers)
        with temporary:
            self.assertEqual(result.status, "FAIL")
            self.assertEqual(result.stage, "ADAPTER")
            self.assertEqual(handlers[Stage.WRITER].calls, 0)
            codes = {
                item["code"]
                for item in result.stage_results[Stage.ADAPTER].diagnostic["violations"]
            }
            self.assertIn("EMBEDDED_HANDOFF_MISMATCH", codes)

    def test_provider_error_is_stage_failure_and_does_not_leak(self) -> None:
        bundle = load_bundle()
        handlers = handlers_for(bundle)
        handlers[Stage.AUDITOR] = RaisingHandler(
            ProviderError(
                "PROVIDER_UNAVAILABLE",
                "provider request unavailable",
                provider="fake",
                retryable=True,
            )
        )
        temporary, result = run_pipeline(bundle, handlers)
        with temporary:
            self.assertEqual(result.status, "FAIL")
            self.assertEqual(result.error_code, "PROVIDER_UNAVAILABLE")
            self.assertEqual(handlers[Stage.ADAPTER].calls, 0)

    def test_return_to_writer_blocks_completion_and_writes_no_final(self) -> None:
        bundle = load_bundle()
        review_envelope = bundle["final_review_result"]["artifact_envelope"]
        review_envelope["artifact"] = {
            "schema_version": "review-result/0.1.3",
            "reviewed_draft_digest": bundle["writer_result"]["artifact_envelope"][
                "canonical_json_sha256"
            ],
            "review_verdict": "RETURN_TO_WRITER",
            "findings": [
                {
                    "finding_type": "EXTERNAL_FACT",
                    "location": {"start_line": 1, "end_line": 1},
                    "original_text": "材料只记录了界面的显示与切换",
                    "evidence_claim_ids": [],
                    "action": "RETURN_TO_WRITER",
                    "reason": "需要 Writer 重新生成，不能局部删除解决。",
                }
            ],
            "return_reason": "发现无法局部修复的经验性断言。",
        }
        review_envelope["canonical_json_sha256"] = canonical_sha256(
            review_envelope["artifact"]
        )
        handlers = handlers_for(bundle)
        temporary, result = run_pipeline(bundle, handlers)
        with temporary:
            self.assertEqual(result.status, "BLOCKED")
            self.assertEqual(result.stage, "FINAL_REVIEW")
            self.assertEqual(result.error_code, "FINAL_REVIEW_RETURN_TO_WRITER")
            self.assertIs(
                result.stage_results[Stage.FINAL_REVIEW].stage_status,
                StageStatus.PASS,
            )
            self.assertIn("04_review.json", result.artifact_paths)
            self.assertNotIn("final.md", result.artifact_paths)

    def test_final_review_pass_rewrite_is_rejected_by_runner(self) -> None:
        bundle = load_bundle()
        review_envelope = bundle["final_review_result"]["artifact_envelope"]
        review_envelope["artifact"]["final_text"] += " 新增的外部事实。"
        review_envelope["canonical_json_sha256"] = canonical_sha256(
            review_envelope["artifact"]
        )
        handlers = handlers_for(bundle)
        temporary, result = run_pipeline(bundle, handlers)
        with temporary:
            self.assertEqual(result.status, "FAIL")
            self.assertEqual(result.stage, "FINAL_REVIEW")
            self.assertEqual(result.error_code, "CONTRACT_POLICY_VIOLATION")
            self.assertNotIn("final.md", result.artifact_paths)
            codes = {
                item["code"]
                for item in result.stage_results[Stage.FINAL_REVIEW].diagnostic[
                    "violations"
                ]
            }
            self.assertIn("PASS_TEXT_CHANGED", codes)


if __name__ == "__main__":
    unittest.main()
