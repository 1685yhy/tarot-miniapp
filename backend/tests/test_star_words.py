"""
睡前星语（SDD P1 · T4-2）测试。

覆盖：
- 短句库合规：总条数 ≥50、每池 ≥12、每条 ≤20 字、黑名单词扫描
  （必 / 绝对 / 改运 / 化解 / 转运 / 注定 / 命 / 预测 / 明天一定会，
  与用户决策对齐的字符级口径）
- 确定性选择器：同 date+user 同句；不同 date 抽样非全同；结果必属对应池
- AI 成功 → source=ai、短语来自 AI 输出（黑名单清洗后）
- AI 输出超长 → 截断到 20 字；AI 输出含黑名单词 → 清洗后无禁词
- AI 抛异常 → 重试上限（3 次）后降级 fallback、短语来自短句库
- 同日缓存：第二次调用命中缓存、AI 只调 1 次；缓存行 data/source 落库
- 并发首请求竞态：insert 撞 UNIQUE 约束 → 回滚回读已落库缓存返回（不 500）
- /moon-card/today：未登录 401；字段完整；phase 与 moon_phase_on 一致；
  date 为北京时间当日；测试环境无 AI key → source=fallback
"""

import asyncio
import json
from datetime import date
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.database import async_session
from app.models.star_word_daily import StarWordDaily
from app.models.user import User
from app.services.moon import moon_phase_on
from app.utils.auth import create_token

# 与用户决策禁词表对齐（2026-08-11 确认）：必/绝对/改运/化解/转运/注定/命
# + 现有 预测/明天一定会；字符级口径（含"不必""必定"等含"必"形态）
# T2-6 统一：禁词表收敛到共享 compliance.AI_OUTPUT_BLACKLIST（避免每处一份拷贝）
from app.services.compliance import AI_OUTPUT_BLACKLIST as BLACKLIST_WORDS

EXPECTED_DIMS = {"love", "career", "social", "health"}

# ── helpers ─────────────────────────────────────────────────────────────


def _new_user(openid: str, zodiac: str | None = None) -> tuple[str, dict[str, str]]:
    """创建隔离测试用户，返回 (user_id, auth_headers)。"""

    async def _go() -> tuple[str, str]:
        async with async_session() as session:
            user = User(openid=openid, nickname="星语测试", zodiac=zodiac)
            session.add(user)
            await session.flush()
            token = create_token(user.id, user.token_version)
            await session.commit()
            return user.id, token

    uid, token = asyncio.run(_go())
    return uid, {"Authorization": f"Bearer {token}"}


def _get_today(uid: str, today: date) -> dict:
    """调用 get_today_star_word（新会话，服务内 commit）。"""

    async def _go() -> dict:
        async with async_session() as session:
            user = await session.get(User, uid)
            from app.services import star_words
            return await star_words.get_today_star_word(session, user, today)

    return asyncio.run(_go())


def _cache_row(uid: str, today: date) -> StarWordDaily | None:
    async def _go() -> StarWordDaily | None:
        async with async_session() as session:
            row = (
                await session.execute(
                    select(StarWordDaily).where(
                        StarWordDaily.user_id == uid,
                        StarWordDaily.word_date == today,
                    )
                )
            ).scalar_one_or_none()
            return row

    return asyncio.run(_go())


class _FakeCompletions:
    def __init__(self, content: str | None = None, raise_error: bool = False):
        self._content = content
        self._raise_error = raise_error
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._raise_error:
            raise RuntimeError("DeepSeek 服务不可用")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))]
        )


class _FakeChat:
    def __init__(self, completions: _FakeCompletions):
        self.completions = completions


class _FakeAIClient:
    def __init__(self, completions: _FakeCompletions):
        self.chat = _FakeChat(completions)


def _fake_ai(content: str | None = None, raise_error: bool = False) -> _FakeAIClient:
    return _FakeAIClient(_FakeCompletions(content, raise_error))


# ══════════════════════════════════════════════════════════════════
# 短句库合规（池规模 / 字数 / 黑名单）
# ══════════════════════════════════════════════════════════════════


def test_pool_total_and_per_pool_size():
    from app.services.star_words import STAR_WORD_POOLS

    assert set(STAR_WORD_POOLS) == EXPECTED_DIMS
    total = 0
    for dim in EXPECTED_DIMS:
        assert len(STAR_WORD_POOLS[dim]) >= 12, f"{dim} 池少于 12 条"
        total += len(STAR_WORD_POOLS[dim])
    assert total >= 50, f"短句库总条数 {total} < 50"


def test_pool_phrases_within_20_chars():
    from app.services.star_words import STAR_WORD_POOLS

    for dim, phrases in STAR_WORD_POOLS.items():
        for phrase in phrases:
            assert len(phrase) <= 20, f"{dim} 池短语超 20 字: {phrase}"
            assert phrase.strip(), f"{dim} 池存在空短语"


