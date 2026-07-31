# 星光映照 · 增长&变现实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 三阶段推进星光映照从审核上线到获客增长再到变现转化，内容引擎+裂变增长+产品体验三线并行。

**Architecture:** 前端（微信小程序 / WXML+WXSS+JS）无需改动架构；后端（FastAPI+SQLAlchemy）已有 share API 和 track/invite 端点；新增公众号/小红书/视频号内容运营体系；数据埋点依托已有 analytics 模块扩展。

**Tech Stack:** WeChat Mini Program (WXML/WXSS/JS), FastAPI (Python), SQLite (生产), Canvas 2D API, 微信小程序码 API

**Spec:** `docs/superpowers/specs/2026-07-31-starlight-growth-monetization-design.md`

## Global Constraints

- 所有付费入口必须在"解读完成之后"展示，不允许在解读过程中出现
- 不做诱导分享（"转发到N个群解锁"），不做付费弹窗打断体验
- 微信审核通过是硬门槛，P0必须先过审
- 品牌调性：深靛蓝+暖金，温暖陪伴，AI塔罗镜子不是预言
- 目标用户：都市女性22-35（主）+ 女大学生18-22（兼）
- 微信小程序平台限制：无CSS Grid、Flexbox only、无DOM操作

---

## Phase 0 — 审核上线 + 基础设施 (预计2-3周)

### Task 0.1: 微信审核材料终审

**Files:**
- Review: `docs/wechat-review/category-explanation.md`
- Review: `docs/wechat-review/no-superstition-statement.md`
- Review: `docs/wechat-review/privacy-policy.md`
- Review: `docs/wechat-review/user-agreement.md`
- Review: `docs/wechat-review/test-account.md`
- Review: `docs/wechat-review/REGISTRATION-GUIDE.md`

**Interfaces:**
- Consumes: 无
- Produces: 审核材料复核完毕，每份文档标注"通过/需修改/缺"

- [ ] **Step 1: 逐份复核审核材料**

逐份打开 docs/wechat-review/ 下的文件，核验：
- 类目说明：微信"生活服务-咨询"类目要求是否匹配，条款引用是否最新
- 无迷信承诺书：是否明确声明"非算命/非预测/仅供娱乐参考"，措辞是否符合微信审核标准
- 隐私政策：列出的数据收集项与 `miniapp/app.js` 和 `backend/app/models/` 中实际收集的数据是否一致
- 用户协议：免责条款、退款条款是否清晰
- 测试账号：账号是否可在生产服务器登录并走完完整流程
- 注册指南：微信公众平台的配置步骤是否完整

- [ ] **Step 2: 标注并记录问题**

对每个文件标注状态：✅ 通过 / ⚠️ 需修改（记录具体问题）/ ❌ 缺失。生成一份复核清单。

- [ ] **Step 3: 修复发现的问题**

按复核清单逐项修复材料内容。

- [ ] **Step 4: Commit**

```bash
git add docs/wechat-review/
git commit -m "review: 微信审核材料终审 — 逐份复核并修复

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 0.2: 截取6张审核截图

**Files:**
- Create: `docs/wechat-review/screenshots/01-home.png`
- Create: `docs/wechat-review/screenshots/02-reading.png`
- Create: `docs/wechat-review/screenshots/03-result.png`
- Create: `docs/wechat-review/screenshots/04-membership.png`
- Create: `docs/wechat-review/screenshots/05-diary.png`
- Create: `docs/wechat-review/screenshots/06-encyclopedia.png`

**Interfaces:**
- Consumes: 小程序在微信开发者工具中运行
- Produces: 6张审核用截图，展示主要功能页面

- [ ] **Step 1: 确认小程序在微信开发者工具中正常运行**

检查：`curl -s https://xingxiang.chat/health` 确认服务器在线。打开微信开发者工具，导入 `/mnt/e/tarot-miniapp/miniapp`，确认编译通过、无 console 红色报错。

- [ ] **Step 2: 逐页截图**

在微信开发者工具中截取：
1. 首页 — 每日一牌区域、星空背景、品牌名称清晰
2. 占卜页 — 牌阵选择、翻牌交互
3. 结果页 — AI解读文本、角色标识、操作按钮
4. 会员页 — 定价方案、对比表
5. 日记页 — 日记列表或空状态
6. 百科页 — 卡牌列表或详情

保存到 `docs/wechat-review/screenshots/`。

- [ ] **Step 3: 检查截图质量**

确认每张图：无loading骨架、无断网占位、无console报错浮窗、无开发调试标记。

- [ ] **Step 4: Commit**

```bash
git add docs/wechat-review/screenshots/
git commit -m "assets: 微信审核6张功能截图

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 0.3: 配置微信公众平台服务器域名

**此任务需要PM在微信公众平台手动操作，不可自动化。**

- [ ] **Step 1: 登录微信公众平台**

打开 https://mp.weixin.qq.com → 使用小程序注册邮箱登录 → 进入「开发」→「开发管理」→「开发设置」

- [ ] **Step 2: 配置服务器域名**

在「服务器域名」栏配置：
- request合法域名: `https://xingxiang.chat`
- socket合法域名: `wss://xingxiang.chat`
- uploadFile合法域名: `https://xingxiang.chat`
- downloadFile合法域名: `https://xingxiang.chat`

