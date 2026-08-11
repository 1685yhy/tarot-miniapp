"""
星辰相遇（SDD P1 · T2-6）合规测试：措辞黑名单扫描 + 海报内容安全检测。

覆盖（task-21-brief Step 1 验收）：
- MEET_BLACKLIST 字符级扫描：相处提示库 / 档位名（星光共鸣·相映·相伴·初见）/
  三牌名 + 牌位名 / 全 144 组合 reason 文案 / 海报 share_text → 断言无黑名单词
- 扫描有效性正控：含黑名单词的样本必须被 find_forbidden 命中（防词表/扫描器
  失效导致的假绿——brief Step 1「先放入已知违规词验证测试有效性」的常驻形态）
- msg_sec_check 接入海报链路（app/api/meet.py）：
  * 命中风险 → share_text 替换为安全兜底文案 + 记日志（不 4xx，不阻塞出图）
  * 抛异常 → 不阻塞返回原文（fail-open，与 community 同口径）
  * 通过/跳过 → 原分享文案原样返回（含 score）
- 白名单统一：宜忌/星语/合盘共用 compliance 模块（AI_OUTPUT_BLACKLIST /
  MEET_BLACKLIST / find_forbidden），不再各测各表
"""

import asyncio
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.meet import MEET_TIPS, _MEET_SHARE_FALLBACK
from app.db.database import async_session
from app.models.card import TarotCard
from app.models.star_meeting import StarMeeting
from app.models.user import User
from app.services.birthchart import ZODIAC_KEYS
from app.services.compatibility import LEVEL_NAMES, compute_compatibility
from app.services.compliance import (
    AI_OUTPUT_BLACKLIST,
    MEET_BLACKLIST,
    find_forbidden,
)
from app.utils.auth import create_token

# 档位名取真实来源 compatibility.LEVEL_NAMES（T2-1 设计定稿：
# 85+ 星光共鸣 / 70+ 星光相映 / 55+ 星光相伴 / 其余 星光初见），不自行拷贝

# 牌位名（T2-2 三牌位）
CARD_POSITION_NAMES = ("关系之牌", "星光之牌", "相处之牌")

BIRTH = {"zodiac": "leo", "birth_date": "1996-08-10", "birth_time": "14:30", "birth_city": "北京"}
B_BIRTH_DATE = "1995-03-21"
B_BIRTH_TIME = "08:00"

RELATIONS = ("friend", "love", "family", "work")


# ── helpers（与 test_meet.py 同款隔离用户/请求）───────────────────────────


def _new_user(openid: str, **fields) -> dict:
    """创建隔离测试用户，返回 {id, token}。"""

    async def _go() -> dict:
        async with async_session() as session:
            user = User(openid=openid, nickname="合规测试", **fields)
            session.add(user)
            await session.flush()
            token = create_token(user.id, user.token_version)
            await session.commit()
            return {"id": user.id, "token": token}

    return asyncio.run(_go())


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _payload(**overrides) -> dict:
    base = {
        "relation": "friend",
        "zodiac_b": "taurus",
        "b_birth_date": B_BIRTH_DATE,
        "b_birth_time": B_BIRTH_TIME,
    }
    base.update(overrides)
    return base


