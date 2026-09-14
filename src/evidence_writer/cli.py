"""Minimal CLI for Contract validation and the synthetic pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

import yaml

from .contracts import Stage, StageResult
from .pipeline import PipelineRunner, StageHandler
from .policies import validate_contract_data
from .storage import FilesystemStorage


class SyntheticStageHandler:
    """Return one configured formal StageResult; contains no stage logic."""

    def __init__(self, result_data: dict) -> None:
        self.result_data = result_data

    def run(self, input_artifact) -> StageResult:
        return StageResult.model_validate(self.result_data)


def _load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("YAML root must be an object")
    return data


def _print_result(status: str, stage: str, error_code: str, paths) -> None:
    print(f"status={status}")
    print(f"stage={stage}")
    print(f"error_code={error_code}")
    print("artifact_paths=" + json.dumps(paths, ensure_ascii=False, sort_keys=True))


def _validate(path: Path) -> int:
    data = _load_yaml(path)
    violations = validate_contract_data(data)
    if violations:
        first = violations[0]
        _print_result("FAIL", "VALIDATE", first.code, {})
        return 1
    _print_result("COMPLETE", "VALIDATE", "-", {})
    return 0


def _run(path: Path) -> int:
    config = _load_yaml(path)
    bundle_path = Path(config["bundle_file"])
    if not bundle_path.is_absolute():
        bundle_path = path.parent / bundle_path
    bundle = _load_yaml(bundle_path.resolve())

    output_dir = Path(config.get("output_dir", "output"))
    if not output_dir.is_absolute():
        output_dir = path.parent / output_dir
    run_id = str(config.get("run_id", "synthetic"))
    if Path(run_id).name != run_id or run_id in {"", ".", ".."}:
        raise ValueError("run_id must be a safe path component")

    handlers: dict[Stage, StageHandler] = {
        Stage.AUDITOR: SyntheticStageHandler(bundle["auditor_result"]),
        Stage.ADAPTER: SyntheticStageHandler(bundle["adapter_result"]),
        Stage.WRITER: SyntheticStageHandler(bundle["writer_result"]),
        Stage.FINAL_REVIEW: SyntheticStageHandler(bundle["final_review_result"]),
    }
    runner = PipelineRunner(
        handlers,
        FilesystemStorage(output_dir.resolve() / run_id),
    )
    result = runner.run(
        bundle["research_artifact_envelope"],
        bundle["capability_registry_snapshot"],
    )
    _print_result(
        result.status,
        result.stage or "-",
        result.error_code or "-",
        result.artifact_paths,
    )
    return 0 if result.status == "COMPLETE" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evidence-writer")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("input", type=Path)
    run = commands.add_parser("run")
    run.add_argument("input", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            return _validate(args.input)
        return _run(args.input)
    except Exception:
        _print_result("FAIL", "INPUT", "CLI_INPUT_INVALID", {})
        return 1


if __name__ == "__main__":
    sys.exit(main())
