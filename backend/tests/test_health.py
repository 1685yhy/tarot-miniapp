"""Tests for the Tarot mini-program API health endpoint."""

from fastapi.testclient import TestClient
from app.main import app


def test_health():
    """Health endpoint should return 200 with status ok."""
    # Disable lifespan to avoid DB dependency during test
    app.router.lifespan_context = None
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
