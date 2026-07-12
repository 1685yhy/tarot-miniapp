"""
Tests for the Tarot card catalog API.

- GET /cards          — list all cards (returns 78)
- GET /cards/{id}     — single card detail
- GET /cards/daily    — random daily card
"""

from fastapi.testclient import TestClient


def test_list_cards_returns_78(client: TestClient):
    """GET /cards should return a list of 78 tarot cards."""
    response = client.get("/cards")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 78
    assert len(data["cards"]) == 78


def test_list_cards_structure(client: TestClient):
    """Each card in the list should have the expected fields."""
    response = client.get("/cards")
    data = response.json()
    sample = data["cards"][0]
    expected_keys = {"id", "name_zh", "name_en", "card_number", "arcana", "suit", "element"}
    assert expected_keys.issubset(sample.keys())


def test_get_card_by_id(client: TestClient):
    """GET /cards/1 should return full card details."""
    response = client.get("/cards/1")
    assert response.status_code == 200
    card = response.json()
    assert card["id"] == 1
    # CardDetail fields
    for key in ("name_zh", "name_en", "meaning_upright", "meaning_reversed",
                "keywords_upright", "love_upright", "career_upright",
                "finance_upright", "health_upright", "image_description"):
        assert key in card


def test_get_card_404(client: TestClient):
    """GET /cards/999 should return 404."""
    response = client.get("/cards/999")
    assert response.status_code == 404


def test_daily_card(client: TestClient):
    """GET /cards/daily should return a single valid card."""
    response = client.get("/cards/daily")
    assert response.status_code == 200
    card = response.json()
    assert "id" in card
    assert "name_zh" in card
    assert card["arcana"] in ("major", "minor")


def test_list_cards_filter_arcana(client: TestClient):
    """GET /cards?arcana=major should return only major arcana."""
    response = client.get("/cards?arcana=major")
    data = response.json()
    assert data["total"] == 22
    assert all(c["arcana"] == "major" for c in data["cards"])


def test_list_cards_filter_arcana_minor(client: TestClient):
    """GET /cards?arcana=minor should return only minor arcana."""
    response = client.get("/cards?arcana=minor")
    data = response.json()
    assert data["total"] == 56
    assert all(c["arcana"] == "minor" for c in data["cards"])
