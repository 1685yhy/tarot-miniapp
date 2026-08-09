"""
微信小程序虚拟支付(xpay)改造测试。

- xpay 签名正确性(HMAC 手算对照)
- 消息推送验签(sha1 对照)+ AES-256-CBC 解密往返
- GET /wechat/msg echostr URL 验证
- xpay_goods_deliver_notify 事件 → 权益发放 → 发货回执,幂等(同一事件两次不重复发权益)
- 道具未配置时 POST /orders 返回 400 优雅降级
- POST /orders xpay 全链路签名参数正确
- GET /orders/{order_no}/status?remote=true 实时查询映射(不回退已发放权益)
- session_key 加密存储与注销清理
"""

import asyncio
import base64
import hashlib
import hmac
import json
import os
import struct
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.wechat_msg import decrypt_msg, verify_msg_signature
from app.config import settings
from app.db.database import async_session
from app.models.order import Order
from app.models.user import User
from app.services.payment import sign_xpay_params, sign_xpay_signature
from app.services.session_key import decrypt_session_key, encrypt_session_key

# ── 固定测试密钥(与 .env 无关,保证断言确定性) ──
APP_KEY_PROD = "test_prod_app_key_0123456789"
APP_KEY_SANDBOX = "test_sandbox_app_key_abcdefghij"
SESSION_KEY_RAW = "test_session_key_0123456789"
OFFER_ID = "10000001"
MSG_TOKEN = "test_msg_token_123"


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def _wechat_encrypt(plaintext: str, encoding_aes_key_43: str) -> str:
    """构造微信安全模式密文(测试用): 随机16字节 + 4字节长度 + 消息, PKCS7 + AES-256-CBC。"""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    key = base64.b64decode(encoding_aes_key_43 + "=")
    iv = key[:16]
    body = os.urandom(16) + struct.pack(">I", len(plaintext.encode())) + plaintext.encode()
    pad_len = 32 - len(body) % 32
    padded = body + bytes([pad_len]) * pad_len
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ct = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(ct).decode()


def _xpay_deliver_xml(openid: str, out_trade_no: str, env: str = "0", amount: str | None = None) -> str:
    amount_xml = f"<Amount><![CDATA[{amount}]]></Amount>" if amount else ""
    return (
        "<xml>"
        "<ToUserName><![CDATA[gh_test]]></ToUserName>"
        "<FromUserName><![CDATA[o4wcpxxx]]></FromUserName>"
        "<CreateTime>1497843672</CreateTime>"
        "<MsgType><![CDATA[event]]></MsgType>"
        f"<Event><![CDATA[xpay_goods_deliver_notify]]></Event>"
        f"<OpenId><![CDATA[{openid}]]></OpenId>"
        f"<OutTradeNo><![CDATA[{out_trade_no}]]></OutTradeNo>"
        f"<Env>{env}</Env>"
        f"{amount_xml}"
        "</xml>"
    )


async def _get_user(openid: str) -> User:
    async with async_session() as s:
        result = await s.execute(select(User).where(User.openid == openid))
        return result.scalar_one_or_none()


async def _create_order(openid: str, order_no: str, product_type="single_reading", amount=9.90, status="pending", env=0, pay_channel="xpay"):
    async with async_session() as s:
        user = (await s.execute(select(User).where(User.openid == openid))).scalar_one()
        order = Order(
            user_id=user.id,
            order_no=order_no,
            product_type=product_type,
            amount=amount,
            status=status,
            pay_channel=pay_channel,
            env=env,
        )
        s.add(order)
        await s.commit()
        return order.id


async def _order_by_no(order_no: str) -> Order:
    async with async_session() as s:
        return (await s.execute(select(Order).where(Order.order_no == order_no))).scalar_one()


async def _seed_user(openid: str, session_key_encrypted=None) -> User:
    async with async_session() as s:
        user = User(openid=openid, nickname=f"xpay-{uuid.uuid4().hex[:6]}")
        if session_key_encrypted:
            user.session_key_encrypted = session_key_encrypted
        s.add(user)
        await s.commit()
        return user


def _dev_login(client: TestClient) -> dict:
    resp = client.post("/auth/dev-login", headers={"X-Dev-Key": settings.DEV_LOGIN_KEY})
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# 1. xpay 签名正确性(HMAC 手算对照)
# ---------------------------------------------------------------------------


