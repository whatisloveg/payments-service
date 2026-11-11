from decimal import Decimal
from uuid import uuid4

import pytest

from app.application.payments import IdempotencyConflict, NewPayment, PaymentService
from app.domain.events import PaymentCreated
from app.domain.exceptions import PaymentNotFound
from app.domain.payment import Currency, PaymentStatus


def new_payment(**overrides) -> NewPayment:
    fields = {
        "amount": Decimal("100.00"),
        "currency": Currency.RUB,
        "description": "Заказ 731",
        "metadata": {"order_id": 731},
        "webhook_url": "http://client.test/hook",
    }
    return NewPayment(**fields | overrides)


@pytest.fixture
def service(uow) -> PaymentService:
    return PaymentService(lambda: uow)


async def test_create_writes_outbox(service, uow):
    payment = await service.create(new_payment(), "key-1")

    assert payment.status == PaymentStatus.PENDING
    assert payment.id in uow.payments.rows
    assert uow.outbox.events == [PaymentCreated(payment.id)]
    assert uow.commits == 1


async def test_repeat_same_key(service, uow):
    first = await service.create(new_payment(), "key-1")
    second = await service.create(new_payment(), "key-1")

    assert second.id == first.id
    assert len(uow.payments.rows) == 1
    assert len(uow.outbox.events) == 1


async def test_same_key_other_params(service):
    await service.create(new_payment(), "key-1")

    with pytest.raises(IdempotencyConflict):
        await service.create(new_payment(amount=Decimal("5.00")), "key-1")


async def test_key_taken_by_parallel_request(service, uow):
    first = await service.create(new_payment(), "key-1")

    # второй запрос проверил ключ раньше, чем первый закоммитился
    lookup = uow.payments.get_by_idempotency_key
    calls = 0

    async def late_lookup(key):
        nonlocal calls
        calls += 1
        return None if calls == 1 else await lookup(key)

    uow.payments.get_by_idempotency_key = late_lookup
    second = await service.create(new_payment(), "key-1")

    assert second.id == first.id
    assert len(uow.outbox.events) == 1


async def test_get_unknown_payment(service):
    with pytest.raises(PaymentNotFound):
        await service.get(uuid4())
