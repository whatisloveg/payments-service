import logging
from uuid import UUID

from app.application.interfaces import PaymentGateway, UnitOfWorkFactory, WebhookSender
from app.domain.exceptions import PaymentNotFound
from app.domain.payment import Payment

logger = logging.getLogger(__name__)


class PaymentProcessor:
    """Проводит платеж через шлюз, сохраняет итог и отправляет webhook"""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        gateway: PaymentGateway,
        webhooks: WebhookSender,
    ) -> None:
        self._uow_factory = uow_factory
        self._gateway = gateway
        self._webhooks = webhooks

    async def process(self, payment_id: UUID) -> Payment:
        async with self._uow_factory() as uow:
            payment = await uow.payments.get(payment_id)
        if payment is None:
            raise PaymentNotFound(payment_id)

        # при повторной доставке платеж уже проведен, осталось только уведомить
        if not payment.is_processed:
            payment = await self._charge(payment)

        await self._webhooks.send(payment)
        logger.info("Платеж %s: webhook отправлен", payment.id)
        return payment

    async def _charge(self, payment: Payment) -> Payment:
        # настоящему шлюзу передали бы payment.id как ключ идемпотентности
        if await self._gateway.charge(payment):
            payment.succeed()
        else:
            payment.fail()

        async with self._uow_factory() as uow:
            if not await uow.payments.save_result(payment):
                # платеж параллельно провел другой обработчик, берем его итог
                saved = await uow.payments.get(payment.id)
                if saved is None:
                    raise PaymentNotFound(payment.id)
                return saved
            await uow.commit()

        logger.info("Платеж %s: %s", payment.id, payment.status)
        return payment
