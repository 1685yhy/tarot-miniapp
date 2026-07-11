# 塔罗占卜小程序 - 产品审查报告 (PM Review v1)

**审查日期**: 2026-07-11
**评分**: 3/10
**状态**: 不可上线

---

## 一、后端审查结果

### 1.1 API 接口完整性

| 接口 | 状态 | 问题 |
|------|------|------|
| `POST /auth/login` | 可用 | 微信登录流程正确，但缺少 `session_key` 返回 |
| `POST /auth/dev-login` | 可用 | 开发测试登录，is_member=True 但未设置 member_expires_at |
| `GET /cards` | 可用 | 支持按 arcana/suit/keyword 筛选 |
| `GET /cards/daily` | 可用 | 随机抽取一张，适合免费每日一牌 |
| `GET /cards/{id}` | 可用 | 获取单牌详情 |
| `POST /readings/spread/{spread_type}` | 可用 | **CRITICAL BUG**: 第127行 `is_paid` 逻辑写反 |
| `GET /readings/{id}` | 可用 | 读取单次解读 |
| `GET /readings/history` | 可用 | 分页历史记录 |
| `POST /readings/{id}/chat` | 可用 | AI追问，无超时兜底处理 |
| `POST /orders` | 可用 | 创建订单，但返回的不是微信支付参数 |
| `POST /orders/callback` | 不可用 | 支付回调未验证微信签名，仅解析 body 中的 out_trade_no |
| `GET /membership/status` | 可用 | 返回用户会员状态 |
| `GET /membership/products` | 可用 | 列出所有商品 |
| `GET /report/annual` | 可用 | 年度报告（仅限会员） |
| `POST /share/track` | 可用 | 分享回馈逻辑有缺陷 |
| `GET /share/stats` | 可用 | 简单统计 |

### 1.2 关键逻辑问题

#### CRITICAL: `create_reading` 的 `is_paid` 字段逻辑错误 (readings.py:127)
```python
# 当前错误代码：
is_paid=user.is_member or user.free_readings_today >= settings.FREE_DAILY_READINGS
```
当用户用完免费次数时 `is_paid=True`，而会员用户因 `free_readings_today` 不会被限制所以 `is_paid=False`。**逻辑完全反了**。正确的逻辑应该是：会员的解读标记为已付费，免费解读标记为未付费。

#### CRITICAL: 支付流程未接入微信支付 (payment.py, membership.js)
- `payment.py:create_order_params()` 返回的是自定义字典，不是微信支付 `wx.requestPayment` 所需的 `timeStamp/nonceStr/package/signType/paySign`
- 前端 `membership.js:onPurchase()` 调用 `wx.showModal` 后直接显示"支付成功"，从未调用 `wx.requestPayment`
- `orders.py:payment_callback` 接收裸 JSON，未验证微信签名，存在安全风险

#### CRITICAL: 前端免费用户被完全阻挡使用牌阵 (index.js:38-41)
```javascript
navigateToReading(e) {
    if (!this.data.user?.is_member) {
      wx.navigateTo({ url: `/pages/membership/membership?from=reading` });
      return;
    }
```
后端限制的是每日免费次数（1次/天），但前端对所有非会员用户一票否决。这导致免费用户完全无法使用任何牌阵占卜，与产品设计矛盾。

#### 重要: 分享奖励逻辑无效 (share.py:39)
```python
sharer.free_readings_today = max(0, sharer.free_readings_today - 1)
```
`free_readings_today` 初始值为 0，减 1 后仍为 0。用户必须先做过占卜（counter 变成 1），分享减回 0，才能得到"一次额外免费"的奖励。分享本应**增加**可用次数而非减少。

#### 重要: AI 引擎无错误重试机制 (ai_engine.py, chat.py)
- `generate_reading()` 调用失败后返回 None，阅读记录会无解释内容
- `chat_followup()` 调用失败后抛出 502，但用户已发送的 message 已保存到数据库（发生在前），后续重试无法找回上下文
- 无 API 超时自定义配置，AI_MAX_TOKENS 写死在 config 中但未在 chats 中使用（chat.py 用硬编码的 1024）

