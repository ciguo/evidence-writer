"""Single serialization boundary for frozen Contract JSON values."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import AnyUrl, BaseModel
from pydantic_core import MultiHostUrl, Url


class ContractSerializationError(TypeError):
    """Raised when a Python value has no frozen Contract JSON representation."""


def to_contract_json(model_or_value: Any) -> Any:
    """Return only plain JSON values accepted at the Contract wire boundary.

    Pydantic models are dumped in JSON mode and null optional fields are omitted,
    because the frozen schema represents those fields as absent rather than null.
    """
    value = model_or_value
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", exclude_none=True)

    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, StrEnum):
        return str(value.value)
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        raise ContractSerializationError("floats are not permitted by Contract v0.1.3")
    if isinstance(value, datetime):
        raise ContractSerializationError("datetime is not permitted by Contract v0.1.3")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (AnyUrl, Url, MultiHostUrl)):
        return str(value)
    if isinstance(value, list):
        return [to_contract_json(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ContractSerializationError("Contract JSON object keys must be strings")
        return {key: to_contract_json(item) for key, item in value.items()}
    raise ContractSerializationError(
        f"unsupported Contract value type: {type(value).__name__}"
    )