- [ ] **Step 3: 配置业务域名**

在「业务域名」栏添加: `xingxiang.chat`

- [ ] **Step 4: 关联商户号**

在「微信支付」→「商户号管理」关联: `MCHID-REDACTED`

- [ ] **Step 5: 添加开发者**

在「成员管理」中添加IDE登录的微信账号为「开发者」

### Task 0.4: 首页元素精简 — 每日一牌占首屏60%

**Files:**
- Modify: `miniapp/pages/index/index.wxml:29-336`
- Modify: `miniapp/pages/index/index.wxss`
- Modify: `miniapp/pages/index/index.js`

**Interfaces:**
- Consumes: 现有 index 页面完整代码
- Produces: 首页内容重排，每日一牌区域占据首屏60%可视区域，其余内容移至下方需滚动查看

- [ ] **Step 1: 重构 index.wxml 布局顺序**

将每日一牌区域（`daily-card-wrap`）移到 hero 区正下方，占据视觉主干。将星光树洞/未完成解读/日记入口/免费次数/会员CTA/牌阵选择等全部放到统一的"below-fold"容器中，加注释标记"以上是首屏 / 以下需滚动"。

核心改动：将当前 index.wxml 从分散的 anim-fade-in-up 块重构为清晰的 Zone 1（首屏卡片）+ Zone 2（滚动区）。

- [ ] **Step 2: 调整 WXSS — Zone 1 占 60vh**

给每日一牌区域加 `min-height: 60vh` 的 flex 容器，确保在任何屏幕上首屏只看到卡片+品牌名+tagline。

- [ ] **Step 3: 调整 WXSS — 减少 Zone 1 元素**

首屏只保留：品牌名"星光映照"、副标题"每日一牌，遇见自己"、每日一牌卡片、今日更新标识。其他全部移入 Zone 2。

- [ ] **Step 4: 验证**

在微信开发者工具中切换不同机型（iPhone SE/12/14 Pro Max），确认每日一牌占据首屏60%以上，且不会遮挡关键信息。

- [ ] **Step 5: Commit**

```bash
git add miniapp/pages/index/
git commit -m "refactor: home page content hierarchy — daily card takes 60vh above fold

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 0.5: 动画瘦身 — 移除冗余动画效果

**Files:**
- Modify: `miniapp/pages/index/index.wxss`
- Modify: `miniapp/pages/index/index.wxml`
- Modify: `miniapp/pages/index/index.js`

**Interfaces:**
- Consumes: 当前 2107 行 index.wxss 中的动画定义
- Produces: 动画从 20+ 种缩减到 10 种以内

- [ ] **Step 1: 移除 shimmer sweep 效果**

在 index.wxss 中删除 `.card-shimmer` 及其 `@keyframes shimmer-sweep` 定义。在 index.wxml 中移除对应 class 引用。

- [ ] **Step 2: 移除轨道光点动画**

删除 `.sparkle-orbit` 相关动画（`.s1`-`.s6` 的旋转动画）。保留静态光点，移除 `@keyframes orbit-spin`。

- [ ] **Step 3: 移除呼吸辉光叠加层**

删除 `.daily-card-glow-overlay` 和 `@keyframes card-glow-breathe`。保留微弱的边框 glow（`box-shadow` 静态），不做呼吸动画。

- [ ] **Step 4: 移除流星彩蛋**

在 index.wxml 中删除 shooting-star 相关元素（如有）。在 WXSS 中删除 `@keyframes shooting-star-fly`。在 JS 中删除触发流星计时的代码。

- [ ] **Step 5: 移除视差星空漂移**

将 `.stars-distant`/`.stars-mid`/`.stars-close` 的 `animation` 属性移除，改为静态定位。

- [ ] **Step 6: 减少光点粒子**

将 sparkle 从 6 个减少到 3 个（保留 s1/s2/s3，删除 s4/s5/s6）。

- [ ] **Step 7: 验证 reduced-motion 覆盖**

检查 `@media (prefers-reduced-motion: reduce)` 规则仍然覆盖所有保留的动画。确保动画开关生效。

- [ ] **Step 8: Commit**

```bash
git add miniapp/pages/index/
git commit -m "refactor: animation audit — remove shimmer/sparkle orbit/shooting star/parallax drift, reduce sparkle particles 6→3

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 0.6: 解读结果页 — 移除撤销按钮和深度解锁卡片

**Files:**
- Modify: `miniapp/pages/reading-result/reading-result.wxml`
- Modify: `miniapp/pages/reading-result/reading-result.wxss`
- Modify: `miniapp/pages/reading-result/reading-result.js`

**Interfaces:**
- Consumes: 当前 reading-result 页面完整代码
- Produces: 移除"撤销解读"按钮和"深度解锁"卡片

- [ ] **Step 1: 移除撤销解读按钮**

在 WXML 中找到 `undo reading` 按钮元素并删除。在 JS 中删除对应的 `onUndoReading` 方法（如存在）。清理 WXSS 中的撤销按钮样式。

- [ ] **Step 2: 移除深度解锁卡片**

在 WXML 中找到 `depth unlock` 或"升级深度解读"相关卡片元素并删除。在 JS 中移除对应的事件处理和状态。

- [ ] **Step 3: 验证**

