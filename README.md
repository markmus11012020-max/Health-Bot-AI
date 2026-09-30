# 🏥 Health-Bot-AI

> ИИ-ассистент отдела продаж компании **OCX** (продукты для здоровья и бережного очищения организма).
> MVP на Streamlit + Webhook API: анонимизирует ПДн по 152-ФЗ, генерирует ответ клиенту + подсказку по допродажам менеджеру.
> **Тестовая сборка:** активен только один AI-провайдер за раз (выбор в сайдбаре).

---

## ✨ Возможности

- 🧠 **Генерация ответов** на вопросы клиентов по базе продуктов OCX
- 💼 **Подсказки допродаж** для менеджера (увеличение чека, акции)
- 🔒 **Соответствие 152-ФЗ** — все имена, телефоны, e-mail и адреса маскируются перед отправкой в LLM
- 🎛 **Переключаемый провайдер** — в сайдбаре выбирается один AI (`AITunnel` по умолчанию / `YandexGPT`)
- ⚡ **Streaming-ответ** — токены по мере генерации (мгновенный UX)
- 🧪 **A/B-варианты промптов** — `standard` / `expert` / `warm` (выбор в сайдбаре или .env)
- 💾 **LRU-кэш ответов** — повторные запросы мгновенно, без обращения к API
- 🌐 **FastAPI Webhook** — эндпоинт `POST /consult` для интеграции с внешними CRM
- ⚙️ **Расширенные параметры** — temperature, max_tokens, вариант промпта, стрим (в сайдбаре)
- 📋 **Копирование обоих блоков** — кнопки «📋 Копировать ответ» + «📋 Копировать подсказку»
- 🧹 **Очистить форму** — сброс полей ввода и технического лога одной кнопкой (защита от «зависания» при пустых ответах)
- 🕓 **История сессии** — последние 10 обращений с возможностью раскрытия
- 📜 **Аудит-логирование** — каждое обращение пишется в `audit.log` (только анонимизированные данные)
- 🧱 **Модульная OOP-архитектура** — чистое разделение UI / бизнес-логики / интеграций

---

## 🏗️ Архитектура

```
Health-Bot-AI/
├── app.py                          # Streamlit entry point (UI)
├── start.bat                       # Windows deploy Streamlit
├── start_webhook.bat               # Windows deploy FastAPI webhook
├── requirements.txt
├── .env.example                    # Пресет переменных окружения
├── knowledge_base.txt              # База продуктов OCX
│
├── config/                         # Конфигурация (settings + промты)
│   ├── settings.py                 # Settings dataclass (env-driven)
│   └── prompts.py                  # A/B-варианты system-prompt (standard/expert/warm)
│
├── src/
│   ├── core/                       # Чистая доменная логика
│   │   ├── anonymizer.py           # PIIAnonymizer (152-ФЗ)
│   │   ├── knowledge_base.py       # KnowledgeBase loader
│   │   ├── response_parser.py      # Парсер 2-блочного ответа LLM
│   │   ├── response_cache.py       # In-memory LRU-кэш ответов
│   │   └── audit_log.py            # JSON-аудит-лог (без ПД)
│   │
│   ├── ai/                         # Адаптеры AI-провайдеров
│   │   ├── base.py                 # ABC: AIClient, ChatRequest, ChatResult
│   │   ├── aitunnel_client.py      # AITunnel (OpenAI-compatible, +stream)
│   │   ├── yandex_client.py        # YandexGPT (OpenAI-compatible, +stream)
│   │   └── orchestrator.py         # Fallback-цепочка + stream()
│   │
│   ├── services/                   # Use-cases
│   │   ├── consultation_service.py # Бизнес-логика + кэш + run() / stream_run()
│   │   └── provider_factory.py     # Composition root / DI + реестр провайдеров
│   │
│   ├── api/                        # FastAPI webhook для интеграций
│   │   └── webhook.py              # POST /consult, GET /health
│   │
│   └── ui/                         # Презентационный слой Streamlit
│       ├── styles.py               # CSS + footer
│       └── components.py           # Виджеты + селекторы + история
│
└── tests/                          # Юнит-тесты
    ├── test_anonymizer.py          # маскирование ПД
    ├── test_response_parser.py     # парсинг 2-блочного ответа
    ├── test_settings.py            # загрузка конфигурации
    ├── test_consultation_service.py # кэш + гарантия отсутствия ПД в LLM-промпте
    └── test_webhook.py             # Pydantic-схемы + /consult + /health
```

