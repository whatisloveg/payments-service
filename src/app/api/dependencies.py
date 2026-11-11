import secrets
from typing import Annotated

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.application.payments import PaymentService
from app.core.settings import settings
from app.infrastructure.db.session import session_factory
from app.infrastructure.db.uow import SqlUnitOfWork

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(api_key: Annotated[str | None, Security(api_key_header)]) -> None:
    """Проверяет X-API-Key"""
    if api_key is None or not secrets.compare_digest(api_key.encode(), settings.api_key.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный X-API-Key")


def get_payment_service() -> PaymentService:
    return PaymentService(lambda: SqlUnitOfWork(session_factory))
