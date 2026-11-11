from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.api.dependencies import get_payment_service, require_api_key
from app.api.v1.schemas import PaymentAccepted, PaymentCreate, PaymentDetails
from app.application.payments import IdempotencyConflict, NewPayment, PaymentService
from app.domain.exceptions import PaymentNotFound

router = APIRouter(prefix="/payments", tags=["payments"], dependencies=[Depends(require_api_key)])

Service = Annotated[PaymentService, Depends(get_payment_service)]


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_payment(
    body: PaymentCreate,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
    service: Service,
) -> PaymentAccepted:
    """Принимает платеж в обработку"""
    data = NewPayment(
        amount=body.amount,
        currency=body.currency,
        description=body.description,
        metadata=body.metadata,
        webhook_url=str(body.webhook_url),
    )
    try:
        payment = await service.create(data, idempotency_key)
    except IdempotencyConflict:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Idempotency-Key уже использован с другими параметрами платежа",
        ) from None

    return PaymentAccepted(
        payment_id=payment.id,
        status=payment.status,
        created_at=payment.created_at,
    )


@router.get("/{payment_id}")
async def get_payment(payment_id: UUID, service: Service) -> PaymentDetails:
    """Возвращает платеж по id"""
    try:
        payment = await service.get(payment_id)
    except PaymentNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    return PaymentDetails.from_entity(payment)
