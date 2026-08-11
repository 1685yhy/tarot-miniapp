# 星光映照 P2 三功能实施计划（第 3 期 · 3 阶段 3 次发布）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 第 3 期 P2 三功能：星友圈（今日星光共鸣 · 结构化轻社区）、星象月报（会员周/月报告 · 复购引擎）、星灵学堂（78 张牌学习 · 塔罗师养成）。按用户 2026-08-11 决策 5 条：学习提醒占当日推送额度且默认关闭、月报定价周 4.9/月 19.9 会员免费、星友圈独立入口、默认参与展示+一键隐身、实施顺序 星友圈 → 星象月报 → 星灵学堂。

**设计文档:** `docs/superpowers/specs/2026-08-11-starlight-p2-design.md`（设计任务 T8-1~T8-5 / T7-1~T7-6 / T6-1~T6-6，共 17 个设计任务；本计划 = 17 任务 + 3 次阶段发布，阶段 1=5 / 阶段 2=6 / 阶段 3=6）

**Architecture:** 后端 FastAPI（backend/，venv=backend/venv，测试 `cd backend && ./venv/bin/python -m pytest`，SQLite+aiosqlite，alembic 迁移在 backend/alembic/versions/）；前端微信小程序（miniapp/，E3 奶油疗愈 token 在 miniapp/styles/common.wxss）。星友圈零 UGC 实时聚合（无快照表）；月报仿 star_monthly_reviews 按人按周期缓存（懒生成）；学堂学习进度/计划独立成表 + daily_push 主题切换（非新槽位）。

**Tech Stack:** FastAPI / SQLAlchemy async / alembic / 微信小程序原生 / 微信订阅消息 API / 微信小程序码 API / 微信支付（orders 管线）/ DeepSeek（周寄语/月总评/陪学，复用现有 client 封装）

## Global Constraints

- 设计文档：`docs/superpowers/specs/2026-08-11-starlight-p2-design.md`（含用户决策 5 条，全部已落入下方约束）
- **星光叙事命名（禁直用产品词）**：星友圈=今日星光共鸣（页面=共鸣墙、互动=共鸣，不是"点赞/关注"）；月报=星象月报（周报=星光一周、月报=星光月度卷轴）；学堂=星灵学堂（大阿卡纳=愚者之旅、小阿卡纳=四元素庭院、随机=今日之牌、关联=与你相遇的牌；学一张牌=点亮一颗星；称号=星辉学者/星光塔罗师；陪学角色=星灵·小星）；共鸣动效文案"两颗星在这一刻同频 ✦"；海报固定句"两颗星在同一片夜空相遇 ✦"
- **合规红线（P0）**：所有结果页/海报固定「仅供娱乐 · 星光映照」尾行；AI 文案全部走 `_OUTPUT_RED_LINE`（不预测/不恐吓/不定性/不替用户决策）；海报文案过 `msg_sec_check`；全项目文案走 compliance 共享禁词表（`find_forbidden`，services/compliance.py:57——`MEET_BLACKLIST`/`AI_OUTPUT_BLACKLIST`）；月报展望段只预告真实天象日期+行动建议、不预测吉凶（"水逆将至"→"慢行的日子要来了"）；陪学只讲牌意/典故/生活关联，不预测用户未来
- **星友圈零 UGC（P0）**：无输入框、无自由文本——内容全部为系统生成结构化字段（星名/星座/星光数/今日牌/星阶）+ 代码常量模板文案；海报文案为固定模板（确定性轮换）+ msg_check 校验 + 免责行；与星光树洞（UGC）并存，入口文案区分（"看看今天谁与你同星" vs "写下心事"）
- **共鸣防刷三件套（P0）**：每日上限 10 次（超出返回"今天已经送出 10 颗星，明天再来 ✦"）+ 唯一约束幂等（uq_from_to_date 同日同人仅 1 次）+ **共鸣不产星尘**（纯情感互动，防刷根本解）
- **学习提醒 1 条/天 + 订阅额度复用（用户决策 1）**：daily_push 槽位内容优先级 = **节点日主题 > 学习提醒主题 > 常规晨讯/星语**；学习提醒不新增条数、不新增槽位——复用 SubscribeQuota 的 quota_available/last_sent_date 原子认领 + slot_preference 分流；默认关闭（reminder_on=false），开启需在计划页明示"学习提醒日，当天星光晨讯/星语将换成今日学牌"；学满当日 N 张即当日停发；节点日（新月/满月/水逆首日）优先召回不因学习计划丢失
- **月报定价（用户决策 2）**：PRODUCTS 新增两 SKU——weekly_report 4.9 / monthly_report 19.9（type=single_purchase，对标星盘报告 19.9 锚点）；会员免费全文；非会员预览（周报=曲线+1 段寄语；月报=封面+目录）+ 单次购买解锁；解锁为永久资产（会员到期后旧解锁仍有效，仿 annual_report_paid）；定价为 PRODUCTS 常量可运营调整
- **AI 成本控制（P0）**：统计段纯 SQL 确定性聚合（曲线/星尘/牌运/天象/手账汇总全零 AI），AI 只写文案段（周寄语 ≤60 字 / 月总评 / 陪学回答 ≤200 字）；懒生成（打开才生成，不做全量批处理）；按人按周期缓存（star_reports 周/月各一份，缓存命中零 AI 调用）；月报手账段直接引用 star_monthly_reviews 已有缓存（不重复调 AI）；AI 失败/无 key → 本地温柔降级模板（统计段永不受影响）；regenerate 限流（周/月各 1 次/周期，AI 失败回退原缓存不覆盖）；陪学免费 3 次/天独立计数（会员不限）
- **确定性算法**：同日同人恒定（build_today_guidance 星光数、今日牌 pick_daily_card、星名 ALIAS_POOL 轮换、random 路径今日之牌、组内头部日种子轮换）；共鸣墙无每日快照表——实时聚合（当前用户量 SQL 毫秒级，数据量为 N 百时再评估快照，预留演进方向）
- **模板字段 20 字**：微信 thing 字段 ≤20 字，学习提醒/海报/红点文案定稿即测试校验（`_truncate_str` 语义）
- **安全与脱敏（api_security_redline）**：共鸣墙公开接口独立限流（30 次/分/IP，仿 meet_info_rate_limit，rate_limit.py:170-182）；墙/海报/星名全部脱敏——返回无昵称/头像/openid/出生信息/日记解读内容，仅内部 UUID（uid）用于共鸣/海报用途；to_user_id 不可反查任何可联系字段；首次进入弹「星光公约」+ 我的页一键隐身（默认参与展示）；微信隐私协议材料补"共鸣展示"用途说明（提审）
- **E3 token**：底 #FAF6EF、卡面 #FFFDF8、墨 #3D3A36（正文≥4.5:1）、细金 #A98B5F、暖金 #8A6B3D（CTA）；星光色盘 12 色复用 `STAR_COLORS`
- **测试纪律**：每任务 TDD（先写失败测试→见红→实现→见绿→commit）；后端命令 `cd backend && ./venv/bin/python -m pytest`（P1 全量基线起步，P2 全程全量回归不破）；数据库改动必须走 alembic 迁移（autogenerate 后手工核对仅含新表/新列，upgrade head 后运行迁移链测试）；北京时间口径统一（beijing_today，star_words.py:45）
- **复用优先**：每任务"复用"栏列明的现有资产必须直接复用，禁止另起炉灶——compliance 共享禁词表（compliance.py）/ star_monthly_reviews 缓存模式（models/star_monthly_review.py）/ astral_activity_logs 唯一约束幂等模式 / canvas-poster + share-poster / 订阅额度+槽位（SubscribeQuota 原子认领）/ card_teaching 库（models/card_teaching.py + /cards/{id}/teaching）

---

# 阶段 1：星友圈（5 任务）

交付物：共鸣墙上线（含共鸣海报+隐私公约+红点+隐身）。发布：后端部署 + 迁移 + 上传体验版（v2.6.0）。

### Task 1（设计 T8-1）: star_resonances 表 + users 两列 + 确定性星名生成 + /resonance/alias

**Files:**
- Create: `backend/app/models/star_resonance.py`（仿 models/astral_activity_log.py 幂等唯一约束模式）
- Create: `backend/alembic/versions/77aa88bb99cc_add_star_resonances_and_alias.py`
- Modify: `backend/app/models/user.py`（加 `resonance_visible: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")`、`star_alias: Mapped[str | None] = mapped_column(String(16), nullable=True)`）
- Create: `backend/app/services/resonance.py`（星名词库 + 确定性生成 + 落库）
- Create: `backend/app/api/resonance.py`（router = APIRouter(prefix="/resonance", tags=["今日星光共鸣"])）
- Create: `backend/app/schemas/resonance.py`
- Test: `backend/tests/test_resonance.py`

