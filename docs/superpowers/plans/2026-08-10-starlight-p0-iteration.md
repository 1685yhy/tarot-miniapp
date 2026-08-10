# 星光映照 P0 四补丁实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 第 1 期 P0 四补丁：今日星光卡升级（星光色/数/宜忌）+ 星光晨讯（订阅消息）+ 星尘签到/星阶 + 星光名片（分享海报升级）

**Architecture:** 后端 FastAPI（backend/，venv=backend/venv，测试 `cd backend && ./venv/bin/python -m pytest`，SQLite+aiosqlite，alembic 迁移）；前端微信小程序（miniapp/，E3 奶油疗愈 token 在 miniapp/styles/common.wxss）。星尘/星阶挂在现有 User 表；星象宜忌复用 energy_engine 的天文事件表；星光晨讯复用 daily_push 定时任务 + 新增订阅额度表；星光名片升级 share-poster 组件 + 新增名片落地页。

**Tech Stack:** FastAPI / SQLAlchemy async / alembic / 微信小程序原生 / 微信订阅消息 API / 微信小程序码 API

## Global Constraints

- 设计文档：docs/superpowers/specs/2026-08-10-starlight-iteration-design.md（命名体系：今日星光/星尘/星阶/星光名片/星光晨讯/星象宜忌）
- E3 token：底 #FAF6EF、卡面 #FFFDF8、墨 #3D3A36（正文≥4.5:1）、细金 #A98B5F、暖金 #8A6B3D（CTA）
- 合规红线：结果页/海报带「仅供娱乐」；禁"必/绝对/改运/化解/转运"措辞；宜忌绑定真实天文事件；推送 1 条/天封顶可关闭
- 星光晨讯发送时间 7:37（非整点）；订阅消息=一次性订阅（授权 1 次=1 条额度）
- 测试纪律：每个任务 TDD（先写测试→见红→实现→见绿→commit）；后端测试基线 318 全绿
- 数据库改动必须走 alembic 迁移（新迁移文件放 backend/alembic/versions/）

---

### Task 1: 用户表新增星尘/星阶字段

**Files:**
- Modify: `backend/app/models/user.py`
- Create: `backend/alembic/versions/<hex>_add_stardust_fields.py`
- Test: `backend/tests/test_stardust.py`

**Interfaces:**
- Produces: `User.stardust_total: int (default 0)`, `User.star_tier: int (default 0)`；星阶阈值常量 `STAR_TIERS = [(0,"微光"),(7,"星光"),(30,"星辉"),(100,"星冠")]` 放 `backend/app/services/stardust.py`

- [ ] **Step 1: 写失败测试**（`backend/tests/test_stardust.py`）：建用户后 stardust_total/star_tier 默认 0；`tier_for(0)==0`、`tier_for(7)==1`、`tier_for(29)==1`、`tier_for(30)==2`、`tier_for(100)==3`；`tier_name(3)=="星冠"`
- [ ] **Step 2: 跑测试确认失败**：`./venv/bin/python -m pytest tests/test_stardust.py -v` → FAIL（模块不存在）
- [ ] **Step 3: 实现**：创建 `backend/app/services/stardust.py`（STAR_TIERS 常量 + `tier_for(stardust:int)->int` + `tier_name(tier:int)->str`）；User 模型加两字段
- [ ] **Step 4: 迁移**：`./venv/bin/python -m alembic revision --autogenerate -m "add stardust fields"` 后手工核对迁移文件只含新增两列，然后 `alembic upgrade head`；若 autogenerate 不可用则手写迁移（add_column 两列 default 0）
- [ ] **Step 5: 跑测试全绿 + commit**：`pytest tests/test_stardust.py -v` PASS；`git add -A && git commit -m "feat: 星尘/星阶字段+阈值服务"`

### Task 2: 签到接口扩展星尘/星阶（星光馈赠+收集星尘）

**Files:**
- Modify: `backend/app/api/tasks.py:56-155`（checkin 接口）
- Modify: `backend/app/schemas/tasks.py`（CheckInResponse 加字段）
- Test: `backend/tests/test_stardust.py`（追加）

**Interfaces:**
- Consumes: `stardust.tier_for/tier_name`（Task 1）
- Produces: `POST /tasks/checkin` 响应新增 `stardust_total:int, star_tier:int, star_tier_name:str`；签到成功 stardust_total+1（每用户每天限 1 次，已由 uq_user_checkin_date 保证）

- [ ] **Step 1: 写失败测试**：签到两次（同一天第 2 次返回已签到）→ 第一次后 stardust_total==1；`GET /tasks/status` 返回 stardust_total/star_tier
- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现**：tasks.py checkin 成功后 `user.stardust_total += 1; user.star_tier = tier_for(user.stardust_total)`；status 接口补字段；schema 补 3 字段
- [ ] **Step 4: 跑测试全绿 + commit**：`git commit -m "feat: 签到收集星尘+星阶升级"`

