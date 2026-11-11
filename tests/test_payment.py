from decimal import Decimal

import pytest

from app.domain.events import PaymentCreated
from app.domain.exceptions import InvalidPayment, PaymentAlreadyProcessed
from app.domain.payment import PaymentStatus
from tests.fakes import make_payment


def test_new_payment():
    payment = make_payment()

    assert payment.status == PaymentStatus.PENDING
    assert payment.processed_at is None
    assert payment.pull_events() == [PaymentCreated(payment.id)]
    assert payment.pull_events() == []


def test_succeed_sets_processing_time():
    payment = make_payment()

    payment.succeed()

    assert payment.status == PaymentStatus.SUCCEEDED
    assert payment.processed_at is not None


def test_processed_payment_cannot_change_status():
    payment = make_payment()
    payment.fail()

    with pytest.raises(PaymentAlreadyProcessed):
        payment.succeed()


@pytest.mark.parametrize("amount", [Decimal("0"), Decimal("-1.50")])
def test_amount_must_be_positive(amount):
    with pytest.raises(InvalidPayment):
        make_payment(amount=amount)
