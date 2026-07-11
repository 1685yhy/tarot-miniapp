# 塔罗占卜小程序 - 产品审查报告 V2

**审查日期**: 2026-07-11
**评分**: 6/10
**状态**: 有条件内测（不可正式上线）

---

## 一、上一轮问题修复验证

### Critical (3/3 已修复)

| 问题 | 状态 | 说明 |
|------|------|------|
| `readings.py` is_paid 逻辑写反 | 已修复 | 第126行改为 `is_paid=user.is_member`，逻辑正确 |
| 支付流程未接入微信支付 | 基本修复 | `payment.py` 生成了 JSAPI 参数；`membership.js` 调用了 `wx.requestPayment`；**但 callback 签名验证仍跳过**（见新问题） |
| `index.js` 免费用户被完全阻挡 | 已修复 | `navigateToReading` 移除了 `is_member` 检查，改为后端 402 重定向 |

### Important (7/7 已修复)

| 问题 | 状态 | 说明 |
|------|------|------|
| 所有页面 pageLoading/pageError 未连接 JS | 已修复 | 所有页面在 `onLoad`/`loadData` 中正确初始化了这两个状态 |
| reading-result.js loading 变量名不匹配 | 已修复 | 统一为 `pageLoading` |
| 分享奖励逻辑错误 (share.py) | 已修复 | 现在是 `min(free_readings_today + 1, FREE_DAILY_READINGS)` |
| chat.js 未调用 scrollToBottom | 已修复 | `onSend()` 中正确调用了 |
| 日记随机抽牌可能越界 (diary.py) | 已修复 | 改为 `func.random()` 数据库随机排序 |
| payment.py 未生成微信支付参数 | 已修复 | 完整实现 JSAPI sign + `wechatpayv3` SDK fallback |
| .env API Key 泄露 | 已修复 | 替换为 `your-deepseek-api-key` 占位符 |

### Minor (部分修复)

| 问题 | 状态 | 说明 |
|------|------|------|
| 百科搜索未做防抖 | 未修复 | filterCards 仍被高频调用 |
| 占卜结果轮播缺少卡牌视觉效果 | 未修复 | tarot-card 组件仍未在 reading-result 中引入 |
| 年度报告不展示 13 张牌 | 未修复 | API 返回了 cards 数组，前端只用 report.text |
| 历史记录无分页 + 未展示 first_card_name | 部分修复 | API 返回 first_card_name 但 profile 列表未展示 |
| 清除历史记录仅前端操作 | 未修复 | 无后端删除 API |
| tarot-card 组件未被使用 | 未修复 | 精美设计但无页面引用 |
| API BASE_URL 硬编码 | 未修复 | 仍为 `'https://your-domain.com'` 占位符 |
| 缺少 sitemap.json | 未修复 | app.json 引用但文件不存在 |
| 无数据库迁移脚本 | 未修复 | 仍依赖 `create_all` |
| 测试覆盖率低 | 未修复 | 仅有一个健康检查测试 |

---

## 二、本次审查发现的新问题

### Critical (上线阻塞)

#### C1. 支付回调签名验证形同虚设
- **文件**: `/mnt/e/tarot-miniapp/backend/app/api/orders.py` 第76-101行
- **问题**: `payment_callback` 中 `# For V3 callbacks, decrypt the resource... Simplified: treat any callback with a matching order_no as valid.` — 实际代码中签名验证部分仅有 `pass`。任何人只要知道 `out_trade_no`（TAROT+时间戳+6位大写字母，模式可预测）即可伪造支付成功通知，绕过支付直接成为会员。
- **影响**: 严重安全漏洞，可被利用免费获取会员权益
- **修复**: 必须集成微信 V3 回调签名验证（验证 `Wechatpay-Signature` 头 + 解密 `resource.ciphertext`）

#### C2. 单次占卜购买无权益处理
- **文件**: `/mnt/e/tarot-miniapp/backend/app/api/orders.py` 第114-115行
- **问题**: `if order.product_type == "single_reading": pass` — 购买了单次深度占卜（9.90元）的用户，回调中不执行任何操作，用户付款后得不到任何权益。
- **影响**: 付费用户权益受损
- **修复**: 为 single_reading 增加逻辑，增加用户 free_readings_today（或独立的 credit 计数器）

