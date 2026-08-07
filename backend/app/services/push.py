"""
WeChat subscription message push service.

Handles:
  - Fetching and caching the WeChat access token (reuses wxacode pattern).
  - Sending template messages via the ``subscribeMessage.send`` API.
  - Three built-in templates: daily card, membership expiry, annual report.
"""

import logging
import time
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Template keys (P0-4: configurable template IDs)
#
# The constants below are stable *keys* used by the frontend and stored in
# push_subscriptions.template_id. The real WeChat template IDs are read from
# settings (WX_TEMPLATE_DAILY_CARD / WX_TEMPLATE_MEMBER_EXPIRE /
# WX_TEMPLATE_ANNUAL_REPORT, set in .env). While a key has no configured
# template ID the push service is treated as NOT OPEN: subscribe returns 400
# and send_subscribe_message logs "模板未配置" instead of calling WeChat.
# ---------------------------------------------------------------------------

TEMPLATE_DAILY_CARD = "TEMPLATE_DAILY_CARD"
TEMPLATE_MEMBER_EXPIRE = "TEMPLATE_MEMBER_EXPIRE"
TEMPLATE_ANNUAL_REPORT = "TEMPLATE_ANNUAL_REPORT"

_TEMPLATE_KEY_TO_SETTING = {
    TEMPLATE_DAILY_CARD: "WX_TEMPLATE_DAILY_CARD",
    TEMPLATE_MEMBER_EXPIRE: "WX_TEMPLATE_MEMBER_EXPIRE",
    TEMPLATE_ANNUAL_REPORT: "WX_TEMPLATE_ANNUAL_REPORT",
}


def resolve_template_id(template_key: str) -> str:
    """Return the configured WeChat template ID for a template key ('' if unset).

    This is where real (approved) template IDs plug in — fill
    ``WX_TEMPLATE_DAILY_CARD`` etc. in .env and the whole chain works.
    """
    attr = _TEMPLATE_KEY_TO_SETTING.get(template_key)
    if not attr:
        return ""
    return str(getattr(settings, attr, "") or "").strip()


def is_template_configured(template_key: str) -> bool:
    """True when a real WeChat template ID is configured for the key."""
    return bool(resolve_template_id(template_key))

# ---------------------------------------------------------------------------
# In-memory access-token cache (shared with wxacode pattern)
# ---------------------------------------------------------------------------

_token_cache: dict = {"token": None, "expires_at": 0}


async def _get_access_token() -> str:
    """Return a valid WeChat access token (from cache or freshly fetched)."""
    now = time.time()
    if _token_cache["token"] and _token_cache["expires_at"] > now + 60:
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


# ---------------------------------------------------------------------------
# Send a subscription message
# ---------------------------------------------------------------------------


async def send_subscribe_message(
    openid: str,
    template_id: str,
    data: dict[str, dict[str, str]],
    page: str = "",
    miniprogram_state: str = "formal",
) -> dict:
    """
    Send a WeChat subscription message via ``subscribeMessage.send``.

    Parameters
    ----------
    openid : str
        Recipient's WeChat openid.
    template_id : str
        WeChat template ID.
    data : dict
        Template data in the format ``{"thing1": {"value": "..."}, "thing2": {"value": "..."}}``.
    page : str
        Optional page path to open when the notification is tapped.
    miniprogram_state : str
        ``formal`` or ``trial``.

    Returns
    -------
    dict
        The JSON response from WeChat (``{"errcode": 0, "errmsg": "ok"}`` on success).
    """
    # P0-4: never call WeChat with an unconfigured / placeholder template ID.
    if not template_id or not str(template_id).strip():
        logger.error(
            "推送模板未配置（template_id 为空）— 跳过发送 openid=%s",
            openid,
        )
        return {"errcode": -1, "errmsg": "模板未配置"}
    if str(template_id) in _TEMPLATE_KEY_TO_SETTING:
        logger.error(
            "推送模板未配置（%s 仍是占位符，请在 .env 配置真实模板 ID）— 跳过发送 openid=%s",
            template_id,
            openid,
        )
        return {"errcode": -1, "errmsg": "模板未配置"}

    token = await _get_access_token()

    body = {
        "touser": openid,
        "template_id": template_id,
        "data": data,
        "miniprogram_state": miniprogram_state,
    }
    if page:
        body["page"] = page

    url = f"https://api.weixin.qq.com/cgi-bin/message/subscribe/bizsend?access_token={token}"

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=body)
        resp.raise_for_status()
        result = resp.json()

    if result.get("errcode") != 0:
        logger.warning(
            "subscribeMessage.send error: errcode=%s errmsg=%s openid=%s template=%s",
            result.get("errcode"),
            result.get("errmsg"),
            openid,
            template_id,
        )
    else:
        logger.info(
            "subscribeMessage.send success: openid=%s template=%s",
            openid,
            template_id,
        )

    return result


