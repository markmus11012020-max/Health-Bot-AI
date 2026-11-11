# Changelog

Все заметные изменения проекта фиксируются в этом файле.

## [Unreleased] — production MVP

### Added

- ТЗ, архитектура, API, compliance memo и программа испытаний в `docs/`.
- Версионирование базы знаний и лексический retrieval с цитатами.
- SafetyGuard: prompt injection, red flags, запрещённые медицинские
  формулировки, дисклеймер.
- API `/v1`: consult, stream (SSE), feedback, health, ready, admin cache clear.
- API-key auth, admin-key, rate limit, idempotency, request ID.
- Аудит и обратная связь в SQLite/PostgreSQL через SQLAlchemy.
- Redis-кэш с TTL и in-memory fallback.
- Docker, docker-compose, CI.
- Расширенные тесты.

### Fixed

- JSON-ответ, обрезанный по `max_tokens`, больше не показывается клиенту сырым:
  парсер извлекает `client_answer`, а `UpsellAdvisor` детерминированно
  восстанавливает подсказку менеджеру.
- Увеличен `MAX_TOKENS` по умолчанию до 1600 и таймаут до 60 с.
- AITunnel по умолчанию использует `deepseek-v4.1-flash-1017`.
- В список анонимизируемых имён добавлен Олег и другие распространённые имена.
- Webhook теперь исполняет `prompt_variant` и `use_cache`.
- YandexGPT использует OpenAI-совместимый base URL.
- Streaming fallback не смешивает токены разных провайдеров.
- Устранено дублирование сайдбара и блоков ответа в Streamlit.
- Реальная latency в истории запросов.
- Конфигурация валидируется при старте.

## [0.1.0] — MVP

- Streamlit UI, FastAPI webhook.
- AITunnel + YandexGPT.
- Анонимизация, кэш, аудит, A/B-промпты, streaming.
- 25 unit-тестов.
