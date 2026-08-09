"""微信小程序虚拟支付(xpay)服务端 API 封装。

所有接口走 https://api.weixin.qq.com/xpay/*?access_token=...,POST JSON。
access_token 统一用 app.services.wx_token 的公共缓存。失败(网络异常或
errcode != 0)时抛 RuntimeError,由调用方决定如何降级。
"""

import logging

import httpx

from app.services.wx_token import get_access_token

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.weixin.qq.com/xpay"

# xpay 订单状态 → 本地订单状态映射 (B7 用)
# 0初始化 / 1创建 / 2已支付待发货 / 3发货中 / 4已发货 / 5已退款 /
# 6关闭 / 7退款失败 / 8用户退款完成
XPAY_STATUS_TO_LOCAL = {
    0: "pending",
    1: "pending",
    2: "paid",
    3: "paid",
    4: "paid",
    5: "refunded",
    6: "cancelled",
    7: "pending",   # 退款失败 → 维持现状,不降级为退款
    8: "refunded",
}


async def _post_xpay(endpoint: str, body: dict) -> dict:
    """POST to an xpay endpoint with the shared access_token. Raises on failure."""
    token = await get_access_token()
    if not token:
        raise RuntimeError("WeChat access_token unavailable — xpay API disabled")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{_BASE_URL}/{endpoint}",
                params={"access_token": token},
                json=body,
            )
            data = resp.json()
    except Exception as exc:
        logger.exception("xpay API %s request failed: %s", endpoint, exc)
        raise RuntimeError(f"xpay API {endpoint} 请求失败") from exc

    if data.get("errcode") not in (0, None):
        logger.error(
            "xpay API %s error: errcode=%s errmsg=%s body=%s",
            endpoint, data.get("errcode"), data.get("errmsg"), body,
        )
        raise RuntimeError(
            f"xpay API {endpoint} 返回错误: {data.get('errcode')} {data.get('errmsg')}"
        )
    return data


async def query_order(out_trade_no: str, env: int, openid: str) -> dict:
    """实时查询 xpay 订单状态(发货回执/退款轮询用)。"""
    return await _post_xpay("query_order", {
        "openid": openid,
        "env": env,
        "out_trade_no": out_trade_no,
    })


async def notify_provide_goods(
    out_trade_no: str,
    env: int,
    openid: str,
    delivery_type: int = 1,
    delivery_id: str = "",
    ext_info: str = "",
) -> dict:
    """发货回执 — 收到 xpay 发货通知并发放权益后必须调用。

    delivery_type: 1=虚拟道具, 2=实物商品。
    """
    return await _post_xpay("notify_provide_goods", {
        "openid": openid,
        "env": env,
        "out_trade_no": out_trade_no,
        "delivery_type": delivery_type,
        "delivery_id": delivery_id,
        "ext_info": ext_info,
    })


async def refund_order(
    out_trade_no: str,
    env: int,
    openid: str,
    refund_amount: int,
    refund_reason: str,
    refund_id: str | None = None,
) -> dict:
    """发起退款(异步,结果需轮询 query_order)。refund_amount 单位: 分。"""
    body = {
        "openid": openid,
        "env": env,
        "out_trade_no": out_trade_no,
        "refund_amount": int(refund_amount),
        "refund_reason": refund_reason,
    }
    if refund_id:
        body["refund_id"] = refund_id
    return await _post_xpay("refund_order", body)