#### 重要: 日记随机抽牌可能越界 (diary.py:22-25)
```python
result = await db.execute(select(func.count(TarotCard.id)))
count = result.scalar()
random_id = random.randint(1, count)
```
如果卡片 ID 不是从 1 开始连续编号（比如删除过卡片），random_id 可能指向不存在的 id。

### 1.3 模型与数据库问题

- **无数据库迁移工具**: alembic 在 requirements.txt 中但无迁移脚本，依赖 `create_all` 无法用于生产
- **keywords 字段存储 JSON 字符串而非 JSON**: `keywords_upright` 和 `keywords_reversed` 是 Text 类型存逗号分隔字符串
- **测试覆盖率极低**: 仅有一个 `test_health.py` 健康检查测试，无 API 测试、无 AI 引擎测试、无支付测试

---

## 二、前端审查结果

### 2.1 每个页面的问题

#### index (首页)
- `navigateToReading` 对所有非会员拒之门外（见上文 CRITICAL）
- `freeCount` 初始为 0，提示 "0/1 次免费"，但用户实际上有 1 次免费机会，体验误导
- 首页默认显示 card-daily-back 让用户点击抽牌，但没有 Loading 状态保护（多次点击会多次调用 API）
- 无 sitemap.json（app.json 中引用但文件不存在）

#### encyclopedia (百科)
- `onShow()` 有注释说刷新但无实现逻辑
- 搜索时 filterCards 被高频调用，未做防抖

#### card-detail (卡牌详情)
- 功能基本完整，卡片内容展示清晰

#### reading (占卜选择)
- `pageLoading` / `pageError` 在 WXML 中定义了条件判断，但 JS 中从未设置这两个变量，骨架屏和错误状态永远不显示
- 选择牌阵后 theme 默认取 spread 的 theme 属性，但如果用户手动点了一下 theme，再次选别的牌阵不会重置 theme

#### reading-result (占卜结果)
- **变量名不匹配**: JS 中设置 `loading` 但 WXML 判断 `pageLoading`（影响所有页面）
- **变量名不匹配**: JS 中设置 `loading` 但 WXML 判断 `pageLoading`（同上）
- 卡牌轮播无图片，仅显示卡名和正逆位，缺少塔罗卡片视觉元素
- 解读区域的 "展开/收起" 会在 interpretation 为 null 时仍然显示

#### chat (AI 追问)
- `scrollToBottom()` 方法定义了但从未在 `onSend()` 中调用
- 头部没有返回按钮或上下文提示（当前在针对哪次解读追问）
- 输入框用 `bindconfirm="onSend"` 在回车时发送，但微信小程序中 `confirm-type="send"` 的行为在不同机型上不一致

#### membership (会员)
- **支付流程未实现**（见 CRITICAL）
- 产品的 `single_reading` 和 `annual_report` 也在会员页面显示，但它们不是会员商品，会造成用户困惑
- `onLoad` 中拿到 products 后直接用 id 作为条件，但 `annual_report` 产品并未在页面上有对应显示

#### profile (个人中心)
- 清除历史记录仅在前端清除数组，后端未调用删除接口
- history-item 仅显示 spread_type，未显示第一张卡牌名（API 返回了 first_card_name）
- 历史记录无分页加载

#### diary (塔罗日记)
- 情绪选项 `thoughtful` 在 WXML 中被渲染为 `💭`，但实际 `mood` 字段存储的是英文，显示正确
- 创建日记后 API 返回的 `card` 字段在日记列表中没有展示

#### annual-report (年度报告)
- API 返回了 `cards` 数组（13张月份的牌），但前端完全不展示
- 生成本身是会员功能，付费用户可以用，但生成后无法保存，页面刷新会丢失

### 2.2 全局前端问题

