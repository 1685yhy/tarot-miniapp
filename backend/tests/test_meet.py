"""
星辰相遇（SDD P1 · T2-2）测试：/meet/quick + /meet/{id} + /meet/list + /meet/{id}/poster。

覆盖（对应 task-17-brief Step 1 验收）：
- quick 落库且返回字段完整（a/b 三要素 + score/level/factors/cards/tips/估算标注）
- 确定性：同输入两次 → 同 score / 同 cards / 同 tips（seed = 双方出生日期|今天）
- b 缺出生日期 → b.moon None + estimated=true（quick 模式只输星座）
- b 有出生日期/时间 → b.moon/b.rising 派生；b_birth_time 无日期 / 非法日期 → 400
- relation 非法 → 400；zodiac_b 非法 → 400；发起人无星座 → 400
- 记录归属校验：他人 GET 详情/海报 → 404；list 只含本人发起或参与
- pick_meet_cards 去重且确定性；MEET_TIPS ≥10 条且无禁词
- PII 最小化：落库只存派生星座 key，result_json 无出生日期/时间明文
- 合规：tips / 卡牌 tip / 海报 share_text 无 注定/天生一对 类禁词
"""

import asyncio
import json
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.meet import MEET_TIPS, pick_meet_cards
from app.db.database import async_session
from app.models.card import TarotCard
from app.models.star_meeting import StarMeeting
from app.models.user import User
from app.services.birthchart import ZODIAC_KEYS
from app.utils.auth import create_token

BANNED_WORDS = ("注定", "天生一对", "命中注定", "该在一起", "百分百", "绝对")

RELATIONS = ("friend", "love", "family", "work")

BIRTH = {"zodiac": "leo", "birth_date": "1996-08-10", "birth_time": "14:30", "birth_city": "北京"}
B_BIRTH_DATE = "1995-03-21"
B_BIRTH_TIME = "08:00"


# ── helpers ─────────────────────────────────────────────────────────────


def _new_user(openid: str, **fields) -> dict:
    """创建隔离测试用户（默认带完整出生信息），返回 {id, token}。"""

    async def _go() -> dict:
        async with async_session() as session:
            user = User(openid=openid, nickname="相遇测试", **fields)
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


def _fake_cards(n: int = 78) -> list[TarotCard]:
    """临时 TarotCard 对象（纯属性读取，不进库）。"""
    return [
        TarotCard(
            id=i, name_zh=f"牌{i}", name_en=f"Card{i}", card_number=i - 1,
            arcana="major" if i <= 22 else "minor", suit=None, element="",
            image_description="", keywords_upright="[]", keywords_reversed="[]",
            meaning_upright=f"含义{i}", meaning_reversed="", love_upright="",
            love_reversed="", career_upright="", career_reversed="",
            finance_upright="", finance_reversed="", health_upright="",
            health_reversed="",
        )
        for i in range(1, n + 1)
    ]


def _scan_banned(text: str) -> list[str]:
    return [w for w in BANNED_WORDS if w in text]


# ── quick：落库 + 字段完整 ──────────────────────────────────────────────


def test_quick_full_shape_and_persisted(client: TestClient):
    """quick 落库（status=completed）且返回字段完整。"""
    user = _new_user(f"meet_a_{uuid.uuid4().hex[:8]}", **BIRTH)
    data = _quick(client, user["token"])

    assert data["relation"] == "friend"
    assert data["meet_id"]
    assert data["a"]["zodiac"] == "leo" and data["a"]["name_zh"] == "狮子座"
    assert data["a"]["sun"]["zodiac"] == "leo"
    assert data["a"]["moon"] and data["a"]["moon"]["zodiac"] in ZODIAC_KEYS
    assert data["a"]["rising"] and data["a"]["rising"]["zodiac"] in ZODIAC_KEYS
    assert data["b"]["zodiac"] == "aries" and data["b"]["name_zh"] == "白羊座"  # 1995-03-21 → 白羊（派生覆盖所选项）
    assert data["b"]["sun"]["zodiac"] == "aries"
    assert data["b"]["moon"] and data["b"]["moon"]["zodiac"] in ZODIAC_KEYS
    assert data["b"]["rising"] and data["b"]["rising"]["zodiac"] in ZODIAC_KEYS

    assert isinstance(data["score"], int) and 55 <= data["score"] <= 95
    assert data["level_name"]
    assert isinstance(data["factors"], list) and data["factors"]
    assert isinstance(data["cards"], list) and len(data["cards"]) == 3
    assert isinstance(data["tips"], list) and len(data["tips"]) >= 1
    assert isinstance(data["estimated"], bool)
    assert "estimate_note" in data

    # 落库检查：status=completed + result_json 可反序列化
    async def _load():
        async with async_session() as session:
            row = await session.get(StarMeeting, data["meet_id"])
            return row

    row = asyncio.run(_load())
    assert row is not None
    assert row.status == "completed"
    assert row.initiator_id == user["id"]
    assert row.relation == "friend"
    saved = json.loads(row.result_json)
    assert saved["score"] == data["score"]
    assert saved["level_name"] == data["level_name"]