**Interfaces:**
- Consumes: `User`（models/user.py）、`beijing_today`（services/star_words.py:45）、`compliance.find_forbidden`（services/compliance.py:57）、`get_current_user`（utils/auth.py）
- Produces:
  - 表 `star_resonances(id CHAR(36) PK, from_user_id CHAR(36) INDEX, to_user_id CHAR(36) INDEX, resonate_date Date, created_at DateTime, UNIQUE uq_from_to_date(from_user_id, to_user_id, resonate_date))`——设计 3.3 SQL 原样
  - `ALIAS_POOL: tuple[str, ...]`（40 个自然意象词定稿："晚风""山茶""松声"…均自然意象，无冒犯词；定稿即过 compliance 扫描）
  - `def generate_alias(user_id: str, day: date) -> str`（确定性：`f"星星·{ALIAS_POOL[(sum(ord(c) for c in user_id) + day.toordinal()) % 40]}"`）
  - `async def get_or_create_alias(db, user) -> str`（无则生成并落库 users.star_alias，幂等）
  - 迁移：新表 + users 两列（带默认值）；`alembic upgrade head` 后 `test_alembic_migration` 模式断言表与列存在
  - `GET /resonance/alias`（鉴权）→ `{alias}`

**复用:** astral_activity_logs 唯一约束幂等模式（models/astral_activity_log.py）；compliance 共享禁词表（词库合规扫描）；beijing_today 日界口径。

- [ ] **Step 1: 写失败测试**：ALIAS_POOL 长度 == 40 且全部自然意象、`find_forbidden` 扫描零命中、词长 ≤8 字；generate_alias 确定性（同 user 同日两次恒同；不同 user 同日至少存在不同词——抽样断言非全同）；GET /resonance/alias 首次生成落库、二次调用同值不重复生成；未登录 401；迁移链（临时 SQLite upgrade head → star_resonances 表存在且 uq_from_to_date 唯一约束生效 → users 含 resonance_visible/star_alias 列，downgrade base 干净）
- [ ] **Step 2: 跑测试确认失败**：`cd backend && ./venv/bin/python -m pytest tests/test_resonance.py -v` → FAIL
- [ ] **Step 3: 实现**：模型+迁移（`alembic revision --autogenerate -m "add star_resonances and alias"` 后手工核对仅含新表与两列，`alembic upgrade head`）+ resonance.py + api/schemas
- [ ] **Step 4: 全量回归 + commit**：`./venv/bin/python -m pytest -q` 全绿；`git commit -m "feat: 共鸣记录表+隐身/星名列+确定性星名 (T8-1)"`

**验收:** 星名确定性可测 + 40 词合规扫描通过；迁移只加新表与两列带默认值；alias 接口读写闭环。

### Task 2（设计 T8-2）: /resonance/wall 实时聚合 + 独立限流

**Files:**
- Modify: `backend/app/api/resonance.py`、`backend/app/schemas/resonance.py`
- Modify: `backend/app/middleware/rate_limit.py`（新增共鸣墙公开接口限流依赖）
- Test: `backend/tests/test_resonance.py`（追加）

**Interfaces:**
- Consumes: `User`（zodiac/star_alias/star_tier/resonance_visible）、`HoroscopeHistory`（models/horoscope.py，今日活跃）、`DiaryEntry`/`CheckIn`/`StarResonance`（今日活跃）、`build_today_guidance`（energy_engine.py:348，star_number 确定性派生——墙无需存当日星光快照）、`pick_daily_card`（services/daily_card.py:17，今日牌同源）、`tier_name`（services/stardust.py:33）、`meet_info_rate_limit` 实现模式（rate_limit.py:170-182）
- Produces:
  - `async def resonance_wall_rate_limit(request)`（RateLimiter(30, 60)，key 前缀 `resonance_wall:`，鉴权按 user、未登录按 IP——与 meet_info_rate_limit 同策略）
  - `def today_active_criteria(...)` 纯函数（今日活跃 = 今日有 horoscope_history 记录 或 今日有 diary/checkin/resonance 记录，且 resonance_visible=true）
  - `GET /resonance/wall`（公开免登录，dependencies=[Depends(resonance_wall_rate_limit)]）→ `{active_count: int, groups: [{type, label, members}], my_card: {...} | null}`
    - 三分组：type=`zodiac`（同星座）/ `number`（同星光数）/ `card`（同今日牌）；label 如"同星座的星光 · 双鱼座" / "同星光数的星光 · 7" / "同一张牌的星光 · 星币七"
    - 组内排序：共鸣数降序 + 日种子轮换头部防固化（`(day.toordinal() + group_idx) % len(members)` 起点）；每组 Top 20；**组内 <3 人合并进"同星光的星"兜底组**（不显零）
    - `members[].uid` = users.id 内部 UUID（仅共鸣/海报用途，返回无任何可联系字段）；每成员含 `{uid, alias, zodiac, star_number, card: {card_id, name_zh}, tier, tier_name, resonate_count, resonated_by_me}`（resonated_by_me 登录时按 uid 计算，未登录 false）
    - `my_card`：当前登录用户 `{alias, zodiac, star_number, card, tier_name, received_today}`；未登录 null
    - 脱敏断言：响应键集不含 nickname/avatar/openid/birth_date/birth_time/invite_code

**复用:** build_today_guidance + pick_daily_card（同日同人恒定性，墙零快照表）；tier_name 星阶体系；meet 公开接口限流模式（rate_limit.py）；astral_activity_logs 幂等模式（模型层已建 T8-1）。

- [ ] **Step 1: 写失败测试**：脱敏键集精确断言（无任何可联系字段）；隐身过滤（resonance_visible=false 用户不出现在 wall）；分组正确（3 用户同 zodiac → 同组且 label 含星座名）；兜底组（组内 2 人 → 合并进"同星光的星"）；今日活跃口径（今日有 horoscope 无日记 → 活跃；仅昨日有 → 不活跃）；resonated_by_me 标记正确；my_card 未登录为 null；公开页免登录 200；连续第 31 次请求 → 429
- [ ] **Step 2: 跑测试确认失败**：`cd backend && ./venv/bin/python -m pytest tests/test_resonance.py -v` → FAIL
- [ ] **Step 3: 实现**：rate_limit.py 新依赖 + wall 聚合（纯 SQL 实时聚合 + 三组划分 + 兜底合并 + 头部轮换）
- [ ] **Step 4: 全量回归 + commit**：`./venv/bin/python -m pytest -q` 全绿；`git commit -m "feat: 共鸣墙实时聚合+三分组+脱敏+限流 (T8-2)"`

**验收:** 脱敏字段有键集断言；隐身/分组/兜底/活跃口径全部有测试；公开限流生效。

### Task 3（设计 T8-3）: /resonance/give + /stats + /visibility + /poster

**Files:**
- Modify: `backend/app/api/resonance.py`、`backend/app/schemas/resonance.py`
- Test: `backend/tests/test_resonance.py`（追加）

**Interfaces:**
- Consumes: `StarResonance` 唯一约束（幂等锚，T8-1）、`beijing_today`、`msg_sec_check`（services/msg_check.py:70）、`compliance.find_forbidden`（compliance.py:57）、`build_today_guidance`、`pick_daily_card`、`tier_name`
- Produces:
  - `POST /resonance/give {to_user_id}`（鉴权）→ `{ok: true, count_today, limit: 10}`；当日已给满 10 次 → 400 `{detail: "今天已经送出 10 颗星，明天再来 ✦"}`；同日同人重复（唯一约束）→ 409 `{detail: "已共鸣过这颗星 ✦"}`；给自己 → 400；to_user_id 不存在或已隐身 → 404
  - `GET /resonance/stats`（鉴权，我的页角标数据源）→ `{given_total, received_total, received_today}`
  - `POST /resonance/visibility {visible: bool}`（鉴权）→ `{ok: true, visible}`（写 users.resonance_visible，关闭即时生效）
  - `GET /resonance/poster?to_user_id=`（鉴权）→ `{alias_a, alias_b, zodiac_a, zodiac_b, star_number_a, star_number_b, card_a: {card_id, name_zh}, card_b: {card_id, name_zh}, tier_name_a, tier_name_b, dimension: "zodiac"|"number"|"card", caption: "两颗星在同一片夜空相遇 ✦", disclaimer: "仅供娱乐 · 星光映照"}`；固定模板文案拼接后过 `msg_sec_check` + `find_forbidden`——命中 → 替换为安全兜底句 + 记日志，接口异常 try/except 不阻塞（T2-6 同款接线）
  - 防刷语义：**共鸣不产星尘**（本任务无任何 stardust 调用）

