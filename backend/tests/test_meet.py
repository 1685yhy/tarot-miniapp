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
    assert data["level_name"] == data["level_name"] and data["level_name"]
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
