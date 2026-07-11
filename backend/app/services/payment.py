"""
Payment service — product configuration and WeChat Pay parameter generation.

PRODUCTS is the single source of truth for what can be purchased.
"""

import time
import uuid

from app.config import settings

# ---------------------------------------------------------------------------
# Product catalogue
# ---------------------------------------------------------------------------

PRODUCTS = {
    "single_reading": {"name": "单次深度占卜", "price": 9.90},
    "membership_monthly": {"name": "月度会员", "price": 29.90},
    "membership_yearly": {"name": "年度会员", "price": 198.00},
    "membership_lifetime": {"name": "永久会员", "price": 298.00},
    "annual_report": {"name": "年度运势报告", "price": 29.90},
}


# ---------------------------------------------------------------------------
# Order / payment helpers
# ---------------------------------------------------------------------------


def generate_order_no() -> str:
    """Generate a human-readable unique order number."""
    ts = int(time.time())
    suffix = uuid.uuid4().hex[:6].upper()
    return f"TAROT{ts}{suffix}"


def create_order_params(openid: str, product_type: str) -> dict:
    """Generate JSAPI-order parameters for WeChat Pay.

    This is a best-effort stub — when the real WeChat Pay v3 SDK is wired in
    it will return the full ``wx.requestPayment`` payload
    (appId, timeStamp, nonceStr, package, signType, paySign).
    """
    product = PRODUCTS.get(product_type)
    if not product:
        raise ValueError(f"未知商品类型: {product_type}")

    order_no = generate_order_no()

    return {
        "order_no": order_no,
        "amount": product["price"],
        "product_name": product["name"],
        "product_type": product_type,
    }
