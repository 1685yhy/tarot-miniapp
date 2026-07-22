"""
Payment service — product configuration and WeChat Pay parameter generation.

PRODUCTS is the single source of truth for what can be purchased.
"""

import base64
import json
import logging
import secrets
import time
import uuid

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Product catalogue
# ---------------------------------------------------------------------------

PRODUCTS = {
    "single_reading": {"name": "单次深度占卜", "price": 9.90, "type": "single_purchase", "cost": 0.002},
    "membership_monthly": {"name": "月度会员", "price": 19.90, "type": "membership", "cost": 0.04, "daily_readings": 10, "unlimited_chat": True},
    "membership_yearly": {"name": "年度会员", "price": 168.00, "type": "membership", "cost": 0.48, "daily_readings": 30, "unlimited_chat": True, "annual_report": True},
    "membership_lifetime": {"name": "永久会员", "price": 298.00, "type": "membership", "cost": 2.00, "daily_readings": -1, "unlimited_chat": True, "annual_report": True},
    "membership_student": {"name": "学生会员", "price": 9.90, "type": "membership", "cost": 0.02, "daily_readings": 10, "unlimited_chat": True},
    "annual_report": {"name": "年度运势报告", "price": 29.90, "type": "single_purchase", "cost": 0.03},
}


# ---------------------------------------------------------------------------
# Order / payment helpers
# ---------------------------------------------------------------------------


def generate_order_no() -> str:
    """Generate a human-readable unique order number."""
    ts = int(time.time())
    suffix = uuid.uuid4().hex[:6].upper()
    return f"TAROT{ts}{suffix}"


def _generate_nonce_str() -> str:
    """Generate a random nonce string for WeChat Pay."""
    return secrets.token_hex(16)


def _load_private_key():
    """Load the merchant RSA private key from the configured PEM file."""
    path = settings.WECHAT_PRIVATE_KEY_PATH.strip()
    if not path:
        raise ValueError("WECHAT_PRIVATE_KEY_PATH not configured")
    with open(path, "r") as f:
        pem_data = f.read()
    from cryptography.hazmat.primitives import serialization
    return serialization.load_pem_private_key(
        pem_data.encode("utf-8"),
        password=None,
    )


