from uuid import uuid4

import pytest
from faststream.rabbit import TestRabbitBroker
from faststream.rabbit.message import RabbitMessage

from app import consumer_app
from app.consumer_app import ATTEMPT_HEADER, broker
from app.domain.exceptions import PaymentNotFound
from app.infrastructure.messaging.topology import payments_exchange, payments_new_queue
from app.infrastructure.webhooks import WebhookDeliveryError


class FakeProcessor:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list = []

    async def process(self, payment_id) -> None:
        self.calls.append(payment_id)
        if self.error:
            raise self.error


@pytest.fixture
async def test_broker():
    async with TestRabbitBroker(broker) as test_broker:
        yield test_broker


@pytest.fixture
def retries(monkeypatch) -> list[dict]:
    sent = []
    publish = broker.publish

    async def spy(message=None, queue="", exchange=None, **kwargs):
        if exchange is None:
            sent.append({"queue": queue.name, "body": message, **kwargs})
            return None
        return await publish(message, queue, exchange, **kwargs)

    monkeypatch.setattr(broker, "publish", spy)
    return sent


@pytest.fixture
def rejected(monkeypatch) -> list[bool]:
    calls = []

    async def reject(self, *args, **kwargs):
        calls.append(True)

    monkeypatch.setattr(RabbitMessage, "reject", reject)
    return calls


async def deliver(test_broker, payment_id, attempt=None, message_id="msg-1"):
    await test_broker.publish(
        {"payment_id": str(payment_id)},
        exchange=payments_exchange,
        routing_key=payments_new_queue.name,
        headers={ATTEMPT_HEADER: attempt} if attempt else None,
        message_id=message_id,
    )


async def test_success(test_broker, retries, rejected, monkeypatch):
    processor = FakeProcessor()
    monkeypatch.setattr(consumer_app, "processor", processor)
    payment_id = uuid4()

    await deliver(test_broker, payment_id)

    assert processor.calls == [payment_id]
    assert retries == []
    assert rejected == []


@pytest.mark.parametrize(("attempt", "queue"), [(None, "2s"), (2, "4s")])
async def test_failure_goes_to_retry_queue(
    test_broker, retries, rejected, monkeypatch, attempt, queue
):
    monkeypatch.setattr(consumer_app, "processor", FakeProcessor(WebhookDeliveryError("500")))
    payment_id = uuid4()

    await deliver(test_broker, payment_id, attempt)

    assert rejected == []
    [retry] = retries
    assert retry["queue"] == f"payments.new.retry.{queue}"
    assert retry["body"].payment_id == payment_id
    assert retry["headers"] == {ATTEMPT_HEADER: (attempt or 1) + 1}
    assert retry["message_id"] == "msg-1"


async def test_last_attempt_is_rejected(test_broker, retries, rejected, monkeypatch):
    monkeypatch.setattr(consumer_app, "processor", FakeProcessor(WebhookDeliveryError("500")))

    await deliver(test_broker, uuid4(), attempt=3)

    assert retries == []
    assert rejected == [True]


async def test_unknown_payment_is_rejected_at_once(test_broker, retries, rejected, monkeypatch):
    payment_id = uuid4()
    monkeypatch.setattr(consumer_app, "processor", FakeProcessor(PaymentNotFound(payment_id)))

    await deliver(test_broker, payment_id)

    assert retries == []
    assert rejected == [True]