### Принципы

- **Single Responsibility** — каждый модуль делает одну вещь
- **Dependency Inversion** — UI зависит от абстракций (`AIClient`, `PIIAnonymizer`)
- **Open/Closed** — добавление нового AI-провайдера = новый класс, реализующий `AIClient`
- **Composition Root** — все зависимости собираются в `provider_factory.build_consultation_service()`
- **Fail-safe анонимизация** — `build_system_prompt` физически не принимает `crm_context`

---

## 🚀 Быстрый старт (Windows)

```bat
:: 1. Клонировать
git clone https://github.com/markmus11012020-max/Health-Bot-AI.git
cd Health-Bot-AI

:: 2. Создать .env из пресета
copy .env.example .env
notepad .env       :: заполнить AITUNNEL_API_KEY, YANDEX_API_KEY, YANDEX_FOLDER_ID

:: 3a. Streamlit UI (порт 8501) — для интерактивной работы менеджера
start.bat

:: 3b. FastAPI webhook (порт 8080) — для интеграции с CRM
start_webhook.bat
```

После запуска:

- **UI:** <http://localhost:8501>
- **Webhook docs:** <http://localhost:8080/docs>
- **Health:** <http://localhost:8080/health>

Пример вызова webhook:

```bash
curl -X POST http://localhost:8080/consult ^
  -H "Content-Type: application/json" ^
  -d "{\"crm_context\":\"Клиент: Мария, оформляет Детокс 4500р.\",\"client_message\":\"Сколько доставка в Самару?\"}"
```

Ответом:

```json
{
  "client_answer": "Здравствуйте! ...",
  "manager_tip": "Предложите Витамин-Буст со скидкой 20% ...",
  "needs_upsell": true,
  "provider": "AITunnel",
  "model": "minimax-m3",
  "cache_hit": false,
  "response_chars": 542
}
```

---

## 🐧 Быстрый старт (Linux / macOS)

```bash
git clone https://github.com/markmus11012020-max/Health-Bot-AI.git
cd Health-Bot-AI
cp .env.example .env
$EDITOR .env

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

---

## ⚙️ Конфигурация

Все настройки берутся из `.env` (см. `.env.example`):

| Переменная              | Назначение                          | По умолчанию                  |
| ----------------------- | ----------------------------------- | ----------------------------- |
| `AITUNNEL_API_KEY`      | API-ключ основного провайдера       | —                             |
| `AITUNNEL_BASE_URL`     | Endpoint AITunnel                   | `https://api.aitunnel.ru/v1`  |
| `AITUNNEL_MODEL`        | Модель AITunnel (на выбор: `minimax-m3`, Gemini, GPT) | `minimax-m3`     |
| `YANDEX_GPT_URL`        | Endpoint YandexGPT (native REST)    | `https://llm.api.cloud.yandex.net/foundationModels/v1/completion` |
| `YANDEX_API_KEY`        | API-ключ YandexGPT                  | —                             |
| `YANDEX_IAM_TOKEN`      | IAM-токен (приоритет над API-ключом)| —                             |
| `YANDEX_FOLDER_ID`      | Folder ID Yandex Cloud              | —                             |
| `YANDEX_GPT_MODEL`      | Модель YandexGPT                    | `yandexgpt-lite`              |
| `YANDEX_TIMEOUT_S`      | Таймаут YandexGPT (сек)             | `120`                         |
| `TEMPERATURE`           | Температура генерации               | `0.2`                         |
| `MAX_TOKENS`            | Лимит токенов                       | `800`                         |
| `REQUEST_TIMEOUT`       | Таймаут HTTP-запроса (сек)          | `30`                          |
| `MAX_RETRIES`           | Число ретраев                       | `2`                           |
| `PROMPT_VARIANT`        | A/B-вариант промпта                 | `standard` (или `expert`/`warm`) |
| `APP_TITLE` / `APP_ICON`| Заголовок и иконка интерфейса       | `Health-Bot-AI \| OCX` / 🏥   |

