# 星光映照 P1 四功能实施计划（第 2 期 · 3 阶段 3 次发布）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 第 2 期 P1 四功能：星光手账（心情日历+月度复盘）、星辰相遇（双人合盘）、星空时刻表+星象节点（日历+节点活动）、睡前星语（21:00 星语+月光卡）。按用户 2026-08-11 决策：手账与日记合并、晨讯/星语二选一、3 阶段 3 次发布、星语直接上 AI+短句库兜底。

**设计文档:** `docs/superpowers/specs/2026-08-11-starlight-p1-design.md`（21 个设计任务 T1-1~T4-5；本计划 = 21 设计任务 + T5-1 全体系串联验证 + T5-2 部署/发布说明，共 23 任务，阶段 1=8 / 阶段 2=7 / 阶段 3=8）

**Architecture:** 后端 FastAPI（backend/，venv=backend/venv，测试 `cd backend && ./venv/bin/python -m pytest`，SQLite+aiosqlite，alembic 迁移在 backend/alembic/versions/）；前端微信小程序（miniapp/，E3 奶油疗愈 token 在 miniapp/styles/common.wxss）。手账复用 diary_entries 不新建心情表；合盘新建 star_meetings；日历零新数据源（ASTRAL_EVENTS_2026 + moon 引擎）；星语改造 21:00 槽位为额度制。

**Tech Stack:** FastAPI / SQLAlchemy async / alembic / 微信小程序原生 / 微信订阅消息 API / 微信小程序码 API / DeepSeek（AI 星语与月度复盘，复用现有 client 封装）

## Global Constraints

- 设计文档：`docs/superpowers/specs/2026-08-11-starlight-p1-design.md`（含用户决策 4 条，全部已落入下方约束）
- **星光叙事命名（禁直用产品词）**：星光手账（心情日历）/ 星辰相遇（合盘）/ 星空时刻表（星象日历）/ 星象节点（节点活动）/ 睡前星语；星点=情绪；五档命名：满溢星光/明亮星光/常亮星光/微暗星光/隐没星光；节点命名：许愿之夜/复盘之夜/慢行期（水逆避"水逆期"负面联想）；水逆指南命名"慢下来的 7 件小事"；月光卡=晚安版星光名片
- **合规红线（P0）**：所有结果页/海报固定「仅供娱乐 · 星光映照」；禁"注定/缘分天定/天生一对/该在一起/分开/克/化解/转运/防小人"类措辞（措辞白名单测试）；合盘只描述相处方式、不定义结局，固定免责行「星辰只描述你们如何相处，不定义任何结局 · 仅供娱乐」；水逆只谈自我关怀；新月只引导许愿不承诺实现；月度复盘绝不下"越来越糟/越来越好"定性结论；AI 文案全部走 `ai_engine._OUTPUT_RED_LINE`（不预测/不恐吓/不命运定性/日记感知不引用）
- **AI 星语（用户决策 4）**：直接上 AI 个性化生成（结合当日星光/能量/心情）；必须保留短句库兜底（AI 失败/无 key/成本控制 → 降级）；同用户同日缓存（star_word_daily 表）；生成失败重试上限（当日 3 次后不再重试 AI，走兜底）；测试必须钉住降级路径
- **1 条/天推送额度（用户决策 2）**：晨讯/星语二选一（`slot_preference` morning 默认 / night）；两槽位共用 `last_sent_date` 原子认领 + `quota_available` 消费 → 全局每日最多 1 条；节点日不新增推送条数（晨讯内容按节点切换；21:00 月相事件优先保留，节点推送发全部有额度用户）
- **确定性算法**：同日同人恒定（build_today_guidance 星光色/数、合盘三要素加权、星语选择、月相、节点每日一句轮换）；合盘每项分数带原因（"同元素·火象相映 +8"）；缺要素权重重归一化 + 结果页明示估算口径
- **模板字段 20 字**：微信 thing 字段 ≤20 字，所有文案库（星语库/节点晨讯/7 件小事/相处提示）定稿即测试校验
- **安全（api_security_redline）**：meet 公开接口独立限流 30 次/分/IP（仿 `card_info_rate_limit`）；meet 落库只存派生星座 key（zodiac/moon/rising），不存出生日期明文（PII 最小化）；海报文案过 `msg_sec_check`；`/moon-card/today` 与 `/journal/*` 均鉴权
- **E3 token**：底 #FAF6EF、卡面 #FFFDF8、墨 #3D3A36（正文≥4.5:1）、细金 #A98B5F、暖金 #8A6B3D（CTA）；星光色盘 12 色复用 `STAR_COLORS`
- **测试纪律**：每任务 TDD（先写失败测试→见红→实现→见绿→commit）；后端命令 `cd backend && ./venv/bin/python -m pytest`（P0 基线 318 全绿起步，P1 全程全量回归不破）；数据库改动必须走 alembic 迁移
- **复用优先**：每个任务"复用"栏列明的 P0 资产必须直接复用（stardust.py / build_today_guidance / SubscribeQuota / maybePromptSubscribe / canvas-poster / wxacode / 月相引擎 / ASTRAL_EVENTS_2026 / diary AI 周回顾 / moon_reviews 缓存模式 / process_invite），禁止另起炉灶

---

# 阶段 1：星光手账 + 睡前星语后端（8 任务）

交付物：手账上线（含月度复盘）+ 星语后端就绪。发布：后端部署 + 迁移 + 上传体验版（v2.3.0）。

### Task 1（设计 T1-1）: 星光亮度映射 + /journal/calendar 月历聚合

**Files:**
- Create: `backend/app/services/journal.py`（亮度常量 + 连续记录 helper）
- Create: `backend/app/api/journal.py`（router = APIRouter(prefix="/journal", tags=["星光手账"])）
- Create: `backend/app/schemas/journal.py`
- Test: `backend/tests/test_journal.py`

**Interfaces:**
- Consumes: `DiaryEntry`（models/diary.py）、`TarotCard`、`build_today_guidance(target: date, zodiac: str|None) -> dict`（energy_engine.py）、`get_current_user`（utils/auth.py）
- Produces:
  - `MOOD_BRIGHTNESS: dict[str, int] = {"excited": 5, "happy": 4, "calm": 3, "thoughtful": 2, "anxious": 1, "sad": 1}`（代码常量不落库）
  - `BRIGHTNESS_NAMES: dict[int, str] = {5: "满溢星光", 4: "明亮星光", 3: "常亮星光", 2: "微暗星光", 1: "隐没星光"}`
  - `def current_streak(dates: set[date], today: date) -> int`（纯函数：从 today 起向前数连续有记录的天然日数）
  - `GET /journal/calendar?year=2026&month=8`（鉴权）→ `{days: [{date, mood, brightness, star_color, has_reflection, card_id}], stats: {days_recorded, bright_count, dim_count, current_streak}}`；star_color = `build_today_guidance(date, user.zodiac)["star_color"]` 确定性生成不存储；bright_count = brightness≥4，dim_count = brightness≤2

**复用:** `build_today_guidance`（星光色/数/宜忌，energy_engine.py:348）；`DiaryEntry` 模型；`get_current_user` 鉴权。

- [ ] **Step 1: 写失败测试**（tests/test_journal.py）：未登录 401；空月返回 days=[] 且 stats 全 0；同一日期两次调用 star_color 一致且等于 build_today_guidance 结果（确定性）；6 档 mood → 正确 brightness（excited=5 … anxious=1）；has_reflection 随 reflection 有无翻转；stats 计数正确；current_streak：无记录=0、连续 3 天=3、中间缺一天即断、跨月连续算连续
- [ ] **Step 2: 跑测试确认失败**：`cd backend && ./venv/bin/python -m pytest tests/test_journal.py -v` → FAIL
- [ ] **Step 3: 实现**：services/journal.py（常量 + current_streak + month 聚合函数）、api/journal.py（calendar 端点）、schemas/journal.py
- [ ] **Step 4: 全量回归 + commit**：`./venv/bin/python -m pytest -q` 全绿（P0 基线 + 新增不破）；`git commit -m "feat: 星光手账月历聚合+亮度映射 (T1-1)"`

**验收:** calendar 接口字段完整、确定性可测；连续记录 streak 逻辑有纯函数测试；全量回归绿。

### Task 2（设计 T1-2）: star_monthly_reviews 表 + /journal/review 月度复盘

**Files:**
- Create: `backend/app/models/star_monthly_review.py`（仿 models/review.py MoonReview 模式）
- Create: `backend/alembic/versions/11aa22bb33cc_add_star_monthly_reviews.py`
- Modify: `backend/app/services/journal.py`（build_monthly_review + AI prompt + 降级模板）
- Modify: `backend/app/api/journal.py`、`backend/app/schemas/journal.py`
- Test: `backend/tests/test_journal_review.py`