确认解读结果页无 UI 残留（空位/断裂的布局）。确认移除后不影响正常解读流程。

- [ ] **Step 4: Commit**

```bash
git add miniapp/pages/reading-result/
git commit -m "refactor: remove undo reading button and depth unlock card from result page

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 0.7: 解读结果页 — 解读文本默认全部展开

**Files:**
- Modify: `miniapp/pages/reading-result/reading-result.wxml`
- Modify: `miniapp/pages/reading-result/reading-result.wxss`
- Modify: `miniapp/pages/reading-result/reading-result.js`

**Interfaces:**
- Consumes: 当前解读结果页的折叠/展开逻辑
- Produces: 解读文本始终完整显示，移除折叠UI

- [ ] **Step 1: 移除折叠/展开切换逻辑**

在 WXML 中找到解读文本的折叠容器和"展开全文"按钮，改为直接渲染完整文本。在 JS 中删除 `expanded` 状态和 `onToggleExpand` 方法。

- [ ] **Step 2: 调整文本区域样式**

解读文本区域取消 `max-height` + `overflow: hidden`，改为自然高度。确保超长文本可正常滚动。

- [ ] **Step 3: Commit**

```bash
git add miniapp/pages/reading-result/
git commit -m "refactor: always expand interpretation text — remove collapse UI

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 0.8: 无障碍 — aria-label 全量覆盖

**Files:**
- Modify: `miniapp/pages/index/index.wxml`
- Modify: `miniapp/pages/reading-result/reading-result.wxml`
- Modify: `miniapp/pages/chat/chat.wxml`
- Modify: `miniapp/pages/membership/membership.wxml`
- Modify: `miniapp/pages/diary/diary.wxml`
- Modify: `miniapp/pages/profile/profile.wxml`
- Modify: `miniapp/pages/encyclopedia/encyclopedia.wxml`
- Modify: `miniapp/pages/reading/reading.wxml`
- Modify: `miniapp/pages/checkin/checkin.wxml`
- Modify: `miniapp/pages/community/community.wxml`
- Modify: `miniapp/pages/daily-card/daily-card.wxml`
- Modify: `miniapp/pages/card-detail/card-detail.wxml`
- Modify: `miniapp/pages/about/about.wxml`
- Modify: `miniapp/pages/share-center/share-center.wxml`
- Modify: `miniapp/utils/a11y.js` (如需要)

**Interfaces:**
- Consumes: 现有所有页面的 WXML
- Produces: 所有 `bindtap` 的 `view` 元素添加 `role="button"` + `aria-label`，所有 `image` 添加 `aria-label`

- [ ] **Step 1: 审计所有交互元素**

用 grep 扫描所有 WXML 文件中 `bindtap` 但缺少 `role="button"` 或 `aria-label` 的 `view` 元素。

```bash
cd /mnt/e/tarot-miniapp/miniapp
grep -rn 'bindtap' pages/ --include="*.wxml" | grep -v 'aria-label' | grep -v '<button'
```

- [ ] **Step 2: 批量添加 aria-label**

对审计出的每个元素添加 `role="button"` 和语义化的 `aria-label`。例如：
- 牌阵卡片：`aria-label="选择三牌占卜牌阵"`
- 日记入口：`aria-label="记录今天的日记"`
- 会员CTA：`aria-label="升级星光会员"`

- [ ] **Step 3: 审核图片 alt 文本**

用 grep 扫描所有 `image` 标签缺少 `aria-label` 的情况，逐一补充。

- [ ] **Step 4: Commit**

```bash
git add miniapp/pages/ miniapp/utils/a11y.js
git commit -m "a11y: full aria-label coverage — all tappable views + images across 14 pages

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 0.9: 加载速度 — 解读loading从4s优化到≤1.5s

**Files:**
- Modify: `miniapp/pages/reading/reading.js`
- Modify: `miniapp/pages/reading/reading.wxml`
- Modify: `miniapp/pages/reading/reading.wxss`
- Modify: `backend/app/api/readings.py`

**Interfaces:**
- Consumes: 当前3阶段加载动画（shuffle→flip→interpret ~4秒）+ 后端解读生成逻辑
- Produces: 默认快速模式（骨架屏0.8s→内容）、沉浸模式（可选，单阶段脉冲≤2s）

- [ ] **Step 1: 前端 — 快速模式默认启用**

在 `reading.js` 中将加载模式默认值从"沉浸式"改为"快速模式"。快速模式显示 skeleton 800ms，然后直接展示结果。删除 3 阶段加载动画的 WXML 元素和 WXSS。

- [ ] **Step 2: 前端 — 沉浸模式精简**

保留沉浸模式作为可选（用户手动切换），但将动画减少为单阶段"正在解读..."脉冲，最长 2 秒。

- [ ] **Step 3: 后端 — 检查解读生成耗时**

在 `backend/app/api/readings.py` 中检查解读接口，确认是否有可优化的慢查询或重复计算。如有，使用缓存或并行请求优化。

- [ ] **Step 4: 验证**

在微信开发者工具中测试：点击牌阵 → 开始解读，记录从点击到看到结果的时间。目标 ≤1.5s。

- [ ] **Step 5: Commit**

```bash
git add miniapp/pages/reading/ backend/app/api/readings.py
git commit -m "perf: reduce reading load time 4s→1.5s — default quick mode, single-stage immersive

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 0.10: 内容引擎 — 公众号基础搭建