**复用:** astral_activity_logs 唯一约束幂等模式；msg_sec_check + compliance 共享禁词表（T2-6 合盘同款接线）；quota_reset_date/beijing_today 日界口径；不产星尘（防刷根本解）。

- [ ] **Step 1: 写失败测试**：give 首次 ok + count_today=1；同人同日二次 → 409 且"已共鸣过"；第 11 次 → 400 且 detail 含"明天再来"；给自己 → 400；隐身目标 → 404；stats 累计（跨日 given_total 累加、received_today 复位）；visibility=false 即时生效（wall 不再含该用户，own 仍可看墙）；poster 键集脱敏断言 + caption 固定句；msg_check mock 命中 → 兜底句；msg_check 抛异常 → 不阻塞返回原文；未登录 401
- [ ] **Step 2: 跑测试确认失败**：`cd backend && ./venv/bin/python -m pytest tests/test_resonance.py -v` → FAIL
- [ ] **Step 3: 实现**：give（先查当日计数 → 插入，唯一约束冲突兜底幂等）+ stats + visibility + poster（模板 + msg_check 接线）
- [ ] **Step 4: 全量回归 + commit**：`./venv/bin/python -m pytest -q` 全绿；`git commit -m "feat: 共鸣送出/统计/隐身/海报端点 (T8-3)"`

**验收:** 三重防刷全有测试（上限/唯一约束/不产星尘）；poster 脱敏 + 内容安全接线完成。

### Task 4（设计 T8-4）: 共鸣墙页（三分组横滑 + 共鸣动效 + 公约弹窗）

**Files:**
- Create: `miniapp/pages/resonance/resonance.js/json/wxml/wxss`（共鸣墙页）
- Modify: `miniapp/app.json`（注册 subPackage `pages/resonance/`；index preloadRule 加 `pages/resonance/`）
- Modify: `miniapp/pages/index/index.wxml/js`（foot-entry 加「今日共鸣」入口，bindtap=onGoResonance；与星光树洞并存——入口文案区分"看看今天谁与你同星"）
- Test: 模拟器

**Interfaces:**
- Consumes: `GET /resonance/wall`（Task 2）、`POST /resonance/give`（Task 3）、`GET /resonance/stats`（Task 3）、`GET /resonance/alias`（Task 1）；`utils/api.js request()`；`utils/cards.js computeImagePath`（今日牌小图）；E3 token（styles/common.wxss）
- 交互要点（设计 3.2）：首次进入弹「星光公约」（`wx.setStorageSync('resonance_pact_v1')` 三行说明——展示：星名/星座/星光数/今日牌/星阶（系统生成）；不展示：微信昵称头像/出生信息/日记解读；可随时在我的页关闭展示）；页头"今日共鸣墙"+ 今日活跃星光数；我的今日卡片置顶；三分组横滑（每组 Top 20）；点 ✦ → 星点飞出上浮消散动效 + 计数 +1（成功后实心星）；已共鸣卡片实心 + 点击 toast"已共鸣过这颗星 ✦"；服务端 400（超 10 次）原样展示；空态"今晚的夜空有些安静——你的星先亮着 ✦"；卡片「生成共鸣海报」入口（Task 5 接海报）

**复用:** E3 token；utils/api.js；utils/animate.js（星点飞行动效参考）；手账/名片夜空视觉语言。

- [ ] **Step 1: 前端实现**：resonance 页（公约弹窗 → 墙渲染三分组 + 我的卡片 → 共鸣动效/防重 → 空态）
- [ ] **Step 2: 模拟器验证**：`node /home/a/bin/mcp-wechatide.js simulator_screenshot '{"project":"E:\\tarot-miniapp\\miniapp"}'` 遍历：首次进入公约弹窗、三分组渲染、点 ✦ 动效 +1、二次点击"已共鸣过"、空态文案、index 入口可达
- [ ] **Step 3: commit**：`git commit -m "feat: 共鸣墙页三分组+共鸣动效+公约弹窗 (T8-4)"`

**验收:** 模拟器截图确认公约/分组/动效/防重/空态渲染；console 无 error。

### Task 5（设计 T8-5）: 共鸣海报 + 我的页红点/隐身设置 + 阶段 1 发布

**Files:**
- Create: `miniapp/utils/resonance-poster.js`（双星版式海报绘制）
- Modify: `miniapp/pages/resonance/resonance.js/wxml`（共鸣卡「生成共鸣海报」入口）
- Modify: `miniapp/pages/profile/profile.js/wxml/wxss`（角标"今天有 N 颗星与你共鸣"——onShow 调 `GET /resonance/stats`；隐身开关设置项"在共鸣墙中出现"——默认开，调 `POST /resonance/visibility`）
- Test: 模拟器

**Interfaces:**
- Consumes: `GET /resonance/poster`（Task 3）、`GET /resonance/stats`、`POST /resonance/visibility`、`GET /share/wxacode`（share.py:234 名片码 scene=invite_code → card-landing 拉新——复用名片码不新增微信调用）、`POST /share/track`（share_type="resonance"）
- 海报版式（设计 3.2/3.4）：双星并置（双方脱敏星名+星座徽章+星光数+今日牌小图+星阶徽章）+ 共鸣维度标签 + 固定句"两颗星在同一片夜空相遇 ✦" + 小程序码 + 「仅供娱乐 · 星光映照」尾行

**复用:** canvas-poster 绘制管线（utils/canvas-poster.js 调色板/圆角/码位）；share-poster 组件版式（components/share-poster/）；/share/wxacode 名片码；POST /share/track。

- [ ] **Step 1: 前端实现**：resonance-poster.js + 海报入口 + profile 红点与隐身开关
- [ ] **Step 2: 模拟器验证**：海报生成无 404、小程序码可拉取；红点数字与 stats 一致；隐身开关切换即时生效（`simulator_screenshot` 遍历）
- [ ] **Step 3: 阶段 1 发布**：
  - 后端部署：`rsync -avz -e "sshpass -p 'Asdfghjkl123!!' ssh -o StrictHostKeyChecking=no" --exclude="__pycache__" --exclude="*.pyc" --exclude=".env" --exclude="venv" --exclude="data" --exclude="certs" app/ root@124.221.233.214:/opt/tarot/backend/app/`；服务器 `/opt/tarot/backend` 下 `alembic upgrade head`（新增 77aa88bb99cc 迁移）；`systemctl restart tarot-api`；curl 健康检查
  - 上传体验版：`node /home/a/bin/mcp-wechatide.js upload '{"project":"E:\\tarot-miniapp\\miniapp","upload-version":"v2.6.0","upload-desc":"P2阶段1: 星友圈共鸣墙+共鸣海报+隐私公约"}'`
  - 发布说明随报告：微信隐私协议材料补"共鸣展示"用途说明（提审）
- [ ] **Step 4: commit**：`git commit -m "feat: 共鸣海报+红点+隐身设置 (T8-5)"`

**验收:** 海报可保存/转发带名片码；红点与 stats 一致；隐身即时生效；阶段 1 发布后共鸣墙全链路可用。

---

# 阶段 2：星象月报（6 任务）

交付物：周报升级 + 月报上线（含付费解锁 + 海报）。发布：后端部署 + 迁移 + 上传体验版（v2.7.0）。

### Task 6（设计 T7-1）: star_reports 表 + 周报聚合（曲线/星尘/牌运）+ AI 寄语 + 缓存/降级

**Files:**
- Create: `backend/app/models/star_report.py`（设计 2.3 SQL 原样：id/user_id/report_type/period_key/data/source/generated_at/updated_at，UNIQUE uq_user_type_period）
- Create: `backend/alembic/versions/88bb99cc00dd_add_star_reports.py`
- Create: `backend/app/services/star_reports.py`（周/月聚合 + 缓存读写 + AI + 降级模板；含从 report.py 抽取的通用区间查询）
- Modify: `backend/app/api/report.py`（`_get_readings_for_days`/`_get_diary_entries_for_days`（api/report.py:546/562）改为调用服务层通用函数，行为不变；**`/report/weekly` 接口保留不动**——profile 页旧海报继续可用）
- Create: `backend/app/api/star_report.py`（router = APIRouter(prefix="/report", tags=["星象月报"])）
- Create: `backend/app/schemas/star_report.py`
- Test: `backend/tests/test_star_report.py`