def test_quick_cards_positions_and_snippet(client: TestClient):
    """三牌位固定：关系之牌 / 星光之牌 / 相处之牌；含牌意截取与 tip。"""
    user = _new_user(f"meet_b_{uuid.uuid4().hex[:8]}", **BIRTH)
    data = _quick(client, user["token"])
    positions = [c["position"] for c in data["cards"]]
    assert positions == ["关系之牌", "星光之牌", "相处之牌"]
    for card in data["cards"]:
        assert isinstance(card["card_id"], int)
        assert card["name_zh"]
        assert card["meaning_snippet"]  # meaning_upright 截取
        assert card["tip"]
    # 相处之牌 tip 走相处提示合规框架（与 tips 池同源）
    assert data["cards"][2]["tip"] in MEET_TIPS or data["cards"][2]["tip"] == data["tips"][0]


# ── quick：确定性 ───────────────────────────────────────────────────────


def test_quick_deterministic_same_input(client: TestClient):
    """确定性承诺：同用户同输入两次 → 同 score / 同 cards / 同 tips。"""
    user = _new_user(f"meet_c_{uuid.uuid4().hex[:8]}", **BIRTH)
    r1 = _quick(client, user["token"])
    r2 = _quick(client, user["token"])
    assert r1["score"] == r2["score"]
    assert r1["level_name"] == r2["level_name"]
    assert [c["card_id"] for c in r1["cards"]] == [c["card_id"] for c in r2["cards"]]
    assert r1["tips"] == r2["tips"]
    assert r1["factors"] == r2["factors"]
    assert r1["meet_id"] != r2["meet_id"]  # 两次落两条记录


# ── quick：缺要素 → 估算 ────────────────────────────────────────────────


def test_quick_zodiac_only_b_estimated(client: TestClient):
    """quick 模式只输星座：b 无出生日期 → b.moon/rising None + estimated=true。"""
    user = _new_user(f"meet_d_{uuid.uuid4().hex[:8]}", **BIRTH)
    data = _quick(client, user["token"], b_birth_date=None, b_birth_time=None)
    assert data["b"]["moon"] is None
    assert data["b"]["rising"] is None
    assert data["estimated"] is True
    assert data["estimate_note"]


def test_quick_initiator_zodiac_only_still_works(client: TestClient):
    """发起人只有星座（无出生信息）→ a.moon/rising None，仍可合盘。"""
    user = _new_user(f"meet_e_{uuid.uuid4().hex[:8]}", zodiac="scorpio")
    data = _quick(client, user["token"], b_birth_date=None, b_birth_time=None)
    assert data["a"]["zodiac"] == "scorpio"
    assert data["a"]["moon"] is None and data["a"]["rising"] is None
    assert data["estimated"] is True


# ── quick：入参校验 ─────────────────────────────────────────────────────


def test_quick_invalid_relation_400(client: TestClient):
    user = _new_user(f"meet_f_{uuid.uuid4().hex[:8]}", **BIRTH)
    r = client.post("/meet/quick", json=_payload(relation="enemy"), headers=_auth(user["token"]))
    assert r.status_code == 400


def test_quick_invalid_zodiac_b_400(client: TestClient):
    user = _new_user(f"meet_g_{uuid.uuid4().hex[:8]}", **BIRTH)
    r = client.post("/meet/quick", json=_payload(zodiac_b="dragon"), headers=_auth(user["token"]))
    assert r.status_code == 400


def test_quick_invalid_b_birth_date_400(client: TestClient):
    user = _new_user(f"meet_h_{uuid.uuid4().hex[:8]}", **BIRTH)
    for bad in ("1995-13-40", "1995/03/21", "abc"):
        r = client.post(
            "/meet/quick", json=_payload(b_birth_date=bad), headers=_auth(user["token"])
        )
        assert r.status_code == 400, f"{bad} 应 400"


def test_quick_b_birth_time_without_date_400(client: TestClient):
    user = _new_user(f"meet_i_{uuid.uuid4().hex[:8]}", **BIRTH)
    r = client.post(
        "/meet/quick",
        json=_payload(b_birth_date=None, b_birth_time="08:00"),
        headers=_auth(user["token"]),
    )
    assert r.status_code == 400


def test_quick_invalid_b_birth_time_400(client: TestClient):
    user = _new_user(f"meet_j_{uuid.uuid4().hex[:8]}", **BIRTH)
    r = client.post(
        "/meet/quick", json=_payload(b_birth_time="99:99"), headers=_auth(user["token"])
    )
    assert r.status_code == 400


def test_quick_initiator_no_zodiac_400(client: TestClient):
    user = _new_user(f"meet_k_{uuid.uuid4().hex[:8]}")  # 无星座无出生日期
    r = client.post("/meet/quick", json=_payload(), headers=_auth(user["token"]))
    assert r.status_code == 400


