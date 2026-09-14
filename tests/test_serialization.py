from __future__ import annotations

from copy import deepcopy
from datetime import date
from pathlib import Path
import unittest

import yaml

from evidence_writer.canonical import canonical_sha256
from evidence_writer.contracts import ResearchPackage, RightsStatus, Source
from evidence_writer.serialization import to_contract_json


ROOT = Path(__file__).resolve().parents[1]


class SerializationTests(unittest.TestCase):
    def test_model_to_contract_json_and_round_trip(self) -> None:
        source = Source.model_validate(
            {
                "id": "S-01",
                "title": "Synthetic",
                "url": "https://example.invalid/source",
                "published_at": "2026-09-13",
                "accessed_at": "2026-09-14",
                "rights_status": "SYNTHETIC",
            }
        )
        package = ResearchPackage.model_validate(
            {
                "schema_version": "research-package/0.1.3",
                "topic": "Synthetic",
                "sources": [source],
                "claims": [
                    {
                        "id": "C-01",
                        "claim_type": "FACT",
                        "text": "Synthetic fact.",
                        "source_ids": ["S-01"],
                        "supporting_claim_ids": [],
                        "origin": "SOURCE_BACKED",
                        "evidence_level": "PRIMARY",
                        "scope": "synthetic",
                        "allowed_use": ["state"],
                        "verification_status": "VERIFIED",
                        "as_of": "2026-09-14",
                    }
                ],
            }
        )
        wire = to_contract_json(package)
        self.assertIs(type(wire), dict)
        self.assertEqual(wire["sources"][0]["published_at"], "2026-09-13")
        self.assertEqual(wire["sources"][0]["accessed_at"], "2026-09-14")
        self.assertEqual(wire["sources"][0]["url"], "https://example.invalid/source")
        self.assertEqual(wire["sources"][0]["rights_status"], "SYNTHETIC")
        self.assertIs(type(wire["sources"][0]["rights_status"]), str)
        reconstructed = ResearchPackage.model_validate(wire)
        self.assertEqual(reconstructed, package)
        self.assertEqual(to_contract_json(reconstructed), wire)

    def test_direct_date_url_enum_and_nested_model_are_plain_json(self) -> None:
        source = Source.model_validate(
            {
                "id": "S-01",
                "title": "Synthetic",
                "url": "https://example.invalid/source",
                "accessed_at": date(2026, 9, 14),
                "rights_status": RightsStatus.SYNTHETIC,
            }
        )
        wire = to_contract_json({"nested": source})
        self.assertEqual(wire["nested"]["accessed_at"], "2026-09-14")
        self.assertIs(type(wire["nested"]["url"]), str)
        self.assertIs(type(to_contract_json(source.url)), str)
        self.assertIs(type(to_contract_json(RightsStatus.SYNTHETIC)), str)
        self.assertNotIn("published_at", wire["nested"])

    def test_semantically_identical_objects_have_identical_digest(self) -> None:
        data = yaml.safe_load(
            (ROOT / "schema_examples" / "complete_chain.valid.yaml").read_text()
        )["research_artifact_envelope"]["artifact"]
        first = ResearchPackage.model_validate(deepcopy(data))
        reordered = {
            "claims": deepcopy(data["claims"]),
            "sources": deepcopy(data["sources"]),
            "topic": data["topic"],
            "schema_version": data["schema_version"],
        }
        second = ResearchPackage.model_validate(reordered)
        self.assertEqual(canonical_sha256(first), canonical_sha256(second))


if __name__ == "__main__":
    unittest.main()
