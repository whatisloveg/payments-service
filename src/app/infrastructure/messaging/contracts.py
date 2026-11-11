from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.domain.events import DomainEvent, PaymentCreated
from app.infrastructure.messaging.topology import PAYMENTS_NEW


class PaymentCreatedMessage(BaseModel):
    payment_id: UUID


def to_message(event: DomainEvent) -> tuple[str, dict[str, Any]]:
    """Ключ маршрутизации и тело сообщения для события"""
    if isinstance(event, PaymentCreated):
        message = PaymentCreatedMessage(payment_id=event.payment_id)
        return PAYMENTS_NEW, message.model_dump(mode="json")
    raise TypeError(f"Нет сообщения для события {type(event).__name__}")
