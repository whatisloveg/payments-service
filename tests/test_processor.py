from uuid import uuid4

import pytest

from app.application.processing import PaymentProcessor
from app.domain.exceptions import PaymentNotFound
from app.domain.payment import PaymentStatus
from app.infrastructure.webhooks import WebhookDeliveryError
from tests.fakes import FakeWebhooks, StubGateway, make_payment


async def pending_payment(uow):
    payment = make_payment()
    await uow.payments.add(payment)
    return payment


@pytest.mark.parametrize(
    ("approve", "status"),
    [(True, PaymentStatus.SUCCEEDED), (False, PaymentStatus.FAILED)],
)
async def test_gateway_result(uow, approve, status):
    payment = await pending_payment(uow)
    webhooks = FakeWebhooks()
    processor = PaymentProcessor(lambda: uow, StubGateway(approve), webhooks)

    await processor.process(payment.id)

    saved = await uow.payments.get(payment.id)
    assert saved.status == status
    assert saved.processed_at is not None
    assert uow.commits == 1
    assert webhooks.sent == [(payment.id, status)]


async def test_redelivery_does_not_charge_twice(uow):
    payment = await pending_payment(uow)
    gateway = StubGateway()
    webhooks = FakeWebhooks()
    processor = PaymentProcessor(lambda: uow, gateway, webhooks)

    await processor.process(payment.id)
    await processor.process(payment.id)

    assert gateway.calls == 1
    assert len(webhooks.sent) == 2


async def test_status_is_kept_when_webhook_fails(uow):
    payment = await pending_payment(uow)
    webhooks = FakeWebhooks(error=WebhookDeliveryError("timeout"))
    processor = PaymentProcessor(lambda: uow, StubGateway(), webhooks)

    with pytest.raises(WebhookDeliveryError):
        await processor.process(payment.id)

    saved = await uow.payments.get(payment.id)
    assert saved.status == PaymentStatus.SUCCEEDED
    assert uow.commits == 1


async def test_parallel_result_wins(uow):
    payment = await pending_payment(uow)
    # пока наш шлюз думал, платеж уже провел другой обработчик
    other = await uow.payments.get(payment.id)
    other.fail()
    await uow.payments.save_result(other)
    uow.payments.get = _stale_first_read(uow.payments.get, payment)

    webhooks = FakeWebhooks()
    processor = PaymentProcessor(lambda: uow, StubGateway(approve=True), webhooks)
    result = await processor.process(payment.id)

    assert result.status == PaymentStatus.FAILED
    assert webhooks.sent == [(payment.id, PaymentStatus.FAILED)]


async def test_unknown_payment(uow):
    processor = PaymentProcessor(lambda: uow, StubGateway(), FakeWebhooks())

    with pytest.raises(PaymentNotFound):
        await processor.process(uuid4())


def _stale_first_read(get, stale):
    calls = 0

    async def wrapper(payment_id):
        nonlocal calls
        calls += 1
        return stale if calls == 1 else await get(payment_id)

    return wrapper
