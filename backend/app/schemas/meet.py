"""星辰相遇（SDD P1 · T2-2）的请求/响应模型。"""

from pydantic import BaseModel, Field


class QuickMeetRequest(BaseModel):
    """快速合盘：只输对方星座（+可选出生日期/时间提升精确度）。

    relation 仅限 friend|love|family|work；zodiac_b 为 birthchart 12 key。
    """

    relation: str
    zodiac_b: str
    b_birth_date: str | None = None  # YYYY-MM-DD
    b_birth_time: str | None = None  # HH:MM 或 HH:MM:SS（需配合 b_birth_date）


class MeetElement(BaseModel):
    """单要素（太阳/月亮/上升之一）。"""

    zodiac: str
    name_zh: str


class MeetSide(BaseModel):
    """一方三要素：sun 必有；moon/rising 缺要素时为 null（前端标注估算）。"""

    zodiac: str
    name_zh: str
    sun: MeetElement
    moon: MeetElement | None = None
    rising: MeetElement | None = None


class MeetFactor(BaseModel):
    """每角色的相容度分解（reason 解释每分，复用 compatibility 框架）。"""

    role: str
    score: int
    reason: str


class MeetCard(BaseModel):
    """合盘三牌之一（确定性选牌；tip 走合规框架）。"""

    position: str  # 关系之牌 | 星光之牌 | 相处之牌
    card_id: int
    name_zh: str
    meaning_snippet: str  # meaning_upright 截取（可解释，非全文）
    tip: str


class MeetDetailResponse(BaseModel):
    """quick 与详情共用的完整结果。"""

    meet_id: str
    relation: str
    a: MeetSide
    b: MeetSide
    score: int
    level_name: str
    factors: list[MeetFactor]
    cards: list[MeetCard]
    tips: list[str]
    estimated: bool
    estimate_note: str


class MeetListItem(BaseModel):
    """我的相遇列表项（发起或参与）。"""

    meet_id: str
    relation: str
    b_name: str  # 对方星座中文名
    score: int | None = None
    level_name: str | None = None
    created_at: str


class MeetListResponse(BaseModel):
    meetings: list[MeetListItem] = Field(default_factory=list)


class MeetPosterSide(BaseModel):
    """海报一侧（脱敏：发起人有昵称，对方只出星座）。"""

    zodiac: str
    name_zh: str
    nickname: str | None = None


class MeetPosterCard(BaseModel):
    """海报牌面摘要（无牌意原文等敏感内容）。"""

    position: str
    name_zh: str


class MeetPosterResponse(BaseModel):
    """脱敏海报数据：昵称/星座/score/level/牌面摘要/分享文案，无日记类原文。"""

    meet_id: str
    relation: str
    a: MeetPosterSide
    b: MeetPosterSide
    score: int
    level_name: str
    cards: list[MeetPosterCard]
    share_text: str
