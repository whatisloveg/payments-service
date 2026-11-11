from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.events import DomainEvent
from app.domain.payment import Currency, Payment, PaymentStatus
from app.infrastructure.db.models import OutboxRow, PaymentRow
from app.infrastructure.messaging.contracts import to_message


class SqlPaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, payment_id: UUID) -> Payment | None:
        row = await self._session.get(PaymentRow, payment_id)
        return _to_entity(row) if row else None

    async def get_by_idempotency_key(self, key: str) -> Payment | None:
        row = await self._session.scalar(
            select(PaymentRow).where(PaymentRow.idempotency_key == key)
        )
        return _to_entity(row) if row else None

    async def add(self, payment: Payment) -> bool:
        stmt = (
            insert(PaymentRow)
            .values(
                id=payment.id,
                amount=payment.amount,
                currency=payment.currency.value,
                description=payment.description,
                meta=payment.metadata,
                status=payment.status.value,
                idempotency_key=payment.idempotency_key,
                webhook_url=payment.webhook_url,
                created_at=payment.created_at,
            )
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
            .returning(PaymentRow.id)
        )
        return await self._session.scalar(stmt) is not None

    async def save_result(self, payment: Payment) -> bool:
        result = await self._session.execute(
            update(PaymentRow)
            .where(PaymentRow.id == payment.id, PaymentRow.status == PaymentStatus.PENDING.value)
            .values(status=payment.status.value, processed_at=payment.processed_at)
        )
        return result.rowcount == 1


class SqlOutbox:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def put(self, events: Iterable[DomainEvent]) -> None:
        for event in events:
            routing_key, payload = to_message(event)
            self._session.add(OutboxRow(routing_key=routing_key, payload=payload))


def _to_entity(row: PaymentRow) -> Payment:
    return Payment(
        id=row.id,
        amount=row.amount,
        currency=Currency(row.currency),
        description=row.description,
        metadata=row.meta,
        idempotency_key=row.idempotency_key,
        webhook_url=row.webhook_url,
        status=PaymentStatus(row.status),
        created_at=row.created_at,
        processed_at=row.processed_at,
    )
