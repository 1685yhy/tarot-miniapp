"""星友圈（SDD P2 · T8-1/T8-2/T8-3）的请求/响应模型。

响应合规：零 UGC、零敏感字段——只暴露系统生成的脱敏星名与聚合展示位，
不暴露 openid/nickname/avatar/birth_date/invite_code 等真实身份字段
（测试用键集断言钉住）。

T8-2 共鸣墙：
- ``today_active_criteria``：今日活跃口径纯函数（隐身即不活跃；今日有
  horoscope_history / diary / checkin / resonance 任一记录即活跃）——
  聚合端点以等价的 SQL EXISTS 落实同口径，本函数是口径的单一文档来源。
- 响应模型：``WallResponse`` = 今日活跃星光数 + 三分组
  （zodiac/number/card，含兜底组 fallback）+ 我的今日卡片（未登录 null）。
"""

from pydantic import BaseModel


class AliasResponse(BaseModel):
    """脱敏星名（首次生成落库，此后恒定）。"""

    alias: str


# ── 共鸣墙（T8-2）───────────────────────────────────────────────────────


def today_active_criteria(
    *,
    resonance_visible: bool,
    has_horoscope: bool = False,
    has_diary: bool = False,
    has_checkin: bool = False,
    has_resonance: bool = False,
) -> bool:
    """今日活跃判定（纯函数，T8-2 共鸣墙口径单一来源）。

    隐身（resonance_visible=false）即不参与展示；今日有任一行为信号
    （看过今日星光 horoscope_history / 手账日记 / 签到 / 共鸣收发）即活跃。
    聚合端点以等价的 SQL EXISTS 子句落实同口径（今日 = 北京时间日界）。
    """
    if not resonance_visible:
        return False
    return has_horoscope or has_diary or has_checkin or has_resonance


class WallCard(BaseModel):
    """今日牌（服务端确定性 pick_daily_card 同源派生，零快照）。"""

    card_id: int
    name_zh: str


class WallMember(BaseModel):
    """墙上一颗星：全脱敏字段，uid 为内部 UUID（仅共鸣/海报用途）。"""

    uid: str
    alias: str
    zodiac: str | None
    star_number: int
    card: WallCard
    tier: int
    tier_name: str
    resonate_count: int
    resonated_by_me: bool


class WallGroup(BaseModel):
    """一组星星：type = zodiac / number / card / fallback（兜底）。"""

    type: str
    label: str
    members: list[WallMember]


class MyCard(BaseModel):
    """我的今日卡片（登录可见，未登录 null；仅本人数据，可联系字段零外泄）。"""

    alias: str
    zodiac: str | None
    star_number: int
    card: WallCard
    tier_name: str
    received_today: int


class WallResponse(BaseModel):
    """共鸣墙聚合响应：今日活跃星光数 + 分组 + 我的卡片。"""

    active_count: int
    groups: list[WallGroup]
    my_card: MyCard | None


# ── 共鸣送出 / 统计 / 隐身 / 海报（T8-3）──────────────────────────────────


class GiveRequest(BaseModel):
    """送出共鸣请求：目标星内部 uid（仅共鸣/海报用途，不对外展示）。"""

    to_user_id: str


class GiveResponse(BaseModel):
    """送出共鸣响应：当日已送出数 + 每日上限（count_today 含本次）。"""

    ok: bool
    count_today: int
    limit: int


class StatsResponse(BaseModel):
    """我的共鸣统计（我的页角标数据源）。"""

    given_total: int
    received_total: int
    received_today: int


class VisibilityRequest(BaseModel):
    """隐身开关请求：false = 一键隐身（从共鸣墙/海报对外展示消失）。"""

    visible: bool


class VisibilityResponse(BaseModel):
    """隐身开关响应（写 users.resonance_visible，关闭即时生效）。"""

    ok: bool
    visible: bool


class PosterResponse(BaseModel):
    """共鸣海报数据：双方全脱敏字段（星名/星座/星光数/今日牌/星阶名）。

    - 零 UGC、零可联系字段（无昵称/头像/openid/uid——测试键集钉住）；
    - ``dimension`` = 双方共鸣维度：同星座 → zodiac；同今日牌 → card；
      否则 → number（同日全站星光数相同，恒真兜底）；
    - ``caption`` / ``disclaimer`` 为固定模板句（代码常量，过内容安全后返回）。
    """

    alias_a: str
    alias_b: str
    zodiac_a: str | None
    zodiac_b: str | None
    star_number_a: int
    star_number_b: int
    card_a: WallCard
    card_b: WallCard
    tier_name_a: str
    tier_name_b: str
    dimension: str
    caption: str
    disclaimer: str
