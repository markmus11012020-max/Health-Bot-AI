"""Smoke-test: verify config + Yandex model URI builder against real .env."""
from config.settings import get_settings
from src.ai.yandex_client import YandexGPTClient

s = get_settings()
print("AITUNNEL_MODEL       :", s.aitunnel_model)
print("YANDEX_GPT_URL (raw)  :", s.yandex_gpt_url)
print("YANDEX_FOLDER_ID      :", s.yandex_folder_id)
print("YANDEX_GPT_MODEL      :", s.yandex_gpt_model)
print("YANDEX_TIMEOUT_S      :", s.yandex_timeout_s)
print("YANDEX_IAM_TOKEN (raw):", repr(s.yandex_iam_token))
print("YANDEX_IAM_TOKEN used :", bool(s.yandex_iam_token.strip()))
print("YANDEX_API_KEY set    :", bool(s.yandex_api_key))

# Build client (no network call) to confirm model URI composition
client = YandexGPTClient(s)
print("Yandex model URI      :", client._model_uri)
print("Yandex base_url       :", client._client.base_url)
print("Yandex timeout        :", client._client.timeout)
# Inspect auth passed to OpenAI client
auth_passed = client._client.api_key
print("Yandex auth passed    :", "IAM" if auth_passed == s.yandex_iam_token.strip() else "API_KEY")
print("Yandex auth length    :", len(auth_passed))
