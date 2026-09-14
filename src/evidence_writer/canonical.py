"""RFC 8785-compatible canonical JSON for the Contract domain.

The frozen v0.1.3 contracts have no floating-point fields.  Floats are
therefore rejected instead of silently using a non-JCS Python representation.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


class CanonicalizationError(ValueError):
    """Raised when a value is outside the frozen Contract JSON domain."""


def _quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def canonical_json(value: Any) -> str:
    """Serialize the Contract JSON domain deterministically.

    Object keys use UTF-16 code-unit ordering, as required by RFC 8785.  The
    Contract schemas deliberately reject floating-point fields; rejecting them
    here prevents accidental divergence from ECMAScript number serialization.
    """

    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _quote(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        raise CanonicalizationError("floats are not permitted by Contract v0.1.3")
    if isinstance(value, list):
        return "[" + ",".join(canonical_json(item) for item in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise CanonicalizationError("JSON object keys must be strings")
        keys = sorted(value, key=lambda key: key.encode("utf-16be"))
        return "{" + ",".join(_quote(key) + ":" + canonical_json(value[key]) for key in keys) + "}"
    raise CanonicalizationError(f"unsupported Contract value type: {type(value).__name__}")


def canonical_sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
