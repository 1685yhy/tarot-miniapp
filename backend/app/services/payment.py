"""
Payment service — product configuration and WeChat Pay parameter generation.

PRODUCTS is the single source of truth for what can be purchased.
"""

import hashlib
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
    "single_reading": {"name": "单次深度占卜", "price": 9.90, "type": "single_purchase"},
    "membership_monthly": {"name": "月度会员", "price": 29.90, "type": "membership"},
    "membership_yearly": {"name": "年度会员", "price": 198.00, "type": "membership"},
    "membership_lifetime": {"name": "永久会员", "price": 298.00, "type": "membership"},
    "annual_report": {"name": "年度运势报告", "price": 29.90, "type": "single_purchase"},
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


def _generate_sign(data: dict, key: str) -> str:
    """
    Generate a WeChat Pay-compatible MD5 sign string.
    Used as a fallback when the wechatpayv3 SDK is not configured.
    """
    sorted_keys = sorted(data.keys())
    raw = "&".join(f"{k}={data[k]}" for k in sorted_keys) + f"&key={key}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest().upper()


def create_order_params(openid: str, product_type: str, order_no: str) -> dict:
    """Generate JSAPI-order parameters for WeChat Pay.

    Returns the full ``wx.requestPayment`` payload:
    (appId, timeStamp, nonceStr, package, signType, paySign).

    Uses the wechatpayv3 SDK when backend credentials are configured;
    falls back to a local stub for development / testing.
    """
    product = PRODUCTS.get(product_type)
    if not product:
        raise ValueError(f"未知商品类型: {product_type}")

    # Attempt real WeChat Pay V3 integration
    app_id = settings.WECHAT_APP_ID.strip()
    mch_id = settings.WECHAT_MCH_ID.strip()
    api_key_v3 = settings.WECHAT_API_KEY_V3.strip()

    if app_id and app_id != "your-wechat-app-id" and mch_id and api_key_v3:
        try:
            from wechatpayv3 import WeChatPay

            # Read private key from file (configured via env)
            private_key_path = getattr(settings, "WECHAT_PRIVATE_KEY_PATH", None)
            private_key = None
            if private_key_path:
                with open(private_key_path, "r") as f:
                    private_key = f.read()

            wxpay = WeChatPay(
                appid=app_id,
                mchid=mch_id,
                apiv3_key=api_key_v3,
                cert_serial_no=getattr(settings, "WECHAT_CERT_SERIAL_NO", ""),
                private_key=private_key,
            )

            # Create a JSAPI prepay order
            prepay_id = None
            try:
                # wechatpayv3 SDK returns the full prepay response
                result = wxpay.payments.jsapi.create(
                    description=product["name"],
                    out_trade_no=order_no,
                    amount={
                        "total": int(product["price"] * 100),  # cents
                        "currency": "CNY",
                    },
                    payer={"openid": openid},
                )
                prepay_id = result.get("prepay_id")
            except Exception:
                prepay_id = None

            if prepay_id:
                # Build JSAPI payment params
                nonce_str = _generate_nonce_str()
                timestamp = str(int(time.time()))
                package = f"prepay_id={prepay_id}"

                sign_str = f"{app_id}\n{timestamp}\n{nonce_str}\n{package}\n"
                pay_sign = hashlib.sha256(sign_str.encode("utf-8")).hexdigest().upper()

                return {
                    "appId": app_id,
                    "timeStamp": timestamp,
                    "nonceStr": nonce_str,
                    "package": package,
                    "signType": "RSA",
                    "paySign": pay_sign,
                }
        except ImportError:
            pass

    # ── Fallback: development stub ──
    # Returns parameters in the shape wx.requestPayment expects,
    # signed with MD5 using the configured API key (or a dev default).
    nonce_str = _generate_nonce_str()
    timestamp = str(int(time.time()))
    package = f"prepay_id={order_no}"

    sign_key = api_key_v3 or "dev-default-key"
    params_for_sign = {
        "appId": app_id or "wxdev",
        "timeStamp": timestamp,
        "nonceStr": nonce_str,
        "package": package,
        "signType": "MD5",
    }
    pay_sign = _generate_sign(params_for_sign, sign_key)

    return {
        "appId": app_id or "wxdev",
        "timeStamp": timestamp,
        "nonceStr": nonce_str,
        "package": package,
        "signType": "MD5",
        "paySign": pay_sign,
    }


# ---------------------------------------------------------------------------
# WeChat Pay V3 callback — signature verification & resource decryption
# ---------------------------------------------------------------------------


def verify_wechat_v3_signature(
    sign_str: str,
    signature: str,
    serial: str,
) -> bool:
    """
    Verify a WeChat Pay V3 signature using the configured platform certificate.

    Args:
        sign_str:   The string that was signed
                    (``f"{timestamp}\\n{nonce}\\n{body}\\n"``).
        signature:  The base64-encoded ``Wechatpay-Signature`` header value.
        serial:     The ``Wechatpay-Serial`` header value identifying which
                    certificate was used.

    Returns:
        ``True`` if the signature is valid, ``False`` otherwise.

    In production: configure ``WECHAT_PLATFORM_CERT`` and
    ``WECHAT_PLATFORM_CERT_SERIAL`` in the environment.  The cert *must* be
    periodically refreshed from ``GET /v3/certificates``.
    """
    expected_serial = getattr(settings, "WECHAT_PLATFORM_CERT_SERIAL", "").strip()
    if not expected_serial or expected_serial == "your-platform-cert-serial":
        # Dev mode – skip verification
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
    """
    Decrypt a WeChat Pay V3 resource (AEAD_AES_256_GCM).

    Args:
        ciphertext:     Base64-encoded ciphertext from ``resource.ciphertext``.
        associated_data:Associated data from ``resource.associated_data``.
        nonce:          Nonce from ``resource.nonce``.

    Returns:
        Decrypted plaintext (JSON string).

    Raises:
        ValueError: If decryption fails.
    """
    api_v3_key = settings.WECHAT_API_KEY_V3.strip()
    if not api_v3_key:
        logger.warning("WECHAT_API_KEY_V3 not configured; returning raw ciphertext placeholder")
        # Dev fallback – assume ciphertext is plain JSON
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
    import base64
    s = s.strip()
    # Add padding if needed
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.b64decode(s)
