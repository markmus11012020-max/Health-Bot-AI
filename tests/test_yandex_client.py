"""YandexGPT model URI and auth resolution."""
from __future__ import annotations

import unittest

from config.settings import Settings
from src.ai.yandex_client import YandexGPTClient


class YandexClientTests(unittest.TestCase):
    def test_model_uri_gets_latest_version(self) -> None:
        settings = Settings(yandex_folder_id="folder", yandex_gpt_model="yandexgpt-lite")
        client = YandexGPTClient(settings)
        self.assertEqual(client.model_name, "gpt://folder/yandexgpt-lite/latest")

    def test_fully_qualified_uri_is_kept(self) -> None:
        settings = Settings(
            yandex_folder_id="folder",
            yandex_gpt_model="gpt://folder/yandexgpt/latest",
        )
        client = YandexGPTClient(settings)
        self.assertEqual(client.model_name, "gpt://folder/yandexgpt/latest")

    def test_iam_token_has_priority(self) -> None:
        settings = Settings(yandex_api_key="api-key", yandex_iam_token="iam-token")
        self.assertEqual(YandexGPTClient._resolve_auth(settings), "iam-token")


if __name__ == "__main__":
    unittest.main()