**此任务由Claude辅助PM完成内容准备，实际操作在微信公众平台。**

- [ ] **Step 1: 确认公众号主体**

确认公众号已注册且主体信息正确。管理后台: https://mp.weixin.qq.com

- [ ] **Step 2: 品牌视觉配置**

- 头像：使用 `starlight_tarot_logo_1024.png`（在 `/home/a/` 下）裁剪为圆形
- 简介："星光映照——AI塔罗陪伴空间。塔罗是镜子，不是预言。每日一牌，遇见自己。"
- 菜单：左「每日一牌」→ 小程序链接 / 中「了解塔罗」→ 品牌故事图文 / 右「联系我们」→ 客服消息

- [ ] **Step 3: 关联小程序**

在公众号后台「小程序管理」关联小程序 AppID: `wxfc41c6b04fa892d1`

- [ ] **Step 4: 首周3篇内容初稿**

准备三篇推送初稿（保存为草稿，上线当天推送）：
1. 《塔罗不是算命，是一面镜子》— 品牌故事，阐述产品理念
2. 《本周星象 · 星光周运 8月第一周》— 开固定栏目先例
3. 《愚人：为什么最厉害的牌是"什么都不知道"》— 深度牌面解读，展示知识厚度

稿件保存在 `docs/content/wechat/` 目录下。

- [ ] **Step 5: Commit**

```bash
git add docs/content/
git commit -m "content: 公众号首周3篇初稿 + 品牌配置方案

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 0.11: 内容引擎 — 小红书账号 + 内容模板

- [ ] **Step 1: 小红书品牌视觉模板设计**

设计一套小红书图文模板（Canva或直接HTML生成导出PNG）：
- 配色：深靛蓝背景(#1A1A3E) + 暖金标题(#F4D48C) + 浅色正文(#F0EDE8)
- 版式：4:3竖版卡片，顶部吸睛标题 + 中部正文 + 底部"搜索'星光映照'小程序"
- 第一张图风格：暗色底+发光金色大字+一张卡牌图

- [ ] **Step 2: 首周3篇小红书内容初稿**

1. "AI塔罗到底准不准？我试了一个月发现..." — 个人体验视角，带小程序入口
2. "每天抽一张牌，我居然戒掉了深夜emo" — 情感共鸣+习惯养成
3. "塔罗0号牌·愚人：为什么它是所有牌里最深刻的一张" — 知识型内容

- [ ] **Step 3: 内容发布SOP文档**

创建 `docs/content/sop-publishing.md`：发布清单（标题/正文/标签/配图/发布时间/数据记录模板）。

- [ ] **Step 4: Commit**

```bash
git add docs/content/
git commit -m "content: 小红书品牌模板 + 首周3篇初稿 + 发布SOP

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 0.12: 裂变 — 分享卡片优化（每日一牌打卡图）

**Files:**
- Modify: `miniapp/components/share-poster/share-poster.js`
- Modify: `miniapp/components/share-poster/share-poster.wxml`
- Create: `miniapp/components/share-poster/daily-card-poster.js`

**Interfaces:**
- Consumes: 现有 share-poster 组件（解读结果分享）
- Produces: 新增"每日一牌打卡图"分享模式：卡牌+日期+连续N天+"星光映照"logo+小程序码

- [ ] **Step 1: 新增 daily-card-poster 模式**

在 share-poster 组件中新增 `mode` 属性，`mode="daily"` 时绘制打卡风格海报：
- 上半部：今日卡牌图像（占60%）
- 中部：卡牌名称 + 日期 + "连续第N天 ✦"
- 下部：品牌标识 + 小程序码

- [ ] **Step 2: 在首页集成分享入口**

在 `index.wxml` 每日一牌区域下方加一个低调的文字链接"保存今日卡牌"，点击打开 share-poster（mode="daily"）。

- [ ] **Step 3: 验证**

抽完每日牌后点击"保存今日卡牌" → 生成打卡图 → 保存相册成功。

- [ ] **Step 4: Commit**

```bash
git add miniapp/components/share-poster/ miniapp/pages/index/
git commit -m "feat: daily card check-in poster — card+date+streak+QR code sharing

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 0.13: 提交微信审核

- [ ] **Step 1: 上线前最终检查**

```
□ 服务器健康检查通过: curl -s https://xingxiang.chat/health
□ 所有页面无红色 console 报错
□ 审核材料6张截图完整
□ 审核材料文档复核通过
□ 服务器域名已在公众平台配置
□ 代码已全部 commit + push
```

- [ ] **Step 2: 上传代码**

在微信开发者工具中点击「上传」，版本号 `v1.2.0`，描述：「精品上线版：首页改版、动画瘦身、无障碍覆盖、分享卡片、加载优化」。

- [ ] **Step 3: 提交审核**

在微信公众平台 → 版本管理 → 选择 `v1.2.0` → 提交审核 → 上传审核材料。

- [ ] **Step 4: 等待结果**

审核通常1-7个工作日。期间P1任务可并行推进。

---

## Phase 1 — 获客增长 (预计3-4周，P0审核提交后可并行启动)

### Task 1.1: 公众号正式运营 — 周更2-3篇

- [ ] **Step 1: P0审核通过后，发布首周三篇**

将 Task 0.10 准备的三篇草稿在审核通过当天和次日依次发布。每篇底部挂小程序入口卡片。

- [ ] **Step 2: 建立内容排期节奏**

创建 `docs/content/editorial-calendar-august.md`：8月内容日历，标注每周选题和发布日期。

- [ ] **Step 3: 持续产出 — 固定栏目**

- 周一「星光周运」：十二星座本周塔罗关键词+建议
- 周三/四「牌面故事」：一张牌的深度解读
- 周六/日「树洞精选」：匿名用户日记/感悟精选

- [ ] **Step 4: Commit**

```bash
git add docs/content/
git commit -m "content: 8月内容日历 + 公众号运营SOP

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 1.2: 小红书内容分发