1. **pageLoading/pageError 状态未在 JS 中初始化**: 几乎所有页面都在 WXML 中写了 `pageLoading`/`pageError` 判断，但 JS 中从未 `setData` 这两个值，导致骨架屏和错误提示功能完全不可用

2. **tarot-card 组件未被引用**: `components/tarot-card/` 是一个设计精美的卡牌组件，但在任何页面都未使用（reading-result 用的是一段简单的文字展示）

3. **无 WebSocket 或轮询**: AI 解读生成期间，前端显示 "占卜中..." 但无进度更新

4. **api.js 的 BASE_URL 为占位符**: `'https://your-domain.com'` 部署时需要手动替换

---

## 三、产品整体评估

### 3.1 付费流程是否闭环
**否**。支付流程完全断裂：
- 下单 → 创建订单（后端 OK）
- 支付 → **断裂**（前端模拟弹窗，未调 wx.requestPayment）
- 回调 → **断裂**（后端未验证微信签名）
- 权益生效 → **断裂**（没有支付成功就没法触发回调，会员权益永远无法自动开通）

### 3.2 用户体验是否存在断层

1. **免费用户无法体验核心功能**: 首页所有牌阵入口都导向会员页面，免费用户只能抽每日一牌和浏览百科
2. **付费引导时机不当**: 用户还没了解产品价值就直接被推到付费页面
3. **加载/错误状态全失效**: 骨架屏设计精美但全部不显示
4. **分享裂变无法使用**: 奖励逻辑错误导致用户永远不会获得分享奖励

### 3.3 遗漏的核心功能

1. **卡牌图片**: 无塔罗牌图片展示（仅文字），百科和占卜结果都缺少视觉吸引力
2. **微信支付集成**: 最核心的商业化功能缺失
3. **数据持久化保存**: 年度报告结果无法保存到用户账户
4. **网络错误处理**: 无统一的网络错误弹窗/重试机制
5. **用户引导**: 首次使用无 onboarding 流程
6. **分享卡片图片生成**: 设计文档提到运势卡片分享，但未实现

---

## 四、问题清单（按优先级）

### Critical (上线阻塞)
1. `readings.py:127` — is_paid 逻辑完全写反
2. 支付流程未接入微信支付（前后端均未实现）
3. `index.js:38` — 免费用户被完全阻挡使用牌阵

### Important (必须修复)
4. 所有页面的 `pageLoading`/`pageError` 状态机未连接到 JS（影响骨架屏和错误提示）
5. `reading-result.js` 设置 `loading` 但 WXML 判断 `pageLoading`
6. 分享奖励 `share.py:39` 减 1 逻辑错误（实际是加 1）
7. `chat.js` 发送消息后未调用 `scrollToBottom()`
8. 日记随机抽牌 `random.randint(1, count)` 可能越界
9. `payment.py` 未生成微信支付所需参数
10. `.env` 文件中包含真实 DeepSeek API Key

### Minor (建议修复)
11. 百科页面搜索未做防抖
12. 占卜结果轮播缺少卡牌视觉效果
13. 年度报告不展示 13 张牌的卡片列表
14. 历史记录无分页加载且未展示 first_card_name
15. 清除历史记录仅前端操作
16. tarot-card 组件未被使用
17. API BASE_URL 硬编码占位符
18. 缺少 sitemap.json
19. 无数据库迁移脚本（alembic 未配置）
20. 仅有一个健康检查测试

---

## 五、总结

**评分: 3/10**

这是一个框架完整、UI 设计精美的项目骨架，但存在多处关键逻辑错误和功能缺失。核心的占卜体验（抽牌+AI解读）功能正常，但**商业化流程完全断裂**——用户无法真实付费成为会员，免费用户也被前端逻辑错误地完全阻挡。多个页面的状态机未正确连接到 JS，导致精心设计的骨架屏和错误状态形同虚设。

如果修复 Critical 问题，将评分提升至 5-6 分（可进行小范围内测）；修复全部 Important 问题后可达 7-8 分（可上线）。