**Interfaces:**
- Consumes: `DiaryEntry`、`TarotCard`、`ASTRAL_EVENTS_2026`（当月新/满月天象）、`reset_ai_quota_if_new_day`（utils/quota.py）、`settings.FREE_DIARY_AI_DAILY`（=5，与 /diary/review 共享配额）、`_OUTPUT_RED_LINE`（ai_engine.py:204）、DeepSeek client 模式（diary.py `_get_ai_client`）、MoonReview 缓存模式（models/review.py）
- Produces: 表 `star_monthly_reviews(id CHAR(36) PK, user_id CHAR(36) INDEX, month CHAR(7), data TEXT, created_at, updated_at, UNIQUE uq_user_month(user_id, month))`
  - `GET /journal/review?month=2026-08`（鉴权）→ `{month, stats: {days_recorded, bright_count, dim_count, bright_ratio}, mood_series: [{date, mood, brightness}], star_color_counts: [{color, count}], top_cards: [{name, count}], trend_summary, insight, next_guide, cached: bool}`；缓存命中即返回（不消耗 AI 配额）；未命中聚合当月日记+最多卡牌+当月新/满月天象 → AI 生成（JSON 输出 trend_summary/insight/next_guide，走 `_OUTPUT_RED_LINE`，不引用日记原文细节）→ 写入缓存；AI 失败/无 key → 本地温柔模板（`_FALLBACK_TREND` 按 bright_ratio 分档文案，不下定性结论）；非会员生成时 `diary_ai_count_today +1`（与 /diary/review 同款 402 逻辑）
  - `POST /journal/review/regenerate {month: "2026-08"}`（鉴权）→ 覆盖当月缓存重新生成；非会员同受 FREE_DIARY_AI_DAILY 配额（402）
  - `GET /journal/review/share-preview?month=2026-08`（鉴权）→ `{month, stats, star_color_counts, summary}`（脱敏：无昵称/无日记原文）

**复用:** moon_reviews 按人按周期缓存模式（models/review.py + wishes.py `get_moon_review/regenerate_moon_review` 的 force 重生成语义）；/diary/review 的 AI 拼装与 JSON 围栏剥离模式（api/diary.py weekly_review）；`_OUTPUT_RED_LINE`；`ASTRAL_EVENTS_2026`；`reset_ai_quota_if_new_day`。

- [ ] **Step 1: 写失败测试**：无记录月份返回空 stats 与友好文案；首次调用调 AI（mock client）并落缓存，第二次调用 `cached=true` 且 AI 只调 1 次；非会员当日已用满 FREE_DIARY_AI_DAILY → 402；regenerate 覆盖缓存（内容变化）；AI 抛异常 → 返回降级模板且 cached 仍写入（source 标记 fallback）；trend_summary/降级文案不含黑名单词（注定/越来越糟/越来越差/天生/命）
- [ ] **Step 2: 跑测试确认失败**：`cd backend && ./venv/bin/python -m pytest tests/test_journal_review.py -v` → FAIL
- [ ] **Step 3: 实现**：模型+迁移（`alembic revision --autogenerate -m "add star_monthly_reviews"` 后手工核对仅含新表，`alembic upgrade head`）；service + 三端点 + schema
- [ ] **Step 4: 全量回归 + commit**：`./venv/bin/python -m pytest -q` 全绿；`git commit -m "feat: 月度星光复盘 AI+缓存+降级 (T1-2)"`

**验收:** 缓存命中不重复调 AI；配额共享生效；降级路径有测试钉住；合规词扫描通过。

### Task 3（设计 T1-3）: /journal/entries + 连续 7 天星尘奖励

**Files:**
- Create: `backend/app/services/diary_entries.py`（从 api/diary.py 抽取公共 upsert）
- Modify: `backend/app/api/diary.py`（create_entry 改调公共函数，行为不变）
- Modify: `backend/app/models/user.py`（加 `journal_streak_reward_week: str | None` VARCHAR(8)）
- Create: `backend/alembic/versions/22bb33cc44dd_add_journal_streak_reward_week.py`
- Modify: `backend/app/api/journal.py`、`backend/app/services/journal.py`
- Test: `backend/tests/test_journal.py`（追加）

**Interfaces:**
- Consumes: `DiaryEntry`、`TarotCard`、`stardust.tier_for/tier_name`、`build_today_guidance`、`current_streak`（Task 1）、tasks.py 签到星尘模式（stardust_total += 1; star_tier = tier_for(...)）
- Produces: `async def upsert_diary_entry(db, user, mood, reflection=None, card_id=None, entry_date=None) -> DiaryEntry`（同日已存在则更新，card_id 缺省时随机取一张；diary.py 与 journal 共用）
  - `POST /journal/entries {mood: 必填(6 档枚举), reflection?: str, card_id?: int}`（鉴权）→ `{id, date, mood, brightness, star_color, card: {id, name_zh, meaning_upright}, reflection, streak, reward: bool}`；写成功后检测连续记录：`streak >= 7` 且 `journal_streak_reward_week != 本周 ISO 周键`（f"{y}-W{w:02d}"）→ `stardust_total += 1; star_tier = tier_for(stardust_total)` 并更新周键（幂等，同周不重复）
- mood 非法值 422（沿用 6 档）

**复用:** DiaryEntry 与 diary.py upsert 语义（抽取为共享函数，不复制逻辑）；`stardust.tier_for`（services/stardust.py）；签到星尘加法模式（api/tasks.py:125-126）；`build_today_guidance`（响应星光色）。

- [ ] **Step 1: 写失败测试**：新建记录 → mood/brightness/star_color 正确；同日再次提交 → 更新而非新建（无重复行）；mood 非法 → 422；造 7 天连续记录（含今天）→ 第 7 天 reward=true 且 stardust_total+1、star_tier 同步；同周第 8 天记录 → 不再奖励（reward=false）；造 6 天 → 不奖励；既有 diary.py 的 entries 测试全绿（抽取无回归）
- [ ] **Step 2: 跑测试确认失败**：`cd backend && ./venv/bin/python -m pytest tests/test_journal.py tests/test_diary_review.py -v` → FAIL
- [ ] **Step 3: 实现**：diary_entries.py 抽取 + diary.py 改造 + User 字段 + 迁移 + journal 端点
- [ ] **Step 4: 全量回归 + commit**：`./venv/bin/python -m pytest -q` 全绿；`git commit -m "feat: 手账记录+连续7天星尘奖励幂等 (T1-3)"`

**验收:** 奖励幂等（同周不重复）；抽取后 diary 全量测试无回归；奖励阈值 7 天边界有测试。

### Task 4（设计 T1-4）: 手账页（月历+五档点星+星点详情）+ 旧日记页跳转

**Files:**
- Create: `miniapp/components/calendar/calendar.js/json/wxml/wxss`（共用月历组件：月网格、今天高亮环、左右滑切月、标记点/星点插槽——阶段 2 日历复用）
- Create: `miniapp/pages/journal/journal.js/json/wxml/wxss`（手账主界面：顶部"今晚，记一颗星"五档一屏点选 + 月历 + 星点详情展开）
- Modify: `miniapp/pages/diary/diary.js`（onShow 跳转 `wx.redirectTo('/pages/journal/journal')`，旧路径保留兼容；原列表/删除/图片上传能力保留在手账详情展开中，复用现有接口）
- Modify: `miniapp/pages/index/index.wxml/js/wxss`（foot-entry 区新增「星光手账」入口，与"记录今天"合并指向 journal）
- Modify: `miniapp/pages/profile/profile.js/wxml`（若有指向 diary 的"情感日记/星光树洞"入口则改指 journal）
- Modify: `miniapp/app.json`（注册 subPackage `pages/journal/`；index preloadRule 加 `pages/journal/`）

**Interfaces:**
- Consumes: `GET /journal/calendar?year=&month=`（Task 1）、`POST /journal/entries`（Task 3）、`GET /diary/entries`、`PUT /diary/entries/{id}`、`DELETE /diary/entries/{id}`、`POST /diary/reflection-prompt`、`POST /diary/upload-image`（详情展开复用）
- 交互要点（设计 1.2）：点星 3 秒完成；成功 toast「今晚的星，已挂上夜空 ✦」；未记录日极淡星尘点（"留一颗星的位子"）；空月引导「夜空从不催促，星会等你」；星点颜色 = 当日星光色、光晕大小 = 亮度档；详情展开可改情绪档（"让这一天更亮一点"）+ 可选文字；暗星不禁忌文案「隐没的星，也是夜空的居民。它只是需要一点时间，再亮起来。」

**复用:** `maybePromptSubscribe` 不涉及；`utils/api.js request()`；E3 token（styles/common.wxss）；diary 既有接口（详情展开复用，不新建）。

