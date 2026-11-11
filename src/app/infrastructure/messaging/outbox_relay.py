import asyncio
import logging
from datetime import UTC, datetime

from faststream.rabbit import RabbitBroker
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.db.models import OutboxRow
from app.infrastructure.messaging.topology import declare_topology, payments_exchange

logger = logging.getLogger(__name__)

RECONNECT_DELAY = 5


class OutboxRelay:
    """Перекладывает события из таблицы outbox в RabbitMQ"""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        broker: RabbitBroker,
        retry_delays: list[int],
        batch_size: int,
        poll_interval: float,
    ) -> None:
        self._session_factory = session_factory
        self._broker = broker
        self._retry_delays = retry_delays
        self._batch_size = batch_size
        self._poll_interval = poll_interval

    async def run(self) -> None:
        await self._connect()
        while True:
            try:
                sent = await self.publish_pending()
            except Exception:
                logger.exception("Outbox: не удалось отправить пачку")
                sent = 0
            # полная пачка - значит в outbox есть еще, спать рано
            if sent < self._batch_size:
                await asyncio.sleep(self._poll_interval)

    async def publish_pending(self) -> int:
        """Отправляет одну пачку событий"""
        sent = 0
        async with self._session_factory() as session, session.begin():
            rows = await session.scalars(
                select(OutboxRow)
                .where(OutboxRow.published_at.is_(None))
                .order_by(OutboxRow.created_at)
                .limit(self._batch_size)
                # несколько инстансов API не возьмут одни и те же записи
                .with_for_update(skip_locked=True)
            )
            for row in rows.all():
                try:
                    await self._broker.publish(
                        row.payload,
                        exchange=payments_exchange,
                        routing_key=row.routing_key,
                        message_id=str(row.id),
                        persist=True,
                    )
                except Exception:
                    logger.warning(
                        "Outbox: %s не опубликован, повтор в следующем цикле", row.id, exc_info=True
                    )
                    break
                row.published_at = datetime.now(UTC)
                sent += 1

        if sent:
            logger.info("Outbox: опубликовано %s", sent)
        return sent

    async def _connect(self) -> None:
        # без брокера API все равно принимает платежи, события ждут в outbox
        while True:
            try:
                await self._broker.connect()
                await declare_topology(self._broker, self._retry_delays)
                return
            except Exception as exc:
                logger.warning("RabbitMQ недоступен (%r), повтор через %s с", exc, RECONNECT_DELAY)
                await asyncio.sleep(RECONNECT_DELAY)
