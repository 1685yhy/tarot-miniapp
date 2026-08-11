"""星友圈（SDD P2 · T8-1）API — 共鸣墙基础端点。

- ``GET /resonance/alias``：返回当前用户脱敏星名（首次生成落库，
  此后恒定；确定性 + 幂等）。星友圈=零 UGC 共鸣墙，星名是唯一对外
  展示身份（真实昵称/头像永不外泄）。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.user import User
from app.schemas.resonance import AliasResponse
from app.services.resonance import get_or_create_alias
from app.utils.auth import get_current_user

router = APIRouter(prefix="/resonance", tags=["今日星光共鸣"])


@router.get("/alias", response_model=AliasResponse)
async def get_alias(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """脱敏星名：首次生成落库，此后恒定（同日同人同值，幂等）。"""
    alias = await get_or_create_alias(db, user)
    return AliasResponse(alias=alias)
