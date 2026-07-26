# M2 可信任 — 用户留存 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) to implement this plan task-by-task.

**Goal:** 补完已实现 M2 功能的缺口 + 全面测试验证，确保用户感到被理解、愿意持续回来

**Architecture:** M2 大部分功能在前序 Phase 1-3（7/23）已实现。本计划聚焦：已实现功能的验证修复 + 3个真实缺口 + 全面自动化测试。

**Tech Stack:** WeChat MiniProgram native (WXML/WXSS/JS) + Python FastAPI + DeepSeek V4 Pro + Alembic + pytest

## 实地勘查：M2 功能完成度

| 功能 | 状态 | 证据 |
|------|------|------|
| 时段问候 | ✅ 已实现 | index.js `_computeGreeting()` 5时段 + 昵称 |
| AI历史上下文 | ✅ 已实现 | ai_engine.py `_build_user_context()` 累计次数/常用牌阵/连续天数/近3次摘要 |
| 卡牌深度解析 | ✅ 已实现 | 后端 `GET /{card_id}/teaching` + 前端 "深度解析" Tab |
| AI多角色 | ✅ 已实现 | ai_personas.py 3角色 + reading.wxml 角色选择器 |
| 签到+等级 | ✅ 已实现 | 后端 `POST /tasks/checkin` + `GET /tasks/status` + 前端checkin页 |
| 日记AI周回顾 | ✅ 已实现 | 后端 `GET /diary/review` + DeepSeek AI 生成 |
| 星座关联 | ❌ 缺口 | zodiacSign 存储但未注入 AI prompt |
| AI角色真连 | ⚠️ 待验证 | personaKey 在 reading.js 中选择，需确认 pipeline 全通 |
| 教学数据入库 | ⚠️ 待验证 | card_teaching_data.json 145KB 存在，需确认 DB 已填充 |
| 数据库迁移 | ⚠️ 待验证 | 2个迁移文件，需确认可执行+可回滚 |
| 自动化测试 | ❌ 缺口 | 5文件409行，无核心流程测试 |
| 每日习惯循环 | ⚠️ 部分 | checkin有streak，daily-card缺连续打卡激励 |

## 全局约束

- 定价：月19.9/年168/学生9.9/永久298
- 免费额度：3次解读/天 + 3次追问/天（后端 config.py 为唯一真相源）
- 设计系统：深靛蓝 #1a1a2e / 暖金 #C9A84C / 薰衣草紫 #9A95B8
- AI提示词中禁止使用"算命""预测命运"等迷信用语
- 所有修改需通过 IDE compile + 后端 pytest + 服务器部署验证
- 测试覆盖率目标：核心流程 ≥80%，API 端点 100%

---

### Task 1: 星座 → AI 提示词集成

**缺口**: 用户可在入门引导中选择星座并存入 `wx.getStorageSync('zodiac_sign')`，但后端 AI prompt 从未读到这个值。

**Files:**
- Modify: `miniapp/pages/reading/reading.js:530-535` — startReading 传参加 zodiac
- Modify: `backend/app/api/readings.py` — 接收 zodiac 参数
- Modify: `backend/app/services/ai_engine.py:build_reading_prompt` — 注入星座上下文
- Modify: `backend/app/schemas/reading.py` — ReadingCreate schema 加 zodiac 字段

**Interfaces:**
- Consumes: `wx.getStorageSync('zodiac_sign')` → string like "pisces"
- Produces: zodiac context block in AI system prompt: "\n【占卜者星座】双鱼座 — 结合星座特质进行解读"

#### 实施步骤

- [ ] **Step 1: 修改 reading schema — 加 zodiac 字段**

```python
# backend/app/schemas/reading.py
class ReadingCreate(BaseModel):
    spread_type: str
    theme: str = "general"
    question: str | None = None
    persona: str | None = None
    zodiac: str | None = None  # 新增
```

- [ ] **Step 2: 修改 readings API — 接收并传递 zodiac**

```python
# backend/app/api/readings.py, start_reading 函数签名
async def start_reading(
    req: ReadingCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # ...existing code...
    prompt = build_reading_prompt(
        spread=spread,
        theme=req.theme,
        question=req.question,
        persona_key=req.persona,
        zodiac_sign=req.zodiac,  # 新增
    )
```