def test_pool_no_blacklist_words():
    from app.services.star_words import STAR_WORD_POOLS

    for dim, phrases in STAR_WORD_POOLS.items():
        for phrase in phrases:
            for word in BLACKLIST_WORDS:
                assert word not in phrase, f"{dim} 池短语含禁词「{word}」: {phrase}"


# ══════════════════════════════════════════════════════════════════
# 确定性选择器
# ══════════════════════════════════════════════════════════════════


def test_select_fallback_phrase_deterministic_and_from_pool():
    from app.services.star_words import select_fallback_phrase

    from app.services.star_words import STAR_WORD_POOLS

    for dim in EXPECTED_DIMS:
        a = select_fallback_phrase(date_seed=19, user_seed=1234, top_dim=dim)
        b = select_fallback_phrase(date_seed=19, user_seed=1234, top_dim=dim)
        assert a == b, f"{dim} 同 date+user 应同句"
        assert a in STAR_WORD_POOLS[dim], f"{dim} 选择器结果应来自对应池"


def test_select_fallback_phrase_varies_across_dates():
    from app.services.star_words import select_fallback_phrase

    for dim in EXPECTED_DIMS:
        phrases = {
            select_fallback_phrase(date_seed=s, user_seed=42, top_dim=dim)
            for s in range(19, 29)  # 10 个不同日期种子
        }
        assert len(phrases) >= 2, f"{dim} 池不同日期应至少出现不同句"


# ══════════════════════════════════════════════════════════════════
# AI 生成 + 降级 + 同日缓存（service 层）
# ══════════════════════════════════════════════════════════════════


def test_ai_success_source_ai_and_cached(client: TestClient, monkeypatch):
    uid, headers = _new_user("starword_ai_ok")
    today = date(2026, 8, 11)
    phrase = "把今天的疲惫，交给月亮收好。"

    fake = _fake_ai(phrase)
    monkeypatch.setattr("app.services.star_words._get_ai_client", lambda: fake)
    monkeypatch.setattr(
        "app.services.star_words.beijing_today", lambda: today
    )

    result = _get_today(uid, today)
    assert result["source"] == "ai"
    assert result["phrase"] == phrase
    assert len(fake.chat.completions.calls) == 1

    # AI prompt 含当日星光/能量维度/心情 与 输出红线
    user_content = fake.chat.completions.calls[0]["messages"][1]["content"]
    system_content = fake.chat.completions.calls[0]["messages"][0]["content"]
    assert "星光色" in user_content
    assert "能量" in user_content
    assert "心情" in user_content
    assert "输出红线" in system_content

    # 缓存落库：data 存 phrase、source 列标记 ai
    row = _cache_row(uid, today)
    assert row is not None
    assert json.loads(row.data) == {"phrase": phrase}
    assert row.source == "ai"


def test_ai_exception_retry_cap_then_fallback(client: TestClient, monkeypatch):
    """AI 抛异常 → 重试上限（3 次）后落 fallback，短语来自短句库。"""
    uid, _ = _new_user("starword_ai_fail")
    today = date(2026, 8, 11)

    fake = _fake_ai(raise_error=True)
    monkeypatch.setattr("app.services.star_words._get_ai_client", lambda: fake)
    monkeypatch.setattr("app.services.star_words._AI_RETRY_BACKOFF_SECONDS", 0)

    result = _get_today(uid, today)
    assert result["source"] == "fallback"
    from app.services.star_words import STAR_WORD_POOLS
    all_phrases = {p for pool in STAR_WORD_POOLS.values() for p in pool}
    assert result["phrase"] in all_phrases, "降级短语必须来自短句库"
    assert len(fake.chat.completions.calls) == 3, "重试上限应为 3 次，之后不再尝试"

    # 降级结果同样落缓存，source=fallback
    row = _cache_row(uid, today)
    assert row is not None
    assert row.source == "fallback"


def test_second_call_hits_cache_ai_once(client: TestClient, monkeypatch):
    """同日第二次调用命中缓存：AI 只调 1 次、内容恒定。"""
    uid, _ = _new_user("starword_cache")
    today = date(2026, 8, 11)

    fake = _fake_ai("把今天的疲惫，交给月亮收好。")
    monkeypatch.setattr("app.services.star_words._get_ai_client", lambda: fake)

    r1 = _get_today(uid, today)
    r2 = _get_today(uid, today)
    assert r1 == r2
    assert r2["source"] == "ai"
    assert len(fake.chat.completions.calls) == 1, "缓存命中不得重复调用 AI"