- [ ] **Step 1: 同步公众号内容**

将每篇公众号内容适配为小红书图文格式（标题改得更吸引人、emoji点缀、卡片式排版），当日或次日发布。

- [ ] **Step 2: 小红书专属内容**

除了公众号内容同步，每周增加1-2篇小红书专属短内容（截图式/投票式/互动式），增加互动率。

- [ ] **Step 3: 追踪数据**

每周记录每篇笔记的：浏览量/点赞/收藏/评论/小程序点击，填入内容数据表。

### Task 1.3: 视频号「每日一牌」试跑

- [ ] **Step 1: 视频模板设计**

15秒短视频模板：卡牌图像渐变出现(3s) → AI配音解读(9s) → 日期+小程序码CTA(3s)

- [ ] **Step 2: 第一周产出7条**

每天一条，测试不同卡牌的互动表现。使用Canva或剪映制作。

- [ ] **Step 3: 数据追踪**

记录每条视频的：播放量/完播率/点赞/评论/主页访问/小程序跳转。

### Task 1.4: 裂变 — 好友送牌功能

**Files:**
- Modify: `miniapp/pages/reading-result/reading-result.wxml`
- Modify: `miniapp/pages/reading-result/reading-result.js`
- Modify: `miniapp/pages/index/index.js`
- Modify: `backend/app/api/share.py`
- Modify: `backend/app/services/share.py`

**Interfaces:**
- Consumes: 已有 share API (POST /share/invite, GET /share/invite-code, GET /share/wxa-code)
- Produces: 好友送牌完整链路：用户A生成邀请→用户B扫码进入→双方自动获得奖励

- [ ] **Step 1: 前端 — 解读结果页加"送好友一张牌"按钮**

在 reading-result 页面底部按钮区添加"送好友一张牌 ✦"按钮。点击生成邀请海报（使用已有 share-poster 组件+邀请码小程码）。

- [ ] **Step 2: 前端 — 接受邀请逻辑**

在 `app.js` 的 `onLaunch` 中检查启动参数 `invite_code`。如有，调用 `POST /share/invite` 完成邀请记录，弹出 toast："好友送你一张牌！获得免费深度解读一次 ✦"

- [ ] **Step 3: 后端 — 邀请奖励发放**

确认 `process_invite()` 在 `backend/app/services/share.py` 中实现：双方各增加一次免费深度解读额度（非会员也可使用）。

- [ ] **Step 4: 验证**

完整链路测试：A生成邀请海报→B扫小程序码→B进入小程序→B看到奖励提示→A也获得奖励。

- [ ] **Step 5: Commit**

```bash
git add miniapp/ backend/
git commit -m "feat: friend invite — send a card, both get free deep reading

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 1.5: 裂变 — 星座契合度分享

**Files:**
- Create: `miniapp/pages/share-center/share-center.js` (功能扩展)
- Modify: `miniapp/pages/share-center/share-center.wxml`
- Modify: `miniapp/components/share-poster/`

**Interfaces:**
- Consumes: 用户星座数据（来自 onboarding 或 profile）+ 已有 share-poster 组件
- Produces: "你们的关系牌"分享图：A星座+B星座→关系解读+卡牌图像

- [ ] **Step 1: 后端 — 星座契合度接口**

新增 `GET /api/share/zodiac-match?sign1=天蝎&sign2=双鱼`，返回：关系卡牌ID、契合度评语（由DeepSeek生成）、分享文案。

- [ ] **Step 2: 前端 — 星座选择+分享**

在 share-center 页面新增"测测你们的关系牌"入口。两栏选择星座→点击"看结果"→生成分享海报。

- [ ] **Step 3: Commit**

```bash
git add miniapp/pages/share-center/ miniapp/components/share-poster/ backend/
git commit -m "feat: zodiac compatibility share — relationship tarot card poster

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 1.6: 产品体验 — 卡片系统精简 7→3

**Files:**
- Modify: `miniapp/styles/cards.wxss` (如存在)
- Modify: `miniapp/app.wxss`
- Modify: 所有引用 `.card-*` 变体类的 WXML 文件

**Interfaces:**
- Consumes: 当前 7 种卡片 CSS 变体（card-warm/teaching/press/reveal/rise/float/shimmer）
- Produces: 3 种卡片变体（card-default / card-interactive / card-featured）

- [ ] **Step 1: 定义 3 种目标卡片样式**