- [ ] **Step 3: 修改 AI engine — build_reading_prompt 注入星座**

```python
# backend/app/services/ai_engine.py
# 在 build_reading_prompt 函数参数中加 zodiac_sign: str | None = None

ZODIAC_CN = {
    "aries": "白羊座", "taurus": "金牛座", "gemini": "双子座",
    "cancer": "巨蟹座", "leo": "狮子座", "virgo": "处女座",
    "libra": "天秤座", "scorpio": "天蝎座", "sagittarius": "射手座",
    "capricorn": "摩羯座", "aquarius": "水瓶座", "pisces": "双鱼座",
}

def build_reading_prompt(..., zodiac_sign: str | None = None):
    # ...existing code...
    
    # Add zodiac context
    zodiac_block = ""
    if zodiac_sign:
        zodiac_cn = ZODIAC_CN.get(zodiac_sign, zodiac_sign)
        zodiac_block = (
            f"\n\n【占卜者星座】{zodiac_cn}\n"
            f"请在解读时自然地结合{zodiac_cn}的性格特质视角，但不要过度强调星座决定论。"
        )
    
    system = f"""你是星光映照的AI塔罗师。...
{user_context_block}
{zodiac_block}
..."""
```

- [ ] **Step 4: 修改前端 — 传 zodiac 参数**

```javascript
// miniapp/pages/reading/reading.js, onStartReading
const zodiacSign = wx.getStorageSync('zodiac_sign') || '';

wx.request({
  // ...
  data: {
    spread_type: spread.type,
    theme: this.data.selectedTheme,
    question: question,
    persona: this.data.selectedPersona || DEFAULT_PERSONA,
    zodiac: zodiacSign,  // 新增
  },
});
```

- [ ] **Step 5: 测试验证**

```bash
# 后端单元测试
cd /mnt/e/tarot-miniapp/backend
python3 -c "
from app.services.ai_engine import build_reading_prompt
p = build_reading_prompt(
    spread={'name': '三牌占卜', 'positions': [{'name':'过去'},{'name':'现在'},{'name':'未来'}], 'cards_per_position': 1},
    spread_key='three_card',
    theme='love',
    question='我的感情运势如何',
    persona_key='gentle_star',
    zodiac_sign='pisces',
)
assert '双鱼座' in p and 'gentle_star' in p.lower(), 'Zodiac or persona not in prompt!'
print('OK: Zodiac and persona injected correctly')
"
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/reading.py backend/app/api/readings.py \
  backend/app/services/ai_engine.py miniapp/pages/reading/reading.js
git commit -m "feat: 星座关联AI解读 — zodiac注入prompt实现个性化
- schema/readings: ReadingCreate 加 zodiac 字段
- AI engine: ZODIAC_CN 映射 + build_reading_prompt 注入星座上下文
- reading.js: startReading 传递 zodiac 参数"
```

---

### Task 2: 验证修复 — AI角色全链路 + 教学数据 + 迁移

**缺口**: 3个已实现功能需要端到端验证和修复。

**Files:**
- Modify: `backend/app/services/ai_engine.py` — 验证 persona prompt suffix 注入
- Verify: `backend/app/db/seed.py` — 确认教学数据入库
- Verify: `backend/alembic/` — 迁移执行+回滚测试

#### 子任务 2.1: AI角色全链路验证

- [ ] **Step 7: 验证 persona 从选择到 prompt 全程贯通**

```bash
cd /mnt/e/tarot-miniapp/backend
python3 -c "
from app.services.ai_engine import build_reading_prompt
from app.services.ai_personas import get_persona_prompt_suffix

# Test all 3 personas
for key in ['gentle_star', 'wise_moon', 'frank_sun']:
    suffix = get_persona_prompt_suffix(key)
    assert len(suffix) > 50, f'{key} suffix too short or missing'
    
    p = build_reading_prompt(
        spread={'name': '三牌占卜', 'positions': [{'name':'过去'},{'name':'现在'},{'name':'未来'}], 'cards_per_position': 1},
        spread_key='three_card',
        theme='general',
        persona_key=key,
    )
    assert suffix[:30] in p, f'{key} suffix not injected into prompt!'
    print(f'OK: {key} prompt injection verified')
print('ALL PERSONAS: full pipeline verified')
"
```