def test_quick_requires_auth(client: TestClient):
    r = client.post("/meet/quick", json=_payload())
    assert r.status_code == 401


# ── PII 最小化 ──────────────────────────────────────────────────────────


def test_quick_pii_minimized_in_db(client: TestClient):
    """落库只存派生星座 key：无出生日期/时间明文，result_json 亦不含。"""
    user = _new_user(f"meet_l_{uuid.uuid4().hex[:8]}", **BIRTH)
    data = _quick(client, user["token"])

    async def _load():
        async with async_session() as session:
            row = await session.get(StarMeeting, data["meet_id"])
            return row.a_zodiac, row.a_moon, row.a_rising, row.b_zodiac, row.b_moon, row.b_rising, row.result_json

    a_z, a_m, a_r, b_z, b_m, b_r, result_json = asyncio.run(_load())
    for key in (a_z, a_m, a_r, b_z, b_m, b_r):
        assert key is None or key in ZODIAC_KEYS
    assert a_z == "leo" and b_z == "aries"  # b 派生太阳（1995-03-21 → 白羊）
    for secret in ("1996-08-10", "1995-03-21", "14:30", "08:00"):
        assert secret not in result_json, f"result_json 泄露出生信息: {secret}"


# ── GET /meet/{id}：归属校验 + 完整结果 ─────────────────────────────────


def test_get_meet_full_result_same_shape(client: TestClient):
    """发起人 GET 详情 → 与 quick 返回同构的完整结果。"""
    user = _new_user(f"meet_m_{uuid.uuid4().hex[:8]}", **BIRTH)
    created = _quick(client, user["token"])
    r = client.get(f"/meet/{created['meet_id']}", headers=_auth(user["token"]))
    assert r.status_code == 200
    data = r.json()
    assert data["meet_id"] == created["meet_id"]
    assert data["score"] == created["score"]
    assert data["a"] == created["a"] and data["b"] == created["b"]
    assert [c["card_id"] for c in data["cards"]] == [c["card_id"] for c in created["cards"]]
    assert data["tips"] == created["tips"]
    assert data["estimated"] == created["estimated"]


def test_get_meet_other_user_404(client: TestClient):
    """归属校验：他人不能读我的相遇结果（404 不泄露存在性）。"""
    owner = _new_user(f"meet_n_{uuid.uuid4().hex[:8]}", **BIRTH)
    other = _new_user(f"meet_o_{uuid.uuid4().hex[:8]}", **BIRTH)
    created = _quick(client, owner["token"])
    r = client.get(f"/meet/{created['meet_id']}", headers=_auth(other["token"]))
    assert r.status_code == 404
    r2 = client.get(f"/meet/{created['meet_id']}", headers=_auth(owner["token"]))
    assert r2.status_code == 200


def test_get_meet_not_found_404(client: TestClient):
    user = _new_user(f"meet_p_{uuid.uuid4().hex[:8]}", **BIRTH)
    r = client.get(f"/meet/{uuid.uuid4()}", headers=_auth(user["token"]))
    assert r.status_code == 404


def test_get_meet_requires_auth(client: TestClient):
    r = client.get(f"/meet/{uuid.uuid4()}")
    assert r.status_code == 401


# ── GET /meet/list：只含本人发起或参与 ──────────────────────────────────


def test_list_only_initiated_or_participated(client: TestClient):
    """list 只含本人发起（quick）或参与（friend_user_id）的记录。"""
    a = _new_user(f"meet_q_{uuid.uuid4().hex[:8]}", **BIRTH)
    b = _new_user(f"meet_r_{uuid.uuid4().hex[:8]}", **BIRTH)
    c = _new_user(f"meet_s_{uuid.uuid4().hex[:8]}", **BIRTH)

    m1 = _quick(client, a["token"])
    m2 = _quick(client, a["token"], zodiac_b="pisces", b_birth_date=None, b_birth_time=None)
    # 参与路径：C 发起、A 为 friend_user_id（T2-3 /meet/join 回填前的手工等价）
    async def _seed_participation():
        async with async_session() as session:
            session.add(
                StarMeeting(
                    initiator_id=c["id"], friend_user_id=a["id"], relation="love",
                    a_zodiac="gemini", b_zodiac="leo",
                    status="completed", result_json='{"score": 88, "level_name": "星光共鸣"}',
                )
            )
            await session.commit()
    asyncio.run(_seed_participation())

    r_a = client.get("/meet/list", headers=_auth(a["token"]))
    assert r_a.status_code == 200
    meetings_a = r_a.json()["meetings"]
    assert len(meetings_a) == 3  # 发起 2 + 参与 1
    ids_a = {m["meet_id"] for m in meetings_a}
    assert {m1["meet_id"], m2["meet_id"]} <= ids_a
    assert len(meetings_a) == len(ids_a)  # 无重复
    item = next(m for m in meetings_a if m["meet_id"] == m1["meet_id"])
    assert item["relation"] == "friend"
    assert item["b_name"] == "白羊座"  # m1 带出生日期 → 派生太阳（1995-03-21）
    assert isinstance(item["score"], int) and item["level_name"]
    assert item["created_at"]

    r_b = client.get("/meet/list", headers=_auth(b["token"]))
    assert r_b.json()["meetings"] == []  # 与 A 的记录完全隔离

    r_c = client.get("/meet/list", headers=_auth(c["token"]))
    assert len(r_c.json()["meetings"]) == 1