- [ ] **Step 1: 前端实现**：calendar 组件 → journal 页（月历数据渲染、五档点星、详情展开）
- [ ] **Step 2: diary.js 跳转 + index/profile 入口改造**：旧 diary 路径 redirectTo journal
- [ ] **Step 3: 模拟器验证**：`node /home/a/bin/mcp-wechatide.js simulator_screenshot '{"project":"E:\\tarot-miniapp\\miniapp"}'` 遍历：点星→月历亮星→toast；切月；详情展开；旧 diary 页跳转；index 入口可达
- [ ] **Step 4: commit**：`git commit -m "feat: 星光手账页+共用月历组件+旧日记跳转 (T1-4)"`

**验收:** 模拟器截图确认五档星点渲染、空态文案、旧路径跳转无 404。

### Task 5（设计 T1-5）: 月度复盘页 + 手账海报 + 复盘入口

**Files:**
- Create: `miniapp/pages/journal-review/journal-review.js/json/wxml/wxss`（情绪曲线 + 亮暗星统计 + AI 温柔总结 + 星光色带"本月星空色带"；保存/分享海报）
- Create: `miniapp/utils/journal-poster.js`（require canvas-poster 的调色板常量与绘制辅助；版式：夜空标题 + 点亮天数/亮暗比例 + 色带 + AI 摘要 + 小程序码 + 「仅供娱乐 · 星光映照」）
- Modify: `miniapp/pages/journal/journal.wxml/js`（月历顶部"本月星光回顾"卡 → journal-review）
- Modify: `miniapp/app.json`（注册 subPackage `pages/journal-review/`）

**Interfaces:**
- Consumes: `GET /journal/review?month=`（Task 2）、`GET /journal/review/share-preview?month=`、`GET /share/wxacode`（海报小程序码 scene=invite_code → card-landing）、`POST /share/track`（share_type="journal"）
- 复盘叙事（设计 1.4）：开场"你的八月，是一整片被点亮的夜空——21 颗星里，15 颗亮着，3 颗正在休息。"式文案由后端 AI/降级模板给出，前端只渲染

**复用:** `canvas-poster.js`（调色板/圆角/码位绘制管线，utils/canvas-poster.js）；`/share/wxacode`（share.py:220 星名片码，scene=invite_code，不新增微信调用）；share-poster 组件版式（components/share-poster/）。

- [ ] **Step 1: 前端实现**：journal-review 页 + journal-poster.js + 复盘入口
- [ ] **Step 2: 模拟器验证**：复盘页渲染；海报生成无 404、小程序码可拉取（`simulator_screenshot` 遍历）
- [ ] **Step 3: commit**：`git commit -m "feat: 月度复盘页+手账海报 (T1-5)"`

**验收:** 海报可保存/分享，底部「仅供娱乐 · 星光映照」，码为名片码（scene=invite_code）。

### Task 6（设计 T4-1）: subscribe_quotas.slot_preference 迁移 + /notify/preference

**Files:**
- Modify: `backend/app/models/subscribe_quota.py`（加 `slot_preference: Mapped[str] = mapped_column(String(16), default="morning", server_default="morning", nullable=False)`）
- Create: `backend/alembic/versions/33cc44dd55ee_add_subscribe_quota_slot_preference.py`
- Modify: `backend/app/api/notify.py`（新增 preference 端点）
- Test: `backend/tests/test_subscribe.py`（追加）

**Interfaces:**
- Consumes: `SubscribeQuota`（models/subscribe_quota.py）、`get_current_user`
- Produces:
  - `POST /notify/preference {slot: "morning"|"night"}`（鉴权）→ `{ok: true, slot_preference}`；非法值 400；无行则 upsert（quota_available=0 也建行，仅记偏好）
  - `GET /notify/preference`（鉴权，设置页回显用）→ `{slot_preference}`（无行默认 "morning"）

**复用:** SubscribeQuota 模型（P0 晨讯额度表）；get_current_user。

- [ ] **Step 1: 写失败测试**：默认 morning（GET）；POST night → 持久化且 GET 回显 night；非法 slot → 400；未登录 → 401
- [ ] **Step 2: 跑测试确认失败**：`cd backend && ./venv/bin/python -m pytest tests/test_subscribe.py -v` → FAIL
- [ ] **Step 3: 实现**：模型列 + 迁移（`alembic revision --autogenerate -m "add slot_preference"` + 核对 + `upgrade head`）+ notify.py 两端点
- [ ] **Step 4: 全量回归 + commit**：`./venv/bin/python -m pytest -q` 全绿；`git commit -m "feat: 推送槽位偏好 morning/night (T4-1)"`

**验收:** 迁移只加一列带默认值；preference 读写闭环；现有 subscribe-grant 测试无回归。

### Task 7（设计 T4-2）: 星语短句库 + 确定性选择器 + AI 生成 + 同日缓存 + /moon-card/today

**Files:**
- Create: `backend/app/services/star_words.py`（短句库 + 选择器 + AI 生成 + 缓存读写 + 模板组装）
- Create: `backend/app/models/star_word_daily.py`（user_id CHAR(36)、word_date Date、data TEXT、source String(8)、created_at，UNIQUE uq_user_word_date(user_id, word_date)）
- Create: `backend/alembic/versions/44dd55ee66ff_add_star_word_daily.py`
- Create: `backend/app/api/moon_card.py`（router = APIRouter(prefix="/moon-card", tags=["睡前星语"])）
- Test: `backend/tests/test_star_words.py`

**Interfaces:**
- Consumes: `build_today_guidance`（星光色/数）、当日能量（`daily_push._today_energy` 同款：HoroscopeHistory 优先 → compute_energy 轻量）、当日 mood（DiaryEntry 今日记录，若存在）、`_OUTPUT_RED_LINE`（ai_engine.py）、DeepSeek client（diary.py `_get_ai_client` 模式）、`moon_phase_on`（services/moon.py）、`daily_push._truncate_str`
- Produces:
  - `STAR_WORD_POOLS: dict[str, list[str]]` = {love, career, social, health} 共 ≥50 条（每池 ≥12），全部治愈系开放积极向、≤20 字、无预测/无评断（如"把今天的疲惫，交给月亮收好。"）
  - `def select_fallback_phrase(date_seed: int, user_seed: int, top_dim: str) -> str`（确定性：`pool[top_dim][(date_seed + user_seed) % len(pool)]`）
  - `async def generate_star_word_ai(db, user, today, energy, today_mood) -> str | None`（≤20 字，system 含 `_OUTPUT_RED_LINE`，结合当日星光/能量维度/心情；失败或无 key → None）
  - `async def get_today_star_word(db, user, today) -> dict` → `{phrase, source: "ai"|"fallback"}`（缓存命中即返；否则 AI → 失败降级 fallback → 写缓存）
  - `def build_star_word_data(today, guidance, energy, phrase) -> dict[str, dict[str, str]]`（thing1=星语≤20 字、thing2="星光数 X · 星光色"、date3=日期、thing4="点击收下你的月光卡 ✦"）
  - `GET /moon-card/today`（鉴权）→ `{date, phase: {emoji, label}, phrase, star_color, star_number, source}`（确定性：同日同人恒定，靠缓存 + 确定性选择双重保证）

**复用:** `build_today_guidance`（星光色/数）；`moon_phase_on`（moon.py:90，六态 emoji/label）；`_OUTPUT_RED_LINE`；`_today_energy` 取数路径（daily_push.py:243）；DeepSeek client 封装模式；wish 祝福模板文风（wishes.py `_WISH_BLESS_TEMPLATES` 风格）。

- [ ] **Step 1: 写失败测试**：池共 ≥50 条且每池 ≥12；每条 ≤20 字；黑名单词扫描（预测/注定/明天一定会/命）；确定性（同 date+user 同句）；不同 date 至少存在不同句（抽样断言非全同）；AI 抛异常 → source=fallback 且短语来自短句库；AI 成功 → source=ai；第二次调用命中缓存（AI 只调 1 次）；/moon-card/today 字段完整且 phase 与 moon_phase_on 一致
- [ ] **Step 2: 跑测试确认失败**：`cd backend && ./venv/bin/python -m pytest tests/test_star_words.py -v` → FAIL
- [ ] **Step 3: 实现**：模型+迁移 + star_words.py + moon_card.py
- [ ] **Step 4: 全量回归 + commit**：`./venv/bin/python -m pytest -q` 全绿；`git commit -m "feat: 星语短句库+AI生成+同日缓存+moon-card数据 (T4-2)"`

**验收:** 降级路径被测试钉住；短句库合规与字数测试全过；同日缓存生效。

### Task 8（设计 T4-3）: 21:00 槽位改造为额度制星语 + 阶段 1 发布

