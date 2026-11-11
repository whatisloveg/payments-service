from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import get_payment_service
from app.application.payments import PaymentService
from app.core.settings import settings
from app.web_app import app

BODY = {
    "amount": "100.50",
    "currency": "RUB",
    "description": "Заказ 731",
    "metadata": {"order_id": 731},
    "webhook_url": "http://client.test/hook",
}


@pytest.fixture
async def client(uow):
    app.dependency_overrides[get_payment_service] = lambda: PaymentService(lambda: uow)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": settings.api_key},
    ) as client:
        yield client
    app.dependency_overrides.clear()


async def test_wrong_api_key(client):
    response = await client.get(f"/api/v1/payments/{uuid4()}", headers={"X-API-Key": "nope"})

    assert response.status_code == 401


async def test_create_and_get(client):
    response = await client.post("/api/v1/payments", json=BODY, headers={"Idempotency-Key": "k1"})

    assert response.status_code == 202
    created = response.json()
    assert created["status"] == "pending"

    response = await client.get(f"/api/v1/payments/{created['payment_id']}")

    assert response.status_code == 200
    payment = response.json()
    assert payment["amount"] == "100.50"
    assert payment["currency"] == "RUB"
    assert payment["metadata"] == {"order_id": 731}
    assert payment["idempotency_key"] == "k1"
    assert payment["processed_at"] is None


async def test_repeat_returns_same_payment(client):
    first = await client.post("/api/v1/payments", json=BODY, headers={"Idempotency-Key": "k1"})
    second = await client.post("/api/v1/payments", json=BODY, headers={"Idempotency-Key": "k1"})

    assert second.status_code == 202
    assert second.json()["payment_id"] == first.json()["payment_id"]


async def test_same_key_with_other_body(client):
    await client.post("/api/v1/payments", json=BODY, headers={"Idempotency-Key": "k1"})
    response = await client.post(
        "/api/v1/payments",
        json=BODY | {"amount": "1.00"},
        headers={"Idempotency-Key": "k1"},
    )

    assert response.status_code == 409


async def test_idempotency_key_is_required(client):
    response = await client.post("/api/v1/payments", json=BODY)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "patch",
    [{"amount": "0"}, {"amount": "1.001"}, {"currency": "GBP"}, {"webhook_url": "not-a-url"}],
)
async def test_invalid_body(client, patch):
    response = await client.post(
        "/api/v1/payments",
        json=BODY | patch,
        headers={"Idempotency-Key": "k1"},
    )

    assert response.status_code == 422


async def test_unknown_payment(client):
    response = await client.get(f"/api/v1/payments/{uuid4()}")

    assert response.status_code == 404