在全局样式中建立：
```css
.card-default   → 基础卡片：圆角16rpx，半透明背景，无动画
.card-interactive → 可点击卡片：inherit default + scale(0.97) on active，边框高亮
.card-featured  → 每日一牌专用：inherit default + 呼吸辉光边框 + warm渐变背景
```

- [ ] **Step 2: 逐页替换**

遍历所有页面 WXML，将 7 种旧变体映射到 3 种新变体：
- card-warm/teaching/rise → card-featured（每日一牌场景）或 card-default
- card-press → card-interactive
- card-float/shimmer/reveal → 删除（或并入 card-featured）

- [ ] **Step 3: 清理 WXSS**

删除不再使用的旧卡片类定义。更新所有受影响的样式规则。

- [ ] **Step 4: Commit**

```bash
git add miniapp/
git commit -m "refactor: consolidate 7 card CSS variants → 3 (default/interactive/featured)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 1.7: 产品体验 — strek+collection 移到profile页

**Files:**
- Modify: `miniapp/pages/index/index.wxml`
- Modify: `miniapp/pages/index/index.wxss`
- Modify: `miniapp/pages/profile/profile.wxml`
- Modify: `miniapp/pages/profile/profile.js`

**Interfaces:**
- Consumes: 首页卡面上的 streak 徽章和 collection 数据
- Produces: 卡面干净，streak/collection/阅读历史集中展示在profile页

- [ ] **Step 1: 移除首页卡面的 streak badge**

在 index.wxml 中删除每日一牌卡片上的 `.streak-badge` 元素。在 index.wxss 中清理相关样式。

- [ ] **Step 2: 在 profile 页新增"我的星光之旅"区块**

整合展示：连续打卡天数、收集卡牌数、总解读次数、日记篇数。用简洁的卡片排列（非进度条堆叠）。

- [ ] **Step 3: Commit**

```bash
git add miniapp/pages/index/ miniapp/pages/profile/
git commit -m "refactor: move streak+collection from daily card to profile page

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 1.8: 产品体验 — 解读结果页排序重排

**Files:**
- Modify: `miniapp/pages/reading-result/reading-result.wxml`
- Modify: `miniapp/pages/reading-result/reading-result.wxss`

**Interfaces:**
- Consumes: 当前结果页内容顺序
- Produces: 角色标识(顶部) → 解读文本 → 行动建议 → 可折叠深度内容 → 分享/保存/日记按钮

- [ ] **Step 1: 重排 WXML 元素顺序**

按目标层级重构元素位置：1) 星光角色标识(icon+name+"正在倾听") 2) TL;DR摘要 3) 完整解读文本 4) 行动建议清单 5) 折叠区：卡牌教学/深度分析 6) 底部按钮行

- [ ] **Step 2: 调整视觉权重**

角色标识加大、解读文本设为正常阅读字号(28rpx)、行动建议用金色左边框强调、底部按钮等距排列。

- [ ] **Step 3: Commit**

```bash
git add miniapp/pages/reading-result/
git commit -m "refactor: reading result hierarchy — persona top, interpretation hero, actions bottom

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 1.9: 产品体验 — 图片资源转WebP + 星场粒子减半

**Files:**
- Modify: `miniapp/images/cards/` 目录中的图片资源
- Modify: `miniapp/pages/index/index.wxss` (星场粒子数)

**Interfaces:**
- Consumes: 当前图片资源（可能是PNG/JPG）
- Produces: WebP格式240px宽度的缩略图 + 星场15颗粒子(从40+减半)

- [ ] **Step 1: 批量转换卡牌图片**

```bash
# 使用 ImageMagick 或类似工具
cd /mnt/e/tarot-miniapp/miniapp/images/cards/
for f in *.png; do
  convert "$f" -resize 240x -quality 80 "${f%.png}.webp"
done
```

- [ ] **Step 2: 更新图片引用路径**

在 cards.js 的 `computeImagePath()` 中将扩展名从 `.png` 改为 `.webp`。更新所有硬编码的图片路径。

- [ ] **Step 3: 星场粒子减半**

在 index.wxss 中将星空伪元素从 ~40 个 box-shadow 减少到 ~15 个。

- [ ] **Step 4: Commit**

```bash
git add miniapp/images/ miniapp/pages/index/
git commit -m "perf: convert card images to WebP 240px + reduce starfield particles 40→15

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 1.10: 数据埋点 — 关键指标追踪

**Files:**
- Modify: `miniapp/utils/analytics.js`
- Modify: `miniapp/app.js`

**Interfaces:**
- Consumes: 已有 analytics 模块
- Produces: DAU/新增/来源渠道/抽牌率/解读完成率/分享率的数据收集

- [ ] **Step 1: 扩展 analytics 模块**

在 `analytics.js` 中新增方法：
- `trackAppLaunch(options)` — 记录启动来源(scene/query参数)
- `trackDailyDraw()` — 记录每日抽牌
- `trackReadingComplete(spreadType)` — 记录解读完成
- `trackShare(channel, type)` — 记录分享行为

- [ ] **Step 2: 在关键节点埋点**

- `app.js onLaunch/onShow` → `trackAppLaunch`
- `index.js drawDailyCard` → `trackDailyDraw`
- `reading-result.js onLoad` → `trackReadingComplete`
- `share-poster onSave/onShare` → `trackShare`

- [ ] **Step 3: Commit**

