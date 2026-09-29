# 🏥 Health-Bot-AI

> ИИ-ассистент отдела продаж компании **OCX** (продукты для здоровья и бережного очищения организма).
> MVP на Streamlit: анонимизирует ПДн по 152-ФЗ, генерирует ответ клиенту + подсказку по допродажам менеджеру.
> Поддерживает fallback между AI-провайдерами.

---

## ✨ Возможности

- 🧠 **Генерация ответов** на вопросы клиентов по базе продуктов OCX
- 💼 **Подсказки допродаж** для менеджера (увеличение чека, акции)
- 🔒 **Соответствие 152-ФЗ** — все имена, телефоны, e-mail и адреса маскируются перед отправкой в LLM
- 🔁 **Отказоустойчивость** — primary `AITunnel` → fallback `YandexGPT`
- 📋 **Копирование ответа** в букопиру через `pyperclip`
- 🧱 **Модульная OOP-архитектура** — чистое разделение UI / бизнес-логики / интеграций

---

## 🏗️ Архитектура

```
Health-Bot-AI/
├── app.py                          # Streamlit entry point (тонкий)
├── start.bat                       # Windows deploy-скрипт
├── requirements.txt
├── .env.example                    # Пресет переменных окружения
├── knowledge_base.txt              # База продуктов OCX
│
├── config/                         # Конфигурация (settings + промты)
│   ├── settings.py                 # Settings dataclass (env-driven)
│   └── prompts.py                  # Шаблоны system-prompt
│
├── src/
│   ├── core/                       # Чистая доменная логика
│   │   ├── anonymizer.py           # PIIAnonymizer (152-ФЗ)
│   │   ├── knowledge_base.py       # KnowledgeBase loader
│   │   └── response_parser.py      # Парсер 2-блочного ответа LLM
│   │
│   ├── ai/                         # Адаптеры AI-провайдеров
│   │   ├── base.py                 # ABC: AIClient, ChatRequest, ChatResult
│   │   ├── aitunnel_client.py      # Primary провайдер
│   │   ├── yandex_client.py        # Fallback провайдер
│   │   └── orchestrator.py         # Cross-provider fallback
│   │
│   ├── services/                   # Use-cases
│   │   ├── consultation_service.py # Бизнес-логика консультации
│   │   └── provider_factory.py     # Composition root / DI
│   │
│   └── ui/                         # Презентационный слой Streamlit
│       ├── styles.py               # CSS + footer
│       └── components.py           # Переиспользуемые виджеты
│
└── tests/                          # Юнит-тесты
    ├── test_anonymizer.py
    ├── test_response_parser.py
    └── test_settings.py
```

### Принципы

- **Single Responsibility** — каждый модуль делает одну вещь
- **Dependency Inversion** — UI зависит от абстракций (`AIClient`, `PIIAnonymizer`)
- **Open/Closed** — добавление нового AI-провайдера = новый класс, реализующий `AIClient`
- **Composition Root** — все зависимости собираются в `provider_factory.build_consultation_service()`

---

## 🚀 Быстрый старт (Windows)

```bat
:: 1. Клонировать
git clone https://github.com/markmus11012020-max/Health-Bot-AI.git
cd Health-Bot-AI

:: 2. Создать .env из пресета
copy .env.example .env
notepad .env       :: заполнить AITUNNEL_API_KEY, YANDEX_API_KEY, YANDEX_FOLDER_ID

:: 3. Запустить (автоматически: стоп процессов → чистка кэша → venv → deps → старт)
start.bat
```

После запуска откройте <http://localhost:8501>.

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
| `AITUNNEL_MODEL`        | Модель AITunnel (на выбор: MiniMax-M3, Gemini, GPT) | `MiniMax-M3`        |
| `YANDEX_API_KEY`        | API-ключ YandexGPT                  | —                             |
| `YANDEX_FOLDER_ID`      | Folder ID Yandex Cloud              | —                             |
| `YANDEX_MODEL`          | Модель YandexGPT                    | `yandexgpt-lite`              |
| `TEMPERATURE`           | Температура генерации               | `0.2`                         |
| `MAX_TOKENS`            | Лимит токенов                       | `800`                         |
| `REQUEST_TIMEOUT`       | Таймаут HTTP-запроса (сек)          | `30`                          |
| `MAX_RETRIES`           | Число ретраев                       | `2`                           |
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

---

## 🔒 Безопасность и 152-ФЗ

`PIIAnonymizer` заменяет **до отправки** в LLM:

- Имена → `[Клиент]`
- Телефоны (все RU-форматы) → `[Телефон]`
- E-mail → `[Email]`
- Адреса → `[Адрес]`

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

# src/services/provider_factory.py
from src.ai.my_provider import MyProvider

AIOrchestrator(providers=[
    AITunnelClient(settings),
    MyProvider(settings),    # ← добавлено
    YandexGPTClient(settings),
])
```

UI / бизнес-логика менять **не нужно**.

---

## 📜 Лицензия

MIT © 2026 OCX / Health-Bot-AI Contributors.
Демонстрационный MVP для собеседования.