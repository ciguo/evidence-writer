from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import unittest
from unittest.mock import patch

import yaml

from evidence_writer.capabilities import CAPABILITY_REGISTRY, CAPABILITY_REGISTRY_VERSION
from evidence_writer.cli import main
from evidence_writer.contracts import AuthorIntent, CapabilityRegistrySnapshot, ResearchPackage
from evidence_writer.providers import ProviderError


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "flu_prevention.yaml"
SOURCE_URL = (
    "https://service.cpma.org.cn/sci/#/hotspotDetail?"
    "articleId=9da18f4270cc4ca98a731c871288d535&code=topic"
)
EXPECTED_FACTS = [
    "一般情况下排毒期平均约5天；低龄儿童、住院重症患者和免疫功能低下者的排毒时间通常更长，婴幼儿可延长至1至3周。",
    "文中优先推荐的重点和高风险人群包括养老机构、长期护理机构、福利院等聚集场所的居住人员及工作人员；该项内容仅限2025—2026流感季指南范围。",
    "流感疫苗通常需要在接种后2至4周才能产生具有保护水平的抗体。",
]
EXPECTED_LIMIT = (
    "该材料属于单一 LINK_ONLY 二手科普来源，无法独立核实 "
    "2026—2027 流感季疫苗供应及国家免费接种政策。"
)
RESULT_KEYS = {
    "auditor_result",
    "adapter_result",
    "writer_result",
    "final_review_result",
}


class PublicSourceExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
        cls.research = cls.data["research_package"]
        cls.claims = {claim["id"]: claim for claim in cls.research["claims"]}

    def test_is_run_llm_input_without_prebuilt_stage_results(self) -> None:
        self.assertTrue(RESULT_KEYS.isdisjoint(self.data))
        self.assertEqual(
            set(self.data),
            {"run_id", "output_dir", "research_package", "author_intent", "capability_registry_snapshot"},
        )

    def test_official_run_llm_input_models_accept_example(self) -> None:
        ResearchPackage.model_validate(self.data["research_package"])
        AuthorIntent.model_validate(self.data["author_intent"])
        CapabilityRegistrySnapshot.model_validate(self.data["capability_registry_snapshot"])

    def test_run_llm_parses_before_mocked_provider_boundary(self) -> None:
        error = ProviderError("OFFLINE_TEST", "no provider call", provider="test")
        output = StringIO()
        with patch("evidence_writer.cli.OpenAIResponsesProvider", side_effect=error) as provider, redirect_stdout(output):
            code = main(["run-llm", str(EXAMPLE)])
        self.assertEqual(code, 1)
        provider.assert_called_once_with()
        self.assertIn("stage=PROVIDER", output.getvalue())
        self.assertIn("error_code=OFFLINE_TEST", output.getvalue())

    def test_registry_snapshot_exactly_matches_runtime(self) -> None:
        snapshot = self.data["capability_registry_snapshot"]
        self.assertEqual(snapshot["registry_version"], CAPABILITY_REGISTRY_VERSION)
        self.assertEqual(snapshot["capability_ids"], list(CAPABILITY_REGISTRY))

    def test_fact_text_is_exact(self) -> None:
        facts = [claim["text"] for claim in self.research["claims"] if claim["claim_type"] == "FACT"]
        self.assertEqual(facts, EXPECTED_FACTS)

    def test_forbidden_is_supported_by_limit(self) -> None:
        limit_claim = self.claims["C-04"]
        forbidden_claim = self.claims["C-05"]
        self.assertEqual(limit_claim["text"], EXPECTED_LIMIT)
        self.assertEqual(forbidden_claim["supporting_claim_ids"], [limit_claim["id"]])
        self.assertIn("已经核实的事实或现行国家政策", forbidden_claim["text"])

    def test_source_url_and_rights_are_exact(self) -> None:
        self.assertEqual(len(self.research["sources"]), 1)
        self.assertEqual(str(self.research["sources"][0]["url"]), SOURCE_URL)
        self.assertEqual(self.research["sources"][0]["rights_status"], "LINK_ONLY")

    def test_deprecated_transcription_language_is_absent(self) -> None:
        combined = "\n".join(((ROOT / "README.md").read_text(encoding="utf-8"), EXAMPLE.read_text(encoding="utf-8")))
        for phrase in ("用户转写", "识别错误", "静默修复"):
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, combined)


if __name__ == "__main__":
    unittest.main()
