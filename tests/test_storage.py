from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import yaml

from evidence_writer.canonical import canonical_sha256
from evidence_writer.contracts import ArtifactEnvelope
from evidence_writer.storage import FilesystemStorage, StorageError


ROOT = Path(__file__).resolve().parents[1]


def handoff_envelope() -> dict:
    bundle = yaml.safe_load(
        (ROOT / "schema_examples" / "complete_chain.valid.yaml").read_text()
    )
    return deepcopy(bundle["auditor_result"]["artifact_envelope"])


class CorruptingStorage(FilesystemStorage):
    def _read_json(self, target: Path):
        value = super()._read_json(target)
        value["artifact"]["authorized_claims"][0]["text"] = "corrupted after write"
        return value


class StorageTests(unittest.TestCase):
    def test_write_reread_revalidate_and_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = FilesystemStorage(directory)
            stored = storage.write_envelope("01_writer_handoff.json", handoff_envelope())
            reread = json.loads(stored.path.read_text(encoding="utf-8"))
            validated = ArtifactEnvelope.model_validate(reread)
            self.assertEqual(
                canonical_sha256(validated.artifact),
                validated.canonical_json_sha256,
            )
            self.assertEqual(stored.digest, validated.canonical_json_sha256)

    def test_corrupt_readback_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(StorageError):
                CorruptingStorage(directory).write_envelope(
                    "01_writer_handoff.json",
                    handoff_envelope(),
                )

    def test_path_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(StorageError):
                FilesystemStorage(directory).write_envelope(
                    "../artifact.json",
                    handoff_envelope(),
                )


if __name__ == "__main__":
    unittest.main()
