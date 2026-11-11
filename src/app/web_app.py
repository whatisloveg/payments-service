import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from faststream.rabbit import Channel, RabbitBroker

from app.api.v1.payments import router as payments_router
from app.core.logging import setup_logging
from app.core.settings import settings
from app.infrastructure.db.session import engine, session_factory
from app.infrastructure.messaging.outbox_relay import OutboxRelay

setup_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Запускает relay outbox вместе с API"""
    # без on_return_raises сообщение, которое некуда положить, молча пропадет
    broker = RabbitBroker(settings.rabbitmq_url, default_channel=Channel(on_return_raises=True))
    relay = OutboxRelay(
        session_factory,
        broker,
        retry_delays=settings.retry_delays,
        batch_size=settings.outbox_batch_size,
        poll_interval=settings.outbox_poll_interval,
    )
    relay_task = asyncio.create_task(relay.run())

    yield

    relay_task.cancel()
    with suppress(asyncio.CancelledError):
        await relay_task
    await broker.stop()
    await engine.dispose()


app = FastAPI(title="Payments", lifespan=lifespan)
app.include_router(payments_router, prefix="/api/v1")
