"""Settings dataclass smoke-test (no real env mutation)."""
from __future__ import annotations

import unittest

from config.settings import Settings


class SettingsTests(unittest.TestCase):
    def test_defaults_when_no_env(self) -> None:
        s = Settings()
        self.assertEqual(s.temperature, 0.2)
        self.assertEqual(s.max_tokens, 800)
        self.assertIn("aitunnel", s.aitunnel_base_url.lower())
        self.assertEqual(s.yandex_gpt_model, "yandexgpt-lite")

    def test_frozen(self) -> None:
        s = Settings()
        with self.assertRaises(Exception):
            s.temperature = 0.9  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()