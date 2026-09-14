"""Vendor-neutral LLM provider boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class ProviderResponse:
    text: str | None
    structured: Any | None
    provider: str
    model: str
    usage: Mapping[str, int] | None = None
    request_id: str | None = None

    def __post_init__(self) -> None:
        if self.text is None and self.structured is None:
            raise ValueError("provider response requires text or structured content")
        if not self.provider or not self.model:
            raise ValueError("provider and model are required")


class ProviderError(RuntimeError):
    """Project-level provider error safe for orchestration."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        provider: str,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.provider = provider
        self.retryable = retryable


def normalize_provider_error(error: Exception, *, provider: str) -> ProviderError:
    """Prevent vendor-specific exception types and messages crossing the boundary."""
    if isinstance(error, ProviderError):
        return error
    return ProviderError(
        "PROVIDER_ERROR",
        f"{provider} provider request failed",
        provider=provider,
        retryable=False,
    )


class LLMProvider(Protocol):
    def generate(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        model: str,
        temperature: float | None = None,
        response_schema: Mapping[str, Any] | None = None,
    ) -> ProviderResponse:
        ...