**Files:**
- Modify: `backend/app/services/daily_push.py`（send_daily_push_if_due 重写；send_starlight_morning_if_due 加偏好过滤）
- Test: `backend/tests/test_daily_push.py`（追加）

**Interfaces:**
- Consumes: `SubscribeQuota.slot_preference`（Task 6）、`get_today_star_word/build_star_word_data`（Task 7）、`get_moon_push_event/build_moon_push_data`（daily_push.py:163/193）、`send_subscribe_message/resolve_template_id/is_template_configured`（services/push.py）、晨讯原子认领/失败退避模式（`_release_morning_claim`/`_MORNING_MAX_ATTEMPTS`）
- Produces:
  - `send_starlight_morning_if_due`：扫描条件加 `slot_preference == "morning"`（7:37 只发晨星用户；其余机制不动）
  - `send_daily_push_if_due` 改造：扫描 `quota_available > 0 AND slot_preference == "night" AND (last_sent_date IS NULL OR != today)` join User；原子认领（复用晨讯同款 `UPDATE ... SET last_sent_date=:today` rowcount==1）→ 内容 = 星语（`get_today_star_word` 写缓存 → `build_star_word_data`）→ `send_subscribe_message(openid, template_id, data, page="pages/moon-card/moon-card")` → 成功 quota-1 同事务 commit；失败认领回退 + 星语槽位独立当日失败计数（同 `_MORNING_MAX_ATTEMPTS=3` 语义，新内存 dict `_night_fail_counts`）
  - 月相事件优先保留：`get_moon_push_event(today)` 命中（新月前 1 天/满月当天）→ 该日 21:00 向**全部**有额度未发用户发节点版（`build_moon_push_data` + 对应 page），不发星语；节点召回不因槽位偏好丢失
  - 存量兼容：`PushSubscription`（TEMPLATE_DAILY_CARD）不再作为 21:00 发送依据，仅作设置页"推送开关"展示数据源；未授权新额度的老用户晚间不再推送（发布说明告知）

**复用:** 晨讯原子认领 + 逐条 commit + 失败退避全套（daily_push.py:270-427）；`send_subscribe_message`（push.py:103）；`get_moon_push_event`；`build_moon_push_data`；`_truncate_str`。

- [ ] **Step 1: 写失败测试**（追加 test_daily_push.py）：night 用户 21:00 收到星语且 quota-1、last_sent_date=今天；morning 用户 21:00 跳过；7:37 晨讯只发 morning（night 用户跳过）；同日双槽位最多 1 条（先发晨讯 → 21:00 认领 rowcount=0 跳过）；满月当天 21:00 → 节点内容优先（发全部有额度用户）；无额度 → 不发；星语 AI 失败 → 发送 fallback 短语且缓存 source=fallback；当日发送失败 3 次后不再尝试该用户；模板未配置 → skipped_config
- [ ] **Step 2: 跑测试确认失败**：`cd backend && ./venv/bin/python -m pytest tests/test_daily_push.py -v` → FAIL
- [ ] **Step 3: 实现**：daily_push.py 两槽位改造
- [ ] **Step 4: 全量回归 + commit**：`./venv/bin/python -m pytest -q` 全绿；`git commit -m "feat: 21:00星语额度制+偏好过滤+月相优先 (T4-3)"`
- [ ] **Step 5: 阶段 1 发布**：
  - 推送落地配套：创建 `miniapp/pages/moon-card/moon-card.js/json/wxml/wxss` **最小可用版**（渲染 `GET /moon-card/today`：月相+星语+星光色+日期，无海报）并注册 subPackage，避免 21:00 星语推送点击落空；完整版（海报/分享/沉淀）由阶段 2 Task 15 完成
  - 后端部署：`rsync -avz -e "sshpass -p 'Asdfghjkl123!!' ssh -o StrictHostKeyChecking=no" --exclude="__pycache__" --exclude="*.pyc" --exclude=".env" --exclude="venv" --exclude="data" --exclude="certs" app/ root@124.221.233.214:/opt/tarot/backend/app/`；服务器 `/opt/tarot/backend` 下 `alembic upgrade head`（3 个迁移：star_monthly_reviews/journal_streak_reward_week/slot_preference/star_word_daily，按实际执行）；`systemctl restart tarot-api`；curl 健康检查
  - 上传体验版：`node /home/a/bin/mcp-wechatide.js upload '{"project":"E:\\tarot-miniapp\\miniapp","upload-version":"v2.3.0","upload-desc":"P1阶段1: 星光手账+月度复盘+星语后端"}'`

**验收:** 双槽位共享每日 1 条（并发交错有原子认领测试）；星语降级路径端到端生效；阶段 1 发布后手账可用、推送点击不落空。

---

# 阶段 2：星空时刻表+节点活动 + 星语前端（7 任务）

交付物：日历+节点上线；星语完整（月光卡+晚安卡海报+二选一引导）。发布：部署 + 上传体验版（v2.4.0）。

### Task 9（设计 T3-1）: /astral/calendar + /astral/events/{date} + /astral/event/{type}

**Files:**
- Create: `backend/app/services/astral_calendar.py`（纯函数：月视图/日详情/下一节点/节点内容）
- Create: `backend/app/api/astral.py`（router = APIRouter(prefix="/astral", tags=["星空时刻表"])）
- Create: `backend/app/schemas/astral.py`
- Test: `backend/tests/test_astral.py`

**Interfaces:**
- Consumes: `ASTRAL_EVENTS_2026`（energy_engine.py:214，~50 条+逆行区间）、`astral_events_on(target: date)`（energy_engine.py:295）、`moon_phase_on(d)`（services/moon.py:90）、`ASTRAL_TYPE_NOTES`、`GUIDANCE_BY_EVENT`、`ASTRAL_TYPE_PRIORITY`、`ASTRAL_TYPE_FACTOR_NAME`、`Wish`（models/wish.py，状态计数）
- Produces（全部为纯函数，日期参数化，便于测试）：
  - `def month_view(year: int, month: int) -> dict` → `{days: [{date, phase: {phase, emoji, label}, events: [{type, label, moon_sign}], is_retrograde_range: bool}], next_event: {type, label, date, days_until} | null}`；区间事件（水逆 2026-01-14~02-04）展开到每一天；每日本来就有月相小字（无事件日也有 phase）；next_event = 从 today 起首个事件 start > today（或今天当天的首个），days_until 纯函数计算
  - `def day_detail(target: date) -> dict` → `{date, events: [{type, label, note}], guidance: {do, dont}, activity: "wish"|"review"|"mercury_guide"|"info"}`；note 复用 ASTRAL_TYPE_NOTES、guidance 复用 GUIDANCE_BY_EVENT；activity 由同日优先级最高事件决定（复用 ASTRAL_TYPE_PRIORITY）：new_moon→wish、full_moon→review、mercury_retrograde→mercury_guide、其余→info
  - `def node_content(node_type: str, today: date, wish_counts: dict | None = None) -> dict`：
    - wish → `{type: "wish", title: "许愿之夜", window: {start, end, days_left}, content: "写给月亮的三行愿望", target_page: "pages/wish/wish"}`（窗口 = 最近新月日 00:00 至其后 2 天，days_left 从今天倒计）
    - review → `{type: "review", title: "复盘之夜", wish_counts: {active, grown, answered}, target_page: "pages/review/review"}`
    - mercury_guide → `{type: "mercury_guide", title: "慢行期", range: {start, end, days_left}, items: ["慢下来的 7 件小事"固定清单 ≥7 条], daily_sentence: 确定性轮换（date_seed % 池长）}`
    - info → `{type: "info", notes: [...]}`
  - API 薄封装（鉴权）：`GET /astral/calendar?year=&month=`、`GET /astral/events/{date}`、`GET /astral/event/{type}`（wish/review 的 wish_counts 部分接 db）

**复用:** ASTRAL_EVENTS_2026 + astral_events_on（数据源零新增）；moon_phase_on（月相小字）；ASTRAL_TYPE_NOTES/GUIDANCE_BY_EVENT/ASTRAL_TYPE_PRIORITY（事件卡内容）；Wish 状态计数（wishes.py 状态语义 active/grown/answered）。

- [ ] **Step 1: 写失败测试**：区间展开（2026-01-14~02-04 每一天 events 含 mercury_retrograde）；同日多事件（2026-08-12 狮子座新月+日全食 → events 两条且按 ASTRAL_TYPE_PRIORITY 排序，activity=info 由最高优先级 solar_eclipse 决定——确定性钉住）；无事件日 phase 字段非空且 activity=info；next_event 倒计时正确（参数化 today）；2027 年（表中无事件）→ days 全空 events、不崩溃；node_content 三形态字段完整；7 件小事清单 ≥7 条且无黑名单词；daily_sentence 同日同人恒定；wish window days_left 边界；未登录 401
- [ ] **Step 2: 跑测试确认失败**：`cd backend && ./venv/bin/python -m pytest tests/test_astral.py -v` → FAIL
- [ ] **Step 3: 实现**：astral_calendar.py + api/astral.py + schemas
- [ ] **Step 4: 全量回归 + commit**：`./venv/bin/python -m pytest -q` 全绿；`git commit -m "feat: 星空时刻表日历/事件/节点内容 (T3-1)"`

