# 星光映照 — 陪伴深化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将星光映照从"塔罗解读工具"升级为"AI塔罗陪伴空间"，通过日记×卡牌深度绑定、AI人格聊天落地、解读→日记链路贯通、三层解读深度，建立竞品无法复制的差异化体验。

**Architecture:** 后端新增 `/diary/reflection-prompt` 端点，修改 chat 端点注入人格prompt，修改 readings 端点支持深度层级。前端改造日记编写页、聊天页、解读结果页三个核心页面。所有AI能力基于已有 DeepSeek V4 Pro API 和 145KB卡牌教学库。

**Tech Stack:** Python/FastAPI (backend), 微信小程序原生 (frontend), DeepSeek V4 Pro, SQLite

## Global Constraints

- 所有API端点需保持向后兼容，不破坏现有前端
- 前端改动仅涉及WXML/WXSS/JS，不引入新依赖
- 日记和社区页面为子包（subPackages），路径为 `pages/diary/` 和 `pages/community/`
- 解读页面路径为 `pages/reading/` 和 `pages/reading-result/`
- 聊天页面路径为 `pages/chat/`
- 后端服务位于 `/opt/tarot/backend`，通过 systemd `tarot-api` 运行
- 提交消息格式: `<type>: <description>` (如 feat:, fix:, change:)
- 服务器部署: 本地编辑 → scp 上传 → systemctl restart tarot-api
- 服务器 .env 路径: `/opt/tarot/backend/.env`
- 测试: 所有API端点通过 `curl -s https://xingxiang.chat/api/...` 验证

---

## Task 1: 日记API修复 — card_id透传 + 反思问题端点

**Files:**
- Modify: `backend/app/schemas/diary.py` — 添加 card_id 和 reflection_prompt 字段
- Modify: `backend/app/api/diary.py` — 接收card_id, 新增 reflection-prompt 端点

**Interfaces:**
- Produces: `POST /diary/reflection-prompt` — 接收 `{card_id: int, card_name: str}`, 返回 `{question: str}`
- Produces: `DiaryCreate.card_id: int | None` — 日记创建时可选传入卡牌ID

### Task 1a: DiaryCreate schema 加 card_id

**Step 1: 修改 schema**

```python
# backend/app/schemas/diary.py — DiaryCreate 改为:
class DiaryCreate(BaseModel):
    mood: str | None = None
    reflection: str | None = None
    card_id: int | None = None  # NEW: 允许前端指定关联卡牌
```

**Step 2: 修改 diary API create_entry — 使用传入的 card_id**

在 `backend/app/api/diary.py` 的 `create_entry` 函数中，将第 89-93 行的随机选卡逻辑改为:

```python
    # ── Use client-provided card_id or fallback to random ──
    if body.card_id is not None:
        card_result = await db.execute(
            select(TarotCard).where(TarotCard.id == body.card_id)
        )
        card = card_result.scalar_one_or_none()
        if card is None:
            raise HTTPException(status_code=404, detail="卡牌不存在")
    else:
        card_result = await db.execute(
            select(TarotCard).order_by(func.random()).limit(1)
        )
        card = card_result.scalar_one_or_none()
        if card is None:
            raise HTTPException(status_code=500, detail="卡牌数据为空")
```

### Task 1b: 新增 POST /diary/reflection-prompt 端点

在 `backend/app/api/diary.py` 末尾添加:

```python
from pydantic import BaseModel as PydanticBaseModel

class ReflectionPromptRequest(PydanticBaseModel):
    card_id: int
    card_name: str

class ReflectionPromptResponse(PydanticBaseModel):
    question: str


@router.post("/reflection-prompt", response_model=ReflectionPromptResponse)
async def get_reflection_prompt(
    body: ReflectionPromptRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a personalized reflection question based on today's card.
    Uses the card teaching database + AI to create a unique, thought-provoking prompt.
    """
    # ── Fetch card teaching data ──
    from app.models.card_teaching import CardTeaching
    result = await db.execute(
        select(CardTeaching).where(CardTeaching.card_id == body.card_id)
    )
    teaching = result.scalar_one_or_none()

    teaching_context = ""
    if teaching:
        teaching_context = (
            f"卡牌符号: {teaching.symbols or '无'}\n"
            f"生活关联: {teaching.life_connection or '无'}\n"
            f"反思提示: {teaching.reflection_prompt or '无'}"
        )

    # ── Call AI to generate reflection question ──
    client = _get_ai_client()
    if not client:
        # Fallback without AI
        return ReflectionPromptResponse(
            question=f"今天的「{body.card_name}」给你带来了什么感受？它在哪些方面触动了你？"
        )

    try:
        response = await client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            max_tokens=200,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是星光映照的塔罗日记引导师。用户今天抽到了一张塔罗牌，"
                        "你需要生成一个引人深思的反思问题，帮助用户将卡牌的智慧融入当天生活。\n\n"
                        "要求:\n"
                        "1. 问题要具体、个人化，不要泛泛的「今天感觉怎么样」\n"
                        "2. 关联卡牌的符号和寓意，但用日常语言表达\n"
                        "3. 问题应该让用户想立刻开始写\n"
                        "4. 温暖而有深度，像朋友的关心\n"
                        "5. 50字以内\n"
                        "6. 只返回问题本身，不要任何前缀或解释"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"卡牌: {body.card_name}\n"
                        f"{teaching_context}\n"
                        f"请为这位用户生成一个今天的反思问题。"
                    ),
                },
            ],
            timeout=30.0,
        )
        question = response.choices[0].message.content.strip()
        return ReflectionPromptResponse(question=question)
    except Exception as exc:
        logger.warning("Failed to generate reflection prompt: %s", exc)
        return ReflectionPromptResponse(
            question=f"今天的「{body.card_name}」想告诉你什么？花几分钟写下你的感受吧。"
        )
```

**Step 3: 重启服务并验证**

```bash
# 部署到服务器
scp backend/app/schemas/diary.py backend/app/api/diary.py root@124.221.233.214:/opt/tarot/backend/app/schemas/ && scp backend/app/api/diary.py root@124.221.233.214:/opt/tarot/backend/app/api/
ssh root@124.221.233.214 "systemctl restart tarot-api"

# 验证
curl -s -X POST https://xingxiang.chat/api/diary/reflection-prompt \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <test-token>" \
  -d '{"card_id": 16, "card_name": "恶魔"}'
```

**Step 4: Commit**

```bash
git add backend/app/schemas/diary.py backend/app/api/diary.py
git commit -m "feat: add card_id to DiaryCreate and reflection-prompt endpoint"
```

---

## Task 2: 日记前端 — 反思问题引导式写作

**Files:**
- Modify: `miniapp/pages/diary/diary.wxml` — 新建日记弹窗加入反思问题卡片
- Modify: `miniapp/pages/diary/diary.wxss` — 反思卡片样式
- Modify: `miniapp/pages/diary/diary.js` — 加载反思问题, 传card_id

**Interfaces:**
- Consumes: `POST /api/diary/reflection-prompt` → `{question: string}`
- Consumes: `POST /api/diary/entries` → 新增 `card_id` 参数

### Task 2a: diary.js — 加载反思问题逻辑

在 `diary.js` 的 `onShow` 或新增 `_loadReflectionPrompt` 方法:

```javascript
// diary.js — 在 data 中添加:
data: {
  // ... existing ...
  reflectionPrompt: '',       // AI生成的反思问题
  reflectionPromptLoading: false,
  todayCardId: null,          // 今日卡牌ID
  todayCardName: '',          // 今日卡牌名
},

// 在 onLoad/onShow 中调用:
_loadReflectionPrompt() {
  const app = getApp();
  const dailyCard = app.globalData?.dailyCard;
  if (!dailyCard || !dailyCard.id) return;

  this.setData({
    todayCardId: dailyCard.id,
    todayCardName: dailyCard.name_zh || '',
    reflectionPromptLoading: true,
  });

  request('/diary/reflection-prompt', 'POST', {
    card_id: dailyCard.id,
    card_name: dailyCard.name_zh || '',
  }).then(res => {
    this.setData({
      reflectionPrompt: res.question || '',
      reflectionPromptLoading: false,
    });
  }).catch(() => {
    // 降级: 使用本地默认问题
    this.setData({
      reflectionPrompt: `今天的「${this.data.todayCardName}」给你带来了什么感受？`,
      reflectionPromptLoading: false,
    });
  });
},

// 修改 onNewEntry — 提交时带上 card_id:
onNewEntry() {
  // ... existing validation ...
  const body = {
    mood: this.data.selectedMood,
    reflection: this.data.reflectionText,
    card_id: this.data.todayCardId || undefined,  // NEW
  };
  request('/diary/entries', 'POST', body).then(/* ... */);
},
```

### Task 2b: diary.wxml — 反思问题卡片

在新建日记弹窗 (`modal-sheet`) 的 textarea 上方添加反思问题卡片:

```xml
<!-- 反思引导卡片 — 放在 modal-sheet 内部, textarea 上方 -->
<view wx:if="{{reflectionPrompt}}" class="reflection-prompt-card">
  <view class="reflection-prompt-header">
    <text class="reflection-prompt-icon">💫</text>
    <text class="reflection-prompt-label">今日反思</text>
  </view>
  <text class="reflection-prompt-question">{{reflectionPrompt}}</text>
  <view wx:if="{{todayCardName}}" class="reflection-prompt-card-tag">
    <text>🃏 {{todayCardName}}</text>
  </view>
</view>
```

### Task 2c: diary.wxss — 反思卡片样式

```css
/* 反思引导卡片 */
.reflection-prompt-card {
  margin: 0 var(--spacing-md) var(--spacing-md);
  padding: var(--spacing-md);
  background: linear-gradient(135deg, rgba(244,212,140,0.12) 0%, rgba(180,140,200,0.08) 100%);
  border: 1.5rpx solid rgba(244,212,140,0.25);
  border-radius: var(--radius-md, 16rpx);
}

.reflection-prompt-header {
  display: flex;
  align-items: center;
  gap: 8rpx;
  margin-bottom: 12rpx;
}

.reflection-prompt-icon {
  font-size: 28rpx;
}

.reflection-prompt-label {
  font-size: var(--font-size-caption, 24rpx);
  color: var(--color-gold);
  font-weight: 600;
  letter-spacing: 2rpx;
}

.reflection-prompt-question {
  display: block;
  font-size: var(--font-size-body, 30rpx);
  color: var(--color-text-primary, #F0EDE8);
  line-height: 1.6;
  font-weight: 400;
}

.reflection-prompt-card-tag {
  margin-top: 12rpx;
  display: inline-flex;
  padding: 4rpx 16rpx;
  background: rgba(244,212,140,0.10);
  border-radius: var(--radius-pill, 999rpx);
}

.reflection-prompt-card-tag text {
  font-size: var(--font-size-xs, 20rpx);
  color: var(--color-gold);
}
```

**Step: Commit**

```bash
git add miniapp/pages/diary/
git commit -m "feat: AI reflection prompt in diary compose with card binding"
```

---

## Task 3: AI人格在聊天中落地

**Files:**
- Modify: `backend/app/api/chat.py` — 注入人格系统提示词
- Modify: `miniapp/pages/chat/chat.wxml` — 人格头部展示
- Modify: `miniapp/pages/chat/chat.wxss` — 人格样式
- Modify: `miniapp/pages/chat/chat.js` — 读取并显示人格

**Interfaces:**
- Consumes: `app/services/ai_personas.py` — `get_persona(key)` 返回 persona dict
- Produces: 聊天API响应不变(向后兼容)，仅AI回复风格改变

### Task 3a: 后端 — 聊天端点注入人格prompt

修改 `backend/app/api/chat.py` 第 63-77 行的 system prompt:

```python
from app.services.ai_personas import get_persona

# ── 在 chat_followup 函数中, 构建 messages 之前: ──
# 从解读记录中获取人格 (reading 表已有 persona 字段)
persona = get_persona(getattr(reading, 'persona', None) or None)
persona_prompt = persona.get("prompt_suffix", "")
persona_name = persona.get("name", "解读者")

# ── 替换 system prompt: ──
messages: list[dict] = [
    {
        "role": "system",
        "content": (
            f"你是「{persona_name}」，星光映照的AI塔罗师。\n"
            f"用户刚才的解读结果是：\n"
            f"{(reading.interpretation or '')[:500]}\n\n"
            f"请以「{persona_name}」的身份，基于这个解读，继续和用户深入探讨。\n"
            f"保持连续性和一致性，体现你的独特风格。\n"
            f"{persona_prompt}\n\n"
            f"【行动建议】\n"
            f"在回答的最后，如果合适的话，请给出 1-3 条具体的行动建议，"
            f"使用 [ACTION]建议内容[/ACTION] 格式。\n"
            f"每条建议请使用第二人称「你」。"
        ),
    }
]
```

### Task 3b: 前端 — 聊天页展示人格身份

**chat.js** — 在 data 和 onLoad 中添加:

```javascript
// data 中添加:
personaName: '',
personaIcon: '',

// onLoad 中读取:
const reading = app.globalData?.currentReading;
if (reading && reading.persona) {
  const p = PERSONA_MAP[reading.persona];
  if (p) {
    this.setData({ personaName: p.name, personaIcon: p.icon });
  }
}

// 页面顶部定义人格映射 (与 reading.js 保持一致):
const PERSONA_MAP = {
  gentle_star: { name: '温和的星', icon: '✦' },
  wise_moon:   { name: '智慧的月', icon: '☽' },
  frank_sun:   { name: '率直的太阳', icon: '☀' },
};
```

**chat.wxml** — 在聊天顶部 (messages区域上方) 添加人格条:

```xml
<!-- 人格身份条 -->
<view wx:if="{{personaName}}" class="persona-bar">
  <text class="persona-bar-icon">{{personaIcon}}</text>
  <text class="persona-bar-name">{{personaName}}</text>
  <text class="persona-bar-label">正在倾听</text>
</view>
```

**chat.wxss** — 人格条样式:

```css
.persona-bar {
  display: flex;
  align-items: center;
  gap: 8rpx;
  padding: 16rpx var(--spacing-md);
  margin: 0 var(--spacing-md);
  background: rgba(244,212,140,0.08);
  border: 1rpx solid rgba(244,212,140,0.15);
  border-radius: var(--radius-pill, 999rpx);
}

.persona-bar-icon {
  font-size: 28rpx;
  color: var(--color-gold);
}

.persona-bar-name {
  font-size: var(--font-size-caption, 24rpx);
  color: var(--color-gold);
  font-weight: 600;
}

.persona-bar-label {
  font-size: var(--font-size-xs, 20rpx);
  color: var(--color-text-tertiary);
  margin-left: auto;
}
```

**Step: Commit**

```bash
git add backend/app/api/chat.py miniapp/pages/chat/
git commit -m "feat: inject persona prompt into chat AI, show persona identity in chat UI"
```

---

## Task 4: 解读→日记链路 + 解读三层深度

**Files:**
- Modify: `backend/app/api/readings.py` — 解读结果加 reflection_question 和 depth 层级
- Modify: `backend/app/schemas/reading.py` — ReadingResponse 加字段
- Modify: `miniapp/pages/reading-result/reading-result.wxml` — 反思卡片 + 深度层级UI
- Modify: `miniapp/pages/reading-result/reading-result.wxss` — 新卡片样式
- Modify: `miniapp/pages/reading-result/reading-result.js` — 深度处理 + 跳转日记

### Task 4a: 后端 — 解读结果加反思问题

在 `readings.py` 的解读生成后, 追加反思问题生成:

```python
# 在返回 ReadingResponse 之前, 生成反思问题:
from app.services.ai_personas import get_persona

persona = get_persona(req.persona_key)
reflection_question = ""

# 使用第一个问题 (context.question) 和第一张牌的卡牌名生成反思
client = _get_ai_client_for_reflection()
if client and drawn_cards:
    first_card = drawn_cards[0]
    try:
        resp = await client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            max_tokens=120,
            messages=[{
                "role": "system",
                "content": (
                    "用户刚完成了一次塔罗解读。请生成一个引人深思的反思问题，"
                    "引导用户将解读智慧应用到生活中。60字以内，温暖而具体。"
                    "只返回问题本身。"
                ),
            }, {
                "role": "user",
                "content": (
                    f"用户问题: {context.question}\n"
                    f"关键卡牌: {first_card.name_zh}\n"
                    f"解读摘要: {(interpretation or '')[:300]}"
                ),
            }],
            timeout=20.0,
        )
        reflection_question = resp.choices[0].message.content.strip()
    except Exception:
        reflection_question = f"「{first_card.name_zh}」的启示对你意味着什么？"

# 在 ReadingResponse 中加入 reflection_question 字段
```

同时在 `schemas/reading.py` 的 `ReadingResponse` 中加:

```python
class ReadingResponse(BaseModel):
    # ... existing fields ...
    reflection_question: str | None = None  # NEW
```

### Task 4b: 后端 — 解读三层深度

在 `readings.py` 中定义深度层级逻辑:

```python
# 解读深度层级
# depth=basic (免费): TL;DR 摘要 + 单牌简析 (~200字)
# depth=standard (免费): 完整牌阵解读 + 教学面板 (~1500字, 当前)
# depth=deep (会员): 完整解读 + 情感分析 + 行动方案 + 牌阵关系图

# 当前默认所有解读为 standard。会员可请求 deep。
# basic 仅返回 interpretation 的前 200 字作为 TL;DR.
```

在 `schemas/reading.py` 的 `CreateReadingRequest` 中加:

```python
class CreateReadingRequest(BaseModel):
    spread_type: str
    question: str | None = None
    theme: str | None = "general"
    persona_key: str | None = None
    depth: str | None = "standard"  # NEW: "basic" | "standard" | "deep"
```

### Task 4c: 前端 — 解读结果页反射卡片

**reading-result.wxml** — 在解读正文下方 (行动建议上方) 添加:

```xml
<!-- 今日反思卡片 — 引导跳转日记 -->
<view wx:if="{{reflectionQuestion}}" class="reflection-card">
  <view class="reflection-card-glow"></view>
  <text class="reflection-card-icon">📝</text>
  <text class="reflection-card-label">将这份启示写进日记</text>
  <text class="reflection-card-question">{{reflectionQuestion}}</text>
  <button class="reflection-card-btn" bindtap="onGoDiaryFromReading">
    <text>记录今日感悟 ✦</text>
  </button>
</view>
```

**reading-result.js** — 跳转日记:

```javascript
onGoDiaryFromReading() {
  const app = getApp();
  // 传递当前解读的第一张卡牌信息给日记页
  const cards = this.data.cards || [];
  if (cards.length > 0) {
    app.globalData.diaryCardHint = {
      card_id: cards[0].id,
      card_name: cards[0].name_zh || cards[0].name,
    };
  }
  wx.navigateTo({ url: '/pages/diary/diary' });
},
```

**reading-result.wxss** — 反射卡片样式:

```css
.reflection-card {
  position: relative;
  margin: var(--spacing-lg) var(--spacing-md);
  padding: var(--spacing-lg);
  background: linear-gradient(135deg, rgba(180,140,200,0.10) 0%, rgba(244,212,140,0.08) 100%);
  border: 1.5rpx solid rgba(244,212,140,0.20);
  border-radius: var(--radius-lg, 24rpx);
  text-align: center;
  overflow: hidden;
}

.reflection-card-glow {
  position: absolute;
  top: -40rpx;
  left: 50%;
  transform: translateX(-50%);
  width: 200rpx;
  height: 80rpx;
  background: radial-gradient(ellipse, rgba(244,212,140,0.15) 0%, transparent 70%);
  pointer-events: none;
}

.reflection-card-icon {
  display: block;
  font-size: 48rpx;
  margin-bottom: 12rpx;
}

.reflection-card-label {
  display: block;
  font-size: var(--font-size-caption, 24rpx);
  color: var(--color-gold);
  font-weight: 600;
  letter-spacing: 2rpx;
  margin-bottom: 12rpx;
}

.reflection-card-question {
  display: block;
  font-size: var(--font-size-body, 30rpx);
  color: var(--color-text-primary);
  line-height: 1.7;
  margin-bottom: 24rpx;
  font-weight: 400;
}

.reflection-card-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 16rpx 48rpx;
  background: linear-gradient(135deg, #F4D48C 0%, #D4B06A 100%);
  border-radius: var(--radius-pill, 999rpx);
  color: #1A1A3E;
  font-size: var(--font-size-body, 30rpx);
  font-weight: 600;
  letter-spacing: 2rpx;
  border: none;
}
```

### Task 4d: 前端 — 解读三层深度UI

**reading-result.wxml** — 免费用户解读底部加会员引导:

```xml
<!-- 会员深度解锁卡 (仅非会员显示) -->
<view wx:if="{{!isMember && readingDepth !== 'deep'}}" class="depth-unlock-card">
  <text class="depth-unlock-icon">🔮</text>
  <text class="depth-unlock-title">想获得更深入的解读？</text>
  <text class="depth-unlock-desc">会员解锁：情感分析 + 详细行动方案 + 牌阵关系图</text>
  <button class="depth-unlock-btn" bindtap="onGoMembership">
    <text>开通会员 · 解锁深度解读 ✦</text>
  </button>
</view>
```

**Step: Commit**

```bash
git add backend/app/api/readings.py backend/app/schemas/reading.py miniapp/pages/reading-result/
git commit -m "feat: reading-to-diary bridge, reflection card, tiered reading depth"
```

---

## Task 5: 日记补充 — 图片 + 编辑删除 + 分享卡片

**Files:**
- Modify: `backend/app/api/diary.py` — 新增 DELETE /entries/{id} 和 PUT /entries/{id} 端点
- Modify: `miniapp/pages/diary/diary.wxml` — 图片选择, 编辑/删除按钮, 分享按钮
- Modify: `miniapp/pages/diary/diary.wxss` — 新组件样式
- Modify: `miniapp/pages/diary/diary.js` — 图片上传, 编辑, 删除, 分享

### Task 5d: 后端 — 日记删除和编辑端点

在 `backend/app/api/diary.py` 中添加:

```python
@router.delete("/entries/{entry_id}")
async def delete_entry(
    entry_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DiaryEntry).where(
            DiaryEntry.id == entry_id,
            DiaryEntry.user_id == user.id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="日记不存在")
    await db.delete(entry)
    return {"ok": True}


@router.put("/entries/{entry_id}", response_model=DiaryEntryResponse)
async def update_entry(
    entry_id: str,
    body: DiaryCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DiaryEntry).where(
            DiaryEntry.id == entry_id,
            DiaryEntry.user_id == user.id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="日记不存在")
    if body.mood is not None:
        entry.mood = body.mood
    if body.reflection is not None:
        entry.reflection = body.reflection
    await db.flush()
    return DiaryEntryResponse(
        id=entry.id, date=str(entry.entry_date),
        mood=entry.mood, reflection=entry.reflection,
    )
```

### Task 5a: 日记条目加图片支持

**diary.js** — 添加图片选择和上传:

```javascript
// data 中加:
selectedImage: '',      // 临时选中的图片路径
uploadingImage: false,

// 选择图片:
onChooseImage() {
  wx.chooseImage({
    count: 1,
    sizeType: ['compressed'],
    sourceType: ['album', 'camera'],
    success: (res) => {
      this.setData({ selectedImage: res.tempFilePaths[0] });
    },
  });
},

// 移除已选图片:
onRemoveImage() {
  this.setData({ selectedImage: '' });
},
```