def test_list_requires_auth(client: TestClient):
    r = client.get("/meet/list")
    assert r.status_code == 401


# ── pick_meet_cards：去重 + 确定性 ──────────────────────────────────────


def test_pick_meet_cards_distinct_and_deterministic():
    """3 张去重且同 seed 恒定。"""
    cards = _fake_cards(78)
    picked = pick_meet_cards(cards, "1996-08-10|1995-03-21|2026-08-11")
    assert len(picked) == 3
    assert len({c.id for c in picked}) == 3  # 去重
    again = pick_meet_cards(cards, "1996-08-10|1995-03-21|2026-08-11")
    assert [c.id for c in again] == [c.id for c in picked]  # 确定性


def test_pick_meet_cards_small_deck():
    """牌数不足 3 → 全量返回（不崩溃）。"""
    cards = _fake_cards(2)
    assert len(pick_meet_cards(cards, "s")) == 2
    assert pick_meet_cards([], "s") == []


# ── 相处提示池：≥10 条 + 合规 ───────────────────────────────────────────


def test_meet_tips_pool_10_plus_and_compliant():
    """MEET_TIPS ≥10 条、非空、开放积极向、无禁词。"""
    assert len(MEET_TIPS) >= 10
    for tip in MEET_TIPS:
        assert tip and tip.strip()
        banned = _scan_banned(tip)
        assert not banned, f"相处提示含禁词 {banned}: {tip}"


def test_quick_outputs_compliant(client: TestClient):
    """响应 tips / 卡牌 tip 无禁词。"""
    user = _new_user(f"meet_t_{uuid.uuid4().hex[:8]}", **BIRTH)
    data = _quick(client, user["token"], b_birth_date=None, b_birth_time=None)
    texts = list(data["tips"]) + [c["tip"] for c in data["cards"]]
    for text in texts:
        banned = _scan_banned(text)
        assert not banned, f"输出含禁词 {banned}: {text}"


# ── GET /meet/{id}/poster：脱敏 ─────────────────────────────────────────


def test_poster_no_sensitive_fields(client: TestClient):
    """海报只含脱敏字段：昵称/星座/score/level/牌面摘要/分享文案，无日记类原文。"""
    user = _new_user(f"meet_u_{uuid.uuid4().hex[:8]}", **BIRTH)
    created = _quick(client, user["token"], b_birth_date=None, b_birth_time=None)
    r = client.get(f"/meet/{created['meet_id']}/poster", headers=_auth(user["token"]))
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == {"meet_id", "relation", "a", "b", "score", "level_name", "cards", "share_text"}
    assert data["a"]["nickname"] == "相遇测试"
    assert data["a"]["zodiac"] == "leo" and data["a"]["name_zh"] == "狮子座"
    assert data["b"]["zodiac"] == "taurus" and data["b"]["name_zh"] == "金牛座"  # 只输星座 → 直接使用所选项
    assert set(data["cards"][0].keys()) == {"position", "name_zh"}  # 牌面摘要，无牌意原文
    assert str(data["score"]) in data["share_text"]
    raw = json.dumps(data, ensure_ascii=False)
    for secret in ("1996-08-10", "1995-03-21", "14:30", "08:00", "含义"):
        assert secret not in raw, f"海报泄露敏感内容: {secret}"
    banned = _scan_banned(data["share_text"])
    assert not banned


def test_poster_other_user_404(client: TestClient):
    owner = _new_user(f"meet_v_{uuid.uuid4().hex[:8]}", **BIRTH)
    other = _new_user(f"meet_w_{uuid.uuid4().hex[:8]}", **BIRTH)
    created = _quick(client, owner["token"])
    r = client.get(f"/meet/{created['meet_id']}/poster", headers=_auth(other["token"]))
    assert r.status_code == 404


# ── 防御性读取：部分 JSON / 空结果 / 缺 score / 脏 key（T2-2 审查修复钉住）──


def test_get_meet_partial_result_json_no_500(client: TestClient):
    """部分 JSON 行（T2-3 邀请行形态）GET 详情 → 200，缺字段为空而非 KeyError 500。"""
    user = _new_user(f"meet_x_{uuid.uuid4().hex[:8]}", **BIRTH)
    created = _quick(client, user["token"])
    partial = {"score": 66, "level_name": "星光共鸣"}  # 缺 factors/cards/tips/estimated/estimate_note

    async def _patch():
        async with async_session() as session:
            row = await session.get(StarMeeting, created["meet_id"])
            row.result_json = json.dumps(partial, ensure_ascii=False)
            await session.commit()
    asyncio.run(_patch())

    r = client.get(f"/meet/{created['meet_id']}", headers=_auth(user["token"]))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["score"] == 66 and data["level_name"] == "星光共鸣"
    for key in ("factors", "cards", "tips", "estimated", "estimate_note"):
        assert data[key] is None, f"{key} 应为空: {data[key]}"