def _rsa_sign(private_key, message: str) -> str:
    """Sign message with private_key using RSA-SHA256, return base64 string."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    signature = private_key.sign(
        message.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def _build_v3_auth_header(method: str, url_path: str, body_json: str) -> tuple:
    """Build the Authorization header for a WeChat Pay V3 API call.

    Returns:
        (auth_header, timestamp, nonce)
    """
    mch_id = settings.WECHAT_MCH_ID.strip()
    cert_serial = settings.WECHAT_MCH_CERT_SERIAL.strip()
    timestamp = str(int(time.time()))
    nonce = _generate_nonce_str()

    sign_str = f"{method}\n{url_path}\n{timestamp}\n{nonce}\n{body_json}\n"
    private_key = _load_private_key()
    signature = _rsa_sign(private_key, sign_str)

    auth = (
        f'WECHATPAY2-SHA256-RSA2048 '
        f'mchid="{mch_id}",'
        f'nonce_str="{nonce}",'
        f'signature="{signature}",'
        f'timestamp="{timestamp}",'
        f'serial_no="{cert_serial}"'
    )
    return auth, timestamp, nonce


def create_order_params(openid: str, product_type: str, order_no: str) -> dict | None:
    """Generate JSAPI-order parameters for WeChat Pay V3.

    Calls WeChat Pay APIv3 POST /v3/pay/transactions/jsapi directly,
    signing the request with the merchant private key (RSA-SHA256).

    Returns a wx.requestPayment-compatible dict on success, or None
    on failure (caller should return an appropriate error to the client).
    """
    product = PRODUCTS.get(product_type)
    if not product:
        raise ValueError(f"未知商品类型: {product_type}")

    app_id = settings.WECHAT_APP_ID.strip()
    mch_id = settings.WECHAT_MCH_ID.strip()
    api_v3_key = settings.WECHAT_API_KEY_V3.strip()
    private_key_path = settings.WECHAT_PRIVATE_KEY_PATH.strip()
    cert_serial = settings.WECHAT_MCH_CERT_SERIAL.strip()

    if not all([app_id, mch_id, api_v3_key, private_key_path, cert_serial]):
        logger.error(
            "WeChat Pay V3 not fully configured -- missing one or more of: "
            "WECHAT_APP_ID, WECHAT_MCH_ID, WECHAT_API_KEY_V3, "
            "WECHAT_PRIVATE_KEY_PATH, WECHAT_MCH_CERT_SERIAL"
        )
        return None

    # Build request body
    total_fen = int(product["price"] * 100)
    notify_url = "https://xingxiang.chat/api/orders/callback"

    body = {
        "appid": app_id,
        "mchid": mch_id,
        "description": product["name"],
        "out_trade_no": order_no,
        "notify_url": notify_url,
        "amount": {
            "total": total_fen,
            "currency": "CNY",
        },
        "payer": {
            "openid": openid,
        },
    }
    body_json = json.dumps(body, separators=(",", ":"))

    # Build Authorization header
    auth_header, _timestamp, _nonce = _build_v3_auth_header(
        "POST", "/v3/pay/transactions/jsapi", body_json,
    )

    # Make API call
    import urllib.request as _urllib

    req = _urllib.Request(
        "https://api.mch.weixin.qq.com/v3/pay/transactions/jsapi",
        data=body_json.encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": auth_header,
            "Accept": "application/json",
            "User-Agent": "tarot-api/1.0",
        },
    )

    try:
        resp = _urllib.urlopen(req, timeout=10)
        resp_body = resp.read().decode("utf-8")
        resp_data = json.loads(resp_body)
        prepay_id = resp_data.get("prepay_id")
        logger.info("WeChat Pay V3 prepay response: %s", resp_body)
    except _urllib.HTTPError as e:
        error_body = e.read().decode("utf-8")
        logger.error(
            "WeChat Pay V3 API error [%d %s]: %s",
            e.code, e.reason, error_body,
        )
        return None
    except Exception as e:
        logger.exception("WeChat Pay V3 request failed: %s", e)
        return None

    if not prepay_id:
        logger.error("WeChat Pay V3 response missing prepay_id: %s", resp_body)
        return None

    # Build JSAPI payment params (RSA signed)
    private_key = _load_private_key()
    pay_nonce = _generate_nonce_str()
    pay_timestamp = str(int(time.time()))
    pay_package = f"prepay_id={prepay_id}"

    pay_sign_str = f"{app_id}\n{pay_timestamp}\n{pay_nonce}\n{pay_package}\n"
    pay_sign = _rsa_sign(private_key, pay_sign_str)

    return {
        "appId": app_id,
        "timeStamp": pay_timestamp,
        "nonceStr": pay_nonce,
        "package": pay_package,
        "signType": "RSA",
        "paySign": pay_sign,
    }


# ---------------------------------------------------------------------------
# WeChat Pay V3 callback - signature verification & resource decryption
# ---------------------------------------------------------------------------


def verify_wechat_v3_signature(
    sign_str: str,
    signature: str,
    serial: str,
) -> bool:
    """Verify a WeChat Pay V3 signature using the configured platform cert."""
    expected_serial = getattr(settings, "WECHAT_PLATFORM_CERT_SERIAL", "").strip()
    if not expected_serial or expected_serial == "your-platform-cert-serial":
        logger.warning("WECHAT_PLATFORM_CERT_SERIAL not configured; skipping V3 verification")
        return True

    if serial != expected_serial:
        logger.error(
            "WeChat certificate serial mismatch: got %s, expected %s",
            serial, expected_serial,
        )
        return False

    pem = getattr(settings, "WECHAT_PLATFORM_CERT", "").strip()
    if not pem:
        logger.error("WECHAT_PLATFORM_CERT not configured")
        return False

    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        cert_bytes = pem.encode("utf-8")
        public_key = serialization.load_pem_x509_certificate(cert_bytes).public_key()

        sig_bytes = _b64decode(signature)
        public_key.verify(
            sig_bytes,
            sign_str.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except Exception as exc:
        logger.exception("WeChat V3 signature verification failed: %s", exc)
        return False


def decrypt_wechat_v3_resource(
    ciphertext: str,
    associated_data: str,
    nonce: str,
) -> str:
    """Decrypt a WeChat Pay V3 resource (AEAD_AES_256_GCM)."""
    api_v3_key = settings.WECHAT_API_KEY_V3.strip()
    if not api_v3_key:
        logger.warning("WECHAT_API_KEY_V3 not configured; returning raw ciphertext placeholder")
        return _b64decode(ciphertext).decode("utf-8")

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        key = api_v3_key.encode("utf-8")
        nonce_bytes = nonce.encode("utf-8")
        aad = associated_data.encode("utf-8")
        ct = _b64decode(ciphertext)

        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce_bytes, ct, aad)
        return plaintext.decode("utf-8")
    except Exception as exc:
        logger.exception("Failed to decrypt WeChat V3 resource: %s", exc)
        raise ValueError("解密失败") from exc


def _b64decode(s: str) -> bytes:
    """Decode a base64 string (with or without padding)."""
    import base64 as _b64
    s = s.strip()
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return _b64.b64decode(s)
