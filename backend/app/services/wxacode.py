"""
WeChat Mini-Program Code (wxacode) generation service.

Handles:
  - Fetching and caching the WeChat access token.
  - Calling the ``getwxacodeunlimit`` API to generate a mini-program code image.
"""

import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory access-token cache
# ---------------------------------------------------------------------------

_token_cache: dict = {"token": None, "expires_at": 0}


async def _get_access_token() -> str:
    """Return a valid WeChat access token (from cache or freshly fetched)."""
    now = time.time()
    if _token_cache["token"] and _token_cache["expires_at"] > now + 60:
        # Buffer of 60 s to avoid edge-of-expiry race conditions
        return _token_cache["token"]

    app_id = settings.WECHAT_APP_ID
    app_secret = settings.WECHAT_APP_SECRET

    if not app_id or not app_secret:
        raise RuntimeError("WECHAT_APP_ID or WECHAT_APP_SECRET not configured")

    url = (
        "https://api.weixin.qq.com/cgi-bin/token"
        f"?grant_type=client_credential&appid={app_id}&secret={app_secret}"
    )

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    if "access_token" not in data:
        raise RuntimeError(
            f"WeChat token API error: {data.get('errcode')} {data.get('errmsg')}"
        )

    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = now + data.get("expires_in", 7200)
    logger.info("WeChat access token refreshed (expires in %d s)", data.get("expires_in", 7200))
    return _token_cache["token"]


async def get_wxacode(
    scene: str = "",
    page: str = "pages/index/index",
    width: int = 280,
) -> bytes:
    """
    Generate a WeChat mini-program code (unlimited) image.

    Returns the raw PNG bytes.

    Parameters match the wxacode.getUnlimited API:
      - scene   -- max 32 characters, visible after scanning
      - page    -- page path, must already be published (not a draft)
      - width   -- image width in px (280 – 1280)
    """
    token = await _get_access_token()

    body = {
        "scene": scene or "default",
        "page": page,
        "width": max(280, min(width, 1280)),
        "auto_color": True,
    }

    url = f"https://api.weixin.qq.com/wxa/getwxacodeunlimit?access_token={token}"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json=body)
        content_type = resp.headers.get("content-type", "")

        # WeChat returns image/png on success; application/json on error
        if "image" in content_type:
            logger.info(
                "wxacode generated: page=%s scene=%s width=%d size=%d bytes",
                page, scene, width, len(resp.content),
            )
            return resp.content

        # Error response — attempt to parse JSON
        try:
            err = resp.json()
            raise RuntimeError(
                f"WeChat wxacode API error: {err.get('errcode')} {err.get('errmsg')}"
            )
        except ValueError:
            resp.raise_for_status()
            raise RuntimeError(
                f"WeChat wxacode API returned unexpected content-type: {content_type}"
            )
