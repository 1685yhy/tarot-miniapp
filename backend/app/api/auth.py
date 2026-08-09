import uuid

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.models.user import User
from app.schemas.user import UserLoginRequest, LoginResponse, UserResponse
from app.utils.auth import create_token, get_current_user

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/dev-login", response_model=LoginResponse)
async def dev_login(
    member: bool | None = None,
    x_dev_key: str | None = Header(None, alias="X-Dev-Key"),
    db: AsyncSession = Depends(get_db),
):
    """开发环境：创建或获取测试用户，绕过微信登录。不传 member 时保留数据库已有会员状态；传 ?member=true/false 显式切换。

    需要请求头 ``X-Dev-Key`` 与 ``settings.DEV_LOGIN_KEY`` 一致（本地 .env 配置），
    防止公网环境被任意调用拿到测试身份。
    """
    # Safety guard: returns 404 when disabled, so the endpoint looks like it doesn't exist
    if not settings.ENABLE_DEV_LOGIN:
        raise HTTPException(status_code=404, detail="Not Found")
    # Shared-secret guard: a configured key is mandatory. Missing header or a
    # mismatch (including an empty configured key) → 401, never grant access.
    expected_key = settings.DEV_LOGIN_KEY
    if not expected_key or x_dev_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid dev key")
    test_openid = "dev_test_user_001"
    result = await db.execute(select(User).where(User.openid == test_openid))
    user = result.scalar_one_or_none()
    if not user:
        user = User(
            openid=test_openid,
            nickname="测试用户",
            is_member=member or False,
        )
        db.add(user)
        await db.flush()
    elif member is not None:
        # 仅在显式传 member 参数时覆盖状态；不传则保留数据库已有状态
        user.is_member = member
        await db.flush()

    token = create_token(user.id, user.token_version)
    return LoginResponse(token=token, user=UserResponse.model_validate(user))


@router.post("/login", response_model=LoginResponse)
async def wx_login(req: UserLoginRequest, db: AsyncSession = Depends(get_db)):
    # 调用微信接口换取 openid
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.weixin.qq.com/sns/jscode2session",
            params={
                "appid": settings.WECHAT_APP_ID,
                "secret": settings.WECHAT_APP_SECRET,
                "js_code": req.code,
                "grant_type": "authorization_code",
            },
        )
        wx_data = resp.json()

    openid = wx_data.get("openid")
    if not openid:
        raise HTTPException(status_code=400, detail=f"微信登录失败: {wx_data}")

    # 查找或创建用户
    result = await db.execute(select(User).where(User.openid == openid))
    user = result.scalar_one_or_none()
    if not user:
        user = User(openid=openid, unionid=wx_data.get("unionid"))
        db.add(user)
        await db.flush()

    # 保存 session_key(xpay 前端签名 signature 的密钥材料), AES-GCM 加密落库
    session_key = wx_data.get("session_key")
    if session_key:
        from app.services.session_key import encrypt_session_key

        user.session_key_encrypted = encrypt_session_key(session_key)
        await db.flush()

    token = create_token(user.id, user.token_version)
    return LoginResponse(token=token, user=UserResponse.model_validate(user))


@router.delete("/me")
async def delete_me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """注销账号：匿名化该用户全部数据。

    - readings / diary / chat / share / invite / community / push 数据删除；
    - 订单记录保留（财务对账需要），但用户 openid 脱敏为不可逆的 deleted_<uuid>；
    - token_version +1，使该用户所有已签发 token 立即失效。
    """
    from app.models.reading import ChatMessage, DrawnCard, Reading
    from app.models.diary import DiaryEntry
    from app.models.checkin import CheckIn
    from app.models.share_log import Invite, ShareLog
    from app.models.community import Post
    from app.models.push_subscription import PushSubscription

    # ── 删除占卜相关数据（抽牌记录 / 追问消息 / 解读）──
    subq = select(Reading.id).where(Reading.user_id == user.id)
    await db.execute(delete(DrawnCard).where(DrawnCard.reading_id.in_(subq)))
    await db.execute(delete(ChatMessage).where(ChatMessage.reading_id.in_(subq)))
    await db.execute(delete(Reading).where(Reading.user_id == user.id))

    # ── 删除其他个人数据 ──
    await db.execute(delete(DiaryEntry).where(DiaryEntry.user_id == user.id))
    await db.execute(delete(CheckIn).where(CheckIn.user_id == user.id))
    await db.execute(delete(ShareLog).where(ShareLog.sharer_id == user.id))
    await db.execute(delete(Invite).where(Invite.inviter_id == user.id))
    await db.execute(delete(Invite).where(Invite.invitee_id == user.id))
    await db.execute(delete(Post).where(Post.user_id == user.id))
    await db.execute(delete(PushSubscription).where(PushSubscription.user_id == user.id))

    # ── 匿名化用户行（订单通过 user_id 关联，保留记录；openid 脱敏）──
    user.openid = f"deleted_{uuid.uuid4().hex}"
    user.unionid = None
    user.nickname = "已注销用户"
    user.avatar_url = None
    user.session_key_encrypted = None  # xpay 签名密钥一并清除
    user.invite_code = None
    user.is_member = False
    user.member_expires_at = None
    user.paid_readings_balance = 0
    user.free_readings_today = 0
    user.free_chats_today = 0
    user.free_deep_readings = 0
    user.share_count = 0
    user.reinterpret_count_today = 0
    user.diary_ai_count_today = 0
    user.quota_reset_date = None
    # 使旧 token 全部失效
    user.token_version += 1
    await db.flush()
    return {"ok": True}
