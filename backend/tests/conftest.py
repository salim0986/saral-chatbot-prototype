"""
Shared pytest fixtures for the SARAL Chatbot backend test suite.
Provides: in-memory SQLite DB, FastAPI test app with dependency overrides.
"""

import pytest
import aiosqlite
from httpx import ASGITransport, AsyncClient

from app.db import get_db, init_db


@pytest.fixture
async def test_db():
    """
    In-memory SQLite database with all tables created.
    Isolated per test - no state leaks between tests.
    """
    async with aiosqlite.connect(":memory:") as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON;")
        # Re-use the same schema from db.py
        from app.db import ALL_TABLES
        for stmt in ALL_TABLES:
            await db.execute(stmt)
        await db.commit()
        yield db


@pytest.fixture
def app(test_db):
    """
    FastAPI app with get_db overridden to use the in-memory test DB.
    This is the correct way to override FastAPI dependencies in tests.
    """
    from app.main import app as fastapi_app

    async def override_get_db():
        yield test_db

    fastapi_app.dependency_overrides[get_db] = override_get_db
    yield fastapi_app
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
async def client(app):
    """Pre-built AsyncClient for the test app."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