- [ ] **Step 8: 修复发现的任何断链**

如果 persona suffix 未注入 prompt（可能在 build_reading_prompt 中缺少调用），补上：

```python
# backend/app/services/ai_engine.py
from app.services.ai_personas import get_persona_prompt_suffix

def build_reading_prompt(..., persona_key: str | None = None):
    persona_block = get_persona_prompt_suffix(persona_key)
    # ...注入到 system prompt...
```

#### 子任务 2.2: 教学数据入库验证

- [ ] **Step 9: 检查教学数据是否在数据库中**

```bash
sshpass -p 'SSHPass-REDACTED' ssh root@124.221.233.214 \
  'cd /opt/tarot/backend && python3 -c "
import asyncio
from app.db.database import async_session
from app.models.card_teaching import CardTeaching
from sqlalchemy import select, func

async def check():
    async with async_session() as db:
        result = await db.execute(select(func.count(CardTeaching.card_id)))
        count = result.scalar()
        print(f\"CardTeaching rows in DB: {count}\")
        if count == 0:
            print(\"NEEDS SEEDING\")
        elif count == 78:
            print(\"ALL 78 CARDS HAVE TEACHING DATA\")
        else:
            print(f\"PARTIAL: {count}/78 cards\")

asyncio.run(check())
"'
```

- [ ] **Step 10: 如果未入库，执行种子脚本**

```bash
# 如果 seed.py 中有 teaching 数据导入逻辑，运行它
# 否则：从 card_teaching_data.json 导入到 CardTeaching 表
sshpass -p 'SSHPass-REDACTED' ssh root@124.221.233.214 \
  'cd /opt/tarot/backend && python3 scripts/seed_card_teaching.py 2>&1 || echo "Need to create seeding script"'
```

如果没有 seeding script，创建一个：

```python
# backend/scripts/seed_card_teaching.py
import json, asyncio
from app.db.database import async_session
from app.models.card_teaching import CardTeaching

async def seed():
    with open('data/card_teaching_data.json', 'r') as f:
        data = json.load(f)
    async with async_session() as db:
        for card_id, teaching in data.items():
            db.add(CardTeaching(
                card_id=int(card_id),
                symbols=json.dumps(teaching.get('symbols', []), ensure_ascii=False),
                story=teaching.get('story', ''),
                keywords_learning=json.dumps(teaching.get('keywords_learning', []), ensure_ascii=False),
                life_connection=teaching.get('life_connection', ''),
                element_association=teaching.get('element_association', ''),
            ))
        await db.commit()
    print(f'Seeded {len(data)} cards with teaching data')

asyncio.run(seed())
```

#### 子任务 2.3: 数据库迁移验证

- [ ] **Step 11: 测试迁移可执行和回滚**

```bash
sshpass -p 'SSHPass-REDACTED' ssh root@124.221.233.214 \
  'cd /opt/tarot/backend && \
   alembic upgrade head && echo "UPGRADE OK" && \
   alembic downgrade -1 && echo "DOWNGRADE OK" && \
   alembic upgrade head && echo "RE-UPGRADE OK"'
```

预期输出：三次操作全部 OK。

- [ ] **Step 12: Commit**

```bash
git add backend/app/services/ai_engine.py backend/scripts/seed_card_teaching.py
git commit -m "fix: M2验证修复 — AI角色链路 + 教学数据 + 迁移验证
- AI引擎: 确保persona prompt suffix正确注入
- 新增 seed_card_teaching.py 脚本
- 验证 Alembic upgrade/downgrade 正常"
```

---

### Task 3: 每日习惯循环强化

**缺口**: daily-card 页有收集进度（22张大牌），但缺乏连续打卡的情感激励。签到在独立页面，与每日一牌无联动。

**Files:**
- Modify: `miniapp/pages/daily-card/daily-card.js` — 加 streak 奖励提醒
- Modify: `miniapp/pages/daily-card/daily-card.wxml` — 加进度条和鼓励文案

#### 实施步骤

- [ ] **Step 13: 修改 daily-card.js — 读取 streak + 显示激励**