**Interfaces:**
- Consumes: `Reading`/`DrawnCard`/`DiaryEntry`、`HoroscopeHistory`（7 天能量总分）、`CheckIn` + `astral_activity_logs` + `journal_streak_reward_week`（本周星尘行为计数）、`build_today_guidance`（7 色带）、`_get_ai_client`（api/report.py:156）、`_OUTPUT_RED_LINE`（ai_engine.py:204）、`beijing_today`（star_words.py:45）
- Produces:
  - `def period_week_key(d: date) -> str`（ISO 周键 `2026-W33`）；`def week_bounds(period: str) -> tuple[date, date]`（周一~周日）；`def last_completed_week(today: date) -> str`（每周一 00:00 后可用上周——设计"每周一后可看上周"）
  - `async def get_readings_for_range(db, user_id, start, end) / get_diary_entries_for_range(db, user_id, start, end)`（从 report.py 抽取的通用区间版，report.py 委托调用）
  - `async def aggregate_week(db, user, start, end) -> dict`（**纯 SQL 确定性聚合**：`{curve: [{date, total}], stardust: {checkin_days, activity_events, total}, cards: {readings_count, most_card: {name, count, keywords}, card_list}, color_band: [7]}`）
  - `async def generate_week_note_ai(db, user, stats) -> str | None`（周寄语 ≤60 字，system 含 `_OUTPUT_RED_LINE`，失败/无 key → None）
  - `def build_week_report(stats, ai_note) -> dict`（完整报告 JSON + `_FALLBACK_WEEK_NOTE` 按能量均值三档降级文案——≥4/≥3/<3，均不下定性结论）
  - `async def get_or_create_week_report(db, user, period, force=False) -> dict`（缓存命中即返，不消耗 AI；未命中：聚合 → AI → 落 star_reports（source=ai|fallback）；force → 覆盖）
  - `GET /report/week?period=2026-W33`（鉴权）→ `{period, week_range: [start, end], report, locked, preview, cached, source}`；非会员 → 预览版（curve + 1 段寄语）+ locked=true；period 缺省 = last_completed_week(today)；空态周（无任何数据）→ 统计 0 + 温柔引导不报错

**复用:** star_monthly_reviews 缓存模式（models/star_monthly_review.py 按人按周期一份，data TEXT + source ai|fallback）；report.py /weekly 聚合函数（抽取到服务层共用，不复制逻辑）；astral_activity_logs 计数（星尘统计）；`_OUTPUT_RED_LINE` + DeepSeek client 模式。

- [ ] **Step 1: 写失败测试**：period_week_key/week_bounds 边界（2026-W33 == 08-10~08-16 周一~周日）；last_completed_week（周一当天 → 上周；周日 → 上周）；聚合：7 天曲线逐日（无 horoscope 记录日 total=null 不崩溃）、牌运 N 次 + 最常牌；缓存：首次 AI 调 1 次，二次 cached=true 零 AI；AI 抛异常 → source=fallback 且统计段完整；非会员 → locked=true 且 report 为预览结构（键集断言）；会员 → 全文；空态周统计 0 不报错；既有 `tests/test_weekly_report.py` 全绿（抽取无回归）；未登录 401
- [ ] **Step 2: 跑测试确认失败**：`cd backend && ./venv/bin/python -m pytest tests/test_star_report.py -v` → FAIL
- [ ] **Step 3: 实现**：模型+迁移（autogenerate 后手工核对仅含新表）+ 服务层抽取与 report.py 委托改造 + api/schemas
- [ ] **Step 4: 全量回归 + commit**：`./venv/bin/python -m pytest -q` 全绿；`git commit -m "feat: 周报聚合+AI寄语+缓存降级 (T7-1)"`

**验收:** 周期边界/跨月周/空态有测试；缓存命中零 AI；抽取后 /report/weekly 无回归。

### Task 7（设计 T7-2）: 月报聚合（天象+手账引用+牌运+星阶估算+展望）+ 缓存

**Files:**
- Modify: `backend/app/services/star_reports.py`、`backend/app/api/star_report.py`、`backend/app/schemas/star_report.py`
- Test: `backend/tests/test_star_report.py`（追加）

**Interfaces:**
- Consumes: `ASTRAL_EVENTS_2026` + `astral_events_on`（energy_engine.py:214/295，月度天象零新数据）、`StarMonthlyReview`（models/star_monthly_review.py，**直接引用缓存 data JSON**——手账段不重复调 AI）、`Reading` 月统计、`CheckIn`/`astral_activity_logs` 月计数（"可得星尘"估算口径——设计决策：不引入星尘流水表）、`stardust.tier_name`（当前星阶）、`_OUTPUT_RED_LINE`、`compliance.find_forbidden`
- Produces:
  - `def period_month_key(d: date) -> str`（`2026-08`）；`def month_bounds(period) -> tuple[date, date]`；`def last_completed_month(today) -> str`（每月 1 日后可看上月）
  - `async def aggregate_month(db, user, start, end) -> dict`（**纯 SQL**：`{astral_events: [{type, label, date}], journal: {active_days, bright_ratio, trend} | null（引用 star_monthly_reviews）, cards: {readings_count, top3}, stardust: {estimated, tier_name}}`）
  - `def build_outlook(next_month: str, events_2026) -> dict`（下月天象预告：首个新月/满月/水逆首日日期 + 温柔行动建议模板——**活动预告非运势预测**，过 compliance 扫描）
  - `async def generate_month_note_ai(...)`（月度总评，`_OUTPUT_RED_LINE`）+ `_FALLBACK_MONTH_NOTE`（本地温柔模板）
  - `GET /report/month?period=2026-08`（鉴权，与 /report/week 同 locked/preview 语义）→ `{period, month_range, report, locked, preview, cached, source}`；无数据月份 → 报告照常生成（统计 0 + 引导文案"夜空等着被你点亮"）；period 缺省 = last_completed_month

**复用:** star_monthly_reviews 缓存直接引用（零新增 AI 调用）；ASTRAL_EVENTS_2026 + astral_events_on；compliance 共享禁词表；`_FALLBACK_INSIGHT` 降级模式语义。

- [ ] **Step 1: 写失败测试**：上月事件表（用 astral_events_on 过滤当月断言类型集合含 new_moon/full_moon/mercury_retrograde——不写死日期字面量）；journal 段引用预置 star_monthly_reviews 缓存（mock AI client 计数 == 1，仅月总评一次）；top3 排序；stardust 估算 == 签到天数+事件数；tier_name 当前星阶；下月展望仅真实事件日期 + 建议不含黑名单词；空态月份统计 0 不报错；会员/非会员锁定语义同周报；未登录 401
- [ ] **Step 2: 跑测试确认失败**：`cd backend && ./venv/bin/python -m pytest tests/test_star_report.py -v` → FAIL
- [ ] **Step 3: 实现**：聚合 + outlook + AI/降级 + 端点
- [ ] **Step 4: 全量回归 + commit**：`./venv/bin/python -m pytest -q` 全绿；`git commit -m "feat: 月报聚合天象+手账引用+展望 (T7-2)"`

**验收:** 月报手账段零新增 AI 调用（测试钉住 mock 计数）；展望文案合规；空态不报错。

### Task 8（设计 T7-3）: 权益（会员判定 + 两 BOOL 解锁列 + unlock 下单）+ regenerate 限流

**Files:**
- Modify: `backend/app/models/user.py`（加 `weekly_report_unlocked: Mapped[bool] = mapped_column(Boolean, default=False)`、`monthly_report_unlocked: Mapped[bool] = mapped_column(Boolean, default=False)`——仿 annual_report_paid 模式）
- Create: `backend/alembic/versions/99cc00dd11ee_add_report_unlock_flags.py`
- Modify: `backend/app/services/payment.py`（PRODUCTS 加两 SKU：`"weekly_report": {"name": "星光一周周报", "price": 4.90, "type": "single_purchase", "cost": 0.005}`、`"monthly_report": {"name": "星光月度卷轴", "price": 19.90, "type": "single_purchase", "cost": 0.02}`）
- Modify: `backend/app/api/orders.py`（payment_callback 权益分支：`weekly_report` → `user.weekly_report_unlocked = True`；`monthly_report` → `user.monthly_report_unlocked = True`——仿 annual_report 分支 orders.py:326-334）
- Modify: `backend/app/api/star_report.py`、`backend/app/schemas/star_report.py`
- Test: `backend/tests/test_star_report.py`（追加）+ `backend/tests/test_xpay.py`（追加 payment_callback 分支）

