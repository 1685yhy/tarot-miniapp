"""
微信小程序"消息推送"通道 — 虚拟支付(xpay)发货回调入口。

- GET  /api/wechat/msg — URL 验证(echostr),sha1(sorted([token,timestamp,nonce]))
  与 signature 比对
- POST /api/wechat/msg — 按 WX_MSG_ENCRYPT_MODE 处理:
  * plain       → 直接解析 XML(xpay 事件一律 403 拒绝: 无验签/解密, 伪造可刷权益)
  * compatible  → 验 msg_signature + AES-256-CBC 解密(取 Encrypt 节点)
  * safe        → 同上(密文是整个 body)
  event=xpay_goods_deliver_notify → 校验归属/环境/金额 → 幂等发放权益 →
  补发发货回执(notify_provide_goods, 失败仅记日志, 不阻塞回调结果) → 返回 "success"。
  按官方契约, 回调返回 success 即视为发货完成; notify_provide_goods 仅是
  推送失败时的补发手段, 已 paid 订单的重复回调同样会补发(微信侧幂等)。
  非 xpay 事件静默返回 success。
"""

import base64
import hashlib
import logging
import struct
import xml.etree.ElementTree as ET

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.models.order import Order
from app.models.user import User
from app.services.fulfillment import fulfill_order

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wechat/msg", tags=["微信消息推送"])

XPAY_DELIVER_EVENT = "xpay_goods_deliver_notify"


# ---------------------------------------------------------------------------
# 签名 & 解密
# ---------------------------------------------------------------------------


def verify_msg_signature(
    token: str,
    timestamp: str,
    nonce: str,
    encrypt: str | None = None,
) -> str:
    """Compute the message-push signature: sha1 of sorted([token, timestamp, nonce[, encrypt]])."""
    parts = [token, timestamp, nonce]
    if encrypt:
        parts.append(encrypt)
    joined = "".join(sorted(parts))
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()


def decrypt_msg(encrypted_b64: str, encoding_aes_key: str) -> str:
    """Decrypt a WeChat message-push ciphertext (AES-256-CBC).

    Key = base64decode(EncodingAESKey + "="); IV = first 16 bytes of key.
    PKCS7 unpad, then strip the 16-byte random prefix + 4-byte big-endian
    message length.
    """
    key = base64.b64decode(encoding_aes_key + "=")
    if len(key) != 32:
        raise ValueError("EncodingAESKey 无效(应为 43 位 base64)")
    iv = key[:16]
    ct = base64.b64decode(encrypted_b64)
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ct) + decryptor.finalize()

    pad_len = padded[-1]
    if not 1 <= pad_len <= 32:
        raise ValueError("PKCS7 填充非法")
    body = padded[:-pad_len]
    if len(body) < 20:
        raise ValueError("密文内容过短")
    msg_len = struct.unpack(">I", body[16:20])[0]
    return body[20 : 20 + msg_len].decode("utf-8")


def _parse_xml(xml_text: str) -> dict[str, str]:
    """Parse the push XML into a flat {tag: text} dict (CDATA included)."""
    root = ET.fromstring(xml_text)
    result = {}
    for child in root:
        result[child.tag] = (child.text or "").strip()
    return result


def _extract_encrypt(xml_text: str) -> str:
    """Pull the <Encrypt> node from a compatible-mode body."""
    parsed = _parse_xml(xml_text)
    encrypt = parsed.get("Encrypt")
    if not encrypt:
        raise HTTPException(status_code=400, detail="缺少 Encrypt 节点")
    return encrypt


# ---------------------------------------------------------------------------
# GET — URL 验证
# ---------------------------------------------------------------------------


@router.get("")
async def verify_url(request: Request):
    """WeChat URL-verification (echostr). Requires a configured WX_MSG_TOKEN."""
    params = request.query_params
    signature = params.get("signature", "")
    timestamp = params.get("timestamp", "")
    nonce = params.get("nonce", "")
    echostr = params.get("echostr", "")

    if not settings.WX_MSG_TOKEN:
        raise HTTPException(status_code=403, detail="消息推送未配置")
    if not echostr:
        raise HTTPException(status_code=403, detail="缺少 echostr")
    if verify_msg_signature(settings.WX_MSG_TOKEN, timestamp, nonce) != signature:
        logger.warning("URL verification failed: signature mismatch")
        raise HTTPException(status_code=403, detail="签名验证失败")
    return Response(content=echostr, media_type="text/plain")


# ---------------------------------------------------------------------------
# POST — 事件推送
# ---------------------------------------------------------------------------


