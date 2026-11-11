import copy
from decimal import Decimal
from uuid import UUID

from app.domain.payment import Currency, Payment, PaymentStatus


def make_payment(**overrides) -> Payment:
    fields = {
        "amount": Decimal("100.00"),
        "currency": Currency.RUB,
        "description": "Заказ 731",
        "metadata": {"order_id": 731},
        "idempotency_key": "key-1",
        "webhook_url": "http://client.test/hook",
    }
    return Payment.create(**fields | overrides)


# отдает копии, как база: без add/save_result изменения не видны
class FakePayments:
    def __init__(self) -> None:
        self.rows: dict[UUID, Payment] = {}

    async def get(self, payment_id: UUID) -> Payment | None:
        return copy.deepcopy(self.rows.get(payment_id))

    async def get_by_idempotency_key(self, key: str) -> Payment | None:
        for payment in self.rows.values():
            if payment.idempotency_key == key:
                return copy.deepcopy(payment)
        return None

    async def add(self, payment: Payment) -> bool:
        if any(p.idempotency_key == payment.idempotency_key for p in self.rows.values()):
            return False
        self.rows[payment.id] = copy.deepcopy(payment)
        return True

    async def save_result(self, payment: Payment) -> bool:
        if self.rows[payment.id].status != PaymentStatus.PENDING:
            return False
        self.rows[payment.id] = copy.deepcopy(payment)
        return True


class FakeOutbox:
    def __init__(self) -> None:
        self.events: list = []

    def put(self, events) -> None:
        self.events.extend(events)


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.payments = FakePayments()
        self.outbox = FakeOutbox()
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info) -> None:
        pass

    async def commit(self) -> None:
        self.commits += 1


class StubGateway:
    def __init__(self, approve: bool = True) -> None:
        self.approve = approve
        self.calls = 0

    async def charge(self, payment: Payment) -> bool:
        self.calls += 1
        return self.approve


class FakeWebhooks:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.sent: list[tuple[UUID, PaymentStatus]] = []

    async def send(self, payment: Payment) -> None:
        if self.error:
            raise self.error
        self.sent.append((payment.id, payment.status))
