import random

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


class FixedRandom(random.Random):
    """Random whose random()/uniform() return scripted values."""

    def __init__(self, value: float) -> None:
        super().__init__(0)
        self.value = value

    def random(self) -> float:
        return self.value

    def uniform(self, a: float, b: float) -> float:
        return a + (b - a) * self.value


async def _no_sleep(_seconds: float) -> None:
    return None


def make_client(flaky_rate: float = 0.05, rng_value: float = 0.5, **kw) -> TestClient:
    settings = Settings(flaky_error_rate=flaky_rate, **kw)
    return TestClient(
        create_app(settings=settings, rng=FixedRandom(rng_value), sleep=_no_sleep),
        raise_server_exceptions=False,
    )


@pytest.fixture
def client() -> TestClient:
    return make_client()
