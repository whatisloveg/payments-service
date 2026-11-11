from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    api_key: str = "local-dev-key"
    database_url: str = "postgresql+asyncpg://payments:payments@localhost:5432/payments"
    rabbitmq_url: str = "amqp://payments:payments@localhost:5672/"
    log_level: str = "INFO"

    outbox_batch_size: int = 100
    outbox_poll_interval: float = 1.0

    consumer_prefetch: int = 10

    # всего попыток на сообщение, паузы между ними 2 с, 4 с и т.д.
    retry_attempts: int = 3
    retry_base_delay: int = 2

    gateway_min_delay: float = 2.0
    gateway_max_delay: float = 5.0
    gateway_success_rate: float = 0.9

    webhook_timeout: float = 5.0

    @property
    def retry_delays(self) -> list[int]:
        return [self.retry_base_delay * 2**i for i in range(self.retry_attempts - 1)]


settings = Settings()