```bash
git add miniapp/utils/analytics.js miniapp/app.js miniapp/pages/
git commit -m "feat: analytics instrumentation — DAU, acquisition source, core actions

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 2 — 转化变现 (预计2-3周)

### Task 2.1: 付费入口全量后移

**Files:**
- Modify: `miniapp/pages/index/index.wxml`
- Modify: `miniapp/pages/index/index.js`
- Modify: `miniapp/pages/chat/chat.wxml`
- Modify: `miniapp/pages/chat/chat.js`
- Modify: `miniapp/pages/reading-result/reading-result.wxml`

**Interfaces:**
- Consumes: 当前分散在各页面的付费CTA
- Produces: 所有付费入口统一只在"解读完成之后"出现，每个页面至多一个付费提示

- [ ] **Step 1: 移除首页的付费CTA**

删除首页的"9.9元首次AI深度解读"卡片（`hero-cta`）、"升级会员·无限解读"文字链接。首页只保留免费次数纯文字提示。

- [ ] **Step 2: 移除聊天页的付费提示**

删除聊天页底部的会员提示横幅。只在用户额度真正耗尽时，在输入框上方显示一行灰色文字："今日追问次数已用完 · 升级会员 →"

- [ ] **Step 3: 在解读结果页添加唯一的付费入口**

解读结果底部，在"分享/保存/日记"按钮之后，添加一行轻量文字："喜欢这个解读？深度模式解锁更多洞察 →"。这是全应用唯一的主动付费CTA位置。

- [ ] **Step 4: Commit**

```bash
git add miniapp/
git commit -m "refactor: move all paywall CTAs to post-reading only — one paywall, one location

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 2.2: 免费试用3天→7天

**Files:**
- Modify: `backend/app/api/membership.py`
- Modify: `backend/app/services/` (membership service)
- Modify: `miniapp/pages/membership/membership.wxml`

**Interfaces:**
- Consumes: 当前3天试用期配置
- Produces: 7天免费试用期

- [ ] **Step 1: 后端 — 修改试用期配置**

在 membership 服务中将 `TRIAL_DAYS = 3` 改为 `TRIAL_DAYS = 7`。检查任何引用3天的地方同步更新。

- [ ] **Step 2: 前端 — 更新文案**

在 membership.wxml 中将"3天免费试用"改为"7天免费试用"。确认试用到期提醒的文案也同步更新。

- [ ] **Step 3: Commit**

```bash
git add backend/ miniapp/
git commit -m "feat: extend free trial 3→7 days — longer trust-building window

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 2.3: 会员页 — 移除"星光好物"电商板块

**Files:**
- Modify: `miniapp/pages/membership/membership.wxml`
- Modify: `miniapp/pages/membership/membership.wxss`
- Modify: `miniapp/pages/membership/membership.js`

**Interfaces:**
- Consumes: membership页面的"星光好物"section（实体周边，全部标注"即将上线"）
- Produces: 移除电商板块，会员页只保留会员价值展示

- [ ] **Step 1: 删除星光好物 WXML**

删除 `shop-section` 整个区块及其所有子元素（实体塔罗牌/水晶手串/香薰蜡烛三个商品卡）。

- [ ] **Step 2: 清理 JS 和 WXSS**

删除 `onShopComingSoon` 等电商相关方法。删除 `.shop-*` 系列样式。

- [ ] **Step 3: 验证**

确认会员页布局完整，无空白缺口。定价方案和对比表正常显示。

- [ ] **Step 4: Commit**

```bash
git add miniapp/pages/membership/
git commit -m "refactor: remove 'Starlight Goods' e-commerce section — not launched, clutters membership page

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 2.4: 付费漏斗数据埋点

**Files:**
- Modify: `miniapp/utils/analytics.js`
- Modify: `miniapp/pages/membership/membership.js`
- Modify: `miniapp/pages/reading-result/reading-result.js`

**Interfaces:**
- Consumes: analytics 模块 + 各页面付费相关操作
- Produces: 免费使用→试用→付费漏斗每步数据

- [ ] **Step 1: 新增付费漏斗事件**

在 analytics.js 中添加：
- `trackTrialStart()` — 开始7天试用
- `trackPurchaseStart(product)` — 点击购买
- `trackPurchaseComplete(product, amount)` — 支付完成
- `trackPaywallView(source)` — 看到付费入口(source: reading_complete/chat_exhausted)
- `trackPaywallDismiss()` — 关闭付费提示（未转化）

- [ ] **Step 2: 在对应页面埋点**

membership.js: 试用按钮 → trackTrialStart / 购买按钮 → trackPurchaseStart
reading-result.js: 付费入口曝光 → trackPaywallView

- [ ] **Step 3: Commit**

