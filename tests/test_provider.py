from __future__ import annotations

import socket
import unittest
from unittest.mock import patch

from evidence_writer.providers import (
    FakeProvider,
    ProviderError,
    normalize_provider_error,
)


class VendorSpecificFailure(Exception):
    pass


class ProviderTests(unittest.TestCase):
    def test_fake_provider_success_is_deterministic(self) -> None:
        provider = FakeProvider(text="fixed", structured={"ok": True})
        first = provider.generate([{"role": "user", "content": "ignored"}], model="fake-model")
        second = provider.generate([{"role": "user", "content": "different"}], model="fake-model")
        self.assertEqual(first.text, second.text)
        self.assertEqual(first.structured, second.structured)
        self.assertEqual(first.provider, "fake")
        self.assertEqual(first.model, "fake-model")

    def test_fake_provider_normalizes_configured_exception(self) -> None:
        provider = FakeProvider(error=VendorSpecificFailure("vendor secret"))
        with self.assertRaises(ProviderError) as caught:
            provider.generate([], model="fake-model")
        self.assertEqual(caught.exception.code, "PROVIDER_ERROR")
        self.assertNotIn("vendor secret", str(caught.exception))
        self.assertNotIsInstance(caught.exception, VendorSpecificFailure)

    def test_normalization_and_fake_provider_require_no_network_or_api_key(self) -> None:
        normalized = normalize_provider_error(
            VendorSpecificFailure("raw vendor text"),
            provider="vendor-x",
        )
        self.assertIsInstance(normalized, ProviderError)
        self.assertEqual(normalized.provider, "vendor-x")
        with patch.object(socket, "create_connection", side_effect=AssertionError("network used")):
            response = FakeProvider().generate([], model="offline")
        self.assertEqual(response.text, "synthetic response")


if __name__ == "__main__":
    unittest.main()