**验收:** 区间展开与同日优先级有确定性测试；2027 空表不崩溃；节点内容三形态可测。

### Task 10（设计 T3-2）: 晨讯节点主题切换（三态）

**Files:**
- Modify: `backend/app/services/daily_push.py`（send_starlight_morning_if_due 内容构建前插入节点判断）
- Test: `backend/tests/test_daily_push.py`（追加）

**Interfaces:**
- Consumes: `astral_events_on(today)`、`build_moon_push_data` 结构、`_truncate_str`
- Produces: `def _astral_morning_event(today: date) -> dict | None`：`astral_events_on(today)` 含 new_moon → 新月版（thing1「今日新月 · 许愿之夜」≤20 字、page=`pages/wish/wish`）；含 full_moon → 满月版（「满月之夜 · 来复盘你的愿望」、page=`pages/review/review`）；含 mercury_retrograde 且 `ev["start"] == today`（水逆首日）→ 水逆版（「水逆开始 · 7 件慢下来的小事」、page=`pages/astral-event/astral-event?type=mercury_retrograde`）；其余 → None（常规晨讯不变）。额度/认领/防疲劳机制不动

**复用:** `astral_events_on`（同源判断）；`build_moon_push_data` 字段结构（daily_push.py:193）；晨讯全链路（额度/认领/退避不动）。

- [ ] **Step 1: 写失败测试**：新月日（2026-01-03）→ 新月版且 page=wish；满月日（2026-01-11）→ 满月版；水逆首日（2026-01-14）→ 水逆版；水逆中段（2026-01-20）→ 常规版（不额外打扰）；常规日（2026-01-05）→ 常规版；全部 thing 字段 ≤20 字；现有晨讯测试回归（内容默认分支不变）
- [ ] **Step 2: 跑测试确认失败**：`cd backend && ./venv/bin/python -m pytest tests/test_daily_push.py -v` → FAIL
- [ ] **Step 3: 实现**：daily_push.py 插入三态判断
- [ ] **Step 4: 全量回归 + commit**：`./venv/bin/python -m pytest -q` 全绿；`git commit -m "feat: 晨讯节点主题三态切换 (T3-2)"`

**验收:** 三态内容/跳转有测试；中段不推送（防疲劳纪律不破）。

### Task 11（设计 T3-3）: astral_activity_logs + 打卡星尘奖励（幂等）

**Files:**
- Create: `backend/app/models/astral_activity_log.py`（id CHAR(36) PK、user_id CHAR(36) INDEX、event_key VARCHAR(32)、event_date Date、created_at，UNIQUE uq_user_event_date(user_id, event_key, event_date)）
- Create: `backend/alembic/versions/55ee66ff77aa_add_astral_activity_logs.py`
- Modify: `backend/app/api/astral.py`
- Test: `backend/tests/test_astral.py`（追加）

**Interfaces:**
- Consumes: `stardust.tier_for`、tasks.py 签到星尘模式（api/tasks.py:125-126）
- Produces:
  - `POST /astral/activity {event_key: "wish"|"review"|"mercury_guide"}`（鉴权）→ `{ok: true, rewarded: bool, stardust_total}`；event_date = 今天；首次 → `stardust_total += 1; star_tier = tier_for(...)`；重复（唯一约束冲突）→ rewarded=false 不重复加
  - `GET /astral/activity/summary?month=2026-08`（鉴权，我的页星阶区用）→ `{month, completed: n, keys: ["wish", ...]}`

**复用:** 签到星尘加法与 tier 同步（tasks.py checkin）；唯一约束幂等模式（checkin 的 uq_user_checkin_date 同款）。

- [ ] **Step 1: 写失败测试**：首次打卡 +1 且 star_tier 同步；同日同 event_key 重复 → rewarded=false 不加；同日不同 key（wish+mercury_guide）→ 各 +1；非法 key → 400；未登录 → 401；summary 计数正确
- [ ] **Step 2: 跑测试确认失败**：`cd backend && ./venv/bin/python -m pytest tests/test_astral.py -v` → FAIL
- [ ] **Step 3: 实现**：模型+迁移 + 两端点
- [ ] **Step 4: 全量回归 + commit**：`./venv/bin/python -m pytest -q` 全绿；`git commit -m "feat: 节点打卡星尘奖励幂等 (T3-3)"`

**验收:** 打卡幂等（唯一约束）；星尘第三来源落地。

### Task 12（设计 T3-4）: 星空时刻表页（月历+事件列表双视图）

**Files:**
- Modify: `miniapp/components/calendar/calendar.js/json/wxml/wxss`（增加事件标记模式：`markers` 配置 prop，事件日渲染符号徽标；月相小字插槽）
- Create: `miniapp/pages/astral-calendar/astral-calendar.js/json/wxml/wxss`（月历视图 + "事件列表"视图切换 + 顶部"下一节点倒计时"）
- Modify: `miniapp/app.json`（注册 subPackage `pages/astral-calendar/`；index preloadRule 加该包）
- Modify: `miniapp/pages/index/index.wxml/js`（今日星光卡内"今日天象"链接 + foot-entry「星空时刻表」入口）

**Interfaces:**
- Consumes: `GET /astral/calendar?year=&month=`、`GET /astral/events/{date}`（Task 9）
- 交互要点（设计 3.2）：事件日符号徽标（新月🌑/满月🌕/水逆☿/日月食/节气）；无事件日显示月相小字；今天高亮环；列表视图显示区间事件起止；倒计时如"3 天后 · 狮子座新月"；空态「星空从不缺席，只是有时安静。」

**复用:** calendar 组件（Task 4 建的共用组件，同一月历视觉语言）；moon 月相 emoji。

- [ ] **Step 1: 前端实现**：calendar 组件标记模式 → astral-calendar 页（双视图+倒计时）→ 首页入口
- [ ] **Step 2: 模拟器验证**：月历标记渲染、列表视图、倒计时文案（`simulator_screenshot`）
- [ ] **Step 3: commit**：`git commit -m "feat: 星空时刻表页 (T3-4)"`

**验收:** 双视图可用；事件日符号与月相小字渲染正确；与手账共用同一月历组件。

### Task 13（设计 T3-5）: 节点活动页三形态

**Files:**
- Create: `miniapp/pages/astral-event/astral-event.js/json/wxml/wxss`
- Modify: `miniapp/app.json`（注册 subPackage `pages/astral-event/`）
- Modify: `miniapp/pages/astral-calendar/astral-calendar.js`（点击事件日 → astral-event?type=xxx）

**Interfaces:**
- Consumes: `GET /astral/event/{type}`（Task 9）、`POST /astral/activity`（Task 11）；跳转复用现有 `pages/wish/wish`、`pages/review/review`
- 三形态（设计 3.2）：wish → 新月窗口倒计时 + 许愿引导卡 → 跳 wish 页；review → 愿望状态总览预览（active/grown/answered 计数）→ 跳 review 页；mercury_retrograde → 区间倒计时 + "慢下来的 7 件小事"清单（勾选打卡，每完成一项点亮一颗星）+ 每日一句 + 全部点亮 → `POST /astral/activity {event_key: "mercury_guide"}` → toast 星尘奖励；合规：水逆只谈自我关怀（"这段日子，允许自己慢一点"），禁"化解/转运/防小人/避开"

**复用:** wish/review 现有页面（节点页只做引导不重做流程）；Task 11 打卡接口。

- [ ] **Step 1: 前端实现**：astral-event 页三形态
- [ ] **Step 2: 模拟器验证**：wish/review 引导跳转；水逆清单勾选点亮+打卡 toast+星尘（`simulator_screenshot` 遍历）
- [ ] **Step 3: commit**：`git commit -m "feat: 节点活动页三形态+水逆打卡 (T3-5)"`

**验收:** 三形态可达；水逆清单打卡幂等（toast 不重复）；文案合规。

### Task 14（设计 T4-4）: 订阅引导二选一 + 推送设置页切换

**Files:**
- Modify: `miniapp/utils/subscribe.js`（maybePromptSubscribe 升级：二选一）
- Modify: `miniapp/pages/profile/profile.js/wxml/wxss`（推送设置区：两枚星光按钮高亮所选）
- Modify: `miniapp/utils/config.js`（文案常量可加，模板 ID 不变）