def test_xpay_paysig_hmac_hand_computed():
    """paySig = HMAC-SHA256(AppKey, 'requestVirtualPayment&'+signData), 小写 hex。"""
    sign_data = json.dumps(
        {"offerId": OFFER_ID, "buyQuantity": 1, "env": 0, "currencyType": "CNY",
         "productId": "1001", "goodsPrice": 990, "outTradeNo": "TAROT0000000000AB12CD", "attach": "single_reading"},
        separators=(",", ":"),
    )
    expected = hmac.new(
        APP_KEY_PROD.encode(),
        f"requestVirtualPayment&{sign_data}".encode(),
        hashlib.sha256,
    ).hexdigest()
    assert sign_xpay_params(APP_KEY_PROD, sign_data) == expected
    # 不同 AppKey → 不同签名
    assert sign_xpay_params(APP_KEY_SANDBOX, sign_data) != expected


def test_xpay_signature_hmac_hand_computed():
    """signature = HMAC-SHA256(session_key, signData), 小写 hex, session_key 不解码。"""
    sign_data = '{"offerId":"10000001","buyQuantity":1}'
    expected = hmac.new(
        SESSION_KEY_RAW.encode(),
        sign_data.encode(),
        hashlib.sha256,
    ).hexdigest()
    assert sign_xpay_signature(SESSION_KEY_RAW, sign_data) == expected
    # 同一 session_key 重复签名结果一致(前端可重复签名)
    assert sign_xpay_signature(SESSION_KEY_RAW, sign_data) == expected


# ---------------------------------------------------------------------------
# 2. 消息推送验签(sha1 对照)+ AES 解密往返
# ---------------------------------------------------------------------------


def test_msg_signature_sha1_hand_computed():
    """msg_signature = sha1(join(sorted([token, timestamp, nonce[, encrypt]])))。"""
    token, ts, nonce = MSG_TOKEN, "1700000000", "nonce_abc"
    assert verify_msg_signature(token, ts, nonce) == hashlib.sha1(
        "".join(sorted([token, ts, nonce])).encode()
    ).hexdigest()
    encrypt = "encrypted_payload_123"
    assert verify_msg_signature(token, ts, nonce, encrypt) == hashlib.sha1(
        "".join(sorted([token, ts, nonce, encrypt])).encode()
    ).hexdigest()
    # token 不同 → 签名不同
    assert verify_msg_signature("other", ts, nonce) != verify_msg_signature(token, ts, nonce)


def test_msg_aes_decrypt_roundtrip():
    """安全模式 AES-256-CBC 解密: 去随机前缀+长度, 还原原文。"""
    key_43 = base64.b64encode(os.urandom(32)).decode()[:43]  # 43位(去填充),解码后32字节
    plain = "<xml><Event><![CDATA[xpay_goods_deliver_notify]]></Event></xml>"
    ct = _wechat_encrypt(plain, key_43)
    assert decrypt_msg(ct, key_43) == plain


# ---------------------------------------------------------------------------
# 3. GET /wechat/msg echostr URL 验证
# ---------------------------------------------------------------------------