**Interfaces:**
- Consumes: `PRODUCTS`（payment.py:22）、orders 下单管线（api/orders.py:36 create_order）、`payment_callback` 权益分发（orders.py:288-334）、会员判定（`user.is_member and user.member_expires_at > now`，membership.py 语义）
- Produces:
  - `def is_member_active(user) -> bool`；`def can_read_full(user, report_type) -> bool`（会员 或 对应 unlocked 列——**会员到期后旧解锁仍有效**，单次购买是永久资产，仿 annual_report_paid 语义）
  - `POST /report/{type}/unlock`（type=week|month，鉴权）→ 复用 create_order 管线（product_type=`weekly_report`|`monthly_report`）→ `{order_no, pay_params}`；已解锁/会员 → 400 `{detail: "你已拥有这份星光 ✦"}`
  - `POST /report/{type}/regenerate`（鉴权，仅会员）→ 限流：周/月各 1 次/周期（内存 dict `_regenerate_used: dict[str, str]`，key=`f"{user_id}:{type}:{period_key}"`）→ 已用 → 429 `{detail: "这份星光已是最新 ✦"}`；重新聚合+AI → 覆盖缓存；**AI 失败 → 回退原缓存不覆盖**（返回原报告，source 不变）
- 复用: annual_report_paid 单次购买 entitlement 模式；orders/fulfillment 全管线（type=single_purchase 已有年度报告/星盘先例）；PRODUCTS 常量治理。

- [ ] **Step 1: 写失败测试**：会员 → can_read_full true；非会员未解锁 → locked；unlock 下单 → 订单 product_type 正确且 pay_params 非空；payment_callback weekly_report/monthly_report → 两列置位 → 再 GET /report/week 全文；会员到期（member_expires_at 过去）→ 已解锁仍全文；已解锁重复 unlock → 400；regenerate 会员首次 ok + 缓存覆盖（内容变化）；同周期二次 → 429；非会员 regenerate → 403；regenerate AI 抛异常 → 返回原缓存且 data 未变；非法 type → 404；test_xpay 全量回归
- [ ] **Step 2: 跑测试确认失败**：`cd backend && ./venv/bin/python -m pytest tests/test_star_report.py tests/test_xpay.py -v` → FAIL
- [ ] **Step 3: 实现**：User 两列 + 迁移（核对仅含两列）+ PRODUCTS + orders.py 分支 + unlock/regenerate 端点
- [ ] **Step 4: 全量回归 + commit**：`./venv/bin/python -m pytest -q` 全绿；`git commit -m "feat: 月报解锁权益+unlock下单+regenerate限流 (T7-3)"`

**验收:** 会员/解锁/到期语义全部有测试；regenerate 限流与 AI 失败回退钉住。

### Task 9（设计 T7-4）: 月报海报数据端点（脱敏）

**Files:**
- Modify: `backend/app/api/star_report.py`、`backend/app/schemas/star_report.py`
- Test: `backend/tests/test_star_report.py`（追加）

**Interfaces:**
- Consumes: star_reports 缓存 data（/report/month）、`tier_name`
- Produces:
  - `GET /report/month/poster?period=`（鉴权）→ `{period, tier_name, core_numbers: {active_days, readings_count, stardust_estimated}, ai_sentence: 总评一句（截断 40 字）, share_text: "我的{month}星象月报 · 本月点亮 {active_days} 颗星 ✦", disclaimer: "仅供娱乐 · 星光映照"}`；**脱敏**：无昵称/无原文统计明细/无日记内容；无缓存 → 404 `{detail: "先看报告，再分享星光 ✦"}`
  - share_text 固定模板 + compliance 扫描
- 复用: 月报缓存数据（零新增 AI）；固定模板文案（确定性）+ compliance 共享禁词表。

- [ ] **Step 1: 写失败测试**：有缓存 → 字段完整 + 键集脱敏断言；无缓存 → 404；share_text 模板确定性（同数据同文案）；ai_sentence ≤ 40 字；未登录 401
- [ ] **Step 2: 跑测试确认失败**：`cd backend && ./venv/bin/python -m pytest tests/test_star_report.py -v` → FAIL
- [ ] **Step 3: 实现**：poster 端点
- [ ] **Step 4: 全量回归 + commit**：`./venv/bin/python -m pytest -q` 全绿；`git commit -m "feat: 月报海报脱敏数据端点 (T7-4)"`

**验收:** 海报数据无敏感字段；无缓存 404 有测试。

### Task 10（设计 T7-5）: 报告页（周/月 Tab + 曲线 canvas + 预览锁态 + 解锁支付流）

**Files:**
- Create: `miniapp/pages/star-report/star-report.js/json/wxml/wxss`（?tab=week|month 双 Tab）
- Create: `miniapp/components/energy-curve/energy-curve.js/json/wxml/wxss`（周曲线 canvas：7 天折线 + 每日星光色点，复用 canvas-poster 绘制辅助）
- Modify: `miniapp/app.json`（注册 subPackage `pages/star-report/`；index preloadRule 加）
- Modify: `miniapp/pages/profile/profile.js/wxml`（我的页"星象月报"卡 → `pages/star-report/star-report?tab=week`）
- Modify: `miniapp/pages/membership/membership.js/wxml`（会员页权益位："星象月报 · 周报月报免费看"入口）
- Test: 模拟器

**Interfaces:**
- Consumes: `GET /report/week`、`GET /report/month`（Task 6/7）、`POST /report/{type}/unlock`（Task 8）、`utils/pay.js`（微信支付封装）、`GET /membership/status`（会员判定回显）
- 交互要点（设计 2.2）：期头（报告期 + 星阶徽章）→ 报告期切换器（最近 4 期）→ 周报：星运曲线 → 星尘统计卡 → 牌运回顾（卡图横滑）→ AI 周寄语 → 本周星光色带；月报：月度天象事件表（每事件一句宜忌）→ 手账汇总 → TOP3 → 星尘与星阶（"微光 → 星光"变迁文案）→ 下月展望 → AI 月度总评；**非会员预览态**：未解锁区块毛玻璃模糊 + 锁形标记，底部吸底"解锁全文 4.9/19.9" → utils/pay.js 下单 → 成功刷新为全文；"开通会员免费看" → 跳 membership；空态（无数据月）"夜空等着被你点亮"；每区星空色描边卡 + 「仅供娱乐 · 星光映照」尾行
- 复用: canvas-poster 曲线绘制管线；tarot-card 组件（牌运卡图）；utils/api.js；E3 token。

- [ ] **Step 1: 前端实现**：star-report 页（双 Tab + 期头/切换器 + 周报五段/月报六段渲染 + 锁态 + 支付流）
- [ ] **Step 2: 模拟器验证**：Tab 切换、曲线渲染、预览毛玻璃锁态、解锁支付流（mock 成功刷新全文）、空态、尾行（`simulator_screenshot` 遍历）
- [ ] **Step 3: commit**：`git commit -m "feat: 星象月报页双Tab+曲线+预览锁态+解锁流 (T7-5)"`

**验收:** 模拟器截图确认周/月结构完整；锁态与支付刷新闭环；免责尾行常驻。

### Task 11（设计 T7-6）: 周报海报升级 + 月报封面海报 + 入口 + 阶段 2 发布

**Files:**
- Modify: `miniapp/components/weekly-report-poster/*`（数据源升级为 `GET /report/week` 全文，版式保留）
- Create: `miniapp/utils/month-report-poster.js`（封面海报：星空卷轴标题 + 星阶徽章 + 3 核心数字 + AI 寄语一句 + 小程序码 + 「仅供娱乐 · 星光映照」）
- Modify: `miniapp/pages/star-report/star-report.js/wxml`（"生成海报"按钮 → 周报走 weekly-report-poster 组件、月报走 month-report-poster）
- Test: 模拟器

**Interfaces:**
- Consumes: `GET /report/week`（全文）、`GET /report/month/poster`（Task 9）、`GET /share/wxacode`（名片码 scene=invite_code → card-landing 拉新）、`POST /share/track`（share_type="month_report"）
- 复用: weekly-report-poster 组件（components/weekly-report-poster/，改数据源）；canvas-poster / share-poster 管线；/share/wxacode 名片码（不新增微信调用）。