def test_save_cache_concurrent_race_reads_back_existing(client: TestClient, monkeypatch):
    """并发首请求竞态（T1-7 Minor-2）：insert 撞 UNIQUE → 回滚回读已落库缓存返回。

    竞态模拟：先落一行缓存（赢家）；再模拟「输家」预检读到空（预检先于赢家
    写入执行）→ 输家走 insert → 撞 ``uq_user_word_date`` 唯一约束 IntegrityError
    → 回滚 → 回读赢家已落库内容返回（同日同人只留一份权威结果，不 500）。
    """
    from sqlalchemy.ext.asyncio import AsyncSession

    uid, _ = _new_user("starword_race")
    today = date(2026, 8, 11)
    winner = {"phrase": "把今天的疲惫，交给月亮收好。", "source": "ai"}

    # 赢家：正常写入一行缓存
    async def _seed() -> None:
        async with async_session() as session:
            from app.services import star_words
            await star_words._save_cache(
                session, uid, today, winner["phrase"], winner["source"]
            )

    asyncio.run(_seed())

    # 输家：首次 execute 返回空结果（模拟预检在赢家写入前执行），随后走真实执行
    real_execute = AsyncSession.execute
    state = {"faked": False}

    class _EmptyResult:
        def scalar_one_or_none(self):
            return None

    async def _execute(self, statement, *args, **kwargs):
        if not state["faked"]:
            state["faked"] = True
            return _EmptyResult()
        return await real_execute(self, statement, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "execute", _execute)

    async def _go() -> dict:
        async with async_session() as session:
            from app.services import star_words
            return await star_words._save_cache(
                session, uid, today, "输家的短语", "fallback"
            )

    result = asyncio.run(_go())
    assert result == winner, "并发输家必须回读赢家已落库内容返回"

    # 落库内容仍是赢家那份，未被输家覆盖
    row = _cache_row(uid, today)
    assert row is not None
    assert json.loads(row.data) == {"phrase": winner["phrase"]}
    assert row.source == winner["source"]


def test_ai_output_sanitized(client: TestClient, monkeypatch):
    """AI 输出含黑名单词 → 落库/返回前必须清洗（T1-2 _SANITIZE 模式）。"""
    uid, _ = _new_user("starword_dirty")
    today = date(2026, 8, 11)

    # 覆盖全部禁词形态：注定/走运/必定/转运/化解/明天一定会
    fake = _fake_ai("你注定会走运，必定转运化解烦恼，明天一定会心想事成。")
    monkeypatch.setattr("app.services.star_words._get_ai_client", lambda: fake)

    result = _get_today(uid, today)
    assert result["source"] == "ai"
    for word in BLACKLIST_WORDS:
        assert word not in result["phrase"], f"清洗后仍含禁词「{word}」: {result['phrase']}"
    # 缓存里也是清洗后的内容
    row = _cache_row(uid, today)
    cached_phrase = json.loads(row.data)["phrase"]
    for word in BLACKLIST_WORDS:
        assert word not in cached_phrase


def test_ai_output_truncated_to_20_chars(client: TestClient, monkeypatch):
    """AI 输出超 20 字 → 截断到 20 字。"""
    uid, _ = _new_user("starword_long")
    today = date(2026, 8, 11)

    fake = _fake_ai("今晚请记得好好睡觉，让月亮替你把所有的疲惫都收起来，明天再出发。")
    monkeypatch.setattr("app.services.star_words._get_ai_client", lambda: fake)

    result = _get_today(uid, today)
    assert result["source"] == "ai"
    assert len(result["phrase"]) <= 20


# ══════════════════════════════════════════════════════════════════
# /moon-card/today 端点
# ══════════════════════════════════════════════════════════════════


def test_moon_card_today_requires_auth(client: TestClient):
    assert client.get("/moon-card/today").status_code == 401


def test_moon_card_today_fields_and_phase(client: TestClient, monkeypatch):
    """字段完整 + phase 与 moon_phase_on 一致 + 同日确定性（缓存）。"""
    uid, headers = _new_user("starword_card", zodiac="leo")
    today = date(2026, 8, 11)
    monkeypatch.setattr("app.services.star_words.beijing_today", lambda: today)

    resp = client.get("/moon-card/today", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert set(data) == {"date", "phase", "phrase", "star_color", "star_number", "source"}
    assert data["date"] == today.isoformat()
    phase = moon_phase_on(today)
    assert data["phase"] == {"emoji": phase["emoji"], "label": phase["label"]}
    assert data["phrase"]
    assert data["star_color"].startswith("#")
    assert isinstance(data["star_number"], int)
    # 测试环境无 DEEPSEEK_API_KEY → 降级路径（短句库兜底）
    assert data["source"] == "fallback"

    # 同日同人恒定：第二次请求内容一致
    resp2 = client.get("/moon-card/today", headers=headers)
    assert resp2.json() == data
