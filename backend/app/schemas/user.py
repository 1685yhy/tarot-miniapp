from pydantic import BaseModel, ConfigDict
from datetime import datetime


class UserLoginRequest(BaseModel):
    code: str  # 微信 wx.login() 返回的 code


class UserResponse(BaseModel):
    id: str
    nickname: str | None
    avatar_url: str | None
    is_member: bool
    member_expires_at: datetime | None
    free_readings_today: int
    free_chats_today: int
    # P0-1: standalone annual-report purchase entitlement (default False keeps
    # backwards-compatible serialization for old clients)
    annual_report_paid: bool = False

    model_config = ConfigDict(from_attributes=True)


class LoginResponse(BaseModel):
    token: str
    user: UserResponse
