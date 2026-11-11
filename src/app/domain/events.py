from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class DomainEvent:
    pass


@dataclass(frozen=True)
class PaymentCreated(DomainEvent):
    payment_id: UUID
