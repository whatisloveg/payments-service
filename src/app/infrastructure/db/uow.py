from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.db.repositories import SqlOutbox, SqlPaymentRepository


class SqlUnitOfWork:
    """Транзакция поверх сессии SQLAlchemy"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        self.payments = SqlPaymentRepository(self._session)
        self.outbox = SqlOutbox(self._session)
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        # все, что не закоммитили, откатится при закрытии сессии
        await self._session.close()

    async def commit(self) -> None:
        await self._session.commit()
