from pydantic import BaseModel
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

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    token: str
    user: UserResponse