**Interfaces:**
- Consumes: `POST /notify/subscribe-grant`（notify.py:124）、`POST /notify/preference` + `GET /notify/preference`（Task 6）
- maybePromptSubscribe 升级：弹窗从"订阅/暂不"改为二选一「星光时刻：清晨 7:37（晨星）/ 夜晚 21:00（晚星）」→ 用户选晨星 → grant + `POST /notify/preference {slot: "morning"}`；选晚星 → grant + `{slot: "night"}`；拒绝不重弹、同会话 1 次、grant 成功后才置持久标记等原约束全部保留
- 设置页：`GET /notify/preference` 回显高亮；切换 → `POST /notify/preference`；解释行"每天只来一条星光——选择星光降临的时刻"；切换 toast「明天起，星光在夜晚 21:00 等你 ✦」（次日生效语义）

**复用:** `maybePromptSubscribe` 全部幂等/时序约束（subscribe.js:89 起，仅改造弹窗内容与 preference 上报）；`_reportGrant` 时序契约（F-1 修复模式）。

- [ ] **Step 1: 前端实现**：subscribe.js 二选一 + profile 设置区
- [ ] **Step 2: 模拟器验证**：触发弹窗二选一 → 选择 → grant+preference 请求成功；设置页回显与切换（console 无 error）
- [ ] **Step 3: commit**：`git commit -m "feat: 订阅引导二选一+推送设置页 (T4-4)"`

**验收:** 二选一链路端到端（后端测试已在 Task 6 覆盖）；设置页切换次日生效提示可见。

### Task 15（设计 T4-5）: 月光卡完整版 + 晚安卡海报 + 阶段 2 发布

**Files:**
- Modify: `miniapp/pages/moon-card/moon-card.js/json/wxml/wxss`（在阶段 1 最小版基础上补完整版）
- Create: `miniapp/utils/moon-card-poster.js`（深空底 + 当夜月相 + 星语 + 日期 + 星光色描边 + 小程序码 + 「仅供娱乐 · 星光映照」；晚安版星光名片）
- Modify: `miniapp/app.json`（无新增注册，moon-card 已在阶段 1 注册）

**Interfaces:**
- Consumes: `GET /moon-card/today`（Task 7）、`GET /share/wxacode`（海报码 scene=invite_code → card-landing，复用名片码不新增微信调用）、`POST /share/track`
- 沉淀（设计 4.1）：月光卡文案结尾引导"睡前三分钟，给今天记一颗星" → 跳 `pages/journal/journal`；分享月光卡 = 拉新入口（小程序码）
- 版式：E3 名片同系（components/share-poster/ 版式参考）；页面含"晚安。月亮替你把今天收尾，星光陪你入睡 ✦"

**复用:** canvas-poster 绘制管线（调色板/圆角/码位）；`/share/wxacode` 名片码（share.py:220，scene=invite_code）；share-poster 组件版式。

- [ ] **Step 1: 前端实现**：moon-card 完整版 + moon-card-poster.js
- [ ] **Step 2: 模拟器验证**：页面渲染（月相+星语+星光色）、海报生成无 404、跳手账链路（`simulator_screenshot`）
- [ ] **Step 3: 阶段 2 发布**：后端 rsync（同 Task 8 命令）→ 服务器 `alembic upgrade head`（新增 astral_activity_logs 迁移）→ `systemctl restart tarot-api` → curl 健康检查；上传体验版 v2.4.0（desc "P1阶段2: 星空时刻表+节点活动+月光卡+二选一"）
- [ ] **Step 4: commit**：`git commit -m "feat: 月光卡完整版+晚安卡海报 (T4-5)"`

**验收:** 月光卡可保存/分享；海报带名片码；跳手账沉淀链路通；阶段 2 发布后日历/节点/星语全可用。

---

# 阶段 3：星辰相遇 + 全体系串联（8 任务）

交付物：合盘上线 + 四功能串联验证。发布：部署 + 发布说明（v2.5.0）。

### Task 16（设计 T2-1）: 12×12 星座兼容表 + 三要素加权算法

**Files:**
- Create: `backend/app/services/compatibility.py`
- Test: `backend/tests/test_compatibility.py`

**Interfaces:**
- Consumes: `birthchart.ZODIAC_KEYS`（services/birthchart.py:35，12 key 权威枚举）
- Produces:
  - `ZODIAC_ELEMENTS: dict[str, str]`（fire/earth/air/water 四组）、`ZODIAC_MODES: dict[str, str]`（cardinal/fixed/mutable）
  - `COMPAT_TABLE: dict[tuple[str, str], int]`（12×12 对称常量，人工定稿：同元素 85-95 分、互补元素（火风/土水）75-85 分、其余固定表 55-75 分；同模式 ±3 微调；同 STAR_COLORS 的治理方式：常量配置化可运营调整）
  - `WEIGHTS: dict[str, float] = {"sun": 0.5, "moon": 0.3, "rising": 0.2}`
  - `def level_name(score: int) -> str`：85+ 星光共鸣 / 70-84 星光相映 / 55-69 星光相伴 / <55 星光初见
  - `def compute_compatibility(*, a_sun, b_sun, a_moon=None, b_moon=None, a_rising=None, b_rising=None) -> dict` → `{score: int, level_name: str, factors: [{role: "sun"|"moon"|"rising", score: int, reason: str}], used: [roles], estimated: bool, estimate_note: str}`；缺要素权重重归一化（仅太阳 → 100% 太阳；无上升 → 太阳 62.5% + 月亮 37.5%）；reason 形如"同元素·火象相映 +8"（每分有解释）

**复用:** birthchart.ZODIAC_KEYS/NAMES；能量引擎"分数原因可见"哲学（energy_engine factors 链）；STAR_COLORS 常量治理方式（同 STAR_GUIDANCE_LIBRARY 校验模式）。

- [ ] **Step 1: 写失败测试**：确定性（同输入两次 → 同 score）；仅太阳 → used=["sun"] 且 score == 太阳分数（100% 权重）；无上升 → 权重 62.5/37.5 重归一化；档位边界（85/84、70/69、55/54）；每 factor 有非空 reason 且含元素描述；表对称（compat(a,b)==compat(b,a)）；全部 144 组合分数在 55-95 区间；同元素组合 ≥85；互补组合 75-85
- [ ] **Step 2: 跑测试确认失败**：`cd backend && ./venv/bin/python -m pytest tests/test_compatibility.py -v` → FAIL
- [ ] **Step 3: 实现**：compatibility.py（元素/模式表 + COMPAT_TABLE 初稿由元素规则生成 + 人工抽查定稿 + 加权计算）
- [ ] **Step 4: 全量回归 + commit**：`./venv/bin/python -m pytest -q` 全绿；`git commit -m "feat: 合盘三要素加权算法+12x12兼容表 (T2-1)"`

**验收:** 确定性 + 重归一化 + 档位边界全部有测试；144 组合分数范围合法。

### Task 17（设计 T2-2）: star_meetings 表 + /meet/quick + /meet/{id} + /meet/list + /meet/{id}/poster

**Files:**
- Create: `backend/app/models/star_meeting.py`（字段严格按设计 2.4 SQL：id/initiator_id/friend_user_id/relation/a_zodiac/a_moon/a_rising/b_zodiac/b_moon/b_rising/status/result_json/created_at/updated_at）
- Create: `backend/alembic/versions/66ff77aa88bb_add_star_meetings.py`
- Create: `backend/app/api/meet.py`（router = APIRouter(prefix="/meet", tags=["星辰相遇"])）
- Create: `backend/app/schemas/meet.py`
- Test: `backend/tests/test_meet.py`

**Interfaces:**
- Consumes: `compute_compatibility`（Task 16）、`birthchart.compute_birthchart/birthchart.sun_sign/moon_sign/rising_sign`、`pick_daily_card`（确定性选牌哲学，daily_card.py:17）、`TarotCard`（meaning_upright 截取）、`User.zodiac/birth_date/birth_time/birth_city`
- Produces:
  - `POST /meet/quick {relation: "friend"|"love"|"family"|"work", zodiac_b, b_birth_date?, b_birth_time?}`（鉴权）→ 发起人三要素（users.zodiac + birthchart 派生）、b 三要素（b_birth_date → sun_sign/moon_sign，b_birth_time → rising_sign）→ 合盘 → 落库 status=completed + result_json → 返回完整结果：`{meet_id, relation, a: {zodiac, name_zh, sun/moon/rising}, b: {...}, score, level_name, factors, cards: [{position: "关系之牌"|"星光之牌"|"相处之牌", card_id, name_zh, meaning_snippet, tip}], tips: [str], estimated: bool, estimate_note}`
  - 合盘三牌（确定性）：`def pick_meet_cards(cards: list[TarotCard], seed_str: str) -> list[TarotCard]`（3 张去重；seed = f"{a 出生日期}|{b 出生日期}|{今天}"，同日同人恒定；与 pick_daily_card 同哲学）；关系之牌 = meaning_upright 截取+模板包装；星光之牌 = "对方眼中的你"；相处之牌 = 相处提示合规框架
  - 相处提示：`MEET_TIPS: list[str]` 模板库（≥10 条，开放积极向，全部合规；如"你们的星光节奏是慢热的——先并肩走一段，再慢慢看清彼此的方向。"）
  - `GET /meet/{meet_id}`（鉴权：initiator 或 friend_user_id）→ 完整结果（读 result_json）
  - `GET /meet/list`（鉴权）→ `{meetings: [{meet_id, relation, b_name, score, level_name, created_at}]}`（发起或参与）
  - `GET /meet/{meet_id}/poster`（鉴权）→ 脱敏海报数据（昵称/星座/score/level/cards 摘要/分享文案，无日记类原文）