def test_get_meet_no_result_json_empty_fields(client: TestClient):
    """result_json 为空（未就绪邀请行）→ 200，结果字段为空（不 404 不 500）。"""
    user = _new_user(f"meet_y_{uuid.uuid4().hex[:8]}", **BIRTH)
    created = _quick(client, user["token"])

    async def _patch():
        async with async_session() as session:
            row = await session.get(StarMeeting, created["meet_id"])
            row.result_json = None
            await session.commit()
    asyncio.run(_patch())

    r = client.get(f"/meet/{created['meet_id']}", headers=_auth(user["token"]))
    assert r.status_code == 200, r.text
    data = r.json()
    for key in ("score", "level_name", "factors", "cards", "tips", "estimated", "estimate_note"):
        assert data[key] is None, f"{key} 应为空: {data[key]}"


def test_poster_missing_score_omitted(client: TestClient):
    """海报缺 score → 字段省略（None→exclude_none），不用 0 伪装；share_text 无 None。"""
    user = _new_user(f"meet_z_{uuid.uuid4().hex[:8]}", **BIRTH)
    created = _quick(client, user["token"], b_birth_date=None, b_birth_time=None)

    async def _patch():
        async with async_session() as session:
            row = await session.get(StarMeeting, created["meet_id"])
            row.result_json = '{"level_name": "星光共鸣"}'  # 缺 score
            await session.commit()
    asyncio.run(_patch())

    r = client.get(f"/meet/{created['meet_id']}/poster", headers=_auth(user["token"]))
    assert r.status_code == 200, r.text
    data = r.json()
    assert "score" not in data  # 缺 score → 省略而非伪装 0
    assert data["level_name"] == "星光共鸣"  # 有 level_name → 正常返回
    assert "None" not in data["share_text"] and data["share_text"]

    # 两者都缺 → 全部省略
    async def _patch_empty():
        async with async_session() as session:
            row = await session.get(StarMeeting, created["meet_id"])
            row.result_json = "{}"
            await session.commit()
    asyncio.run(_patch_empty())

    r2 = client.get(f"/meet/{created['meet_id']}/poster", headers=_auth(user["token"]))
    assert r2.status_code == 200, r2.text
    data2 = r2.json()
    assert "score" not in data2 and "level_name" not in data2
    assert data2["share_text"] and "None" not in data2["share_text"]


def test_get_meet_dirty_zodiac_no_500(client: TestClient):
    """脏星座 key（非 12 key 的落库行）→ 详情/海报 200，name_zh 兜底为 key（不 KeyError 500）。"""
    user = _new_user(f"meet_w2_{uuid.uuid4().hex[:8]}", **BIRTH)
    meet_id = str(uuid.uuid4())

    async def _seed():
        async with async_session() as session:
            session.add(
                StarMeeting(
                    id=meet_id, initiator_id=user["id"], relation="friend",
                    a_zodiac="dirty-key", a_moon="also-bad", b_zodiac="taurus",
                    status="completed", result_json='{"score": 77, "level_name": "星光共鸣"}',
                )
            )
            await session.commit()
    asyncio.run(_seed())

    r = client.get(f"/meet/{meet_id}", headers=_auth(user["token"]))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["a"]["zodiac"] == "dirty-key"
    assert data["a"]["name_zh"] == "dirty-key"  # ZODIAC_NAMES_ZH.get() 兜底
    assert data["a"]["sun"]["name_zh"] == "dirty-key"
    assert data["a"]["moon"]["name_zh"] == "also-bad"

    r2 = client.get(f"/meet/{meet_id}/poster", headers=_auth(user["token"]))
    assert r2.status_code == 200, r2.text


# ═════════════════════════════════════════════════════════════════════════════
# T2-3 邀请版（task-18-brief）：POST /meet/invite + GET /meet/public/{id}
# + POST /meet/join（回填 friend_user_id + 双向奖励）
# ═════════════════════════════════════════════════════════════════════════════

_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"fake-meet-wxacode-png"


def _meet_row(meet_id: str) -> StarMeeting:
    """直查 star_meetings 行（测试断言落库状态）。"""

    async def _go():
        async with async_session() as session:
            return await session.get(StarMeeting, meet_id)

    return asyncio.run(_go())


def _user_row(user_id: str) -> User:
    """直查 users 行（断言奖励字段）。"""

    async def _go():
        async with async_session() as session:
            return await session.get(User, user_id)

    return asyncio.run(_go())


def _mock_wxacode(monkeypatch, calls: list) -> None:
    """把 app.api.meet.get_wxacode 替换为 fake，calls 收集调用 kwargs。"""
    import app.api.meet as meet_api

    async def fake_get_wxacode(**kwargs):
        calls.append(kwargs)
        return _FAKE_PNG

    monkeypatch.setattr(meet_api, "get_wxacode", fake_get_wxacode)


