from collections.abc import Callable, Iterable
from typing import Protocol, Self

from app.domain.events import DomainEvent
from app.domain.payment import Payment
from app.domain.repositories import PaymentRepository


class Outbox(Protocol):
    """События на отправку в брокер"""

    def put(self, events: Iterable[DomainEvent]) -> None: ...


class UnitOfWork(Protocol):
    """Одна транзакция"""

    payments: PaymentRepository
    outbox: Outbox

    async def __aenter__(self) -> Self: ...

    async def __aexit__(self, *exc_info: object) -> None: ...

    async def commit(self) -> None: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]


class PaymentGateway(Protocol):
    async def charge(self, payment: Payment) -> bool:
        """True, если шлюз провел платеж"""


class WebhookSender(Protocol):
    async def send(self, payment: Payment) -> None:
        """Сообщает клиенту итог платежа"""
