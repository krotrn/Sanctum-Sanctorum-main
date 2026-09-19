"""Shared test fixtures.  You should NOT need to modify this file.

Every test gets a brand-new in-memory SQLite database and a frozen clock.
"""
from datetime import datetime, timedelta
from itertools import count

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registers tables on Base.metadata)
from app.clock import get_now
from app.db import Base, get_db
from app.main import create_app

START = datetime(2026, 1, 1, 12, 0, 0)


class FrozenClock:
    """A controllable replacement for ``app.clock.get_now``."""

    def __init__(self, start: datetime) -> None:
        self.current = start

    def __call__(self) -> datetime:
        return self.current

    def advance(self, **kwargs) -> datetime:
        self.current += timedelta(**kwargs)
        return self.current


def isbn13(seed: int) -> str:
    """Build a checksum-valid ISBN-13 from an integer seed."""
    body = f"978{seed:09d}"
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(body))
    return body + str((10 - total % 10) % 10)


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(START)


@pytest.fixture
def client(clock):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    application = create_app(init_db=False)
    application.dependency_overrides[get_db] = override_get_db
    application.dependency_overrides[get_now] = clock
    with TestClient(application) as test_client:
        yield test_client
    engine.dispose()


@pytest.fixture
def make_book(client):
    seeds = count(1)

    def _make(**overrides) -> dict:
        n = next(seeds)
        payload = {
            "title": f"Test Book {n}",
            "author": f"Author {n}",
            "isbn": isbn13(n),
            "price_cents": 1000,
            "stock": 10,
            "restricted": False,
        }
        payload.update(overrides)
        response = client.post("/books", json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    return _make


@pytest.fixture
def make_member(client):
    seeds = count(1)

    def _make(**overrides) -> dict:
        n = next(seeds)
        payload = {"name": f"Member {n}", "email": f"member{n}@example.com", "tier": "apprentice"}
        payload.update(overrides)
        response = client.post("/members", json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    return _make