#### C3. AI 解读失败无重试机制，阅读记录留空
- **文件**: `/mnt/e/tarot-miniapp/backend/app/services/ai_engine.py` 第145-147行
- **问题**: `generate_reading()` 出错时返回 `None`，`readings.py` 第170-172行检查到 None 后不设 interpretation。用户看到"正在生成解读..."后只能看到空白解读，无法重试（重试也不会重新调用 AI，因为 reading 已创建）。
- **影响**: 核心体验严重受损——AI 解读失败后用户永远得不到该次占卜的结果
- **修复**: 添加自动重试逻辑（至少重试1次）；或在前端提供"重新生成解读"按钮，调用新的 API 端点重新生成

### Important (必须修复)

#### I1. 年度报告 13 张牌前端不展示（遗留问题）
- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/annual-report/annual-report.wxml` 第42-49行
- **问题**: API `/report/annual` 返回了包含13张月度牌的 `cards` 数组（含 card_name、direction、meaning），但前端只展示 `report.report` AI文本，完全不展示这些卡牌信息。用户无法看到每个月抽到了什么牌。
- **修复**: 在报告中添加13张牌的视觉展示区域，可使用 tarot-card 组件

#### I2. 清除历史记录无后端 API（遗留问题）
- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/profile/profile.js` 第59-68行
- **问题**: 清除按钮仅在前端 `this.setData({ readingHistory: [] })` 清空数组，未调用后端 API。用户下次打开页面时历史记录依然存在。
- **修复**: 添加后端 DELETE `/readings/history` 接口并调用

#### I3. tarot-card 精美组件未被引用（遗留问题）
- **文件**: `/mnt/e/tarot-miniapp/miniapp/components/tarot-card/` 全套文件
- **问题**: 该组件包含星空背景、金色边框、翻转动画等精美设计，但无任何页面引用。reading-result 的 card-swiper 仅用纯文字展示卡牌名和正逆位，毫无视觉吸引力。
- **修复**: 在 reading-result 的 swiper-item 中引入 tarot-card 组件替代纯文字展示；在 annual-report 中展示月度牌时也可复用

#### I4. BASE_URL 硬编码为占位符（遗留问题）
- **文件**: `/mnt/e/tarot-miniapp/miniapp/utils/api.js` 第1行
- **问题**: `const BASE_URL = 'https://your-domain.com'` 部署时需手动修改，无法多环境部署
- **修复**: 通过 `wx.getAccountInfoSync().miniProgram.envVersion` 区分开发/体验/正式环境，或从 app.json 的 extConfig 读取

#### I5. 订单回调中 single_reading 和 annual_report 商品在会员页展示造成混淆
- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/membership/membership.wxml` 第42-63行
- **问题**: `/membership/products` 返回了 5 个产品（含 single_reading 和 annual_report），它们不是会员商品却在会员页面展示。用户可能混淆"单次占卜"和"月度会员"的区别。
- **修复**: 在前端过滤掉非会员商品，或后端 products 接口增加 `type` 字段区分

#### I6. AI 解读无进度反馈，用户等待无预期
- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/reading-result/reading-result.wxml` 第21-28行
- **问题**: reading-result 的 loading 页仅有 "塔罗牌灵正在回应..." 的静态文字，无进度条或预计等待时间。AI 解读通常需要 5-15 秒，用户没有等待预期可能中途退出。
- **修复**: 增加阶段提示（"抽牌完成 → AI 解读中 → 生成报告"）或打字机效果显示实时流式输出