- PII 最小化：落库只存派生星座 key（a_zodiac/a_moon/a_rising/b_zodiac/b_moon/b_rising），不存出生日期明文

**复用:** birthchart 三要素引擎（services/birthchart.py sun_sign:73 / moon_sign:142 / rising_sign:186）；pick_daily_card 确定性；`/share/zodiac-match` 作为快速版雏形保留兼容（api/share.py:307，不删）；TarotCard meaning_upright。

- [ ] **Step 1: 写失败测试**：quick 落库且返回字段完整；确定性（同输入两次 → 同 score/同 cards）；b 缺出生日期 → b.moon None + estimated=true；relation 非法 → 400；zodiac_b 非法 → 400；他人 GET /meet/{id} → 403/404（不能读别人结果）；list 只含本人发起或参与；pick_meet_cards 去重且确定性；poster 无敏感字段
- [ ] **Step 2: 跑测试确认失败**：`cd backend && ./venv/bin/python -m pytest tests/test_meet.py -v` → FAIL
- [ ] **Step 3: 实现**：模型+迁移 + compatibility 接线 + meet.py/schemas
- [ ] **Step 4: 全量回归 + commit**：`./venv/bin/python -m pytest -q` 全绿；`git commit -m "feat: 相遇记录表+快速合盘+结果详情 (T2-2)"`

**验收:** 快速版链路完整可测；确定性承诺（同日同人恒定）有测试；PII 最小化落库。

### Task 18（设计 T2-3）: 邀请/加入流程 + 公开落地接口 + 限流 + 邀请奖励接线

**Files:**
- Modify: `backend/app/api/meet.py`
- Modify: `backend/app/middleware/rate_limit.py`（新增 meet 公开接口限流）
- Test: `backend/tests/test_meet.py`（追加）

**Interfaces:**
- Consumes: `get_wxacode`（services/wxacode.py:59）、share.py 的 7 天有界缓存模式（`_WXACODE_CACHE_TTL/_prune/_evict`，share.py:43-57）、`card_info_rate_limit` 模式（rate_limit.py:155）、`process_invite`（services/share.py:129）、`get_or_create_invite_code`
- Produces:
  - `POST /meet/invite {meet_id}`（鉴权，仅发起人）→ status=pending → 返回 PNG（`get_wxacode(scene=f"m:{meet_id}", page="pages/meet-landing/meet-landing", width=430, env_version="trial")` + 按 meet_id 缓存 7 天，meet.py 内同款有界缓存）
  - `GET /meet/public/{meet_id}`（公开、挂 `meet_info_rate_limit` 30 次/分/IP，仿 card-info）→ 仅 `{meet_id, nickname, zodiac_cn, star_tier_name, status}`（脱敏：无联系方式/无出生信息/无 invite_code）
  - `POST /meet/join {meet_id, zodiac_b, b_birth_date?, b_birth_time?}`（需登录）→ 合盘计算、回填 b 三要素 + friend_user_id（若好友已登录注册）+ status=completed；若 initiator 有 invite_code 且为首次完成 → 调 `process_invite(db, inviter_code=initiator.invite_code, invitee_user=user)`（双方各 +1 免费解读，幂等：仅 pending→completed 首次触发）
- 限流依赖：`async def meet_info_rate_limit(request)`（RateLimiter(30, 60)，同 card_info_rate_limit 实现，key 前缀 `meet_info:`）

**复用:** `get_wxacode` + 7 天缓存/逐出模式（share.py）；`card_info_rate_limit` 实现复制为新依赖（rate_limit.py:152-164）；`process_invite` 邀请奖励（share.py:129）；`tier_name`（stardust.py）。

- [ ] **Step 1: 写失败测试**：invite 返回 image/png；invite 重复调用命中缓存（mock get_wxacode 计数 1 次）；public 只出 5 个脱敏字段（断言无 openid/invite_code/birth 相关键）；public 超限 → 429；join 后双方都能 GET /meet/{id}；已登录好友 join 触发 process_invite（双方 free_deep_readings +1）；重复 join/同人二次 → 不重复奖励（幂等）；未登录 join → 401；非法 meet_id → 404
- [ ] **Step 2: 跑测试确认失败**：`cd backend && ./venv/bin/python -m pytest tests/test_meet.py -v` → FAIL
- [ ] **Step 3: 实现**：rate_limit.py 新依赖 + meet.py 三端点 + 奖励接线
- [ ] **Step 4: 全量回归 + commit**：`./venv/bin/python -m pytest -q` 全绿；`git commit -m "feat: 相遇邀请/加入/公开接口/邀请奖励 (T2-3)"`

**验收:** 公开接口脱敏+限流；邀请奖励幂等；双方结果可见。

### Task 19（设计 T2-4）: 相遇页（输入 → 结果三屏）

**Files:**
- Create: `miniapp/pages/meet/meet.js/json/wxml/wxss`
- Modify: `miniapp/app.json`（注册 subPackage `pages/meet/`）
- Modify: `miniapp/pages/index/index.wxml/js`（foot-entry「星辰相遇」入口）、`miniapp/pages/profile/profile.js/wxml`（我的页入口）

**Interfaces:**
- Consumes: `POST /meet/quick`（Task 17）、`GET /meet/{meet_id}`、`GET /meet/list`、`POST /meet/invite`（Task 18）
- 交互要点（设计 2.2）：关系选择用 4 枚星光徽章（友/恋/亲/事）；星座 12 宫格（星座符号+元素底色）；可选出生日期/时间；结果页自上而下：双星徽章并置 → 共鸣度大圆环（百分值+档位名）→ 三要素分解卡（相容度条+一句话原因，可展开"为什么"）→ 三牌横排（牌图+牌名+一句）→ 相处提示卡 → 固定免责尾行「星辰只描述你们如何相处，不定义任何结局 · 仅供娱乐」
- 空态标注：「月亮落座未知，共鸣度按太阳星座估算」（estimated=true 时）；结果页分享文案「我和 TA 的星辰共鸣度是 92 · 看看你和谁星光相映 ✦」

**复用:** `utils/cards.js computeImagePath`（牌图路径）；`utils/energy.js`（星座元素底色可参考）；E3 token。

- [ ] **Step 1: 前端实现**：meet 页（输入表单 + 结果三屏 + 分享/邀请入口）
- [ ] **Step 2: 模拟器验证**：快速合盘走通（输入 → 结果渲染）、空态文案、邀请按钮触发码拉取
- [ ] **Step 3: commit**：`git commit -m "feat: 星辰相遇页+结果三屏 (T2-4)"`

**验收:** 输入即仪式交互可达；结果页结构自上而下完整；免责尾行常驻。

### Task 20（设计 T2-5）: meet-landing 落地页 + 合盘海报

**Files:**
- Create: `miniapp/pages/meet-landing/meet-landing.js/json/wxml/wxss`（scene 参数解析 m:{meet_id}）
- Create: `miniapp/utils/meet-poster.js`（双人徽章+共鸣度+三牌+小程序码+「仅供娱乐 · 星光映照」；复用 canvas-poster 调色板/绘制辅助；海报即拉新入口）
- Modify: `miniapp/app.json`（注册 subPackage `pages/meet-landing/`）

**Interfaces:**
- Consumes: `GET /meet/public/{meet_id}`（公开页：发起人昵称+星座+星阶，脱敏）、`POST /meet/join`（微信登录后）、`GET /meet/{meet_id}`、`GET /meet/{meet_id}/poster`（海报数据）、`POST /share/invite`（落地页登录注册场景兜底触发）
- 流程（设计 2.1 邀请版）：扫码 → meet-landing 公开页 → 好友填星座/出生 → 微信登录 → POST /meet/join → 跳结果页；结果页继续分享/接受方完成触发邀请奖励

**复用:** card-landing 落地页模式（pages/card-landing/，scene 解析/脱敏展示）；canvas-poster 管线；`/meet/public` + poster 数据。