```javascript
// daily-card.js onLoad 中添加:
async _loadStreakContext() {
  try {
    const res = await request('/tasks/status');
    if (res && res.streak !== undefined) {
      const streak = res.streak || 0;
      const level = res.level || { name: '星光旅人' };
      
      let encouragement = '';
      if (streak === 0) {
        encouragement = '今天开始你的星光之旅吧 ✦';
      } else if (streak < 3) {
        encouragement = `已连续 ${streak} 天 · 星光初现`;
      } else if (streak < 7) {
        encouragement = `连续 ${streak} 天 · 星辰相伴`;
      } else if (streak < 30) {
        encouragement = `连续 ${streak} 天 · 月光常驻 ${level.name}`;
      } else {
        encouragement = `${level.name} · 星光不负赶路人`;
      }
      
      this.setData({
        dailyStreak: streak,
        streakEncouragement: encouragement,
        nextMilestone: streak < 7 ? 7 : (streak < 30 ? 30 : 100),
        milestoneProgress: streak < 7 ? (streak / 7 * 100) : (streak < 30 ? (streak / 30 * 100) : 100),
      });
    }
  } catch (e) {
    // Silently fail — streak info is optional enhancement
  }
},
```

- [ ] **Step 14: 修改 daily-card.wxml — 添加鼓励区**

在每日牌位下方添加：
```xml
<!-- Streak encouragement -->
<view class="streak-banner" wx:if="{{dailyStreak >= 0}}">
  <view class="streak-progress-bar">
    <view class="streak-progress-fill" style="width: {{milestoneProgress}}%"></view>
  </view>
  <text class="streak-text">{{streakEncouragement}}</text>
  <text class="streak-hint" wx:if="{{dailyStreak < 7}}">再坚持 {{nextMilestone - dailyStreak}} 天解锁星辰学徒 ✦</text>
</view>
```

- [ ] **Step 15: 样式 + 编译验证 + Commit**

---

### Task 4: 全面自动化测试套件

**缺口**: 当前测试 409 行、5 文件、仅覆盖健康检查和基础 CRUD。需要核心流程测试。

**Files:**
- Create: `backend/tests/test_ai_personas.py` — 角色系统测试
- Create: `backend/tests/test_tasks.py` — 签到+等级测试
- Create: `backend/tests/test_diary_review.py` — 日记AI周回顾测试
- Create: `backend/tests/test_readings_flow.py` — 完整占卜流程测试
- Create: `backend/tests/test_teaching.py` — 教学数据测试

#### 测试矩阵

| 测试文件 | 覆盖 | 用例数 |
|---------|------|--------|
| test_ai_personas.py | 3角色 prompt 生成、get_persona 查找、默认回退 | 5 |
| test_tasks.py | 签到成功、重复签到拒绝、streak计算、等级晋级 | 6 |
| test_diary_review.py | AI周回顾生成、无日记时回退、参数校验 | 4 |
| test_readings_flow.py | 创建解读→AI生成→结果存储→会员额度、星座注入 | 8 |
| test_teaching.py | 78张牌教学数据完整性、symbols结构、API返回格式 | 4 |

- [ ] **Step 16: 写 test_ai_personas.py**
- [ ] **Step 17: 写 test_tasks.py**
- [ ] **Step 18: 写 test_diary_review.py**
- [ ] **Step 19: 写 test_readings_flow.py**
- [ ] **Step 20: 写 test_teaching.py**
- [ ] **Step 21: 全量测试运行**

```bash
cd /mnt/e/tarot-miniapp/backend
python3 -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

预期：≥30 tests, ≥27 pass, 覆盖率增量 ≥60%

- [ ] **Step 22: Commit**

---

## M2 完成验证门

```bash
# 1. IDE 编译
cd /mnt/e && powershell.exe -Command "cd 'E:\微信web开发者工具'; .\cli.bat auto-preview --project 'E:\tarot-miniapp\miniapp' --port 9428"

# 2. 后端全量测试
cd /mnt/e/tarot-miniapp/backend && python3 -m pytest tests/ -v

# 3. 迁移回滚测试
sshpass -p '...' ssh root@124.221.233.214 'cd /opt/tarot/backend && alembic downgrade -1 && alembic upgrade head'

# 4. 服务器健康
curl -s https://xingxiang.chat/health

# 5. 教学数据验证
# 确认 /cards/{id}/teaching 返回完整数据

# 6. 星座注入验证
# 确认 AI prompt 包含 zodiac context
```
