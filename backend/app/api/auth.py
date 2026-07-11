import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.models.user import User
from app.schemas.user import UserLoginRequest, LoginResponse, UserResponse
from app.utils.auth import create_token

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/dev-login", response_model=LoginResponse)
async def dev_login(db: AsyncSession = Depends(get_db)):
    """开发环境：创建或获取测试用户，绕过微信登录"""
    test_openid = "dev_test_user_001"
    result = await db.execute(select(User).where(User.openid == test_openid))
    user = result.scalar_one_or_none()
    if not user:
        user = User(
            openid=test_openid,
            nickname="测试用户",
            is_member=True,  # 开发环境直接给会员
        )
        db.add(user)
        await db.flush()

    token = create_token(user.id)
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

    token = create_token(user.id)
    return LoginResponse(token=token, user=UserResponse.model_validate(user))