- [ ] **Step 1: 前端实现**：weekly-report-poster 数据源升级 + month-report-poster.js + 海报按钮
- [ ] **Step 2: 模拟器验证**：两张海报生成无 404、小程序码可拉取、月报海报 3 核心数字正确（`simulator_screenshot`）
- [ ] **Step 3: 阶段 2 发布**：后端部署 rsync（同 Task 5 命令）→ 服务器 `alembic upgrade head`（新增 88bb99cc00dd/99cc00dd11ee 迁移）→ `systemctl restart tarot-api` → curl 健康检查；上传体验版 `node /home/a/bin/mcp-wechatide.js upload '{"project":"E:\\tarot-miniapp\\miniapp","upload-version":"v2.7.0","upload-desc":"P2阶段2: 星象月报+周报升级+付费解锁"}'`
- [ ] **Step 4: commit**：`git commit -m "feat: 周报海报升级+月报封面海报 (T7-6)"`

**验收:** 海报带码保存/转发；月报海报 3 核心数字+星阶徽章渲染正确；阶段 2 发布后报告/解锁/海报全可用。

---

# 阶段 3：星灵学堂（6 任务）

交付物：学堂上线（含陪学 + 学习提醒 + 称号/壁纸庆祝）。发布：后端部署 + 迁移 + 上传体验版（v2.8.0）。

### Task 12（设计 T6-1）: star_learning_progress 表 + /academy/learned + 复习 + 里程碑奖励

**Files:**
- Create: `backend/app/models/star_learning_progress.py`（设计 1.3 SQL 原样：id/user_id/card_id/learned_at DATE/review_count/created_at/updated_at，UNIQUE uq_user_card）
- Create: `backend/alembic/versions/aa00dd11ee22_add_star_learning_progress.py`
- Modify: `backend/app/models/user.py`（加 `academy_milestones: Mapped[str | None] = mapped_column(String(255), nullable=True)`——已领里程碑 JSON 账本，幂等锚，仿 journal_streak_reward_week 语义）
- Create: `backend/app/services/academy.py`（里程碑表 + 判定 + 发放）
- Create: `backend/app/api/academy.py`（router = APIRouter(prefix="/academy", tags=["星灵学堂"])）
- Create: `backend/app/schemas/academy.py`
- Test: `backend/tests/test_academy.py`

**Interfaces:**
- Consumes: `TarotCard`（arcana/suit/card_number）、`stardust.tier_for/tier_name`（services/stardust.py:19/33）、签到星尘加法模式（api/tasks.py:125-126：`stardust_total += n; star_tier = tier_for(stardust_total)` 同步推导）、`star_collectibles.grant_wallpaper`（star_collectibles.py:91）、`compliance.find_forbidden`
- Produces:
  - `MILESTONES` 代码常量（表驱动）：`first_star`（learned≥1，+1）/ `seven_stars`（learned≥7，+1）/ `fool_journey`（major≥22，+3，称号「星辉学者」）/ `element_court`（minor≥56，+5）/ `full_78`（learned≥78，+10，称号「星光塔罗师」，解锁星光壁纸 1 张）——**全通封顶 +19 星尘**
  - `def check_milestones(learned: int, major: int, minor: int, awarded: list[str]) -> list[dict]`（纯函数：返回未领的里程碑）
  - `async def apply_milestones(db, user, learned, major, minor) -> list[dict]`（星尘加法 + tier 同步 + 称号入账 academy_milestones + 壁纸；账本内已有 key 跳过）
  - `POST /academy/learned {card_id}`（鉴权）→ `{ok, learned: bool, review_count, milestone: null | {key, title, stardust_gained, wallpaper_granted}}`；**INSERT 成功（rowcount==1）才跑里程碑判定**（幂等锚：uq_user_card 唯一约束 + 账本双保险）；重复 POST（已学）→ learned=false 不重复奖励；card_id 非法 → 404
  - `GET /academy/lesson/{card_id}`（**公开免登录可看牌库**）→ `{card: {id, name_zh, arcana, suit, card_number, image_url}, teaching: {symbols, story, keywords_learning, life_connection, element_association}, my: {learned, review_count} | null}`（teaching 直接读 card_teaching 表，未登录 my=null）
  - `POST /academy/review {card_id}`（鉴权）→ `{ok, review_count}`（review_count+1，**仅计数不设奖励防刷**）
- 复用: card_teaching 库（models/card_teaching.py + /cards/{id}/teaching 组装语义）；签到星尘加法 + tier 同步（tasks.py）；star_collectibles 壁纸发放管线；astral_activity_logs 唯一约束幂等模式（uq_user_card + 里程碑账本双保险）；compliance 共享禁词表（里程碑文案）。

- [ ] **Step 1: 写失败测试**：首学 → first_star +1 且 star_tier 同步；重复 learned → 幂等无奖励；第 7 张 → seven_stars +1；22 张 major 全学 → fool_journey +3 + 称号入账（断言 academy_milestones 含 key）；56 minor → element_court +5；78 全学 → full_78 +10 + 壁纸（mock grant_wallpaper 调用）；封顶：0→78 张全学 stardust 总增量 == 19；已学再学同卡 → learned=false 且里程碑不重发；review 递增且无星尘；lesson 未登录可看 + my=null；card_id 非法 404；里程碑文案过 compliance 扫描；未登录 401
- [ ] **Step 2: 跑测试确认失败**：`cd backend && ./venv/bin/python -m pytest tests/test_academy.py -v` → FAIL
- [ ] **Step 3: 实现**：模型+迁移（核对仅含新表与一列）+ academy.py + 三端点
- [ ] **Step 4: 全量回归 + commit**：`./venv/bin/python -m pytest -q` 全绿；`git commit -m "feat: 学习进度+已学/复习+里程碑奖励幂等 (T6-1)"`

**验收:** 里程碑边界（1/7/22/56/78）与封顶 +19 有测试；奖励双保险幂等；lesson 公开接口可用。

### Task 13（设计 T6-2）: star_learning_plans 表 + /academy/plan + /academy/lesson/next + /academy/overview

**Files:**
- Create: `backend/app/models/star_learning_plan.py`（设计 1.3 SQL 原样：user_id PK/cards_per_day/reminder_on/path/cursor_pos/created_at/updated_at）
- Create: `backend/alembic/versions/bb11ee22ff33_add_star_learning_plans.py`
- Modify: `backend/app/services/academy.py`、`backend/app/api/academy.py`、`backend/app/schemas/academy.py`
- Test: `backend/tests/test_academy.py`（追加）

**Interfaces:**
- Consumes: `TarotCard`、`pick_daily_card`（services/daily_card.py:17，random 路径确定性）、`Reading`（related 路径：历史抽牌频次 TOP 未学牌）、`SubscribeQuota`（开启提醒时校验已有订阅额度——`quota_available` 或 `last_sent_date` 有值视为已授权，无额度给引导授权提示不硬拦）
- Produces:
  - `def major_cards(cards) -> list[TarotCard]`（card_number 0-21 升序）；`def minor_cards(cards) -> list[TarotCard]`（suit 火/水/风/土 + rank 升序）；`def next_card(path, cursor_pos, major, minor, user_id, day) -> tuple[TarotCard, int, bool]`（random：pick_daily_card 同牌；related：Reading 历史 TOP 未学；越界 → done=True 循环回 0）
  - `GET /academy/overview`（鉴权）→ `{total: 78, learned, percent, paths: {major: {learned, total: 22}, minor: {learned, total: 56}, random: {learned}, related: {learned}}, titles: [称号...]（由 academy_milestones 推导）, today_card: {card_id, name_zh, reason} | null}`（random 路径按日确定性）
  - `GET /academy/lesson/next?path=&pos=`（鉴权）→ `{card_id, name_zh, path, next_pos, done}`；推进写回 plans.cursor_pos（upsert；random/related 按 date_seed+user 确定性取，同日同人恒定）
  - `GET /academy/plan`（鉴权）→ `{cards_per_day, reminder_on, path, cursor_pos}`（无行 → `{0, false, "major", 0}`）
  - `POST /academy/plan {cards_per_day: 0|1|3|5, reminder_on: bool, path: "major"|"minor"|"random"|"related"}`（鉴权）→ 回显 + `{quota_warning: bool}`；非法值 → 422；reminder_on=true 且无订阅额度 → 200 + quota_warning=true（引导授权不硬拦）；**学习提醒默认关闭**
