"""合规测试层统一扫描表（SDD P1 · T2-6）：合盘/星语/宜忌 测试共用的禁词表与扫描函数。

口径：本模块是「测试层」统一扫描表——宜忌（energy_engine）、睡前星语
（star_words）、合盘（meet/compatibility）的文案/模板合规断言共用同一张表 +
同一个函数，避免每处一份拷贝。运行期清洗器按域独立：journal._sanitize /
star_words._sanitize 的替换语义词表（_BLACKLIST_WORDS / _SANITIZE_REPLACEMENTS）
是各域自己的改写规则，保留在各域模块，不属于本表、本表不接管。

- ``MEET_BLACKLIST``：合盘文案禁词（Task 21 定稿）——相处提示库 / 档位名 /
  三牌名 / reason 文案 / 分享文案，字符级口径（含「不必/必定」等含「必」形态）。
- ``AI_OUTPUT_BLACKLIST``：AI/模板文案通用红线词——星语口径
  （必/绝对/改运/化解/转运/注定/命/预测/明天一定会，2026-08-11 用户决策）
  ⊇ 宜忌口径（必/绝对/改运/化解/转运/注定），字符级。
- ``find_forbidden(text, words)``：返回命中列表（空列表 = 合规）；
  ``has_forbidden(text, words)``：布尔短路版。均为纯函数、无状态。

三层防护第一层 = 文案库/模板写死时即被测试钉住（本表）；第二层 = AI 输出红线
提示词（ai_engine._OUTPUT_RED_LINE 等）；第三层 = 输出后清洗/兜底
（star_words._sanitize / journal._sanitize 等，按域独立维护）。
"""

from __future__ import annotations

# 合盘文案禁词（Task 21 定稿，T2-6 brief）：
# 不预测、不承诺、不命运定性——「注定/天生一对/该在一起」等确定性措辞、
# 「缘分/防小人/转运/化解」等玄学操作承诺、「分开/克」等恐吓暗示，
# 以及字符级「必/绝对」（含「不必/必定/绝对」等一切形态）。
MEET_BLACKLIST: tuple[str, ...] = (
    "注定",
    "缘分",
    "天生一对",
    "该在一起",
    "分开",
    "克",
    "化解",
    "转运",
    "防小人",
    "必",
    "绝对",
)

# AI/模板文案通用红线词（用户决策 2026-08-11 确认的星语口径，
# 覆盖宜忌扫描口径；字符级，含「不必/必定/命运/走运」等一切形态）。
AI_OUTPUT_BLACKLIST: tuple[str, ...] = (
    "必",
    "绝对",
    "改运",
    "化解",
    "转运",
    "注定",
    "命",
    "预测",
    "明天一定会",
)


def find_forbidden(text: str, words: tuple[str, ...] = MEET_BLACKLIST) -> list[str]:
    """字符级禁词扫描：返回命中的禁词列表（空列表 = 合规）。

    任一禁词以子串形式出现即命中（含「不必」「必定」等含「必」形态）。
    """
    return [word for word in words if word in text]


def has_forbidden(text: str, words: tuple[str, ...] = MEET_BLACKLIST) -> bool:
    """布尔短路版：只要命中一个禁词即 True（大文本少扫描）。"""
    return any(word in text for word in words)
