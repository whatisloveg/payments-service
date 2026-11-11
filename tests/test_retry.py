from app.core.settings import Settings
from app.infrastructure.messaging.topology import next_retry_delay


def test_delays_grow_exponentially():
    assert Settings(retry_attempts=4, retry_base_delay=2).retry_delays == [2, 4, 8]


def test_last_attempt_goes_to_dlq():
    delays = Settings(retry_attempts=3, retry_base_delay=2).retry_delays

    assert [next_retry_delay(attempt, delays) for attempt in (1, 2, 3)] == [2, 4, None]