### Task 3: 星象宜忌引擎 + horoscope/daily 加字段

**Files:**
- Modify: `backend/app/services/energy_engine.py`（新增 `build_today_guidance(date, zodiac) -> dict`）
- Modify: `backend/app/api/horoscope.py`（daily 响应加 star_color/star_number/advice_do/advice_dont）
- Modify: `backend/app/schemas/horoscope.py`
- Test: `backend/tests/test_horoscope.py`（追加）

**Interfaces:**
- Consumes: `energy_engine.astral_events_on/moon_phase_on/moon_sign_on`（已有）
- Produces: `build_today_guidance()` 返回 `{"star_color": "#A98B5F", "star_number": int(1-9), "advice_do": str, "advice_dont": str}`；star_number 由日期确定性派生（如日期数字和 mod 9 +1）；advice 由当天天文事件决定（新月→「宜·许下心愿/忌·急于求成」、满月→「宜·复盘整理/忌·冲动决定」、水逆→「宜·慢下来/忌·重大签约」、无事件→中性积极文案）；文案库 ≥12 条，全部积极开放向、禁预测词

- [ ] **Step 1: 写失败测试**：build_today_guidance 返回 4 字段且类型正确；同一日期确定性一致；不同事件日文案不同（构造新月日/满月日断言）；文案不含禁用词（必/绝对/改运/化解/转运）
- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现**：energy_engine.py 加 build_today_guidance（复用 astral_events_on）；horoscope.py daily 响应并入 guidance 字段；schema 更新
- [ ] **Step 4: 全量回归**：`pytest -q` 318+ 全绿
- [ ] **Step 5: commit**：`git commit -m "feat: 星象宜忌引擎+今日星光卡数据"`

### Task 4: 前端今日星光卡升级（星光色/数/宜忌）

**Files:**
- Modify: `miniapp/pages/index/index.wxml`（能量卡下加三行：星光色·星光数·星象宜忌）
- Modify: `miniapp/pages/index/index.wxss`（E3 token）
- Modify: `miniapp/pages/index/index.js`（接 horoscope/daily 新字段）
- Modify: `miniapp/utils/energy.js`（若前端有 fallback 数据生成逻辑，同步加宜忌 fallback）

**Interfaces:**
- Consumes: Task 3 的接口字段

- [ ] **Step 1: 前端实现**：index 页能量卡下方加一行"星光色【色块】 · 星光数 7 · 星象宜忌：宜·表达心意 / 忌·独自纠结"（色块用暖金/细金系 12 色轮）；数据缺失时优雅隐藏
- [ ] **Step 2: 模拟器验证**：微信开发者工具打开首页，确认渲染无错、颜色/文案正确（MCP: `node /home/a/bin/mcp-wechatide.js simulator_screenshot '{"project":"E:\\tarot-miniapp\\miniapp"}'`）
- [ ] **Step 3: commit**：`git commit -m "feat: 今日星光卡星光色/数/宜忌"`

### Task 5: 星光晨讯（订阅额度 + 发送任务）

**Files:**
- Create: `backend/app/models/subscribe_quota.py`（SubscribeQuota: user_id PK、quota_available int、last_sent_date Date、updated_at）
- Create: `backend/alembic/versions/<hex>_add_subscribe_quota.py`
- Modify: `backend/app/api/notify.py`（新增 POST /notify/subscribe-grant：用户授权后调用，quota+1；改造 trigger_daily_push 为按额度消费发送）
- Modify: `backend/app/services/daily_push.py`（发送逻辑：取有额度且未发过今日的用户，7:37 发送「今日星光」；成功后 quota-1、记 last_sent_date）
- Modify: `backend/app/config.py`（WX_TEMPLATE_DAILY_CARD 已有；新增 SEND_TIME="07:37"）
- Test: `backend/tests/test_subscribe.py`

**Interfaces:**
- Consumes: horoscope 每日数据（Task 3 字段）、`wx_token.get_access_token()`（已有）
- Produces: `POST /notify/subscribe-grant`（auth 后 quota+1）；`daily_push` 循环发送订阅消息（template_id=WX_TEMPLATE_DAILY_CARD，data 含今日星光一句话+能量+星光色/数/宜忌）；同用户同日最多 1 条

- [ ] **Step 1: 写失败测试**：grant 后 quota==1；发送后 quota==0 且 last_sent_date==今天；同日重复发送被跳过；quota==0 不发
- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现**：模型+迁移；notify.py grant 接口；daily_push 按额度+last_sent_date 过滤发送（复用现有 access_token/发送封装，参考现有 trigger_daily_push 实现）
- [ ] **Step 4: 全量回归 + commit**：`pytest -q` 全绿；`git commit -m "feat: 星光晨讯订阅额度+定时发送"`

