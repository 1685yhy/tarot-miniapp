"""
Tests for the membership / product-listing API.

GET /membership/products — lists purchasable products (no DB needed)
"""

from fastapi.testclient import TestClient


def test_list_products_returns_list(client_no_db: TestClient):
    """GET /membership/products should return a list of products."""
    response = client_no_db.get("/membership/products")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_product_structure(client_no_db: TestClient):
    """Each product should have id, name, price, and type."""
    response = client_no_db.get("/membership/products")
    products = response.json()
    for product in products:
        assert "id" in product
        assert "name" in product
        assert "price" in product
        assert "type" in product
        assert isinstance(product["price"], (int, float))


def test_known_products_present(client_no_db: TestClient):
    """Known products like single_reading should be present."""
    response = client_no_db.get("/membership/products")
    products = {p["id"]: p for p in response.json()}
    assert "single_reading" in products
    assert products["single_reading"]["price"] == 9.90