@router.post("")
async def receive_message(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive a message-push event. Returns plain "success" on OK."""
    params = request.query_params
    timestamp = params.get("timestamp", "")
    nonce = params.get("nonce", "")
    msg_signature = params.get("msg_signature", "")

    body_bytes = await request.body()
    raw_xml = body_bytes.decode("utf-8", errors="replace")

    mode = (settings.WX_MSG_ENCRYPT_MODE or "safe").lower()
    if mode == "plain":
        xml_text = raw_xml
    else:
        # compatible / safe: 验 msg_signature + AES 解密
        if not settings.WX_MSG_TOKEN:
            raise HTTPException(status_code=403, detail="消息推送未配置")
        encrypt = _extract_encrypt(raw_xml)
        expected = verify_msg_signature(settings.WX_MSG_TOKEN, timestamp, nonce, encrypt)
        if not msg_signature or expected != msg_signature:
            logger.warning("Message-push signature verification failed")
            raise HTTPException(status_code=403, detail="消息签名验证失败")
        if not settings.WX_MSG_ENCODING_AES_KEY:
            raise HTTPException(status_code=500, detail="EncodingAESKey 未配置")
        try:
            xml_text = decrypt_msg(encrypt, settings.WX_MSG_ENCODING_AES_KEY)
        except Exception as exc:
            logger.exception("Message-push decrypt failed: %s", exc)
            raise HTTPException(status_code=400, detail="消息解密失败")

    parsed = _parse_xml(xml_text)
    event = parsed.get("Event")
    if mode == "plain" and event == XPAY_DELIVER_EVENT:
        # 明文模式无验签/解密,伪造回调可刷权益 → 直接拒绝(P1-1)
        logger.warning(
            "xpay deliver notify rejected in plain mode (WX_MSG_ENCRYPT_MODE=plain) — "
            "no signature/decryption, refusing to fulfill"
        )
        raise HTTPException(status_code=403, detail="消息推送未启用安全模式")
    if event != XPAY_DELIVER_EVENT:
        # 非 xpay 事件(如普通推送/其它回调): 静默确认,不处理
        logger.info("ignoring non-xpay event: %r", event)
        return Response(content="success", media_type="text/plain")

    await _handle_xpay_deliver(parsed, db)
    return Response(content="success", media_type="text/plain")


async def _handle_xpay_deliver(parsed: dict, db: AsyncSession) -> None:
    """Handle xpay_goods_deliver_notify: verify, fulfill, and ack delivery."""
    openid = parsed.get("OpenId")
    out_trade_no = parsed.get("OutTradeNo")
    env_raw = parsed.get("Env")
    if not openid or not out_trade_no:
        raise HTTPException(status_code=400, detail="缺少 xpay 通知字段")

    result = await db.execute(select(Order).where(Order.order_no == out_trade_no))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    user_result = await db.execute(select(User).where(User.id == order.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # ── 归属校验: 通知 OpenId 必须等于订单用户的 openid ──
    if user.openid != openid:
        logger.warning(
            "xpay deliver openid mismatch for order %s: got %s, expected %s",
            out_trade_no, openid, user.openid,
        )
        raise HTTPException(status_code=400, detail="支付者与订单不一致")

    # ── 金额校验: 通知若携带金额字段(分)则必须与订单一致 ──
    amount_fen = parsed.get("Amount") or parsed.get("TotalFee")
    if amount_fen is not None:
        try:
            notified_fen = int(amount_fen)
        except (TypeError, ValueError):
            notified_fen = -1
        expected_fen = int(round(float(order.amount) * 100))
        if notified_fen != expected_fen:
            logger.warning(
                "xpay deliver amount mismatch for order %s: got %s fen, expected %s fen",
                out_trade_no, notified_fen, expected_fen,
            )
            raise HTTPException(status_code=400, detail="金额不匹配")

    env = int(env_raw) if str(env_raw).isdigit() else None

    # ── 环境校验(P2): 通知 env 必须与订单 env 一致(防沙箱/正式串单) ──
    if env is not None and order.env is not None and int(env) != int(order.env):
        logger.warning(
            "xpay deliver env mismatch for order %s: got %s, expected %s",
            out_trade_no, env, order.env,
        )
        raise HTTPException(status_code=400, detail="支付环境不匹配")

    # ── 幂等发放权益; 仅 pending 订单履约: 已 paid(重复回调)不重复发放,
    #    refunded/cancelled 不发货(P2) ──
    fulfilled = await fulfill_order(
        db, order, user,
        txn_meta={"channel": "xpay", "env": env},
    )

    # ── 发货回执(补发): 回调返回 success 即视为发货完成, 这里再主动通知微信已发货。
    #    微信侧幂等 —— 首次与已 paid 的重复回调都补发(P1-2); 失败仅记日志,
    #    不阻塞回调结果(不再按"强制步骤"返回 502 让微信重推)。
    #    refunded/cancelled 订单不补发。──
    if fulfilled or order.status == "paid":
        from app.services.xpay_api import notify_provide_goods

        try:
            await notify_provide_goods(
                out_trade_no=order.order_no,
                env=env if env is not None else int(settings.WX_XPAY_ENV or 0),
            )
        except RuntimeError as exc:
            logger.error("notify_provide_goods failed for %s: %s", order.order_no, exc)

    logger.info("Order %s fulfilled via xpay deliver notify (env=%s)", order.order_no, env)
