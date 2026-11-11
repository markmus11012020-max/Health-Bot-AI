# 🏥 Health-Bot-AI

> ИИ-ассистент отдела продаж компании **OCX** (продукты для здоровья и
> бережного очищения организма).
>
> Production MVP: Streamlit UI + FastAPI API. Анонимизирует ПДн по 152-ФЗ,
> генерирует ответ клиенту и внутреннюю подсказку менеджеру по допродажам.

[![CI](https://github.com/markmus11012020-max/Health-Bot-AI/actions/workflows/ci.yml/badge.svg)](https://github.com/markmus11012020-max/Health-Bot-AI/actions/workflows/ci.yml)

---

## ✨ Возможности

- 🧠 **Ответ клиенту** на основе базы знаний OCX
- 💼 **Подсказка менеджеру** по допродажам, акциям и следующему шагу
- 🔒 **152-ФЗ**: имена, телефоны, e-mail, адреса, СНИЛС, ИНН, паспорт,
  дата рождения, карта и IP маскируются до отправки в LLM
- 🛡 **Guardrails**: prompt injection, медицинские red flags, запрещённые
  формулировки, дисклеймер
- 🎛 **Два провайдера**: AITunnel (основной) + YandexGPT (fallback)
- ⚡ **Streaming**: SSE для API и мгновенный отклик в UI
- 💾 **Кэш**: Redis или in-process LRU с TTL и версионированным ключом
- 🗄 **Аудит и обратная связь**: SQLite/PostgreSQL через SQLAlchemy
- 🔑 **API-безопасность**: API key, admin key, rate limit, idempotency
- 📚 **RAG-lite**: версионированная база знаний, лексический retrieval,
  цитаты в ответе
- 🧩 **Устойчивый разбор ответа**: JSON, обрезанный JSON и legacy two-block;
  детерминированный upsell-fallback, если модель не вернула блок менеджера
- 🧪 **Тесты**: unit/integration, lint, typecheck, CI
- 🐳 **Docker Compose**: PostgreSQL + Redis + API + UI

---

## 🏗️ Архитектура

```text
[Streamlit UI]   [API clients]
       \              /
        [FastAPI /v1]
             |
    [ConsultationService]
    /        |           \
[Anonymizer] [RAG/KB]  [Cache]
    |          |           |
[PromptBuilder] [retriever] [Redis/LRU]
    |
[AIOrchestrator] → [AITunnel] / [YandexGPT]
    |
[Parser + Guardrails] → [SQLite/PostgreSQL audit & feedback]
```

Подробности: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

### Структура проекта

```text
Health-Bot-AI/
├── app.py                          # Streamlit entry point
├── start.bat                       # Windows: UI
├── start_webhook.bat               # Windows: API
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml                  # pytest / ruff / mypy
├── .env.example
├── knowledge_base.txt
│
├── config/
│   ├── settings.py                 # env-driven settings + validation
│   └── prompts.py                  # A/B prompts + JSON contract
│
├── src/
│   ├── ai/                         # provider adapters + orchestrator
│   ├── api/                        # FastAPI /v1
│   ├── core/                       # anonymizer, safety, KB, cache, DB, audit
│   ├── services/                   # use-cases + composition root
│   └── ui/                         # Streamlit components/styles
│
├── tests/
└── docs/
    ├── ТЗ.md
    ├── ARCHITECTURE.md
    ├── API.md
    ├── COMPLIANCE.md
    ├── TEST_PLAN.md
    └── requirements/               # исходный шаблон ТЗ (PDF)
```

---

## 🚀 Быстрый старт (Windows)

```bat
:: 1. Клонировать
git clone https://github.com/markmus11012020-max/Health-Bot-AI.git
cd Health-Bot-AI

:: 2. Создать .env
copy .env.example .env
notepad .env       :: заполнить AITUNNEL_API_KEY, YANDEX_API_KEY, YANDEX_FOLDER_ID

:: 3. Установить зависимости
python -m venv venv
venv\Scripts\activate
pip install -r requirements-dev.txt

:: 4. Проверить
python -m pytest -q
python -m ruff check .
python -m mypy src config app.py

:: 5a. Streamlit UI (8501)
start.bat

:: 5b. FastAPI API (8080)
start_webhook.bat
```

После запуска:

- **UI:** <http://localhost:8501>
- **API docs:** <http://localhost:8080/docs>
- **Health:** <http://localhost:8080/health>
- **Ready:** <http://localhost:8080/ready>

### Linux / macOS

```bash
git clone https://github.com/markmus11012020-max/Health-Bot-AI.git
cd Health-Bot-AI
cp .env.example .env
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
python -m streamlit run app.py
```

### Docker Compose

```bash
# В .env обязательно задайте API_KEY и ADMIN_API_KEY
docker compose up --build -d
```

Сервисы:

| Сервис | Порт | Назначение |
|---|---|---|
| `api` | 8080 | FastAPI |
| `ui` | 8501 | Streamlit |
| `db` | 5432 | PostgreSQL 16 |
| `redis` | 6379 | Redis 7 |

---

## ⚙️ Конфигурация

Все настройки берутся из `.env` (см. `.env.example`).

| Переменная | Назначение | По умолчанию |
|---|---|---|
| `ENVIRONMENT` | `development` / `test` / `production` | `development` |
| `APP_VERSION` | Версия приложения | `1.0.0` |
| `LOG_LEVEL` | Уровень логов | `INFO` |
| `AITUNNEL_API_KEY` | API-ключ AITunnel | — |
| `AITUNNEL_BASE_URL` | Endpoint AITunnel | `https://api.aitunnel.ru/v1` |
| `AITUNNEL_MODEL` | Модель AITunnel | `deepseek-v4.1-flash-1017` |
| `YANDEX_GPT_URL` | OpenAI-совместимый endpoint YandexGPT | `https://llm.api.cloud.yandex.net/v1` |
| `YANDEX_API_KEY` | API-ключ YandexGPT | — |
| `YANDEX_IAM_TOKEN` | IAM-токен (приоритет выше API-ключа) | — |
| `YANDEX_FOLDER_ID` | Folder ID Yandex Cloud | — |
| `YANDEX_GPT_MODEL` | Модель YandexGPT | `yandexgpt-lite` |
| `YANDEX_TIMEOUT_S` | Таймаут YandexGPT | `120` |
| `TEMPERATURE` | Температура генерации | `0.2` |
| `MAX_TOKENS` | Лимит токенов | `1600` |
| `REQUEST_TIMEOUT` | Таймаут HTTP | `60` |
| `MAX_RETRIES` | Число ретраев | `2` |
| `ENABLE_FALLBACK` | Fallback между провайдерами | `true` |
| `KB_PATH` | Путь к базе знаний | `knowledge_base.txt` |
| `KB_TOP_K` | Число чанков в промпте | `3` |
| `KB_MAX_CHARS` | Лимит контекста БЗ | `6000` |
| `CACHE_MAXSIZE` | Размер LRU-кэша | `256` |
| `CACHE_TTL_SECONDS` | TTL кэша | `86400` |
| `REDIS_URL` | Redis для общего кэша | — |
| `DATABASE_URL` | SQLite/PostgreSQL DSN | `sqlite:///data/health_bot.db` |
| `API_KEY` | API-ключ (обязателен в production) | — |
| `ADMIN_API_KEY` | Ключ админ-операций | — |
| `RATE_LIMIT_REQUESTS` | Запросов на окно | `60` |
| `RATE_LIMIT_WINDOW_SECONDS` | Окно rate limit | `60` |
| `IDEMPOTENCY_TTL_SECONDS` | TTL Idempotency-Key | `3600` |
| `GUARDRAILS_ENABLED` | Включить guardrails | `true` |
| `PROMPT_VARIANT` | `standard` / `expert` / `warm` | `standard` |

> В production обязательно задайте `API_KEY`, `ADMIN_API_KEY` и PostgreSQL.
> `ENVIRONMENT=production` включает проверки `/ready`.

---

## 🌐 API

Полное описание: [`docs/API.md`](docs/API.md). OpenAPI: <http://localhost:8080/docs>.

### `POST /v1/consult`

```bash
curl -X POST http://localhost:8080/v1/consult ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: your-api-key" ^
  -d "{\"crm_context\":\"Клиент: Мария, оформляет Детокс 4500 руб.\",\"client_message\":\"Сколько доставка в Самару?\",\"prompt_variant\":\"warm\",\"use_cache\":true}"
```

Ответ:

```json
{
  "request_id": "0f9f5e2a...",
  "client_answer": "Здравствуйте! Доставка в Самару — 300 ₽...",
  "manager_tip": "Предложите Витамин-Буст со скидкой 20%...",
  "needs_upsell": true,
  "citations": ["УСЛОВИЯ ДОСТАВКИ", "АКЦИИ И ДОПРОДАЖИ"],
  "confidence": 0.88,
  "safety_flags": [],
  "provider": "AITunnel",
  "model": "deepseek-v4.1-flash-1017",
  "cache_hit": false,
  "response_chars": 542,
  "usage": {"prompt_tokens": 1200, "completion_tokens": 180}
}
```

### `POST /v1/consult/stream`

Возвращает `text/event-stream`: `meta` → `token` → `done` (или `error`).

### Остальные эндпоинты

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/health` | liveness |
| `GET` | `/ready` | readiness: БД, кэш, провайдеры |
| `POST` | `/v1/consult` | обработка обращения |
| `POST` | `/v1/consult/stream` | SSE-стриминг |
| `POST` | `/v1/feedback` | оценка менеджера |
| `POST` | `/v1/admin/cache/clear` | сброс кэша (admin key) |

Старые `/consult` и `/consult/clear-cache` сохранены как алиасы.

---

## 🔒 Безопасность и 152-ФЗ

`PIIAnonymizer` заменяет **до отправки** в LLM:

- имена → `[Клиент]`
- телефоны → `[Телефон]`
- e-mail → `[Email]`
- адреса → `[Адрес]`
- СНИЛС, ИНН, паспорт, дата рождения, карта, IP → соответствующие плейсхолдеры

Анонимизация применяется к **обоим** полям (`crm_context` и `client_message`).
Соответствие плейсхолдеров исходным значениям не сохраняется.

Дополнительно:

- `SafetyGuard` блокирует явный prompt injection;
- red flags (беременность, хронические заболевания, лекарства, аллергия,
  острая боль, ребёнок) добавляют рекомендацию врача;
- запрещённые медицинские формулировки смягчаются;
- в ответ добавляется дисклеймер;
- в аудит пишутся только метаданные и **количество** ПДн по категориям.

Подробности: [`docs/COMPLIANCE.md`](docs/COMPLIANCE.md).

---

## 🧪 Тесты и качество

```bash
python -m pytest -q
python -m pytest --cov=src --cov=config --cov-report=term-missing
python -m ruff check .
python -m mypy src config app.py
```

Покрытие:

- анонимизация ПДн и отсутствие утечек в LLM-промпт;
- парсинг JSON и legacy two-block;
- guardrails: injection, red flags, medical claims;
- версионирование и retrieval базы знаний;
- TTL/LRU-кэш и версионированные ключи;
- fallback и streaming без смешивания провайдеров;
- SQLite-аудит и обратная связь;
- API: auth, rate limit, idempotency, SSE, feedback, readiness.

---

## 🐳 Production-заметки

- Для нескольких воркеров задайте `REDIS_URL` — кэш станет общим.
- Для PostgreSQL задайте `DATABASE_URL=postgresql+psycopg://...`.
- Rate limit и idempotency в текущей версии in-process; для multi-worker
  замените на Redis (интерфейсы `RateLimiter` и `IdempotencyStore` готовы).
- TLS и Nginx/WAF — на уровне инфраструктуры.
- Секреты храните в Vault/KMS, не в git.
- Перед пилотом: DPIA, реестр субпроцессоров, пентест, нагрузочные тесты.

### Ограничения текущей версии

- AmoCRM-интеграция — следующий этап (сейчас webhook).
- RAG использует лексический retrieval; pgvector/embeddings — R1.
- Нет встроенной админки и RBAC; admin-операции защищены ключом.
- Нет multi-turn памяти; `conversation_id` зарезервирован.

---

## 📚 Документация

- [Техническое задание](docs/ТЗ.md)
- [Архитектура](docs/ARCHITECTURE.md)
- [API](docs/API.md)
- [Compliance / 152-ФЗ](docs/COMPLIANCE.md)
- [Программа испытаний](docs/TEST_PLAN.md)
- [Changelog](docs/CHANGELOG.md)

---

## 📜 Лицензия

MIT © 2026 OCX / Health-Bot-AI Contributors.
Демонстрационный production MVP.
