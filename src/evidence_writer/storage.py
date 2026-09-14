"""Verified local filesystem persistence for Contract artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from .canonical import canonical_json, canonical_sha256
from .contracts import ArtifactEnvelope
from .serialization import to_contract_json


class StorageError(RuntimeError):
    """Raised when persistence or read-back verification fails."""


@dataclass(frozen=True)
class StoredArtifact:
    path: Path
    digest: str


class FilesystemStorage:
    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)

    def _target(self, filename: str) -> Path:
        candidate = Path(filename)
        if candidate.name != filename or filename in {"", ".", ".."}:
            raise StorageError("artifact filename must be a single safe path component")
        return self.base_dir / filename

    def _atomic_write(self, target: Path, content: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = handle.name
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            temporary = None
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass

    def _read_json(self, target: Path) -> Any:
        return json.loads(target.read_text(encoding="utf-8"))

    def write_envelope(
        self,
        filename: str,
        envelope: ArtifactEnvelope | dict[str, Any],
    ) -> StoredArtifact:
        target = self._target(filename)
        try:
            serialized = to_contract_json(envelope)
            validated = ArtifactEnvelope.model_validate(serialized)
            normalized = to_contract_json(validated)
            digest = canonical_sha256(validated.artifact)
            if digest != validated.canonical_json_sha256:
                raise StorageError("artifact digest does not match envelope")
            self._atomic_write(target, canonical_json(normalized) + "\n")
            reread = self._read_json(target)
            revalidated = ArtifactEnvelope.model_validate(reread)
            renormalized = to_contract_json(revalidated)
            if renormalized != normalized:
                raise StorageError("artifact changed during filesystem round-trip")
            if canonical_sha256(revalidated.artifact) != revalidated.canonical_json_sha256:
                raise StorageError("artifact digest failed after filesystem read-back")
            return StoredArtifact(target.resolve(), digest)
        except StorageError:
            raise
        except Exception as error:
            raise StorageError("artifact persistence verification failed") from error

    def write_final(self, filename: str, text: str) -> Path:
        target = self._target(filename)
        if not isinstance(text, str) or not text:
            raise StorageError("final text must be non-empty")
        try:
            self._atomic_write(target, text)
            if target.read_text(encoding="utf-8") != text:
                raise StorageError("final text changed during filesystem round-trip")
            return target.resolve()
        except StorageError:
            raise
        except Exception as error:
            raise StorageError("final text persistence verification failed") from error
