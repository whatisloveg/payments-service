import pytest

from tests.fakes import FakeUnitOfWork


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()
