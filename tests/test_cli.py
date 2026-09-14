from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

import yaml

from evidence_writer.cli import main


ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_validate_reports_complete(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            code = main(
                ["validate", str(ROOT / "schema_examples" / "complete_chain.valid.yaml")]
            )
        self.assertEqual(code, 0)
        self.assertIn("status=COMPLETE", output.getvalue())
        self.assertIn("stage=VALIDATE", output.getvalue())

    def test_synthetic_run_reports_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "run.yaml"
            config_path.write_text(
                yaml.safe_dump(
                    {
                        "bundle_file": str(
                            ROOT / "schema_examples" / "complete_chain.valid.yaml"
                        ),
                        "output_dir": directory,
                        "run_id": "run-01",
                    }
                ),
                encoding="utf-8",
            )
            output = StringIO()
            with redirect_stdout(output):
                code = main(["run", str(config_path)])
            self.assertEqual(code, 0)
            rendered = output.getvalue()
            self.assertIn("status=COMPLETE", rendered)
            self.assertIn("stage=FINAL_REVIEW", rendered)
            self.assertIn("01_writer_handoff.json", rendered)
            self.assertTrue((Path(directory) / "run-01" / "final.md").is_file())


if __name__ == "__main__":
    unittest.main()