def _join(client: TestClient, token: str, meet_id: str, **overrides):
    """POST /meet/join 默认体（好友星座+出生信息），可覆盖。"""
    base = {
        "meet_id": meet_id,
        "zodiac_b": "capricorn",
        "b_birth_date": "1997-09-12",  # → 处女座（派生覆盖所填）
        "b_birth_time": "10:00",
    }
    base.update(overrides)
    return client.post("/meet/join", json=base, headers=_auth(token))


def _new_code() -> str:
    return f"STAR-{uuid.uuid4().hex[:4].upper()}"


def _invite(client: TestClient, token: str, meet_id: str):
    return client.post("/meet/invite", json={"meet_id": meet_id}, headers=_auth(token))


# ── POST /meet/invite ──────────────────────────────────────────────────────


def test_invite_returns_png_and_sets_pending(client: TestClient, monkeypatch):
    """invite → image/png（scene=m:{meet_id}，meet-landing 页）+ meet 翻转为 pending。"""
    calls: list = []
    _mock_wxacode(monkeypatch, calls)
    user = _new_user(f"inv_a_{uuid.uuid4().hex[:8]}", **BIRTH)
    created = _quick(client, user["token"])

    r = _invite(client, user["token"], created["meet_id"])
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("image/png")
    assert r.content == _FAKE_PNG
    assert len(calls) == 1
    kwargs = calls[0]
    assert kwargs["scene"] == f"m:{created['meet_id']}"
    assert kwargs["page"] == "pages/meet-landing/meet-landing"
    assert kwargs["width"] == 430
    assert kwargs["env_version"] == "trial"  # 体验版构建即可扫码打开

    row = _meet_row(created["meet_id"])
    assert row.status == "pending"  # 邀请中：等待好友加入


def test_invite_repeat_hits_cache(client: TestClient, monkeypatch):
    """重复邀请命中 7 天缓存（按 meet_id）：get_wxacode 只调 1 次。"""
    calls: list = []
    _mock_wxacode(monkeypatch, calls)
    user = _new_user(f"inv_b_{uuid.uuid4().hex[:8]}", **BIRTH)
    created = _quick(client, user["token"])

    r1 = _invite(client, user["token"], created["meet_id"])
    r2 = _invite(client, user["token"], created["meet_id"])
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.content == r2.content == _FAKE_PNG
    assert len(calls) == 1  # 缓存命中——微信接口只调一次


def test_invite_requires_auth(client: TestClient):
    r = client.post("/meet/invite", json={"meet_id": str(uuid.uuid4())})
    assert r.status_code == 401


def test_invite_not_found_404(client: TestClient):
    user = _new_user(f"inv_c_{uuid.uuid4().hex[:8]}", **BIRTH)
    r = _invite(client, user["token"], str(uuid.uuid4()))
    assert r.status_code == 404


def test_invite_non_initiator_404(client: TestClient):
    """非发起人调用 invite → 404（不泄露记录存在性）。"""
    owner = _new_user(f"inv_d_{uuid.uuid4().hex[:8]}", **BIRTH)
    other = _new_user(f"inv_e_{uuid.uuid4().hex[:8]}", **BIRTH)
    created = _quick(client, owner["token"])
    r = _invite(client, other["token"], created["meet_id"])
    assert r.status_code == 404


def test_invite_after_friend_joined_400(client: TestClient, monkeypatch):
    """好友已加入（friend_user_id 已回填）→ 再次邀请 400。"""
    _mock_wxacode(monkeypatch, [])
    initiator = _new_user(f"inv_f_{uuid.uuid4().hex[:8]}", **BIRTH, invite_code=_new_code())
    friend = _new_user(f"inv_g_{uuid.uuid4().hex[:8]}", zodiac="capricorn")
    created = _quick(client, initiator["token"])
    assert _invite(client, initiator["token"], created["meet_id"]).status_code == 200
    rj = _join(client, friend["token"], created["meet_id"])
    assert rj.status_code == 200, rj.text

    r = _invite(client, initiator["token"], created["meet_id"])
    assert r.status_code == 400


# ── GET /meet/public/{meet_id}：脱敏 + 限流 ────────────────────────────────


def test_public_meet_sanitized_no_auth(client: TestClient, monkeypatch):
    """公开接口无需登录，只出 5 个脱敏字段，无 openid/invite_code/birth 相关键。"""
    _mock_wxacode(monkeypatch, [])
    initiator = _new_user(f"pub_a_{uuid.uuid4().hex[:8]}", **BIRTH, invite_code=_new_code())
    created = _quick(client, initiator["token"])
    assert _invite(client, initiator["token"], created["meet_id"]).status_code == 200

    r = client.get(f"/meet/public/{created['meet_id']}")  # 无 Authorization
    assert r.status_code == 200, r.text
    data = r.json()
    assert set(data.keys()) == {"meet_id", "nickname", "zodiac_cn", "star_tier_name", "status"}
    assert data["meet_id"] == created["meet_id"]
    assert data["nickname"] == "相遇测试"
    assert data["zodiac_cn"] == "狮子座"  # 中文名，不出星座 key
    assert data["star_tier_name"] == "微光"  # 无星尘 → 0 阶
    assert data["status"] == "pending"

    raw = json.dumps(data, ensure_ascii=False)
    for secret in ("openid", "invite_code", "STAR-", "birth", "14:30", "1996"):
        assert secret not in raw, f"公开接口泄露敏感内容: {secret}"


