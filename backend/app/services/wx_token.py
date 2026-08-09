"""公共微信 access_token 缓存。

msg_check / push / xpay_api 共用同一个模块级缓存:
- 提前 300s 过期,避免 token 在微信侧失效;
- 未配置 WECHAT_APP_ID / WECHAT_APP_SECRET 时返回 None(不抛异常),
  由调用方决定降级行为(push 保留原 raise 语义)。
"""

import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Cached WeChat access token (valid ~7200s; refresh 300s early)
_access_token: str = ""
_access_token_expires: float = 0.0


async def get_access_token() -> str | None:
    """Fetch a cached Mini Program access_token, or None when not configured."""
    global _access_token, _access_token_expires

    if not settings.WECHAT_APP_ID or not settings.WECHAT_APP_SECRET:
        return None
    if _access_token and time.time() < _access_token_expires:
        return _access_token

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://api.weixin.qq.com/cgi-bin/token",
                params={
                    "grant_type": "client_credential",
                    "appid": settings.WECHAT_APP_ID,
                    "secret": settings.WECHAT_APP_SECRET,
                },
            )
            data = resp.json()
    except Exception as exc:
        logger.warning("WeChat access_token request failed: %s", exc)
        return None

    token = data.get("access_token")
    if not token:
        logger.warning("WeChat access_token request rejected: %s", data.get("errmsg"))
        return None
    _access_token = token
    _access_token_expires = time.time() + int(data.get("expires_in", 7200)) - 300
    return token
