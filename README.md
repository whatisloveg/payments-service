# Payments service

Асинхронная обработка платежей. API принимает платеж и сразу отвечает `202`, consumer проводит его через эмулятор шлюза и шлет результат на `webhook_url`.

FastAPI, SQLAlchemy 2 (async), PostgreSQL, RabbitMQ (FastStream), Alembic.

## Запуск

```bash
docker compose up --build
```

- Swagger: http://localhost:8000/docs, ключ `local-dev-key`
- RabbitMQ: http://localhost:15672, `payments` / `payments`

Миграции накатывает контейнер `migrations`, `api` и `consumer` стартуют после него. Ключ и порт можно поменять через `.env` (пример в `.env.example`).

## Примеры

Создать платеж:

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: local-dev-key" \
  -H "Idempotency-Key: order-10582" \
  -H "Content-Type: application/json" \
  -d '{"amount": "1500.00", "currency": "RUB", "description": "Заказ 10582", "metadata": {"order_id": 10582}, "webhook_url": "http://webhook-receiver:9000/payments"}'
```

Ответ, код 202:

```json
{"payment_id":"86f57c6a-33b8-471d-a95e-78aa118fabf0","status":"pending","created_at":"2026-11-11T00:23:37.653441Z"}
```

Через несколько секунд (шлюз отвечает 2-5 с) статус станет `succeeded` или `failed`:

```bash
curl http://localhost:8000/api/v1/payments/<payment_id> -H "X-API-Key: local-dev-key"
```

Webhook в примере уходит на `webhook-receiver`. Это маленький сервер в compose, он изображает сервер клиента: принимает webhook и печатает его в лог. К самому сервису платежей он не относится, нужен только чтобы было куда слать webhook при проверке.

```bash
docker compose logs -f webhook-receiver
```

Повтор запроса с тем же `Idempotency-Key` вернет тот же платеж. Тот же ключ с другим телом - `409`.

Ретраи и DLQ проверяются через `"webhook_url": "http://webhook-receiver:9000/fail"`: на этот путь receiver отвечает 500, consumer делает 3 попытки с паузами 2 и 4 с, потом сообщение уходит в `payments.new.dlq`. Логи consumer:

```bash
docker compose logs -f consumer
```

## Обработка платежа

1. `POST /api/v1/payments` в одной транзакции сохраняет платеж и запись в таблицу `outbox`.
2. Relay в процессе API раз в секунду забирает неотправленные записи и публикует их в exchange `payments` с ключом `payments.new`. Запись помечается отправленной только после подтверждения от брокера. Если RabbitMQ недоступен, API продолжает принимать платежи, события ждут в `outbox`.
3. Consumer читает `payments.new`, ждет ответа шлюза, сохраняет статус и отправляет webhook.
4. При ошибке сообщение уходит в ретрай-очередь `payments.new.retry.<N>s`, а через TTL возвращается в `payments.new`. Номер попытки лежит в заголовке `x-attempt`.
5. Когда попытки кончились, consumer делает `reject`, и RabbitMQ перекладывает сообщение через `payments.dlx` в `payments.new.dlq`.

Доставка at-least-once, так что дубли consumer должен переживать спокойно. Если платеж уже не `pending`, шлюз второй раз не вызывается, повторяется только webhook. Статус пишется с условием `WHERE status = 'pending'`: два обработчика одного платежа друг друга не перезапишут.

Два одновременных запроса с одним `Idempotency-Key` тоже не создадут два платежа: на ключе уникальный индекс, вставка идет через `ON CONFLICT DO NOTHING`.

Под каждую задержку своя очередь. Если держать сообщения с разным TTL в одной, короткие будут ждать, пока истечет длинное перед ними.

Webhook - POST с JSON, успехом считается любой ответ 2xx:

```json
{"payment_id":"86f57c6a-33b8-471d-a95e-78aa118fabf0","status":"failed","amount":"1500.00","currency":"RUB","metadata":{"order_id":10582},"processed_at":"2026-11-11T00:23:40.375986+00:00"}
```

## Структура

Код в `src/app` разложен по слоям `domain`, `application`, `infrastructure`, `api`, настройки и логи в `core`. Точки входа - `web_app.py` и `consumer_app.py`.

## Тесты

База и брокер для тестов не нужны, нужен Python 3.12+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r src/requirements.txt
pytest
```

## Настройки

Все настройки в `src/app/core/settings.py`, любую можно задать переменной окружения (`RETRY_ATTEMPTS`, `GATEWAY_SUCCESS_RATE` и т.д.). Из `.env` compose берет только `API_KEY`, `API_PORT` и `LOG_LEVEL`, остальные надо добавить в `environment`.