def _quick(client: TestClient, token: str, **overrides) -> dict:
    r = client.post("/meet/quick", json=_payload(**overrides), headers=_auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def _scan(text: str, words: tuple[str, ...] = MEET_BLACKLIST) -> list[str]:
    """字符级禁词扫描（同一口径：任一禁词出现在文案即返回命中列表）。"""
    return find_forbidden(text, words)


# ══════════════════════════════════════════════════════════════════
# 1. 措辞白名单扫描（三层防护第一层：文案库/模板恒无黑名单词）
# ══════════════════════════════════════════════════════════════════


def test_meet_tips_no_blacklist():
    """相处提示库全量过 MEET_BLACKLIST。"""
    assert len(MEET_TIPS) >= 10, "相处提示库应 ≥10 条"
    for tip in MEET_TIPS:
        assert not _scan(tip), f"相处提示含禁词 {_scan(tip)}: {tip}"


def test_meet_level_names_no_blacklist():
    """档位名（真实来源 compatibility.LEVEL_NAMES）过 MEET_BLACKLIST。"""
    assert len(LEVEL_NAMES) == 4
    for name in LEVEL_NAMES:
        assert not _scan(name), f"档位名含禁词 {_scan(name)}: {name}"


def test_meet_card_names_no_blacklist(client: TestClient):
    """三牌名（牌库全部卡牌名）+ 牌位名过 MEET_BLACKLIST（含 meaning 截断的
    卡牌 tip 是塔罗象征内容而非关系预测文案，故只扫牌名——与 brief 一致）。"""

    async def _names() -> list[str]:
        async with async_session() as session:
            rows = (await session.execute(select(TarotCard.name_zh))).scalars().all()
            return list(rows)

    names = asyncio.run(_names())
    # 牌库规模钉住 78 张（与 seed.py 导入断言一致，守护种子完整性）
    assert len(names) == 78, f"牌库应恒为 78 张（种子完整性），实际 {len(names)}"
    for name in names:
        assert not _scan(name), f"卡牌名含禁词 {_scan(name)}: {name}"
    for pos in CARD_POSITION_NAMES:
        assert not _scan(pos), f"牌位名含禁词 {_scan(pos)}: {pos}"


def test_meet_compat_reasons_no_blacklist():
    """全 144 组合 reason 文案（同元素/互补/异元素 × 全部档位）过 MEET_BLACKLIST。"""
    reasons: set[str] = set()
    for a in ZODIAC_KEYS:
        for b in ZODIAC_KEYS:
            result = compute_compatibility(a_sun=a, b_sun=b)
            for factor in result["factors"]:
                reasons.add(factor["reason"])
    assert len(reasons) >= 4  # 至少覆盖四种关系模板（同元素/火风/土水/异元素）
    for reason in reasons:
        assert not _scan(reason), f"reason 含禁词 {_scan(reason)}: {reason}"


def test_meet_share_texts_no_blacklist(client: TestClient):
    """海报 share_text（有分/无分两形态 + 兜底文案）过 MEET_BLACKLIST。"""
    user = _new_user(f"comply_a_{uuid.uuid4().hex[:8]}", **BIRTH)
    created = _quick(client, user["token"])
    r = client.get(f"/meet/{created['meet_id']}/poster", headers=_auth(user["token"]))
    assert r.status_code == 200, r.text
    data = r.json()
    assert "share_text" in data and str(data["score"]) in data["share_text"]
    assert not _scan(data["share_text"]), f"分享文案含禁词 {_scan(data['share_text'])}: {data['share_text']}"

    # 无 score 形态（result_json 缺 score）
    async def _patch():
        async with async_session() as session:
            row = await session.get(StarMeeting, created["meet_id"])
            row.result_json = "{}"
            await session.commit()

    asyncio.run(_patch())
    r2 = client.get(f"/meet/{created['meet_id']}/poster", headers=_auth(user["token"]))
    assert r2.status_code == 200, r2.text
    share2 = r2.json()["share_text"]
    assert share2 and "None" not in share2
    assert not _scan(share2), f"分享文案含禁词 {_scan(share2)}: {share2}"

    # 兜底文案本身合规
    assert not _scan(_MEET_SHARE_FALLBACK), f"兜底文案含禁词 {_scan(_MEET_SHARE_FALLBACK)}: {_MEET_SHARE_FALLBACK}"


def test_compliance_scanner_detects_known_violation():
    """扫描有效性正控：黑名单词/表一旦失效测试必红（防假绿）。"""
    sample = "我们命中注定要在一起，绝对没错"
    hits = _scan(sample)
    assert "注定" in hits and "绝对" in hits, f"扫描器未命中已知禁词: {hits}"

    hits_ai = find_forbidden("明天一定会转运", AI_OUTPUT_BLACKLIST)
    assert "明天一定会" in hits_ai and "转运" in hits_ai, f"AI 红线扫描未命中: {hits_ai}"


def test_shared_blacklist_covers_legacy_sets():
    """统一白名单收敛：宜忌（必/绝对/改运/化解/转运/注定）与星语口径
    （+命/预测/明天一定会）必须是 AI_OUTPUT_BLACKLIST 的子集——老测试
    迁移到共享表后行为只增不减。"""
    legacy_guidance = ("必", "绝对", "改运", "化解", "转运", "注定")
    legacy_star_words = legacy_guidance + ("命", "预测", "明天一定会")
    assert set(legacy_guidance) <= set(AI_OUTPUT_BLACKLIST)
    assert set(legacy_star_words) <= set(AI_OUTPUT_BLACKLIST)


# ══════════════════════════════════════════════════════════════════
# 2. 海报内容安全：msg_sec_check 接入（命中→兜底；异常→不阻塞原文）
# ══════════════════════════════════════════════════════════════════


def test_poster_msg_check_risky_replaced_with_fallback(client: TestClient, monkeypatch):
    """msg_sec_check 命中风险 → share_text 替换为安全兜底文案 + 不 4xx。"""
    async def _fake_risky(content: str, openid: str | None = None) -> dict:
        return {"safe": False, "skipped": False, "err": "risky content"}

    monkeypatch.setattr("app.api.meet.msg_sec_check", _fake_risky)

    user = _new_user(f"comply_r_{uuid.uuid4().hex[:8]}", **BIRTH)
    created = _quick(client, user["token"])
    r = client.get(f"/meet/{created['meet_id']}/poster", headers=_auth(user["token"]))
    assert r.status_code == 200, r.text  # 命中风险不阻塞出图
    assert r.json()["share_text"] == _MEET_SHARE_FALLBACK


def test_poster_msg_check_exception_returns_original(client: TestClient, monkeypatch):
    """msg_sec_check 抛异常 → 不阻塞，share_text 返回原文（fail-open）。"""
    async def _fake_boom(content: str, openid: str | None = None) -> dict:
        raise RuntimeError("wechat api down")

    monkeypatch.setattr("app.api.meet.msg_sec_check", _fake_boom)

    user = _new_user(f"comply_e_{uuid.uuid4().hex[:8]}", **BIRTH)
    created = _quick(client, user["token"])
    r = client.get(f"/meet/{created['meet_id']}/poster", headers=_auth(user["token"]))
    assert r.status_code == 200, r.text
    share = r.json()["share_text"]
    assert str(created["score"]) in share  # 原文（含 score）原样返回


def test_poster_msg_check_safe_keeps_original(client: TestClient, monkeypatch):
    """msg_sec_check 通过/跳过（测试环境未配置 → skipped）→ 原文返回。"""
    user = _new_user(f"comply_s_{uuid.uuid4().hex[:8]}", **BIRTH)
    created = _quick(client, user["token"])
    r = client.get(f"/meet/{created['meet_id']}/poster", headers=_auth(user["token"]))
    assert r.status_code == 200, r.text
    share = r.json()["share_text"]
    assert str(created["score"]) in share  # 未 mock：msg_sec_check skipped → fail-open 原样