```bash
git add miniapp/
git commit -m "feat: monetization funnel analytics — trial→paywall→purchase tracking

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 2.5: UGC内容闭环 — 用户日记精选分享

**Files:**
- Modify: `miniapp/pages/diary/diary.js`
- Modify: `miniapp/pages/diary/diary.wxml`
- Modify: `miniapp/components/share-poster/`
- Modify: `backend/app/api/diary.py`

**Interfaces:**
- Consumes: 日记数据 + share-poster组件
- Produces: 用户可将自己的日记生成匿名精美分享图

- [ ] **Step 1: 日记分享卡片**

在日记详情页添加"生成分享图"按钮。使用 share-poster 组件生成匿名卡片：日记片段（去个人信息）+ 当日卡牌图像 + 日期 + 品牌标识。

- [ ] **Step 2: 后端 — 日记匿名化**

在 diary API 中添加 GET `/diary/{id}/share-preview` 端点，返回匿名化后的日记片段（移除昵称/星座等个人信息）。

- [ ] **Step 3: Commit**

```bash
git add miniapp/pages/diary/ miniapp/components/share-poster/ backend/
git commit -m "feat: UGC diary share card — anonymous journal excerpt + daily card poster

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 2.6: AI周报分享长图

**Files:**
- Create: `miniapp/components/weekly-report-poster/`
- Modify: `miniapp/pages/profile/profile.wxml`
- Modify: `backend/app/api/report.py`

**Interfaces:**
- Consumes: AI周报数据（已存在于 report API）+ Canvas 2D
- Produces: 用户可生成"本周情绪旅程"长图分享

- [ ] **Step 1: 后端 — 周报数据接口**

确认 `GET /api/report/weekly` 返回数据包含：心情趋势、关键词汇总、最常出现的卡牌、AI一句话总结。

- [ ] **Step 2: 前端 — 周报长图组件**

新建 `weekly-report-poster` 组件，使用Canvas绘制竖版长图（9:16比例）：顶部"我的星光一周"标题 → 心情趋势小图 → 高频卡牌 → AI总结 → 底部品牌+小程序码。

- [ ] **Step 3: 在profile页集成**

在profile页"AI周回顾"区域添加"生成分享图"按钮。

- [ ] **Step 4: Commit**

```bash
git add miniapp/components/weekly-report-poster/ miniapp/pages/profile/ backend/
git commit -m "feat: AI weekly report share poster — mood journey long image

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 2.7: A/B测试 — 首次付费价格测试

**Files:**
- Modify: `miniapp/pages/reading-result/reading-result.wxml`
- Modify: `miniapp/pages/reading-result/reading-result.js`

**Interfaces:**
- Consumes: 解读结果页的付费入口
- Produces: 简单的A/B测试框架：50%用户看到9.9元，50%用户看到19.9元

- [ ] **Step 1: 实现简易A/B分流**

在 `reading-result.js` 的 `onLoad` 中，基于用户 openid 的 hash 值进行50/50分流：
```javascript
const bucket = (user.openid || '').split('').reduce((a, c) => a + c.charCodeAt(0), 0) % 2;
this.setData({ priceTestBucket: bucket === 0 ? '9.9' : '19.9' });
```

- [ ] **Step 2: 按分组渲染不同价格**

WXML 中根据 `priceTestBucket` 显示不同的价格文案和CTA文本。

- [ ] **Step 3: 追踪分组数据**

在 analytics 中记录 `priceTestBucket` 值，关联到后续的 `trackPurchaseComplete` 事件。

- [ ] **Step 4: Commit**

```bash
git add miniapp/pages/reading-result/
git commit -m "feat: A/B test — first reading price 9.9 vs 19.9 yuan

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## 总任务清单

### Phase 0 (13 tasks)
- [ ] 0.1 微信审核材料终审
- [ ] 0.2 截取6张审核截图
- [ ] 0.3 配置微信公众平台服务器域名（PM手动）
- [ ] 0.4 首页元素精简 — 每日一牌占首屏60%
- [ ] 0.5 动画瘦身 — 移除冗余动画效果
- [ ] 0.6 解读结果页 — 移除撤销和深度解锁
- [ ] 0.7 解读结果页 — 文本默认全部展开
- [ ] 0.8 无障碍 — aria-label全量覆盖
- [ ] 0.9 加载速度 — 解读loading ≤1.5s
- [ ] 0.10 内容引擎 — 公众号基础搭建
- [ ] 0.11 内容引擎 — 小红书账号+内容模板
- [ ] 0.12 裂变 — 每日一牌打卡分享图
- [ ] 0.13 提交微信审核

### Phase 1 (10 tasks)
- [ ] 1.1 公众号正式运营 — 周更2-3篇
- [ ] 1.2 小红书内容分发
- [ ] 1.3 视频号每日一牌试跑
- [ ] 1.4 裂变 — 好友送牌功能
- [ ] 1.5 裂变 — 星座契合度分享
- [ ] 1.6 产品体验 — 卡片系统精简7→3
- [ ] 1.7 产品体验 — streak+collection移到profile
- [ ] 1.8 产品体验 — 解读结果页排序重排
- [ ] 1.9 产品体验 — 图片WebP+星场粒子减半
- [ ] 1.10 数据埋点 — 关键指标追踪

### Phase 2 (7 tasks)
- [ ] 2.1 付费入口全量后移
- [ ] 2.2 免费试用3天→7天
- [ ] 2.3 会员页—移除电商板块
- [ ] 2.4 付费漏斗数据埋点
- [ ] 2.5 UGC内容闭环—日记精选分享
- [ ] 2.6 AI周报分享长图
- [ ] 2.7 A/B测试—首次付费价格

---

*本实施计划基于设计文档 `docs/superpowers/specs/2026-07-31-starlight-growth-monetization-design.md` 生成。每个Task自包含，可独立执行和验证。*