def test_wechat_msg_echostr_verification(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "WX_MSG_TOKEN", MSG_TOKEN)
    ts, nonce, echostr = "1700000001", "nonce_1", "hello_from_wechat"
    signature = verify_msg_signature(MSG_TOKEN, ts, nonce)
    resp = client.get(
        f"/wechat/msg?signature={signature}&timestamp={ts}&nonce={nonce}&echostr={echostr}"
    )
    assert resp.status_code == 200
    assert resp.text == echostr

    # 错误签名 → 403
    resp = client.get(
        f"/wechat/msg?signature=deadbeef&timestamp={ts}&nonce={nonce}&echostr={echostr}"
    )
    assert resp.status_code == 403

    # 未配置 token → 403
    monkeypatch.setattr(settings, "WX_MSG_TOKEN", "")
    resp = client.get(
        f"/wechat/msg?signature={signature}&timestamp={ts}&nonce={nonce}&echostr={echostr}"
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 4. xpay 事件 → 权益发放 → 发货回执, 幂等
# ---------------------------------------------------------------------------


def test_xpay_deliver_notify_fulfills_once(client: TestClient, monkeypatch):
    """同一 xpay 发货事件两次: 权益只发一次, 发货回执只调一次。"""
    monkeypatch.setattr(settings, "WX_MSG_ENCRYPT_MODE", "plain")
    openid = f"xpay_deliver_{uuid.uuid4().hex[:8]}"
    asyncio.run(_seed_user(openid))
    order_no = f"TAROT{uuid.uuid4().hex[:12].upper()}"
    asyncio.run(_create_order(openid, order_no))

    calls = []

    async def fake_notify_provide_goods(**kwargs):
        calls.append(kwargs)
        return {"errcode": 0, "errmsg": "ok"}

    monkeypatch.setattr("app.services.xpay_api.notify_provide_goods", fake_notify_provide_goods)

    xml = _xpay_deliver_xml(openid, order_no)
    for _ in range(2):
        resp = client.post("/wechat/msg", content=xml, headers={"Content-Type": "text/xml"})
        assert resp.status_code == 200
        assert resp.text == "success"

    assert len(calls) == 1, "发货回执应只调用一次"
    assert calls[0]["out_trade_no"] == order_no
    assert calls[0]["env"] == 0
    assert calls[0]["openid"] == openid

    user = asyncio.run(_get_user(openid))
    assert (user.paid_readings_balance or 0) == 1, "权益只发放一次"
    order = asyncio.run(_order_by_no(order_no))
    assert order.status == "paid"
    assert order.pay_channel == "xpay"
    assert order.env == 0
    assert order.delivered_at is not None


def test_xpay_deliver_notify_safe_mode_encrypted(client: TestClient, monkeypatch):
    """安全模式(加密+msg_signature 验签)下 xpay 事件同样能处理。"""
    key_43 = base64.b64encode(os.urandom(32)).decode()[:43]
    monkeypatch.setattr(settings, "WX_MSG_TOKEN", MSG_TOKEN)
    monkeypatch.setattr(settings, "WX_MSG_ENCODING_AES_KEY", key_43)
    monkeypatch.setattr(settings, "WX_MSG_ENCRYPT_MODE", "safe")

    openid = f"xpay_safe_{uuid.uuid4().hex[:8]}"
    asyncio.run(_seed_user(openid))
    order_no = f"TAROT{uuid.uuid4().hex[:12].upper()}"
    asyncio.run(_create_order(openid, order_no))

    async def fake_notify_provide_goods(**kwargs):
        return {"errcode": 0, "errmsg": "ok"}

    monkeypatch.setattr("app.services.xpay_api.notify_provide_goods", fake_notify_provide_goods)

    plain_xml = _xpay_deliver_xml(openid, order_no, amount="990")
    encrypt = _wechat_encrypt(plain_xml, key_43)
    ts, nonce = "1700000002", "nonce_safe"
    msg_signature = verify_msg_signature(MSG_TOKEN, ts, nonce, encrypt)

    resp = client.post(
        f"/wechat/msg?timestamp={ts}&nonce={nonce}&msg_signature={msg_signature}",
        content=f"<xml><Encrypt><![CDATA[{encrypt}]]></Encrypt></xml>",
        headers={"Content-Type": "text/xml"},
    )
    assert resp.status_code == 200
    assert resp.text == "success"

    user = asyncio.run(_get_user(openid))
    assert (user.paid_readings_balance or 0) == 1
    order = asyncio.run(_order_by_no(order_no))
    assert order.status == "paid"

    # 错误 msg_signature → 403
    bad = client.post(
        f"/wechat/msg?timestamp={ts}&nonce={nonce}&msg_signature=beef",
        content=f"<xml><Encrypt><![CDATA[{encrypt}]]></Encrypt></xml>",
        headers={"Content-Type": "text/xml"},
    )
    assert bad.status_code == 403


def test_xpay_deliver_notify_rejects_openid_mismatch(client: TestClient, monkeypatch):
    """通知 OpenId 与订单归属用户不一致 → 400, 不发权益。"""
    monkeypatch.setattr(settings, "WX_MSG_ENCRYPT_MODE", "plain")
    openid = f"xpay_mismatch_{uuid.uuid4().hex[:8]}"
    asyncio.run(_seed_user(openid))
    order_no = f"TAROT{uuid.uuid4().hex[:12].upper()}"
    asyncio.run(_create_order(openid, order_no))

    calls = []

    async def fake_notify_provide_goods(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("app.services.xpay_api.notify_provide_goods", fake_notify_provide_goods)

    xml = _xpay_deliver_xml("someone_else_openid", order_no)
    resp = client.post("/wechat/msg", content=xml, headers={"Content-Type": "text/xml"})
    assert resp.status_code == 400
    assert calls == []
    assert asyncio.run(_order_by_no(order_no)).status == "pending"


def test_wechat_msg_ignores_non_xpay_event(client: TestClient, monkeypatch):
    """非 xpay 事件静默返回 success。"""
    monkeypatch.setattr(settings, "WX_MSG_ENCRYPT_MODE", "plain")
    xml = "<xml><ToUserName><![CDATA[gh_test]]></ToUserName><Event><![CDATA[other_event]]></Event></xml>"
    resp = client.post("/wechat/msg", content=xml, headers={"Content-Type": "text/xml"})
    assert resp.status_code == 200
    assert resp.text == "success"


# ---------------------------------------------------------------------------
# 5. 道具未配置 → POST /orders 400 优雅降级
# ---------------------------------------------------------------------------


def test_create_order_400_when_xpay_product_unconfigured(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "PAY_CHANNEL", "xpay")
    monkeypatch.setattr(settings, "XPAY_PRODUCT_MAP", "{}")
    token = _dev_login(client)["token"]
    resp = client.post(
        "/orders",
        json={"product_type": "single_reading"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "该商品即将上线,敬请期待"


# ---------------------------------------------------------------------------
# 6. POST /orders xpay 全链路签名参数
# ---------------------------------------------------------------------------


def test_create_order_xpay_params_full(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "PAY_CHANNEL", "xpay")
    monkeypatch.setattr(settings, "WX_XPAY_OFFER_ID", OFFER_ID)
    monkeypatch.setattr(settings, "WX_XPAY_APPKEY_PROD", APP_KEY_PROD)
    monkeypatch.setattr(settings, "WX_XPAY_APPKEY_SANDBOX", APP_KEY_SANDBOX)
    monkeypatch.setattr(settings, "WX_XPAY_ENV", 0)
    monkeypatch.setattr(settings, "XPAY_PRODUCT_MAP", json.dumps({"single_reading": "1001"}))

    login = _dev_login(client)
    token = login["token"]
    user_id = login["user"]["id"]

    # 该用户需要有加密存储的 session_key(模拟真实登录时落库)
    async def _set_session_key():
        async with async_session() as s:
            user = (await s.execute(select(User).where(User.id == user_id))).scalar_one()
            user.session_key_encrypted = encrypt_session_key(SESSION_KEY_RAW)
            await s.commit()
    asyncio.run(_set_session_key())

    resp = client.post(
        "/orders",
        json={"product_type": "single_reading"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["payment_params"] is None, "xpay 通道不应返回 jsapi payment_params"
    params = data["xpay_params"]
    assert params["mode"] == "short_series_goods"

    sign_data = params["signData"]
    payload = json.loads(sign_data)
    assert payload["offerId"] == OFFER_ID
    assert payload["buyQuantity"] == 1
    assert payload["env"] == 0
    assert payload["currencyType"] == "CNY"
    assert payload["productId"] == "1001"
    assert payload["goodsPrice"] == 990  # 9.90 元 → 分
    assert 8 <= len(payload["outTradeNo"]) <= 32
    assert payload["attach"] == "single_reading"

    # paySig / signature 与独立手算结果一致
    assert params["paySig"] == sign_xpay_params(APP_KEY_PROD, sign_data)
    assert params["signature"] == sign_xpay_signature(SESSION_KEY_RAW, sign_data)

    # 订单落库: pay_channel/env 正确
    order = asyncio.run(_order_by_no(payload["outTradeNo"]))
    assert order.pay_channel == "xpay"
    assert order.env == 0
    assert order.status == "pending"

    # 无 session_key 的用户 → 400(登录凭证缺失)
    from app.utils.auth import create_token

    no_sk_openid = f"xpay_nosk_{uuid.uuid4().hex[:8]}"
    asyncio.run(_seed_user(no_sk_openid))
    no_sk_token = create_token(asyncio.run(_get_user(no_sk_openid)).id)
    resp2 = client.post(
        "/orders",
        json={"product_type": "single_reading"},
        headers={"Authorization": f"Bearer {no_sk_token}"},
    )
    assert resp2.status_code == 400
    assert resp2.json()["detail"] == "登录凭证缺失,请重新登录"


# ---------------------------------------------------------------------------
# 7. GET /orders/{order_no}/status?remote=true (xpay 状态映射, 不回退权益)
# ---------------------------------------------------------------------------


def test_order_status_remote_query_and_mapping(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "PAY_CHANNEL", "xpay")
    openid = f"xpay_remote_{uuid.uuid4().hex[:8]}"
    asyncio.run(_seed_user(openid))
    order_no = f"TAROT{uuid.uuid4().hex[:12].upper()}"
    asyncio.run(_create_order(openid, order_no))

    async def fake_query_order(**kwargs):
        return {"errcode": 0, "errmsg": "ok", "state": 4}  # 已发货

    monkeypatch.setattr("app.services.xpay_api.query_order", fake_query_order)

    # 需要一个能查看该订单的 token —— 直接给该用户签发
    from app.utils.auth import create_token

    token = create_token(asyncio.run(_get_user(openid)).id)
    auth = {"Authorization": f"Bearer {token}"}

    resp = client.get(f"/orders/{order_no}/status?remote=true", headers=auth)
    assert resp.status_code == 200
    data = resp.json()
    assert data["remote"] is True
    assert data["remote_state"] == "paid"
    # 本地保持 pending —— 权益未由推送补齐前不置 paid
    assert data["status"] == "pending"
    assert data["paid"] is False

    # 远程已退款 → 本地 refunded, 但权益不回退
    async def fake_query_refunded(**kwargs):
        return {"errcode": 0, "errmsg": "ok", "state": 5}

    monkeypatch.setattr("app.services.xpay_api.query_order", fake_query_refunded)
    resp = client.get(f"/orders/{order_no}/status?remote=true", headers=auth)
    data = resp.json()
    assert data["status"] == "refunded"
    assert data["remote_state"] == "refunded"
    order = asyncio.run(_order_by_no(order_no))
    assert order.refund_status == "refunded"

    # 远程已支付但本地已 paid(权益已发) → 永不回退
    async def fake_query_cancelled(**kwargs):
        return {"errcode": 0, "errmsg": "ok", "state": 6}

    monkeypatch.setattr("app.services.xpay_api.query_order", fake_query_cancelled)

    async def _mark_paid():
        async with async_session() as s:
            order = (await s.execute(select(Order).where(Order.order_no == order_no))).scalar_one()
            order.status = "paid"
            order.paid_at = datetime.now(timezone.utc)
            await s.commit()
    asyncio.run(_mark_paid())
    resp = client.get(f"/orders/{order_no}/status?remote=true", headers=auth)
    assert resp.json()["status"] == "paid", "已发放权益的订单不可被远程状态回退"


# ---------------------------------------------------------------------------
# 8. session_key 加密存储与注销清理
# ---------------------------------------------------------------------------


def test_login_stores_encrypted_session_key_and_delete_clears(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "WECHAT_API_KEY_V3", "TestApiV3Key0123456789")
    raw_session_key = "sk_abcdef_1234567890"

    class _FakeResp:
        def __init__(self, data):
            self._data = data

        def json(self):
            return self._data

    class _FakeClient:
        def __init__(self, data):
            self._data = data

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return _FakeResp(self._data)

    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda *a, **k: _FakeClient({
            "openid": f"sk_openid_{uuid.uuid4().hex[:8]}",
            "session_key": raw_session_key,
        }),
    )

    resp = client.post("/auth/login", json={"code": "test_code"})
    assert resp.status_code == 200
    token = resp.json()["token"]
    openid = resp.json()["user"]["id"]  # id 而非 openid,用 id 查库
    user = asyncio.run(_get_user_by_id(openid))
    assert user.session_key_encrypted is not None
    assert raw_session_key not in user.session_key_encrypted, "session_key 必须加密存储"
    assert decrypt_session_key(user.session_key_encrypted) == raw_session_key

    # 注销 → 清空
    resp = client.delete("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    user = asyncio.run(_get_user_by_id(openid))
    assert user.session_key_encrypted is None


async def _get_user_by_id(user_id: str) -> User:
    async with async_session() as s:
        return (await s.execute(select(User).where(User.id == user_id))).scalar_one()
