"""
TDD Gate - Phase 0
Tests the /api/health endpoint.
Uses conftest.py app fixture (DB dependency overridden).
"""

import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_health_returns_200(client):
    response = await client.get("/api/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_returns_correct_body(client):
    response = await client.get("/api/health")
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "saral-chatbot"
    assert "version" in body


@pytest.mark.asyncio
async def test_health_content_type_is_json(client):
    response = await client.get("/api/health")
    assert "application/json" in response.headers["content-type"]
