"""微信小程序虚拟支付(xpay)服务端 API 封装（小程序虚拟支付官方契约）。

所有接口走 https://api.weixin.qq.com/xpay/*?access_token=...,POST JSON。
服务端接口统一签名(pay_sig):
  pay_sig = HMAC-SHA256(AppKey, "xpay/<接口名>&" + 请求体JSON), 小写 hex
  AppKey 按请求 env 选择: env=0 → WX_XPAY_APPKEY_PROD, env=1 → WX_XPAY_APPKEY_SANDBOX。
  签名的请求体字符串必须与真正发送的 HTTP body 完全一致,
  因此 _post_xpay 用 content=body_json 原样发送, 不做二次序列化。
access_token 统一用 app.services.wx_token 的公共缓存。失败(网络异常或
errcode != 0)时抛 RuntimeError,由调用方决定如何降级。
"""

import hashlib
import hmac
import json
import logging

import httpx

from app.config import settings
from app.services.wx_token import get_access_token

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.weixin.qq.com/xpay"

# 小程序虚拟支付 order.status → 本地订单状态映射（官方枚举, 非旧小游戏 state）
# 3=已支付 4=已支付且已发货 5=已退款 6=已取消 8=退款完成
XPAY_STATUS_TO_LOCAL = {
    3: "paid",
    4: "paid",
    5: "refunded",
    6: "cancelled",
    8: "refunded",
}


def _app_key_for_env(env: int) -> str:
    """按支付环境选择 AppKey（必须与 env 一致, 否则 pay_sig 校验失败）。"""
    app_key = (
        settings.WX_XPAY_APPKEY_PROD
        if int(env) == 0
        else settings.WX_XPAY_APPKEY_SANDBOX
    )
    if not app_key:
        raise RuntimeError("xpay AppKey 未配置 (WX_XPAY_APPKEY_PROD / WX_XPAY_APPKEY_SANDBOX)")
    return app_key


def sign_pay_sig(env: int, uri: str, body: dict) -> str:
    """服务端接口签名: pay_sig = HMAC-SHA256(AppKey, 'xpay/<uri>&' + body_json), 小写 hex。"""
    body_json = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    app_key = _app_key_for_env(env)
    return hmac.new(
        app_key.encode("utf-8"),
        f"xpay/{uri}&{body_json}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


async def _post_xpay(uri: str, body: dict, env: int) -> dict:
    """POST to an xpay endpoint with access_token + pay_sig. Raises on failure."""
    token = await get_access_token()
    if not token:
        raise RuntimeError("WeChat access_token unavailable — xpay API disabled")

    body_json = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    pay_sig = sign_pay_sig(env, uri, body)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{_BASE_URL}/{uri}",
                params={"access_token": token, "pay_sig": pay_sig},
                content=body_json,
                headers={"Content-Type": "application/json"},
            )
            data = resp.json()
    except Exception as exc:
        logger.exception("xpay API %s request failed: %s", uri, exc)
        raise RuntimeError(f"xpay API {uri} 请求失败") from exc

    if data.get("errcode") not in (0, None):
        logger.error(
            "xpay API %s error: errcode=%s errmsg=%s body=%s",
            uri, data.get("errcode"), data.get("errmsg"), body,
        )
        raise RuntimeError(
            f"xpay API {uri} 返回错误: {data.get('errcode')} {data.get('errmsg')}"
        )
    return data


async def query_order(out_trade_no: str, env: int, openid: str) -> dict:
    """实时查询 xpay 订单状态(退款轮询/状态确认用)。

    官方契约: 请求体 {openid, env, order_id}(order_id=下单业务单号 out_trade_no,
    与 wx_order_id 二选一), query 参数带 pay_sig; 响应状态在 order.status。
    """
    return await _post_xpay(
        "query_order",
        {"openid": openid, "env": int(env), "order_id": out_trade_no},
        env,
    )


async def notify_provide_goods(out_trade_no: str, env: int) -> dict:
    """通知微信已发货完成（补发/重发用）。

    官方契约: 请求体 {order_id, env}(order_id=下单业务单号 out_trade_no,
    与 wx_order_id 二选一)。正常流程下 xpay_goods_deliver_notify 回调返回
    success 即视为发货完成, 本接口仅用于消息推送失败时手动补发。
    """
    return await _post_xpay(
        "notify_provide_goods",
        {"order_id": out_trade_no, "env": int(env)},
        env,
    )


async def refund_order(
    openid: str,
    env: int,
    out_trade_no: str,
    refund_order_id: str,
    left_fee: int,
    refund_fee: int,
    refund_reason: int = 3,
    biz_meta: str = "",
    req_from: int = 3,
) -> dict:
    """发起退款(异步, 结果需轮询 query_order 直至退款完成)。

    官方契约 10 参: openid / order_id(=out_trade_no, 与 wx_order_id 二选一) /
    refund_order_id(商户退款单号) / left_fee(当前剩余可退金额,分) /
    refund_fee(本次退款金额,分, 需满足 (0, left_fee]) / biz_meta /
    refund_reason(0-5: 0无描述 1产品问题 2售后问题 3用户主动退款 4价格问题 5其他) /
    req_from(1-3: 1人工客服退款 2用户发起 3其它) / env + query 的 pay_sig。
    """
    body = {
        "openid": openid,
        "env": int(env),
        "order_id": out_trade_no,
        "refund_order_id": refund_order_id,
        "left_fee": int(left_fee),
        "refund_fee": int(refund_fee),
        "refund_reason": int(refund_reason),
        "biz_meta": biz_meta,
        "req_from": int(req_from),
    }
    return await _post_xpay("refund_order", body, env)