- 复用: pick_daily_card 确定性哲学；订阅额度+槽位（SubscribeQuota——仅校验引导不消费）；card_teaching 库（lesson 组装，T6-1 已建）。

- [ ] **Step 1: 写失败测试**：plan 读写闭环；非法 cards_per_day（2/7）→ 422；非法 path → 422；reminder_on=true 无额度 → quota_warning=true 且仍保存；overview 进度/percent/titles/today_card；next major 游标推进（0→1→…）；越界 → done=true 回 0；random 同日同人恒定（两次调用同卡）；related 按历史 TOP 未学；未开启计划默认值；未登录 401
- [ ] **Step 2: 跑测试确认失败**：`cd backend && ./venv/bin/python -m pytest tests/test_academy.py -v` → FAIL
- [ ] **Step 3: 实现**：模型+迁移 + 排序/游标/确定性函数 + 三端点
- [ ] **Step 4: 全量回归 + commit**：`./venv/bin/python -m pytest -q` 全绿；`git commit -m "feat: 学习计划+下一张+学堂概览 (T6-2)"`

**验收:** 路径游标与确定性有测试；额度引导不硬拦；overview 字段完整。

### Task 14（设计 T6-3）: daily_push 学习提醒主题（三态优先级）

**Files:**
- Modify: `backend/app/services/daily_push.py`（内容构建插入三态判定）
- Test: `backend/tests/test_daily_push.py`（追加）

**Interfaces:**
- Consumes: `StarLearningPlan`（reminder_on/cards_per_day）、`StarLearningProgress`（今日已学数）、`SubscribeQuota`（quota_available/last_sent_date/slot_preference）、`_astral_morning_event`（daily_push.py:242，节点日）、`get_today_star_word`/`build_star_word_data`（star_words.py:410/441）、`_truncate_str`（daily_push.py:233）、`TEMPLATE_DAILY_CARD`
- Produces:
  - `async def _learning_reminder_event(db, target, today) -> dict | None`（三态判定中间件：今日已学 < cards_per_day 且 reminder_on 且今日非节点日 → `{title: f"今日学牌：{card.name_zh}", keywords: f"关键词·{k1}·{k2}", page: f"pages/academy/lesson/lesson?card_id={card.id}"}`（与 Task 16/17 注册的 subPackage 页面路径一致）；学满当日 N 张或非学习日 → None）
  - `def build_learning_push_data(event) -> dict[str, dict[str, str]]`（thing1=title ≤20 字、thing2=keywords ≤20 字、date3=日期、thing4="点击点亮这颗星 ✦"）
  - 集成点：`send_starlight_morning_if_due`（daily_push.py:363，7:37）与 `send_daily_push_if_due`（daily_push.py:530，21:00）内容构建统一三态：**节点日主题 > 学习提醒主题 > 常规晨讯/星语**；额度/原子认领/失败退避/slot_preference 分流机制不动；学习提醒默认关闭（reminder_on=false 天然不触发）
- 复用: 订阅额度+槽位全套（quota_available/last_sent_date 原子认领 + slot_preference 分流——学习提醒不新增条数/不新增槽位，主题切换）；晨讯节点三态判定（T3-2 已有 `_astral_morning_event`）；`_truncate_str`。

- [ ] **Step 1: 写失败测试**：学习提醒字段（thing1 ≤20 字含牌名、page=pages/academy/lesson/lesson?card_id=、thing4 固定）；节点日（新月 2026-01-03）→ 节点内容优先于学习提醒；学习日（普通日+reminder_on+未学满）→ 学习提醒替代常规晨讯；已学满当日 N 张 → 常规内容（停发学习提醒）；reminder_on=false → 常规；无额度 → 不发送（既有扫描条件）；21:00 night 用户 → 学习提醒；满月当天 21:00 → 节点内容优先；现有晨讯/星语测试全绿回归（默认分支不变）
- [ ] **Step 2: 跑测试确认失败**：`cd backend && ./venv/bin/python -m pytest tests/test_daily_push.py -v` → FAIL
- [ ] **Step 3: 实现**：daily_push.py 三态判定与构建函数 + 两槽位集成
- [ ] **Step 4: 全量回归 + commit**：`./venv/bin/python -m pytest -q` 全绿；`git commit -m "feat: 学习提醒主题三态优先级 (T6-3)"`

**验收:** 节点>学习>常规优先级有测试；学满即停发；1 条/天纪律不破（既有并发测试回归）。

### Task 15（设计 T6-4）: /academy/chat 陪学（teaching 上下文 + 配额 + 红线清洗 + 降级）

**Files:**
- Modify: `backend/app/models/user.py`（加 `academy_chat_count_today: Mapped[int] = mapped_column(Integer, default=0)`——独立计数字段，与 free_chats_today 分离）
- Create: `backend/alembic/versions/cc22ff33aa44_add_academy_chat_count.py`
- Modify: `backend/app/utils/quota.py`（`reset_ai_quota_if_new_day`（quota.py:8）增加 `user.academy_chat_count_today = 0`——复用 quota_reset_date 日复位管线）
- Modify: `backend/app/services/ai_personas.py`（新增 `"academy_tutor"` persona 条目：温柔系讲学基调，沿用 wise_moon 文风，只讲牌意/典故/生活关联）
- Modify: `backend/app/services/academy.py`、`backend/app/api/academy.py`、`backend/app/schemas/academy.py`
- Test: `backend/tests/test_academy.py`（追加）

**Interfaces:**
- Consumes: `CardTeaching`、`get_persona`/`get_persona_prompt_suffix`（ai_personas.py:89/99）、`_OUTPUT_RED_LINE`（ai_engine.py:204）、`star_words._sanitize`（star_words.py:148 黑名单替换清洗模式）、`compliance.find_forbidden`、`_get_ai_client`（star_words.py:175 模式）、`reset_ai_quota_if_new_day`（utils/quota.py:8）、`settings.FREE_CHAT_MESSAGES`（=3，config.py:49，同值语义独立字段）
- Produces:
  - `async def academy_chat(db, user, card_id, message) -> dict` → `{reply, remaining: int | None, degraded: bool}`；流程：日复位（reset_ai_quota_if_new_day）→ 配额校验（非会员 `academy_chat_count_today < 3`，超限 → 402 `{detail: "今天的小星课堂结束啦，明天再来 ✦"}`；会员不限 remaining=None）→ 读 teaching → 注入上下文（symbols/story/life_connection/keywords_learning）→ persona=academy_tutor + `_OUTPUT_RED_LINE`（陪学只讲牌意/典故/生活关联，**不预测用户未来、不替用户决策**）→ AI 回答 ≤200 字 → `_sanitize` + `find_forbidden` 清洗 → 非会员计数 +1
  - `POST /academy/chat {card_id, message}`（鉴权）→ 同上；message 空 → 422；card_id 非法 → 404；无 key/AI 失败 → 降级 `{reply: "小星在休息，先看看学习卡吧 ✦", degraded: true}`（不空屏）；**同卡同人二次提问直接回短版**（内存缓存 `_academy_chat_short: dict[str, tuple[str, str]]`，key=`f"{user_id}:{card_id}"`，当日命中 → 回前 80 字短版，不重复调 AI——AI 成本控制）
- 复用: card_teaching 库；`_OUTPUT_RED_LINE` + star_words._sanitize 清洗模式；compliance 共享禁词表；ai_personas 注入模式（wise_moon 温柔系基调）；quota_reset_date 日复位管线（复用非新建）。

- [ ] **Step 1: 写失败测试**：免费 3 次内成功 + remaining 递减（3→2→1）；第 4 次 → 402；会员 10 次全成功 remaining=None；AI 失败 → degraded=true 降级文案；mock AI 输出含黑名单词 → 清洗后 reply 不含；日复位（quota_reset_date=昨天 → 首次调用计数从 0 起）；message 空 → 422；card_id 非法 → 404；同卡二次 → 短版且 AI 调用次数不增；未登录 401
- [ ] **Step 2: 跑测试确认失败**：`cd backend && ./venv/bin/python -m pytest tests/test_academy.py -v` → FAIL
- [ ] **Step 3: 实现**：User 字段 + 迁移 + quota.py 复位 + persona 条目 + chat 服务/端点
- [ ] **Step 4: 全量回归 + commit**：`./venv/bin/python -m pytest -q` 全绿；`git commit -m "feat: 陪学小星AI+配额+清洗+降级短版 (T6-4)"`