---

## 🧪 Тесты

```bash
python -m unittest discover tests -v
```

Покрытие:

- `test_anonymizer.py` — маскирование имён / телефонов / email / адресов
- `test_response_parser.py` — парсинг 2-блочного ответа LLM
- `test_settings.py` — загрузка конфигурации и заморозка dataclass'а
- `test_consultation_service.py` — **гарантия, что сырые ПД не уходят в LLM-промпт + кэш**
- `test_webhook.py` — Pydantic-валидация, эндпоинты `/health` и `/consult`, обработка ошибок

25 тестов проходят.

---

## 🔒 Безопасность и 152-ФЗ

`PIIAnonymizer` заменяет **до отправки** в LLM:

- Имена → `[Клиент]`
- Телефоны (все RU-форматы) → `[Телефон]`
- E-mail → `[Email]`
- Адреса → `[Адрес]`

Анонимизация применяется к **обоим** полям (`crm_context` и `client_message`)
перед формированием `system_prompt` и `user_message`. В LLM **никогда**
не уходят сырые ФИО/телефоны/e-mail. Это зафиксировано тестом
`tests/test_consultation_service.py`.

Сырые ПДн **никогда** не покидают оперативную память процесса.

---

## ➕ Добавление нового AI-провайдера

```python
# src/ai/my_provider.py
from src.ai.base import AIClient, ChatRequest, ChatResult

class MyProvider(AIClient):
    name = "MyProvider"

    def chat(self, request: ChatRequest) -> ChatResult:
        ...

    def stream(self, request: ChatRequest) -> Generator[str, None, None]:
        # Опционально — для streaming-UI
        ...

# src/services/provider_factory.py
from src.ai.my_provider import MyProvider

PROVIDER_REGISTRY["my"] = MyProvider   # ← добавлено
```

Чтобы провайдер появился в сайдбаре — добавьте человекочитаемую метку в
`_PROVIDER_LABELS` в `src/ui/components.py`. UI-логику самого селектора менять
**не нужно**.

---

## 🌐 Webhook API (для интеграции)

`src/api/webhook.py` — FastAPI-приложение для интеграции с AmoCRM и другими CRM.

### Эндпоинты

| Метод  | Путь                | Назначение                                     |
| ------ | ------------------- | ---------------------------------------------- |
| GET    | `/health`           | health-check + состояние кэша/провайдеров       |
| POST   | `/consult`          | Обработка обращения → 2 блока (client + tip)   |
| POST   | `/consult/clear-cache` | Сброс кэша (полезно для тестов)             |

### Схема запроса `POST /consult`

```json
{
  "crm_context": "Клиент: Мария, +79271234567. Сделка: Детокс 4500р.",
  "client_message": "Сколько доставка в Самару? И будет ли слабость?",
  "provider": "aitunnel",            // опционально: aitunnel | yandex
  "prompt_variant": "warm",           // опционально: standard | expert | warm
  "use_cache": true                   // опционально
}
```

### Схема ответа `200 OK`

```json
{
  "client_answer": "Здравствуйте! ...",
  "manager_tip": "Предложите Витамин-Буст со скидкой 20% ...",
  "needs_upsell": true,
  "provider": "AITunnel",
  "model": "minimax-m3",
  "cache_hit": false,
  "response_chars": 542
}
```

### Запуск

```bash
# Локально
uvicorn src.api.webhook:app --host 0.0.0.0 --port 8080

# Windows
start_webhook.bat
```

Документация OpenAPI: <http://localhost:8080/docs>.

---

## 📜 Лицензия

MIT © 2026 OCX / Health-Bot-AI Contributors.
Демонстрационный MVP для собеседования.