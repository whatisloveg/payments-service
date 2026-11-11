from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.application.interfaces import UnitOfWorkFactory
from app.domain.exceptions import PaymentNotFound
from app.domain.payment import Currency, Payment


@dataclass(frozen=True)
class NewPayment:
    amount: Decimal
    currency: Currency
    description: str
    metadata: dict[str, Any]
    webhook_url: str


class IdempotencyConflict(Exception):
    """Ключ уже занят платежом с другими параметрами"""


class PaymentService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def create(self, data: NewPayment, idempotency_key: str) -> Payment:
        """Создает платеж, на повтор отдает уже созданный"""
        async with self._uow_factory() as uow:
            payment = await uow.payments.get_by_idempotency_key(idempotency_key)
            if payment is None:
                payment = Payment.create(idempotency_key=idempotency_key, **asdict(data))
                if await uow.payments.add(payment):
                    uow.outbox.put(payment.pull_events())
                    await uow.commit()
                    return payment
                # ключ только что занял параллельный запрос
                payment = await uow.payments.get_by_idempotency_key(idempotency_key)

        if not _same_request(payment, data):
            raise IdempotencyConflict(idempotency_key)
        return payment

    async def get(self, payment_id: UUID) -> Payment:
        async with self._uow_factory() as uow:
            payment = await uow.payments.get(payment_id)
        if payment is None:
            raise PaymentNotFound(payment_id)
        return payment


def _same_request(payment: Payment, data: NewPayment) -> bool:
    return (
        payment.amount == data.amount
        and payment.currency == data.currency
        and payment.description == data.description
        and payment.metadata == data.metadata
        and payment.webhook_url == data.webhook_url
    )
