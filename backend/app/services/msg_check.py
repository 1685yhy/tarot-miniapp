"""WeChat content-safety wrapper (msgSecCheck v2) for community posts.

Two layers:
1. Local obvious-keyword gate — instant, blocks clearly abusive content even
   if the WeChat API is unreachable.
2. WeChat ``msgSecCheck`` v2 — authoritative check using the Mini Program
   access token. Failures are logged and treated as *pass* (fail-open) so the
   community feature is never bricked by a WeChat API outage; local keyword
   hits are the guaranteed floor.

Enabled only when ``WECHAT_MSG_CHECK_ENABLED`` is true and the WeChat
credentials (WECHAT_APP_ID / WECHAT_APP_SECRET) are configured.
"""

import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Obvious sensitive phrases — first line of defence, kept intentionally short
# to avoid false positives. Any hit blocks the post outright.
_SENSITIVE_KEYWORDS = (
    "赌博", "赌场", "博彩", "裸聊", "招嫖", "卖淫", "代开发票", "办假证",
    "刷单", "传销", "洗钱", "毒品", "冰毒", "枪支", "假币", "诈骗", "杀猪盘",
    "色情", "约炮",
)

# Cached WeChat access token (valid ~7200s; refresh 300s early)
_access_token: str = ""
_access_token_expires: float = 0.0


async def _get_access_token() -> str | None:
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


async def msg_sec_check(content: str, openid: str | None = None) -> dict:
    """Check user-generated content for violations.

    Returns:
        {"safe": bool, "skipped": bool, "err": str | None}

    - safe=True   → content may be published
    - safe=False  → content must be blocked (local keyword or WeChat risky)
    - skipped=True → the remote check did not run (disabled / unconfigured /
                     API failure) — fail-open
    Never raises.
    """
    # Layer 1: local obvious-keyword gate
    for kw in _SENSITIVE_KEYWORDS:
        if kw in content:
            logger.warning("Community post blocked by local keyword: %r", kw)
            return {"safe": False, "skipped": False, "err": "local keyword"}

    # Layer 2: WeChat msgSecCheck v2
    if not settings.WECHAT_MSG_CHECK_ENABLED:
        return {"safe": True, "skipped": True, "err": None}

    token = await _get_access_token()
    if not token:
        logger.warning("msgSecCheck skipped: no WeChat access token (fail-open)")
        return {"safe": True, "skipped": True, "err": None}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                "https://api.weixin.qq.com/wxa/msg_sec_check",
                params={"access_token": token},
                json={
                    "version": 2,
                    "scene": 2,  # 评论
                    "openid": openid or "",
                    "content": content[:2500],
                },
            )
            data = resp.json()
    except Exception as exc:
        logger.warning("msgSecCheck call failed (fail-open): %s", exc)
        return {"safe": True, "skipped": True, "err": str(exc)}

    if data.get("errcode") == 87014:  # 内容含有违法违规内容
        return {"safe": False, "skipped": False, "err": "risky content"}

    # v2 API: result.suggest ∈ pass / review / risky
    suggest = ((data.get("result") or {}).get("suggest") or "").lower()
    if suggest == "risky" or suggest == "review":
        logger.warning("msgSecCheck flagged content as %s", suggest)
        return {"safe": False, "skipped": False, "err": f"suggest={suggest}"}

    errcode = data.get("errcode", 0)
    if errcode != 0:
        logger.warning(
            "msgSecCheck returned errcode %s: %s (fail-open)",
            errcode, data.get("errmsg"),
        )
        return {"safe": True, "skipped": True, "err": data.get("errmsg")}

    return {"safe": True, "skipped": False, "err": None}
