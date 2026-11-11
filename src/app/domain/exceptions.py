from uuid import UUID


class DomainError(Exception):
    pass


class InvalidPayment(DomainError):
    pass


class PaymentNotFound(DomainError):
    def __init__(self, payment_id: UUID) -> None:
        super().__init__(f"Платеж {payment_id} не найден")
        self.payment_id = payment_id


class PaymentAlreadyProcessed(DomainError):
    def __init__(self, payment_id: UUID) -> None:
        super().__init__(f"Платеж {payment_id} уже обработан")
        self.payment_id = payment_id
