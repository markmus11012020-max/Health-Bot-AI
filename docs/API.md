# API Health-Bot-AI

Базовый URL: `http://localhost:8080`

Все эндпоинты, кроме `/health` и `/ready`, требуют заголовок `X-API-Key`,
если в окружении задан `API_KEY`. В production `API_KEY` обязателен.

## Аутентификация

```http
X-API-Key: <API_KEY>
```

Административные операции:

```http
X-Admin-Key: <ADMIN_API_KEY>
```

## POST /v1/consult

Обработать обращение клиента.

### Запрос

```json
{
  "crm_context": "Клиент: Мария, оформляет Детокс 4500 руб.",
  "client_message": "Сколько стоит доставка в Самару?",
  "provider": "aitunnel",
  "prompt_variant": "warm",
  "use_cache": true
}
```

| Поле | Тип | Обязательно | Описание |
|---|---|---|---|
| `crm_context` | string | да | Контекст сделки, 1–4000 символов |
| `client_message` | string | да | Сообщение клиента, 1–4000 символов |
| `provider` | `aitunnel` \| `yandex` | нет | Переопределить провайдера |
| `prompt_variant` | `standard` \| `expert` \| `warm` | нет | Переопределить промпт |
| `use_cache` | boolean | нет | Использовать кэш, по умолчанию `true` |
| `conversation_id` | string | нет | Идентификатор диалога для истории |

Заголовки:

```http
X-API-Key: ...
Idempotency-Key: 8f14e45f-ea3b-4f2a-9d1c-2b7f6a1e9c33
X-Request-ID: optional
```

### Ответ 200

```json
{
  "request_id": "0f9f5e2a-...",
  "client_answer": "Здравствуйте! Доставка в Самару — 300 ₽...",
  "manager_tip": "Предложите Витамин-Буст со скидкой 20%...",
  "needs_upsell": true,
  "citations": ["О-комплекс Детокс", "Условия доставки"],
  "confidence": 0.86,
  "safety_flags": [],
  "provider": "AITunnel",
  "model": "minimax-m3",
  "cache_hit": false,
  "response_chars": 542,
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0
  }
}
```

### Ошибки

| Код | Причина |
|---|---|
| 401 | Неверный или отсутствующий API-ключ |
| 422 | Ошибка валидации |
| 429 | Превышен rate limit |
| 502 | Провайдер LLM недоступен |
| 500 | Внутренняя ошибка без stack trace |

## POST /v1/consult/stream

То же тело, что у `/v1/consult`. Ответ — `text/event-stream`:

```text
event: meta
data: {"request_id":"...","provider":"AITunnel"}

event: token
data: {"text":"Здравствуйте"}

event: token
data: {"text":", доставка"}

event: done
data: {"cache_hit":false,"response_chars":542}
```

При ошибке после первого токена поток завершается событием `error`; fallback
на другого провайдера не выполняется, чтобы не смешивать ответы.

## POST /v1/feedback

Оценка менеджера.

```json
{
  "request_id": "0f9f5e2a-...",
  "rating": 5,
  "correct": true,
  "comment": "Хороший ответ"
}
```

`comment` анонимизируется перед сохранением: в БД не должны попадать сырые
ПДн.

## GET /health

Liveness probe.

```json
{"status": "ok", "version": "1.0.0"}
```

## GET /ready

Readiness probe: проверяет БД, кэш и наличие ключей провайдеров.

```json
{
  "status": "ready",
  "database": "ok",
  "cache": "ok",
  "providers": {"aitunnel": "configured", "yandex": "not_configured"}
}
```

## POST /v1/admin/cache/clear

Сброс кэша. Требует `X-Admin-Key`.

```json
{"cleared_entries": 12}
```

## Совместимость

Старые эндпоинты `/consult`, `/consult/clear-cache` сохранены как алиасы
`/v1/consult` и `/v1/admin/cache/clear` для обратной совместимости.
