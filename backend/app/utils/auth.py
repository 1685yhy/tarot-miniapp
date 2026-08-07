from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.models.user import User


def create_token(user_id: str, token_version: int = 0) -> str:
    """Create a JWT for the user.

    ``tv`` (token_version) is embedded in the payload so that logging out or
    deleting an account (which bumps ``User.token_version``) invalidates all
    previously issued tokens.
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "tv": token_version,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="无效的登录凭证")


async def get_user_from_token(token: str, db: AsyncSession) -> User:
    """Validate a raw JWT and return the matching user (with token_version check)."""
    payload = decode_token(token)
    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    # Tokens issued before logout/account-deletion carry a stale tv → reject.
    if user.token_version != payload.get("tv", 0):
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    return user


async def get_current_user(
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization:
        raise HTTPException(status_code=401, detail="未登录")
    token = authorization.replace("Bearer ", "")
    return await get_user_from_token(token, db)


async def get_optional_user(
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Like ``get_current_user`` but returns None instead of 401.

    Used by endpoints that behave differently for logged-in users but
    must stay open to anonymous callers (e.g. /cards/daily).
    """
    if not authorization:
        return None
    try:
        return await get_user_from_token(authorization.replace("Bearer ", ""), db)
    except HTTPException:
        return None


def utc_aware(dt):
    """Normalize a possibly-naive datetime (e.g. from SQLite) to aware UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
