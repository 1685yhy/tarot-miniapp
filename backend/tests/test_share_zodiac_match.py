"""
Tests for the zodiac-match share endpoint (v1.5 viral feature).

- GET /share/zodiac-match — relationship tarot card for a zodiac pairing
- validation, response structure, fun-tone guarantee
"""

from fastapi.testclient import TestClient


def test_zodiac_match_returns_relationship_card(client: TestClient):
    """Valid zodiac pair should return a card + AI/fallback blurb."""
    response = client.get("/share/zodiac-match?sign1=aries&sign2=taurus")
    assert response.status_code == 200
    data = response.json()

    # Spec fields
    assert isinstance(data["card_id"], int)
    assert isinstance(data["card_name"], str) and data["card_name"]
    assert isinstance(data["compatibility_text"], str) and data["compatibility_text"]
    assert isinstance(data["share_text"], str) and data["share_text"]

    # Extra fields for the frontend to compute the card image path
    assert isinstance(data["name_en"], str) and data["name_en"]
    assert data["arcana"] in ("major", "minor")
    assert isinstance(data["card_number"], int)
    assert "suit" in data


def test_zodiac_match_card_is_valid_db_card(client: TestClient):
    """The returned card_id should exist in the cards catalog."""
    response = client.get("/share/zodiac-match?sign1=leo&sign2=scorpio")
    data = response.json()
    card_detail = client.get(f"/cards/{data['card_id']}")
    assert card_detail.status_code == 200
    assert card_detail.json()["name_zh"] == data["card_name"]


def test_zodiac_match_fun_tone_no_destiny_language(client: TestClient):
    """
    The blurb must stay light and fun — no "destiny / soulmate"
    absolute language (the fallback templates guarantee this even
    without the AI service, which is disabled in tests).
    """
    forbidden = ("命运", "天生一对", "灵魂伴侣", "命中注定", "完美契合")
    response = client.get("/share/zodiac-match?sign1=cancer&sign2=pisces")
    data = response.json()
    assert not any(w in data["compatibility_text"] for w in forbidden)
    assert not any(w in data["share_text"] for w in forbidden)


def test_zodiac_match_invalid_sign(client: TestClient):
    """Unknown sign keys should return 400."""
    response = client.get("/share/zodiac-match?sign1=aries&sign2=unknown")
    assert response.status_code == 400

    response = client.get("/share/zodiac-match?sign1=aries")
    assert response.status_code == 422  # missing required query param


def test_zodiac_match_is_deterministic_shape(client: TestClient):
    """Two different pairings should both return the full shape."""
    for sign1, sign2 in (("gemini", "libra"), ("aquarius", "capricorn")):
        response = client.get(f"/share/zodiac-match?sign1={sign1}&sign2={sign2}")
        assert response.status_code == 200
        data = response.json()
        assert set(data.keys()) >= {
            "card_id", "card_name", "name_en", "arcana", "card_number",
            "suit", "compatibility_text", "share_text",
        }
