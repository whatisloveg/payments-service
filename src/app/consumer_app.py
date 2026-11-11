import asyncio
import logging

import httpx
from faststream import FastStream
from faststream.exceptions import RejectMessage
from faststream.rabbit import Channel, RabbitBroker, RabbitMessage

from app.application.processing import PaymentProcessor
from app.core.logging import setup_logging
from app.core.settings import settings
from app.domain.exceptions import PaymentNotFound
from app.infrastructure.db.session import engine, session_factory
from app.infrastructure.db.uow import SqlUnitOfWork
from app.infrastructure.gateway import FakePaymentGateway
from app.infrastructure.messaging.contracts import PaymentCreatedMessage
from app.infrastructure.messaging.topology import (
    declare_topology,
    next_retry_delay,
    payments_exchange,
    payments_new_queue,
    retry_queue,
)
from app.infrastructure.webhooks import HttpWebhookSender

setup_logging(settings.log_level)
logger = logging.getLogger("consumer")

ATTEMPT_HEADER = "x-attempt"

broker = RabbitBroker(
    settings.rabbitmq_url,
    # без prefetch брокер отдаст всю очередь разом и все пойдет параллельно
    default_channel=Channel(prefetch_count=settings.consumer_prefetch, on_return_raises=True),
)
app = FastStream(broker)

http_client = httpx.AsyncClient(timeout=settings.webhook_timeout)
processor = PaymentProcessor(
    uow_factory=lambda: SqlUnitOfWork(session_factory),
    gateway=FakePaymentGateway(
        min_delay=settings.gateway_min_delay,
        max_delay=settings.gateway_max_delay,
        success_rate=settings.gateway_success_rate,
    ),
    webhooks=HttpWebhookSender(http_client),
)


@app.on_startup
async def setup_topology() -> None:
    # DLQ и ретрай-очереди должны быть до первого сообщения
    await broker.connect()
    await declare_topology(broker, settings.retry_delays)


@app.after_shutdown
async def close_resources() -> None:
    await http_client.aclose()
    await engine.dispose()


@broker.subscriber(payments_new_queue, payments_exchange)
async def handle_new_payment(event: PaymentCreatedMessage, message: RabbitMessage) -> None:
    """Обрабатывает платеж из очереди"""
    attempt = int(message.headers.get(ATTEMPT_HEADER, 1))
    try:
        await processor.process(event.payment_id)
    except PaymentNotFound:
        logger.error("Платеж %s не найден, сообщение в DLQ", event.payment_id)
        raise RejectMessage() from None
    except Exception as exc:
        delay = next_retry_delay(attempt, settings.retry_delays)
        if delay is None:
            logger.exception(
                "Платеж %s: попытки кончились (%s), сообщение в DLQ", event.payment_id, attempt
            )
            raise RejectMessage() from exc

        logger.warning(
            "Платеж %s: попытка %s не удалась (%s), повтор через %s с",
            event.payment_id,
            attempt,
            exc,
            delay,
        )
        await broker.publish(
            event,
            queue=retry_queue(delay),
            headers={ATTEMPT_HEADER: attempt + 1},
            message_id=message.message_id,
            persist=True,
        )


if __name__ == "__main__":
    asyncio.run(app.run())
