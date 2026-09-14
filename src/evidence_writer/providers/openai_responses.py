"""OpenAI-compatible Responses API provider using only the standard library."""

from __future__ import annotations

import json
import os
import socket
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .base import ProviderError, ProviderResponse


class OpenAIResponsesProvider:
    """Small Responses API client configured exclusively through EW env vars."""

    provider_name = "openai-compatible-responses"

    def __init__(self) -> None:
        required = {
            "api_key": "EVIDENCE_WRITER_LLM_API_KEY",
            "base_url": "EVIDENCE_WRITER_LLM_BASE_URL",
            "model": "EVIDENCE_WRITER_LLM_MODEL",
            "timeout": "EVIDENCE_WRITER_LLM_TIMEOUT_SECONDS",
        }
        values = {name: os.environ.get(variable) for name, variable in required.items()}
        missing = [required[name] for name, value in values.items() if not value]
        if missing:
            raise ProviderError(
                "PROVIDER_CONFIG_MISSING",
                "required LLM environment configuration is missing",
                provider=self.provider_name,
            )
        try:
            timeout = float(values["timeout"] or "")
            if timeout <= 0:
                raise ValueError
        except ValueError as error:
            raise ProviderError(
                "PROVIDER_CONFIG_INVALID",
                "LLM timeout must be a positive number",
                provider=self.provider_name,
            ) from error
        self.api_key = values["api_key"] or ""
        self.base_url = (values["base_url"] or "").rstrip("/")
        self.model = values["model"] or ""
        self.timeout = timeout

    def generate(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        model: str,
        temperature: float | None = None,
        response_schema: Mapping[str, Any] | None = None,
    ) -> ProviderResponse:
        payload: dict[str, Any] = {"model": model, "input": list(messages)}
        if temperature is not None:
            payload["temperature"] = temperature
        if response_schema is not None:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "evidence_writer_stage",
                    "strict": True,
                    "schema": response_schema,
                }
            }
        request = Request(
            f"{self.base_url}/responses",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                data = json.load(response)
        except HTTPError as error:
            raise ProviderError(
                "PROVIDER_HTTP_ERROR",
                f"provider returned HTTP status {error.code}",
                provider=self.provider_name,
                retryable=error.code in {408, 409, 429} or error.code >= 500,
            ) from error
        except (URLError, TimeoutError, socket.timeout, OSError, ValueError) as error:
            raise ProviderError(
                "PROVIDER_UNAVAILABLE",
                "provider request failed",
                provider=self.provider_name,
                retryable=True,
            ) from error

        text = data.get("output_text")
        if not text:
            chunks = []
            for output in data.get("output", []):
                for content in output.get("content", []):
                    if content.get("type") in {"output_text", "text"} and content.get("text"):
                        chunks.append(content["text"])
            text = "".join(chunks) or None
        if text is None:
            raise ProviderError(
                "PROVIDER_RESPONSE_INVALID",
                "provider response contained no output text",
                provider=self.provider_name,
            )
        structured = None
        if response_schema is not None:
            try:
                structured = json.loads(text)
            except (TypeError, json.JSONDecodeError) as error:
                raise ProviderError(
                    "PROVIDER_RESPONSE_INVALID",
                    "provider response was not valid structured JSON",
                    provider=self.provider_name,
                ) from error
        usage = data.get("usage")
        return ProviderResponse(
            text=text,
            structured=structured,
            provider=self.provider_name,
            model=model,
            usage=usage if isinstance(usage, dict) else None,
            request_id=data.get("id"),
        )

    def connectivity_test(self) -> ProviderResponse:
        return self.generate(
            [{"role": "user", "content": "Reply with exactly: OK"}],
            model=self.model,
            temperature=0,
        )