上传逻辑: 图片使用 `wx.uploadFile` 上传到 `/diary/upload-image` 端点（如需要后端支持），或转为 base64 内嵌。

### Task 5b: 日记条目加编辑和删除

**diary.js** — 编辑和删除:

```javascript
// 长按条目弹出操作菜单
onLongPressEntry(e) {
  const id = e.currentTarget.dataset.id;
  wx.showActionSheet({
    itemList: ['编辑', '删除'],
    success: (res) => {
      if (res.tapIndex === 0) {
        this._editEntry(id);
      } else if (res.tapIndex === 1) {
        this._deleteEntry(id);
      }
    },
  });
},

_editEntry(id) {
  const entry = this.data.entries.find(e => e.id === id);
  if (!entry) return;
  this.setData({
    showComposer: true,
    editingEntryId: id,
    selectedMood: entry.mood || '',
    reflectionText: entry.reflection || '',
  });
},

_deleteEntry(id) {
  wx.showModal({
    title: '删除日记',
    content: '确定要删除这条日记吗？',
    success: (res) => {
      if (res.confirm) {
        request(`/diary/entries/${id}`, 'DELETE').then(() => {
          this._loadEntries();
        });
      }
    },
  });
},
```

### Task 5c: 日记分享卡片

**diary.js** — 生成分享图片:

```javascript
onShareEntry(e) {
  const id = e.currentTarget.dataset.id;
  const entry = this.data.entries.find(e => e.id === id);
  if (!entry) return;

  // 使用 canvas-poster 生成日记卡片
  const { generateDiaryCard } = require('../../utils/canvas-poster');
  generateDiaryCard(entry).then((imagePath) => {
    wx.previewImage({ urls: [imagePath] });
  });
},
```

**diary.wxml** — 每个条目加长按操作:

```xml
<!-- 日记条目加 longpress 和操作按钮 -->
<view class="diary-entry" 
  wx:for="{{entries}}" wx:key="id"
  bindlongpress="onLongPressEntry" data-id="{{item.id}}">
  
  <!-- 右上角操作按钮 -->
  <view class="diary-entry-actions">
    <text class="diary-action-btn" bindtap="onShareEntry" data-id="{{item.id}}">分享</text>
  </view>
  
  <!-- ... existing entry content ... -->
</view>
```

**Step: Commit**

```bash
git add miniapp/pages/diary/ miniapp/utils/canvas-poster.js
git commit -m "feat: diary image upload, edit/delete, share card generation"
```

---

## Deployment Sequence

按顺序执行每个Task，每个Task完成后验证:

1. **Task 1** → 部署后端, curl 验证 `/api/diary/reflection-prompt`
2. **Task 2** → IDE 验证日记页面反思问题显示
3. **Task 3** → IDE 验证聊天页人格条 + 不同人格回复差异
4. **Task 4** → IDE 验证解读结果页反思卡片 + 跳转日记 + 深度层级
5. **Task 5** → IDE 验证日记图片/编辑/删除/分享

每个Task独立可测试，不依赖后续Task即可验证。

---

## Verification Checklist

部署完成后，在IDE中验证以下体验链路:

- [ ] 首页抽每日一牌 → 点「记录今天」→ 日记页显示AI生成的反思问题 (关联今日卡牌)
- [ ] 写日记 → 提交成功 → 日记列表显示新条目 (长按可编辑/删除)
- [ ] 首页选牌阵解读 → 解读结果页显示反思卡片 → 点「记录今日感悟」→ 跳转日记页
- [ ] 解读结果页 → 点「追问更多」→ 聊天页顶部显示人格身份条
- [ ] 聊天页咨询同一个问题，切换不同人格应得到不同风格的回复
- [ ] 非会员用户解读结果页底部显示深度解锁引导卡片


