from __future__ import annotations

from pathlib import Path
import unittest

import yaml

from evidence_writer.capabilities import CAPABILITY_REGISTRY, CAPABILITY_REGISTRY_VERSION
from evidence_writer.policies import validate_contract_data


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "flu_prevention.yaml"
EXPECTED_FACTS = [
    "住院重症患者",
    "养老机构、长期护理机构、福利院等聚集场所的居住人员及工作人员",
    "接种后2至4周产生具有保护水平的抗体",
]
EXPECTED_LIMIT = (
    "该材料属于单一 LINK_ONLY 二手科普来源，无法独立核实 "
    "2026—2027 流感季疫苗供应及国家免费接种政策。"
)


class PublicSourceExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
        cls.research = cls.data["research_artifact_envelope"]["artifact"]
        cls.claims = {claim["id"]: claim for claim in cls.research["claims"]}

    def test_complete_bundle_passes_deterministic_policy_ingress(self) -> None:
        self.assertEqual(validate_contract_data(self.data), [])

    def test_registry_snapshot_exactly_matches_runtime(self) -> None:
        snapshot = self.data["capability_registry_snapshot"]
        self.assertEqual(snapshot["registry_version"], CAPABILITY_REGISTRY_VERSION)
        self.assertEqual(snapshot["capability_ids"], list(CAPABILITY_REGISTRY))

    def test_fact_text_is_exact(self) -> None:
        facts = [
            claim["text"]
            for claim in self.research["claims"]
            if claim["claim_type"] == "FACT"
        ]
        self.assertEqual(facts, EXPECTED_FACTS)
        for claim in self.research["claims"]:
            if claim["claim_type"] == "FACT":
                self.assertIn("2025—2026流感季", claim["scope"])

    def test_forbidden_is_supported_by_limit(self) -> None:
        limit_claim = self.claims["C-04"]
        forbidden_claim = self.claims["C-05"]
        self.assertEqual(limit_claim["claim_type"], "LIMIT")
        self.assertEqual(limit_claim["text"], EXPECTED_LIMIT)
        self.assertEqual(forbidden_claim["claim_type"], "FORBIDDEN")
        self.assertEqual(forbidden_claim["supporting_claim_ids"], [limit_claim["id"]])
        self.assertIn("已经核实的事实或现行国家政策", forbidden_claim["text"])

    def test_source_is_link_only(self) -> None:
        self.assertEqual(len(self.research["sources"]), 1)
        self.assertEqual(self.research["sources"][0]["rights_status"], "LINK_ONLY")

    def test_deprecated_transcription_language_is_absent(self) -> None:
        combined = "\n".join(
            [
                (ROOT / "README.md").read_text(encoding="utf-8"),
                EXAMPLE.read_text(encoding="utf-8"),
            ]
        )
        for phrase in ("用户转写", "识别错误", "静默修复"):
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, combined)


if __name__ == "__main__":
    unittest.main()
