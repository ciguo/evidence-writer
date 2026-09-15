from __future__ import annotations

from pathlib import Path
import unittest

import yaml

from evidence_writer.contracts import ArtifactEnvelope, ReviewResult, WriterInput
from evidence_writer.llm_stages import FinalReviewHandler, RunContext
from evidence_writer.providers import FakeProvider


ROOT = Path(__file__).resolve().parents[1]


def _inputs() -> tuple[WriterInput, ArtifactEnvelope, str]:
    bundle = yaml.safe_load(
        (ROOT / "schema_examples" / "complete_chain.valid.yaml").read_text(
            encoding="utf-8"
        )
    )
    writer_input = WriterInput.model_validate(
        bundle["adapter_result"]["artifact_envelope"]["artifact"]
    )
    draft_envelope = ArtifactEnvelope.model_validate(
        bundle["writer_result"]["artifact_envelope"]
    )
    draft_text = draft_envelope.artifact["draft_markdown"]
    return writer_input, draft_envelope, draft_text


def _review(structured: dict) -> ReviewResult:
    writer_input, draft_envelope, _ = _inputs()
    provider = FakeProvider(structured=structured)
    result = FinalReviewHandler(
        provider,
        "offline",
        RunContext(writer_input=writer_input),
    ).run(draft_envelope)
    return ReviewResult.model_validate(result.artifact_envelope.artifact)


class FinalReviewAcceptanceTests(unittest.TestCase):
    def test_pass_requires_final_text_to_equal_draft(self) -> None:
        _, _, draft_text = _inputs()
        review = _review(
            {
                "review_verdict": "PASS",
                "findings": [],
                "final_text": draft_text,
                "return_reason": "",
            }
        )
        self.assertEqual(review.final_text, draft_text)

        with self.assertRaisesRegex(ValueError, "PASS final_text"):
            _review(
                {
                    "review_verdict": "PASS",
                    "findings": [],
                    "final_text": draft_text + " 新增的外部事实。",
                    "return_reason": "",
                }
            )

    def test_local_repair_is_recomputed_from_declared_deletion(self) -> None:
        _, _, draft_text = _inputs()
        original = "设计必然带来什么后果"
        repaired = "设计"
        expected = draft_text.replace(original, repaired)
        review = _review(
            {
                "review_verdict": "LOCAL_REPAIR",
                "findings": [
                    {
                        "finding_type": "CAUSALITY",
                        "location": {"start_line": 1, "end_line": 1},
                        "original_text": original,
                        "evidence_claim_ids": [],
                        "action": "LOCAL_REPAIR",
                        "repaired_text": repaired,
                        "reason": "删除未经授权的因果断言。",
                    }
                ],
                "final_text": expected,
                "return_reason": "",
            }
        )
        self.assertEqual(review.final_text, expected)

    def test_local_repair_cannot_add_words_or_replace_other_text(self) -> None:
        _, _, draft_text = _inputs()
        base = {
            "review_verdict": "LOCAL_REPAIR",
            "findings": [
                {
                    "finding_type": "CAUSALITY",
                    "location": {"start_line": 1, "end_line": 1},
                    "original_text": "设计必然带来什么后果",
                    "evidence_claim_ids": [],
                    "action": "LOCAL_REPAIR",
                    "repaired_text": "设计已经改善核对效率",
                    "reason": "非法增加事实。",
                }
            ],
            "final_text": draft_text.replace(
                "设计必然带来什么后果", "设计已经改善核对效率"
            ),
            "return_reason": "",
        }
        with self.assertRaisesRegex(ValueError, "deletion-only"):
            _review(base)

        base["findings"][0]["repaired_text"] = "设计"
        base["final_text"] = draft_text + " 任意重写。"
        with self.assertRaisesRegex(ValueError, "deterministic local repairs"):
            _review(base)


if __name__ == "__main__":
    unittest.main()