#### I7. 聊天页无阅读上下文提示
- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/chat/chat.js` 第15-17行
- **问题**: 聊天页只接收 `readingId` 参数，标题/头部无任何信息告诉用户当前在针对哪次解读追问。用户可能忘记之前占卜的问题和牌面。
- **修复**: 在聊天页顶部显示原问题的摘要和牌阵类型

### Minor (建议修复)

#### M1. 首页每日一牌无防抖
- 用户快速点击可多次触发 drawDailyCard 调用，虽然在免费次数用完后会被阻止，但中间可能触发多余请求

#### M2. 百科搜索未做防抖
- 用户快速输入时每次 keystroke 都触发 `filterCards`，性能浪费

#### M3. 会员页面 loading 状态不一致
- `membership.js` line 18 同时 setData `pageLoading: false` 和 `loading: false`，但 data 中只有 `pageLoading` 没有 `loading`。WXML 中 `wx:if="{{!loading}}"` 中的 `loading` 是 undefined，实际上总是为 true，导致商品列表始终显示。但因为有 `wx:if="{{pageLoading}}"` 的骨架屏，实际并未造成显示问题。

#### M4. 年度报告结果无法保存
- 用户刷新页面或重新进入后之前生成的报告丢失，无持久化存储到用户账户

#### M5. 阅读计数显示问题
- profile 页 `stats-row` 的 `free_readings_today` 显示的是"已用次数"而非"剩余次数"，可能导致用户困惑

#### M6. 缺少统一的网络错误重试机制
- 每个页面各自处理错误，没有在 api.js 层做统一的网络错误拦截和自动重试逻辑

#### M7. 缺少 sitemap.json
- app.json 引用了 `sitemapLocation: "sitemap.json"` 但文件不存在，可能导致微信开发者工具警告

#### M8. 无数据库迁移脚本
- 生产环境依赖 `create_all()` 创建表结构，无法安全做 schema 变更

#### M9. 测试覆盖率极低
- 仅有一个 `test_health.py`，无 API 测试、AI 引擎测试、支付回调测试

---

## 三、付费流程闭环评估

| 环节 | 状态 | 说明 |
|------|------|------|
| 下单 | 可用 | `POST /orders` 创建订单，返回支付参数 |
| 支付 | 基本可用 | `wx.requestPayment` 已接入；`payment.py` 有完整 JSAPI 参数生成（含 V3 SDK fallback） |
| 回调 | 有风险 | callback 端点存在，但签名验证被跳过；技术上可用但不安全 |
| 权益开通 | 部分可用 | 月度/年度/永久会员可正常开通；**single_reading 未实现权益**；无任何幂等性保障 |
| 前端反馈 | 可用 | 支付成功/取消 toast 提示正常 |

**结论**: 付费流程从"完全断裂"（v1评分）变为"基本可用但有风险和盲区"。可以走通完整的下单-支付-会员开通链路，但存在安全隐患和部分商品无权益的缺陷。**不可用于正式生产环境**，但可以用于小范围测试。

---

## 四、问题清单（按严重程度）

### Critical（3项）
1. 支付回调签名验证形同虚设 (`orders.py:76-101`)
2. `single_reading` 购买无权益处理 (`orders.py:114-115`)
3. AI 解读失败无重试，reading interpretation 留空 (`ai_engine.py:145-147`)

### Important（7项）
4. 年度报告 13 张牌前端不展示 (`annual-report.wxml:42-49`)
5. 清除历史记录前端假清除 (`profile.js:59-68`)
6. tarot-card 组件未被使用 (遗留，`components/tarot-card/`)
7. BASE_URL 硬编码占位符 (`api.js:1`)
8. 非会员商品在会员页展示 (`membership.wxml:42-63`)
9. AI 解读无进度反馈 (`reading-result.wxml:21-28`)
10. 聊天页无阅读上下文提示 (`chat.js:15-17`)

### Minor（9项）
11. 首页每日一牌无防抖
12. 百科搜索未做防抖
13. 会员页 loading 状态遗留变量
14. 年度报告结果无法保存
15. 阅读计数显示逻辑不直观
16. 无统一网络错误重试机制
17. 缺少 sitemap.json
18. 无数据库迁移脚本
19. 测试覆盖不足

---

## 五、总结

**评分: 6/10 — 有条件内测，不可正式上线**

与上一轮（3/10）相比，项目取得了显著进步。三个阻塞性 Critical 问题已全部修复：免费用户现在可以使用每日占卜、支付参数已正确生成和调用、is_paid 逻辑正确。

UI 全面升级为神秘金色主题，所有页面的加载骨架屏、错误状态、空状态和动画效果均正确运行。整体的视觉体验达到可上线水平。

核心商业化链路（占卜 -> AI解读 -> 会员）可以基本走通，但存在三个关键缺陷：**支付回调安全验证缺失**（可被伪造）、**单次占卜商品无权益**（付了钱但没得到东西）、**AI解读失败不可重试**（核心体验受损）。这三个问题必须在正式上线前修复。

遗留的 Minor 问题（tarot-card 组件未使用、BASE_URL 硬编码、年报卡牌不展示等）不影响核心功能，建议在后续迭代中逐步优化。