### Task 6: 前端订阅引导（星光晨讯授权）

**Files:**
- Modify: `miniapp/pages/daily-card/daily-card.js`、`miniapp/pages/reading-result/reading-result.js`、`miniapp/pages/wish/wish.js`（占卜/许愿完成后弹 wx.requestSubscribeMessage，模板 ID 从配置读，同意后调 POST /notify/subscribe-grant）
- Modify: `miniapp/utils/config.js`（WX_SUBSCRIBE_TEMPLATE_DAILY 常量，默认空=不弹）
- 引导文案：「订阅后，明早 7:37 收到你的今日星光」

**Interfaces:**
- Consumes: Task 5 的 grant 接口

- [ ] **Step 1: 实现**：抽牌结果页/许愿成功页/每日一牌翻转后弹订阅（模板未配置时不弹、用户拒绝不重弹、同会话最多 1 次）；同意→调 grant
- [ ] **Step 2: 模拟器验证**：走通一次抽牌→订阅弹窗→grant 请求成功（console 无 error）
- [ ] **Step 3: commit**：`git commit -m "feat: 星光晨讯订阅引导"`

### Task 7: 星光名片（分享海报升级 + 落地页 + 小程序码）

**Files:**
- Create: `miniapp/pages/card-landing/card-landing.js/json/wxml/wxss`（scene 参数落地页：展示名片卡面+星阶+星光数+「扫码加入星光映照」）
- Modify: `miniapp/components/share-poster/share-poster.js/wxml`（海报加星阶徽章+星光数+小程序码位）
- Modify: `miniapp/pages/reading-result/reading-result.js`（结果页分享入口改用星光名片样式）
- Modify: `miniapp/app.json`（注册 card-landing 页）
- Modify: `backend/app/api/share.py`（新增 GET /share/wxacode：调微信 getwxacodeunlimit 生成带 scene=userid 的小程序码，缓存 7 天）
- Test: `backend/tests/test_share.py`（追加 wxacode 接口测试：未登录 401、成功返回 image/png）

**Interfaces:**
- Consumes: `wx_token.get_access_token()`；User.invite_code（已有）
- Produces: `GET /share/wxacode` → PNG 字节流

- [ ] **Step 1: 后端测试+实现**：test_share.py 加 wxacode 用例；share.py 实现（wxacodeunlimit，scene=invite_code，page=pages/card-landing/card-landing，env_version=trial 保持体验版可用）
- [ ] **Step 2: 前端落地页**：card-landing 读取 scene（invite_code→查用户星阶/星光数/昵称），展示星光名片样式卡
- [ ] **Step 3: share-poster 升级**：海报版式加星阶徽章+星光数+小程序码（从 /share/wxacode 拉取），保持 E3 风格；海报底部「仅供娱乐 · 星光映照」
- [ ] **Step 4: 模拟器验证**：分享流程跑通（海报生成无 404、小程序码可拉取）
- [ ] **Step 5: 全量回归 + commit**：`pytest -q` 全绿；`git commit -m "feat: 星光名片海报+落地页+小程序码"`

### Task 8: 部署 + 重新上传体验版

**Files:** 无代码改动

- [ ] **Step 1: 后端部署**：`rsync -avz -e "sshpass -p 'Asdfghjkl123!!' ssh -o StrictHostKeyChecking=no" --exclude="__pycache__" --exclude="*.pyc" --exclude=".env" --exclude="venv" --exclude="data" --exclude="certs" app/ root@124.221.233.214:/opt/tarot/backend/app/`；服务器 `alembic upgrade head`（/opt/tarot/backend 下）；`systemctl restart tarot-api`；curl 健康检查
- [ ] **Step 2: 服务器 .env**：WX_TEMPLATE_DAILY_CARD 填用户申请的模板 ID（用户提供后）；SEND_TIME=07:37（默认即可）
- [ ] **Step 3: 上传体验版**：`node /home/a/bin/mcp-wechatide.js upload '{"project":"E:\\tarot-miniapp\\miniapp","upload-version":"v2.2.0","upload-desc":"P0四补丁: 今日星光卡/星光晨讯/星尘签到星阶/星光名片"}'`
- [ ] **Step 4: 汇报**：改动清单+测试结果+用户待办（模板 ID 申请、真机验证点）

## Self-Review 记录
- Spec 覆盖：四补丁全部对应 Task 1-7（星光卡 Task3-4、晨讯 Task5-6、签到星阶 Task1-2、名片 Task7）；合规红线落在各任务文案要求；分期路线第 1 期 = 本计划全部
- 类型一致性：stardust_total/star_tier/tier_for/tier_name 贯穿 Task1-2；build_today_guidance 贯穿 Task3-4；SubscribeQuota/quota_available 贯穿 Task5-6；/share/wxacode 贯穿 Task7
- 无占位符（模板 ID 属用户待办，代码以配置空值优雅降级）
