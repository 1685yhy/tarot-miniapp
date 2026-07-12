"""Tests for the Tarot mini-program API health endpoint."""

from contextlib import asynccontextmanager

from fastapi.testclient import TestClient

from app.main import app


@asynccontextmanager
async def noop_lifespan(_app):
    """No-op lifespan to avoid DB dependency during test."""
    yield


def test_health():
    """Health endpoint should return 200 with status ok."""
    # Suppress lifespan to avoid DB dependency during test
    app.router.lifespan_context = noop_lifespan
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
