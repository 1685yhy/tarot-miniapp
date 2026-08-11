"""星友圈共鸣服务（SDD P2 · T8-1）：脱敏星名词库 + 确定性生成 + 落库。

设计（T8-1 简报 + 设计 3.3）：
- ``ALIAS_POOL``：40 个自然意象词定稿（晚风/山茶/松声…），定稿即过
  compliance 扫描（MEET_BLACKLIST + AI_OUTPUT_BLACKLIST 双表零命中，
  测试钉住）；词长 ≤8 字，配合前缀「星星·」落 users.star_alias(String(16))。
- ``generate_alias``：纯确定性（user_id 字符码和 + 日期序数对 40 取模）——
  同日同人恒定，跨日/跨用户自然轮换；无 IO、无随机。
- ``get_or_create_alias``：无则生成并落库 users.star_alias（幂等：
  已有值原样返回；确定性保证并发双写同值，无唯一约束冲突面）。
- 共鸣防刷（每日 10 次上限）在 star_resonances 表 + 计数逻辑落实
  （Task 2 实现共鸣写入端点，本任务先建表 + 星名基础）。
"""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.star_words import beijing_today

# 星名词库（40 词定稿，全部自然意象，无冒犯/玄学承诺词；合规扫描见测试）
ALIAS_POOL: tuple[str, ...] = (
    "晚风", "山茶", "松声", "流萤", "竹影", "晨露", "细雨", "初雪",
    "萤火", "涟漪", "月桂", "晨星", "林雾", "溪泉", "蔷薇", "麦浪",
    "青苔", "云雀", "白鹭", "松涛", "荷风", "稻香", "雪松", "杜鹃",
    "海潮", "星砂", "晚霞", "朝霞", "篝火", "灯影", "风铃", "雨巷",
    "雾凇", "霜叶", "夜莺", "星辰", "银波", "花火", "桂香", "竹风",
)


def generate_alias(user_id: str, day: date) -> str:
    """确定性星名：``星星·{ALIAS_POOL[(user_id 字符码和 + day 序数) % 40]}``。

    同日同人恒定（seed 恒定）；跨日自然轮换（day.toordinal() 参与）；
    不同用户大概率不同词（抽样断言非全同）。
    """
    seed = sum(ord(c) for c in user_id) + day.toordinal()
    return f"星星·{ALIAS_POOL[seed % len(ALIAS_POOL)]}"


async def get_or_create_alias(db: AsyncSession, user: User) -> str:
    """获取（必要时生成并落库）用户脱敏星名：幂等。

    users.star_alias 已有值 → 原样返回；否则以今日（beijing_today 日界
    口径）为种子生成并写库。flush 后由端点上层 get_db 统一 commit。
    """
    if user.star_alias:
        return user.star_alias
    alias = generate_alias(user.id, beijing_today())
    user.star_alias = alias
    await db.flush()
    return alias
