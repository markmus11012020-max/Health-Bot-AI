"""Settings dataclass smoke-test (no real env mutation)."""
from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from config.settings import Settings


class SettingsTests(unittest.TestCase):
    def test_defaults_when_no_env(self) -> None:
        s = Settings()
        self.assertEqual(s.temperature, 0.2)
        self.assertEqual(s.max_tokens, 1600)
        self.assertIn("aitunnel", s.aitunnel_base_url.lower())
        self.assertEqual(s.yandex_gpt_model, "yandexgpt-lite")

    def test_frozen(self) -> None:
        s = Settings()
        with self.assertRaises(FrozenInstanceError):
            s.temperature = 0.9  # type: ignore[misc]

    def test_invalid_prompt_variant_fails_fast(self) -> None:
        with self.assertRaises(ValueError):
            Settings(prompt_variant="unknown")

    def test_invalid_temperature_fails_fast(self) -> None:
        with self.assertRaises(ValueError):
            Settings(temperature=3.0)

    def test_native_yandex_url_is_normalised(self) -> None:
        s = Settings(
            yandex_gpt_url=(
                "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
            )
        )
        self.assertEqual(s.yandex_gpt_url, "https://llm.api.cloud.yandex.net/v1")

    def test_production_validation_reports_missing_api_key(self) -> None:
        s = Settings(environment="production", api_key="", admin_api_key="")
        issues = s.validate()
        self.assertTrue(any("API_KEY" in item for item in issues))
        self.assertTrue(any("ADMIN_API_KEY" in item for item in issues))


if __name__ == "__main__":
    unittest.main()