- [ ] **Step 1: 前端实现**：meet-landing 页 + meet-poster.js
- [ ] **Step 2: 模拟器验证**：scene 解析（m:{id}）、公开页渲染、join 后跳转、海报生成无 404
- [ ] **Step 3: commit**：`git commit -m "feat: meet落地页+合盘海报 (T2-5)"`

**验收:** 邀请版 6 步闭环；海报带码即拉新；公开页无敏感信息。

### Task 21（设计 T2-6）: 合规：措辞黑白名单测试 + 海报内容安全检测

**Files:**
- Create: `backend/tests/test_meet_compliance.py`
- Modify: `backend/app/api/meet.py`（海报/分享文案拼接后调 msg_check）

**Interfaces:**
- Consumes: `msg_sec_check(content: str, openid: str | None) -> dict`（services/msg_check.py:70）、`MEET_TIPS`/`COMPAT_TABLE` reason 文案/档位名（Task 16）、`_OUTPUT_RED_LINE` 语义
- Produces:
  - `MEET_BLACKLIST: tuple[str, ...] = ("注定", "缘分", "天生一对", "该在一起", "分开", "克", "化解", "转运", "防小人", "必", "绝对")`
  - 合规测试（仿 `STAR_GUIDANCE_LIBRARY` 校验模式，energy_engine.py:345）：遍历相处提示库、档位名（星光共鸣/相映/相伴/初见）、三牌名、reason 文案、分享文案 → 断言不含黑名单词
  - meet.py：海报/分享文案拼接后调 `msg_sec_check` → 命中风险 → 替换为安全兜底文案 + 记日志；接口异常不阻塞（try/except 降级返回原文）

**复用:** `msg_sec_check`（msg_check.py）；STAR_GUIDANCE_LIBRARY 校验测试模式（test_p0_fixes.py / test_share_zodiac_match.py 同款）；`_OUTPUT_RED_LINE`（若后续 AI 文案启用）。

- [ ] **Step 1: 写失败测试**：全部相处提示模板/档位名/三牌名/reason/分享文案过黑名单扫描；任意黑名单词出现在文案时测试必失败（先放入一个已知违规词验证测试有效性再移除）；msg_check mock：命中 → 返回兜底文案；msg_check 抛异常 → 不阻塞返回原文
- [ ] **Step 2: 跑测试确认失败**：`cd backend && ./venv/bin/python -m pytest tests/test_meet_compliance.py -v` → FAIL
- [ ] **Step 3: 实现**：meet.py 接入 msg_check + 兜底；必要时修订文案库
- [ ] **Step 4: 全量回归 + commit**：`./venv/bin/python -m pytest -q` 全绿；`git commit -m "feat: 合盘合规黑白名单测试+内容安全 (T2-6)"`

**验收:** 措辞白名单测试全绿（三层防护第一层）；msg_check 已接入海报链路。

### Task 22（设计 T5-1）: 四功能串联验证（海报体系/星尘经济/推送偏好/入口统一）

**Files:**
- Modify: `miniapp/pages/index/index.wxml/js/wxss`（foot-entry 三入口齐备：星光手账/星辰相遇/星空时刻表；今日星光卡"今晚的星已点亮"角标——读 `GET /journal/calendar` 当月今日有记录时显示）
- Modify: `miniapp/pages/profile/profile.wxml/js/wxss`（星阶区展示：手账连续记录天数（calendar stats.current_streak）+ 本月节点完成数（`GET /astral/activity/summary`）+ 推送偏好回显（`GET /notify/preference`））
- Create: `backend/tests/test_p1_integration.py`（跨功能测试）

**Interfaces:**
- Consumes: 全量既有端点（journal/astral/meet/notify/share）
- 串联验证点（设计五）：
  1. 星尘经济闭环：签到 +1 / 手账连续 7 天 +1 / 节点打卡 +1 → stardust_total → tier_for 升级 → 名片星阶
  2. 推送体系闭环：槽位偏好 + 节点日晨讯三态 + 21:00 月相事件优先 → 任意组合下每日 ≤1 条
  3. 分享裂变闭环：四种海报 scene 区分（名片=invite_code、相遇=m:{meet_id}、月光卡=名片码、手账海报=名片码）
  4. 情感主线闭环：月光卡 → 跳手账 → 月度复盘有料
  5. 合规统一框架：所有新结果页/海报含「仅供娱乐 · 星光映照」

**复用:** 全部 P1 端点；stardust.tier_for；/share/wxacode。

- [ ] **Step 1: 写失败/集成测试**（test_p1_integration.py）：星尘三来源各自幂等且 star_tier 随 stardust_total 同步；night 用户全天只收 21:00 星语（7:37 不发）+ 月相事件日仍 ≤1 条；四海报 scene 断言（invite_code 码 vs m:{id} 码）；跨功能回归（手账记录 → 复盘有数据）
- [ ] **Step 2: 全量回归**：`cd backend && ./venv/bin/python -m pytest -q` 全绿（P0 基线 + P1 全部）
- [ ] **Step 3: 前端串联**：index foot-entry 三入口 + 角标微联动 + profile 星阶区三数据展示
- [ ] **Step 4: 模拟器遍历验证**：四功能入口逐一走通（`simulator_screenshot`），报告截图+console 无 error
- [ ] **Step 5: commit**：`git commit -m "feat: 四功能串联验证+入口统一 (T5-1)"`

**验收:** 后端全量测试全绿（含新集成测试）；模拟器四入口遍历通过；星尘三来源/推送每日 1 条/海报 scene 均有断言。

### Task 23（设计 T5-2）: 部署 + 发布说明 + 上传体验版（阶段 3 发布）

**Files:** 无代码改动（仅发布）

- [ ] **Step 1: 后端部署**：rsync（同 Task 8 命令）→ 服务器 `alembic upgrade head`（新增 star_meetings 迁移；累计 6 个 P1 迁移全部应用）→ `systemctl restart tarot-api` → curl 健康检查
- [ ] **Step 2: 上传体验版**：`node /home/a/bin/mcp-wechatide.js upload '{"project":"E:\\tarot-miniapp\\miniapp","upload-version":"v2.5.0","upload-desc":"P1阶段3: 星辰相遇+全体系串联"}'`
- [ ] **Step 3: 发布说明（随阶段 3 发布一并告知用户）**：
  - 21:00"今晚之牌"升级为额度制睡前星语：未重新授权用户晚间不再推送（微信一次性订阅固有机制，无法自动续）；设置页引导重新授权一次
  - 晨讯/星语二选一：默认晨讯 7:37；切换后次日生效
  - 手账与情感日记合并：原日记页跳转手账，数据不迁移仅视图升级
- [ ] **Step 4: 验证报告**：改动清单 + 测试结果（全量绿）+ 迁移核对 + 真机验证点清单（订阅引导、手账点星、合盘分享、节点打卡）

**验收:** 服务器迁移全部应用；三阶段全部功能线上可用；发布说明覆盖存量行为变化。

---

## Self-Review 记录

- **Spec 覆盖**：设计文档四功能 × 21 任务全部对应——手账 T1-1~T1-5（Task 1-5）、星语后端 T4-1~T4-3（Task 6-8）、日历 T3-1~T3-5（Task 9-13）、星语前端 T4-4~T4-5（Task 14-15）、合盘 T2-1~T2-6（Task 16-21）；另加 T5-1 全体系串联（Task 22）与 T5-2 部署/发布说明（Task 23）覆盖设计"五、四功能关联设计"与"六、实施路线"的交付要求；用户决策 4 条全部落实（合并=Task 4、二选一=Task 6/8/14、3 阶段=Task 8/15/23 各一次发布、AI 星语=Task 7 直接上 AI + Task 7/8 钉住降级路径）
- **类型一致性**：`MOOD_BRIGHTNESS/BRIGHTNESS_NAMES/current_streak` 贯穿 Task 1-3；`star_monthly_reviews` 贯穿 Task 2/5；`slot_preference` 贯穿 Task 6/8/14/22；`star_word_daily/source=ai|fallback` 贯穿 Task 7/8/15；`astral_activity_logs/event_key` 贯穿 Task 11/13/22；`star_meetings/meet_id/compute_compatibility` 贯穿 Task 16-21；`rewarded/stardust_total` 幂等语义在 Task 3/11 统一；无一处签名断链
- **无 TBD**：迁移文件名/版本号（v2.3.0→v2.4.0→v2.5.0）/部署命令/测试命令均给出可执行值；文案库（星语 ≥50 条、7 件小事、相处提示 ≥10 条）均为定稿任务（含合规测试），非占位；模板 ID 沿用 P0 配置语义（未配置则推送链路整体跳过，属既有优雅降级而非占位）
