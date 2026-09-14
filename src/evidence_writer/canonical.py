"""RFC 8785-compatible canonical JSON for the Contract domain.

The frozen v0.1.3 contracts have no floating-point fields. Floats are rejected
instead of silently using a non-JCS Python representation.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .serialization import ContractSerializationError, to_contract_json


class CanonicalizationError(ValueError):
    """Raised when a value is outside the frozen Contract JSON domain."""


def _quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _render_json(value: Any) -> str:
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
    if isinstance(value, list):
        return "[" + ",".join(_render_json(item) for item in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value, key=lambda key: key.encode("utf-16be"))
        return "{" + ",".join(
            _quote(key) + ":" + _render_json(value[key]) for key in keys
        ) + "}"
    raise CanonicalizationError(
        f"unsupported normalized Contract value type: {type(value).__name__}"
    )


def canonical_json(value: Any) -> str:
    """Serialize through the sole Contract boundary, then apply JCS ordering."""
    try:
        normalized = to_contract_json(value)
    except ContractSerializationError as error:
        raise CanonicalizationError(str(error)) from error
    return _render_json(normalized)


def canonical_sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
