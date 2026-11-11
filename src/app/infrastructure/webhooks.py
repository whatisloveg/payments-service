import httpx

from app.domain.payment import Payment


class WebhookDeliveryError(Exception):
    """Webhook не доставлен"""


class HttpWebhookSender:
    """Отправляет итог платежа на webhook_url"""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def send(self, payment: Payment) -> None:
        body = {
            "payment_id": str(payment.id),
            "status": payment.status,
            "amount": str(payment.amount),
            "currency": payment.currency,
            "metadata": payment.metadata,
            "processed_at": payment.processed_at.isoformat() if payment.processed_at else None,
        }
        try:
            response = await self._client.post(payment.webhook_url, json=body)
        except httpx.HTTPError as exc:
            raise WebhookDeliveryError(f"{payment.webhook_url}: {exc!r}") from exc

        if not response.is_success:
            raise WebhookDeliveryError(f"{payment.webhook_url} ответил {response.status_code}")