def test_public_meet_not_found_404(client: TestClient):
    r = client.get(f"/meet/public/{uuid.uuid4()}")
    assert r.status_code == 404


def test_public_meet_rate_limited_429(client: TestClient):
    """公开接口超限 → 429（30 次/分/IP，meet_info_rate_limit）。"""
    meet_id = str(uuid.uuid4())  # 限流在 handler 前生效，无需真实记录
    last = None
    for _ in range(40):
        last = client.get(f"/meet/public/{meet_id}")
    assert last.status_code == 429


# ── POST /meet/join：回填 + 奖励 + 幂等 ───────────────────────────────────


def test_join_backfills_rewards_and_both_visible(client: TestClient, monkeypatch):
    """好友加入 → b 三要素回填 + friend_user_id + completed；双方可见；双方各 +1。"""
    _mock_wxacode(monkeypatch, [])
    initiator = _new_user(f"join_a_{uuid.uuid4().hex[:8]}", **BIRTH, invite_code=_new_code())
    friend = _new_user(f"join_b_{uuid.uuid4().hex[:8]}", zodiac="capricorn")
    created = _quick(client, initiator["token"], zodiac_b="taurus")
    assert _invite(client, initiator["token"], created["meet_id"]).status_code == 200

    r = _join(client, friend["token"], created["meet_id"])
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["meet_id"] == created["meet_id"]
    assert data["a"]["zodiac"] == "leo"  # a 侧复用落库三要素
    assert data["b"]["zodiac"] == "virgo"  # 1997-09-12 → 处女座（派生覆盖所填 capricorn）
    assert data["b"]["sun"]["zodiac"] == "virgo"
    assert data["b"]["moon"] and data["b"]["rising"]
    assert isinstance(data["score"], int) and 55 <= data["score"] <= 95
    assert data["reward_granted"] is True

    # 落库回填
    row = _meet_row(created["meet_id"])
    assert row.status == "completed"
    assert row.friend_user_id == friend["id"]
    assert row.b_zodiac == "virgo" and row.b_moon and row.b_rising
    saved = json.loads(row.result_json)
    assert saved["score"] == data["score"]

    # 双方都能 GET /meet/{id}
    r1 = client.get(f"/meet/{created['meet_id']}", headers=_auth(initiator["token"]))
    r2 = client.get(f"/meet/{created['meet_id']}", headers=_auth(friend["token"]))
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["score"] == data["score"]

    # 双向奖励：双方各 +1 免费解读
    assert _user_row(initiator["id"]).free_deep_readings == 1
    assert _user_row(friend["id"]).free_deep_readings == 1


def test_join_repeat_and_third_party_idempotent(client: TestClient, monkeypatch):
    """重复 join/同人二次/第三人 → 400，奖励不重复（幂等）。"""
    _mock_wxacode(monkeypatch, [])
    initiator = _new_user(f"join_c_{uuid.uuid4().hex[:8]}", **BIRTH, invite_code=_new_code())
    friend = _new_user(f"join_d_{uuid.uuid4().hex[:8]}", zodiac="capricorn")
    third = _new_user(f"join_e_{uuid.uuid4().hex[:8]}", zodiac="pisces")
    created = _quick(client, initiator["token"])
    assert _invite(client, initiator["token"], created["meet_id"]).status_code == 200

    r1 = _join(client, friend["token"], created["meet_id"])
    assert r1.status_code == 200 and r1.json()["reward_granted"] is True

    r2 = _join(client, friend["token"], created["meet_id"])  # 同人二次
    assert r2.status_code == 400
    r3 = _join(client, third["token"], created["meet_id"])  # 第三人
    assert r3.status_code == 400

    assert _user_row(initiator["id"]).free_deep_readings == 1
    assert _user_row(friend["id"]).free_deep_readings == 1
    assert _user_row(third["id"]).free_deep_readings == 0


def test_join_requires_auth(client: TestClient):
    r = client.post("/meet/join", json={"meet_id": str(uuid.uuid4()), "zodiac_b": "capricorn"})
    assert r.status_code == 401


def test_join_not_found_404(client: TestClient):
    user = _new_user(f"join_f_{uuid.uuid4().hex[:8]}", zodiac="capricorn")
    r = _join(client, user["token"], str(uuid.uuid4()))
    assert r.status_code == 404


