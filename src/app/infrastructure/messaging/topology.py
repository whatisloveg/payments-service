from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

PAYMENTS_NEW = "payments.new"
PAYMENTS_NEW_DLQ = "payments.new.dlq"

payments_exchange = RabbitExchange("payments", type=ExchangeType.DIRECT, durable=True)
dead_letter_exchange = RabbitExchange("payments.dlx", type=ExchangeType.DIRECT, durable=True)

payments_new_queue = RabbitQueue(
    PAYMENTS_NEW,
    durable=True,
    arguments={
        "x-dead-letter-exchange": dead_letter_exchange.name,
        "x-dead-letter-routing-key": PAYMENTS_NEW_DLQ,
    },
)
dead_letter_queue = RabbitQueue(PAYMENTS_NEW_DLQ, durable=True)


def retry_queue(delay: int) -> RabbitQueue:
    """Очередь-задержка: по TTL сообщение возвращается в payments.new"""
    return RabbitQueue(
        f"{PAYMENTS_NEW}.retry.{delay}s",
        durable=True,
        arguments={
            "x-message-ttl": delay * 1000,
            "x-dead-letter-exchange": payments_exchange.name,
            "x-dead-letter-routing-key": PAYMENTS_NEW,
        },
    )


def next_retry_delay(attempt: int, delays: list[int]) -> int | None:
    """Пауза перед следующей попыткой или None, если они кончились"""
    return delays[attempt - 1] if attempt <= len(delays) else None


async def declare_topology(broker: RabbitBroker, retry_delays: list[int]) -> None:
    """Объявляет обменники, очереди и привязки"""
    exchange = await broker.declare_exchange(payments_exchange)
    dlx = await broker.declare_exchange(dead_letter_exchange)

    queue = await broker.declare_queue(payments_new_queue)
    await queue.bind(exchange, routing_key=PAYMENTS_NEW)

    dlq = await broker.declare_queue(dead_letter_queue)
    await dlq.bind(dlx, routing_key=PAYMENTS_NEW_DLQ)

    # в ретрай-очереди пишем через exchange по умолчанию, биндинги не нужны
    for delay in retry_delays:
        await broker.declare_queue(retry_queue(delay))
