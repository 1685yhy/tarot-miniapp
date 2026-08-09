"""session_key 加密存储 — 基于 WECHAT_API_KEY_V3 派生密钥的 AES-256-GCM。

jscode2session 返回的 session_key 是 xpay 前端签名(signature)的密钥材料,
属于敏感凭证,落库前必须加密。密钥从 WECHAT_API_KEY_V3(SHA-256)派生,
每份密文使用独立随机 nonce(12 字节)。存储格式: ``v1:<b64 nonce>:<b64 ct>``。
"""

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

_VERSION = "v1"


def _derive_key() -> bytes:
    """从 WECHAT_API_KEY_V3 派生 AES-256 密钥(SHA-256,32 字节)。"""
    api_v3_key = (settings.WECHAT_API_KEY_V3 or "").strip()
    if not api_v3_key:
        raise ValueError("WECHAT_API_KEY_V3 not configured — cannot encrypt session_key")
    return hashlib.sha256(api_v3_key.encode("utf-8")).digest()


def encrypt_session_key(session_key: str) -> str:
    """Encrypt a raw session_key into the ``v1:<nonce>:<ct>`` storage blob."""
    nonce = os.urandom(12)
    ciphertext = AESGCM(_derive_key()).encrypt(nonce, session_key.encode("utf-8"), None)
    return "{v}:{n}:{c}".format(
        v=_VERSION,
        n=base64.b64encode(nonce).decode("ascii"),
        c=base64.b64encode(ciphertext).decode("ascii"),
    )


def decrypt_session_key(blob: str | None) -> str | None:
    """Decrypt a storage blob back into the raw session_key (None when empty)."""
    if not blob:
        return None
    version, nonce_b64, ct_b64 = blob.split(":", 2)
    if version != _VERSION:
        raise ValueError(f"未知的 session_key 密文版本: {version}")
    nonce = base64.b64decode(nonce_b64)
    ciphertext = base64.b64decode(ct_b64)
    plaintext = AESGCM(_derive_key()).decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")