def test_join_own_meet_400(client: TestClient, monkeypatch):
    """发起人不能加入自己的相遇（同人防刷）。"""
    _mock_wxacode(monkeypatch, [])
    user = _new_user(f"join_g_{uuid.uuid4().hex[:8]}", **BIRTH)
    created = _quick(client, user["token"])
    assert _invite(client, user["token"], created["meet_id"]).status_code == 200
    r = _join(client, user["token"], created["meet_id"])
    assert r.status_code == 400


def test_join_not_invited_completed_meet_400(client: TestClient):
    """从未邀请（status=completed）的相遇不可 join。"""
    user = _new_user(f"join_h_{uuid.uuid4().hex[:8]}", **BIRTH)
    friend = _new_user(f"join_i_{uuid.uuid4().hex[:8]}", zodiac="capricorn")
    created = _quick(client, user["token"])
    r = _join(client, friend["token"], created["meet_id"])
    assert r.status_code == 400


def test_join_invalid_params_400(client: TestClient, monkeypatch):
    """join 入参校验与 quick 同口径：非法星座/日期/时间无日期 → 400。"""
    _mock_wxacode(monkeypatch, [])
    initiator = _new_user(f"join_j_{uuid.uuid4().hex[:8]}", **BIRTH)
    friend = _new_user(f"join_k_{uuid.uuid4().hex[:8]}", zodiac="capricorn")
    created = _quick(client, initiator["token"])
    assert _invite(client, initiator["token"], created["meet_id"]).status_code == 200

    r = _join(client, friend["token"], created["meet_id"], zodiac_b="dragon")
    assert r.status_code == 400
    r = _join(client, friend["token"], created["meet_id"], b_birth_date="1997-13-40")
    assert r.status_code == 400
    r = _join(client, friend["token"], created["meet_id"], b_birth_date=None, b_birth_time="10:00")
    assert r.status_code == 400


def test_join_no_invite_code_no_reward(client: TestClient, monkeypatch):
    """发起人无 invite_code → join 正常完成但不触发奖励（reward_granted=False）。"""
    _mock_wxacode(monkeypatch, [])
    initiator = _new_user(f"join_l_{uuid.uuid4().hex[:8]}", **BIRTH)  # 无邀请码
    friend = _new_user(f"join_m_{uuid.uuid4().hex[:8]}", zodiac="capricorn")
    created = _quick(client, initiator["token"])
    assert _invite(client, initiator["token"], created["meet_id"]).status_code == 200

    r = _join(client, friend["token"], created["meet_id"])
    assert r.status_code == 200, r.text
    assert r.json()["reward_granted"] is False
    assert _user_row(initiator["id"]).free_deep_readings == 0
    assert _user_row(friend["id"]).free_deep_readings == 0


def test_join_friend_already_used_invite_no_duplicate_reward(client: TestClient, monkeypatch):
    """好友先前已用邀请码（invites 表有记录）→ join 完成但奖励不重复。"""
    _mock_wxacode(monkeypatch, [])
    inviter_code = _new_code()
    inviter = _new_user(f"join_n_{uuid.uuid4().hex[:8]}", **BIRTH, invite_code=inviter_code)
    initiator = _new_user(f"join_o_{uuid.uuid4().hex[:8]}", **BIRTH, invite_code=_new_code())
    friend = _new_user(f"join_p_{uuid.uuid4().hex[:8]}", zodiac="capricorn")

    # 好友先前已通过 /share/invite 接受过邀请码
    ra = client.post("/share/invite", json={"invite_code": inviter_code}, headers=_auth(friend["token"]))
    assert ra.status_code == 200

    created = _quick(client, initiator["token"])
    assert _invite(client, initiator["token"], created["meet_id"]).status_code == 200
    r = _join(client, friend["token"], created["meet_id"])
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["reward_granted"] is False  # process_invite 幂等：不接受过邀请的 invitee
    assert data["reward_note"]  # 提示原因
    assert _user_row(friend["id"]).free_deep_readings == 1  # 只有 /share/invite 那次 +1
    assert _user_row(initiator["id"]).free_deep_readings == 0


def test_join_outputs_compliant(client: TestClient, monkeypatch):
    """join 响应 tips / 卡牌 tip 无禁词；只输星座 → estimated=True。"""
    _mock_wxacode(monkeypatch, [])
    initiator = _new_user(f"join_q_{uuid.uuid4().hex[:8]}", **BIRTH, invite_code=_new_code())
    friend = _new_user(f"join_r_{uuid.uuid4().hex[:8]}", zodiac="capricorn")
    created = _quick(client, initiator["token"])
    assert _invite(client, initiator["token"], created["meet_id"]).status_code == 200

    r = _join(client, friend["token"], created["meet_id"], b_birth_date=None, b_birth_time=None)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["b"]["moon"] is None and data["b"]["rising"] is None
    assert data["estimated"] is True
    texts = list(data["tips"]) + [c["tip"] for c in data["cards"]]
    for text in texts:
        banned = _scan_banned(text)
        assert not banned, f"输出含禁词 {banned}: {text}"
