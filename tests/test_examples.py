from __future__ import annotations

from pathlib import Path
import unittest

import yaml

from evidence_writer.contracts import (
    AuthorIntent,
    CapabilityRegistrySnapshot,
    ClaimType,
    ResearchPackage,
    RightsStatus,
)


ROOT = Path(__file__).resolve().parents[1]


class ExampleInputTests(unittest.TestCase):
    def test_flu_prevention_example_is_valid_and_evidence_bounded(self) -> None:
        data = yaml.safe_load(
            (ROOT / "examples" / "flu_prevention.yaml").read_text(encoding="utf-8")
        )

        research = ResearchPackage.model_validate(data["research_package"])
        intent = AuthorIntent.model_validate(data["author_intent"])
        registry = CapabilityRegistrySnapshot.model_validate(
            data["capability_registry_snapshot"]
        )

        self.assertEqual(research.sources[0].rights_status, RightsStatus.LINK_ONLY)
        self.assertIn(ClaimType.LIMIT, {claim.claim_type for claim in research.claims})
        self.assertIn(ClaimType.FORBIDDEN, {claim.claim_type for claim in research.claims})
        self.assertEqual(intent.fact_authority, "NONE")
        self.assertTrue(registry.capability_ids)


if __name__ == "__main__":
    unittest.main()
