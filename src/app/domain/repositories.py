from typing import Protocol
from uuid import UUID

from app.domain.payment import Payment


class PaymentRepository(Protocol):
    async def get(self, payment_id: UUID) -> Payment | None: ...

    async def get_by_idempotency_key(self, key: str) -> Payment | None: ...

    async def add(self, payment: Payment) -> bool:
        """False, если платеж с таким ключом уже есть"""

    async def save_result(self, payment: Payment) -> bool:
        """Сохраняет итог, если платеж еще в статусе pending, иначе False"""
