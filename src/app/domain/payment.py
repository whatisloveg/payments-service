import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Self

from app.domain.events import DomainEvent, PaymentCreated
from app.domain.exceptions import InvalidPayment, PaymentAlreadyProcessed


class Currency(StrEnum):
    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class Payment:
    """Платеж и переходы его статуса"""

    id: uuid.UUID
    amount: Decimal
    currency: Currency
    description: str
    metadata: dict[str, Any]
    idempotency_key: str
    webhook_url: str
    status: PaymentStatus
    created_at: datetime
    processed_at: datetime | None = None
    events: list[DomainEvent] = field(default_factory=list, init=False, repr=False, compare=False)

    @classmethod
    def create(
        cls,
        *,
        amount: Decimal,
        currency: Currency,
        description: str,
        metadata: dict[str, Any],
        idempotency_key: str,
        webhook_url: str,
    ) -> Self:
        """Новый платеж в статусе pending"""
        if amount <= 0:
            raise InvalidPayment("Сумма должна быть больше нуля")

        payment = cls(
            id=uuid.uuid4(),
            amount=amount,
            currency=currency,
            description=description,
            metadata=metadata,
            idempotency_key=idempotency_key,
            webhook_url=webhook_url,
            status=PaymentStatus.PENDING,
            created_at=datetime.now(UTC),
        )
        payment.events.append(PaymentCreated(payment.id))
        return payment

    @property
    def is_processed(self) -> bool:
        return self.status != PaymentStatus.PENDING

    def succeed(self) -> None:
        self._finish(PaymentStatus.SUCCEEDED)

    def fail(self) -> None:
        self._finish(PaymentStatus.FAILED)

    def pull_events(self) -> list[DomainEvent]:
        """Отдает накопленные события и очищает список"""
        events, self.events = self.events, []
        return events

    def _finish(self, status: PaymentStatus) -> None:
        if self.is_processed:
            raise PaymentAlreadyProcessed(self.id)
        self.status = status
        self.processed_at = datetime.now(UTC)
