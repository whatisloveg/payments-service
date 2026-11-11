import asyncio
import random

from app.domain.payment import Payment


class FakePaymentGateway:
    """Эмулятор платежного шлюза"""

    def __init__(self, min_delay: float, max_delay: float, success_rate: float) -> None:
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._success_rate = success_rate

    async def charge(self, payment: Payment) -> bool:
        await asyncio.sleep(random.uniform(self._min_delay, self._max_delay))
        return random.random() < self._success_rate