**验收:** 配额/降级/清洗/短版缓存全有测试；独立计数不与占卜追问互挤；合规红线生效。

### Task 16（设计 T6-5）: 学堂主页（78 星图 + 四路径 + 计划设置）+ 学习卡页

**Files:**
- Create: `miniapp/pages/academy/academy.js/json/wxml/wxss`（学堂主页）
- Create: `miniapp/pages/academy/lesson/lesson.js/json/wxml/wxss`（学习卡页）
- Modify: `miniapp/app.json`（注册 subPackage `pages/academy/`，pages: ["academy/academy", "lesson/lesson"]；index preloadRule 加 `pages/academy/`）
- Modify: `miniapp/pages/index/index.wxml/js`（foot-entry 加「星灵学堂」入口）
- Modify: `miniapp/pages/encyclopedia/encyclopedia.js/wxml`（详情卡加"去学堂学这张牌"互链 → `pages/academy/lesson/lesson?card_id=`——学堂=路径化学习、百科=全量浏览，两页互相跳转）
- Test: 模拟器

**Interfaces:**
- Consumes: `GET /academy/overview`（Task 13）、`GET /academy/lesson/{card_id}`（Task 12）、`GET /academy/lesson/next?path=&pos=`（Task 13）、`POST /academy/learned`、`POST /academy/review`（Task 12）、`GET/POST /academy/plan`（Task 13）；`utils/cards.js computeImagePath`（牌图）；`utils/subscribe.js maybePromptSubscribe`（计划页提醒开启引导）；E3 token
- 交互要点（设计 1.2）：学堂主页 = 星空书卷：78 星点环（大阿卡纳 22 亮金 + 小阿卡纳 56 按四元素配色，已学点亮/未学淡星尘点——与手账夜空同语言）；进度文案"78 颗星里，你已经点亮了 N 颗"；四路径卡：愚者之旅/四元素庭院/今日之牌/与你相遇的牌；计划设置面板：每日 N 张（1/3/5）+ 提醒开关（默认关 + 明示"学习提醒日，当天星光晨讯/星语将换成今日学牌" + quota_warning 引导授权）；学习卡页：牌面大图 + 星光色描边（取牌元素色）+ 四区块渐进展开（关键词 3 星光词 → 符号解读 → 典故 → 生活关联）；「我已记住 ✦」→ POST /academy/learned → toast"这颗星，为你点亮 ✦" + 星点转亮动效 + 里程碑弹层；「问小星」入口 → chat 页；空态"78 颗星在书卷里等你——从愚者之行走起"
- 复用: 手账夜空视觉语言（journal 页样式）；utils/cards.js；maybePromptSubscribe；E3 token；utils/animate.js（星点转亮/星光雨动效）。

- [ ] **Step 1: 前端实现**：academy 主页（星图 + 四路径 + 计划设置）+ lesson 学习卡页 + 入口/互链
- [ ] **Step 2: 模拟器验证**：星图渲染、四路径进入、学习卡四区块渐进、我已记住点亮 + toast、计划设置开关、百科互链、空态（`simulator_screenshot` 遍历）
- [ ] **Step 3: commit**：`git commit -m "feat: 星灵学堂主页+学习卡页 (T6-5)"`

**验收:** 模拟器截图确认星图/四路径/学习卡/里程碑动效渲染；console 无 error。

### Task 17（设计 T6-6）: 陪学对话 UI + 称号/壁纸庆祝 + 阶段 3 发布

**Files:**
- Create: `miniapp/pages/academy/chat/chat.js/json/wxml/wxss`（半屏对话页）
- Modify: `miniapp/pages/academy/lesson/lesson.js/wxml`（「问小星」→ chat 页，带 card_id）
- Modify: `miniapp/pages/academy/academy.js/wxml`（里程碑庆祝：全屏星光雨动效 + 称号授予弹层——全通大阿卡纳/全通 78 张时）
- Modify: `miniapp/pages/profile/profile.js/wxml/wxss`（称号展示：我的页星阶区徽章行——GET /academy/overview titles，与星阶徽章并列）
- Modify: `miniapp/app.json`（subPackage pages/academy/ 加 "chat/chat"）
- Test: 模拟器

**Interfaces:**
- Consumes: `POST /academy/chat`（Task 15）、`GET /academy/overview`（titles，Task 13）
- 交互要点（设计 1.2）：气泡式对话（小星头像 = 星灵·小星形象，复用星语/手账小星视觉；星光色气泡）；回答 ≤200 字；底部常驻「仅供娱乐 · 星光映照」小字；降级文案原样展示；免费配额提示（"今日还可问 2 次"）；我的页称号徽章与星阶徽章并列（星辉学者/星光塔罗师）
- 复用: 星灵·小星形象资产；E3 token；utils/animate.js 星光雨。

- [ ] **Step 1: 前端实现**：chat 半屏页 + 庆祝动效 + 称号徽章行
- [ ] **Step 2: 模拟器验证**：问小星对话（气泡/配额提示/降级文案）、里程碑星光雨、我的页称号徽章（`simulator_screenshot` 遍历）
- [ ] **Step 3: 阶段 3 发布**：后端部署 rsync（同 Task 5 命令）→ 服务器 `alembic upgrade head`（新增 aa00dd11ee22/bb11ee22ff33/cc22ff33aa44 迁移；累计 6 个 P2 迁移全部应用）→ `systemctl restart tarot-api` → curl 健康检查；上传体验版 `node /home/a/bin/mcp-wechatide.js upload '{"project":"E:\\tarot-miniapp\\miniapp","upload-version":"v2.8.0","upload-desc":"P2阶段3: 星灵学堂+陪学小星+学习提醒"}'`
- [ ] **Step 4: 发布说明（随阶段 3 发布一并告知用户）**：开启学习提醒后，当日 7:37 晨讯/21:00 星语将换成"今日学牌"内容（仍 1 条/天，不新增条数）；学习提醒默认关闭；共鸣展示用途已写入隐私协议材料
- [ ] **Step 5: commit + 验证报告**：`git commit -m "feat: 陪学对话UI+庆祝动效+称号展示 (T6-6)"`；最终报告：三阶段改动清单 + 全量测试结果（全绿）+ 迁移核对（6 个 P2 迁移）+ 真机验证点清单（共鸣/解锁支付/学牌/陪学/学习提醒）

**验收:** 陪学链路可用（含降级）；称号徽章行展示；三阶段全部功能线上可用；发布说明覆盖学习提醒行为变化。

---

## Self-Review 记录

- **Spec 覆盖**：设计文档三功能 × 17 设计任务全部对应——星友圈 T8-1~T8-5（Task 1-5）、月报 T7-1~T7-6（Task 6-11）、学堂 T6-1~T6-6（Task 12-17）；用户决策 5 条全部落实（学习提醒占额度默认关闭=Task 13/14、月报定价 4.9/19.9 会员免费=Task 8、星友圈独立入口=Task 4/5、默认参与+一键隐身=Task 2/3/5、实施顺序 星友圈→月报→学堂=三阶段顺序）；3 次阶段发布（Task 5/11/17 = v2.6.0/v2.7.0/v2.8.0）对应设计"五、P2 实施路线"的 3 次发布要求
- **类型一致性**：`star_resonances/uq_from_to_date/star_alias/resonance_visible` 贯穿 Task 1-5；`resonance_wall_rate_limit` 贯穿 Task 2/3；`star_reports/report_type/period_key/source` 贯穿 Task 6-11；`weekly_report_unlocked/monthly_report_unlocked` 贯穿 Task 8/10/11；`star_learning_progress/uq_user_card/academy_milestones` 贯穿 Task 12/13/14/16；`star_learning_plans/reminder_on/cards_per_day` 贯穿 Task 13/14/16；`academy_chat_count_today` 贯穿 Task 15/16/17；`_learning_reminder_event` 三态与 P1 既有 `_astral_morning_event`/`get_moon_push_event` 共用同一优先级链；`GET /report/weekly` 保留不动（Task 6 抽取无回归）；无一处签名断链
- **无 TBD**：迁移文件名/版本号（v2.6.0→v2.7.0→v2.8.0）/部署命令/测试命令均给出可执行值；文案库（40 词星名词库、月报降级模板、学习提醒 thing 模板、海报固定句）均为定稿任务（含 compliance 扫描测试），非占位；里程碑 5 档奖励数值与设计用户决策一致（封顶 +19）；模板 ID 沿用 P0/P1 配置语义（未配置则推送链路整体跳过，属既有优雅降级而非占位）
