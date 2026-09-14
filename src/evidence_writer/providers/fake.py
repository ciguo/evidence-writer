"""Deterministic provider used by tests and synthetic examples only."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .base import ProviderResponse, normalize_provider_error


class FakeProvider:
    provider_name = "fake"

    def __init__(
        self,
        *,
        text: str | None = "synthetic response",
        structured: Any | None = None,
        error: Exception | None = None,
    ) -> None:
        self._text = text
        self._structured = structured
        self._error = error
        self.call_count = 0

    def generate(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        model: str,
        temperature: float | None = None,
        response_schema: Mapping[str, Any] | None = None,
    ) -> ProviderResponse:
        self.call_count += 1
        if self._error is not None:
            raise normalize_provider_error(self._error, provider=self.provider_name)
        return ProviderResponse(
            text=self._text,
            structured=self._structured,
            provider=self.provider_name,
            model=model,
            usage={"input_tokens": 0, "output_tokens": 0},
            request_id=f"fake-{self.call_count}",
        )