# ---------------------------------------------------------------------------
# Convenience builders for the three template types
# ---------------------------------------------------------------------------


def build_daily_card_data(
    card_name: str,
    keyword: str,
    date_str: str,
    hint: str = "点击查看今日牌面详解",
) -> dict[str, dict[str, str]]:
    """
    Build the data payload for the daily-card template.

    Expected template fields (WeChat subscription message):
      - thing1: 卡牌名称
      - thing2: 关键词
      - date3:  日期
      - thing4: 提示语
    """
    return {
        "thing1": {"value": _truncate(card_name, 20)},
        "thing2": {"value": _truncate(keyword, 20)},
        "date3": {"value": date_str},
        "thing4": {"value": _truncate(hint, 20)},
    }


def build_member_expire_data(
    days_left: int,
    member_tier: str = "星光会员",
    tip: str = "续费后继续享受无限解读权益",
) -> dict[str, dict[str, str]]:
    """
    Build the data payload for the membership-expiry template.

    Expected template fields:
      - thing1: 会员等级
      - number2: 剩余天数
      - thing3: 温馨提示
    """
    return {
        "thing1": {"value": _truncate(member_tier, 20)},
        "number2": {"value": str(days_left)},
        "thing3": {"value": _truncate(tip, 20)},
    }


def build_annual_report_data(
    year: str,
    reading_count: str,
    top_card: str,
    summary: str = "点击查看你的完整星光旅程",
) -> dict[str, dict[str, str]]:
    """
    Build the data payload for the annual-report template.

    Expected template fields:
      - thing1: 年份
      - number2: 解读次数
      - thing3: 年度之牌
      - thing4: 简介
    """
    return {
        "thing1": {"value": _truncate(year, 20)},
        "number2": {"value": reading_count},
        "thing3": {"value": _truncate(top_card, 20)},
        "thing4": {"value": _truncate(summary, 20)},
    }


# ---------------------------------------------------------------------------
# Batch send: iterate subscribed users and send one-by-one
# ---------------------------------------------------------------------------


async def batch_send(
    openid_list: list[str],
    template_id: str,
    data_builder,
    page: str = "",
    *,
    template_data_kwargs: Optional[dict] = None,
) -> dict[str, dict]:
    """
    Send a template message to a list of openids.

    WeChat limits subscription messages to 1 000 sends per hour per template
    for a given app. Callers should cap ``openid_list`` accordingly.

    Parameters
    ----------
    openid_list : list[str]
        List of recipient openids.
    template_id : str
        WeChat template ID.
    data_builder : callable
        A function that returns the data dict for ``send_subscribe_message``.
    page : str
        Optional page path.
    template_data_kwargs : dict, optional
        Extra kwargs forwarded to ``data_builder``.

    Returns
    -------
    dict[str, dict]
        Mapping of openid -> WeChat API response.
    """
    results = {}
    kwargs = template_data_kwargs or {}
    for openid in openid_list:
        try:
            data = data_builder(**kwargs)
            result = await send_subscribe_message(
                openid=openid,
                template_id=template_id,
                data=data,
                page=page,
            )
            results[openid] = result
        except Exception:
            logger.exception("Failed to send push to openid=%s template=%s", openid, template_id)
            results[openid] = {"errcode": -1, "errmsg": "exception"}
    return results


def _truncate(value: str, max_len: int = 20) -> str:
    """Truncate a string to max_len characters (WeChat template value limit)."""
    return value if len(value) <= max_len else value[:max_len]
