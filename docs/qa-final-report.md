# 塔罗小程序 QA 最终回归测试报告

> **测试日期**: 2026-07-11  
> **测试环境**: 后端 http://localhost:8000 | 前端 miniapp/ 目录  
> **测试人员**: QA 自动化回归 + 代码审查

---

## Part 1: 后端 API 回归测试（17 个端点）

### 测试汇总

| # | 端点 | 结果 | 说明 |
|---|------|------|------|
| 1 | `GET /health` | **通过** | 返回 `{"status":"ok"}` (注：运行中服务未含 config_status 字段，但代码中已实现) |
| 2 | `GET /cards` | **通过** | 返回 78 张牌 |
| 3 | `GET /cards?arcana=major` | **通过** | 返回 22 张大阿尔卡纳 |
| 4 | `GET /cards?keyword=爱情` | **通过** | URL 编码后返回 3 张牌(恋人、圣杯七、圣杯骑士)；原生中文字符串直接放在 URL 中会导致 "Invalid HTTP request" |
| 5 | `GET /cards/daily` x3 | **通过** | 每次返回不同的随机牌 |
| 6 | `GET /cards/1` | **通过** | 返回愚者详情，字段完整 |
| 7 | `POST /auth/dev-login` | **通过** | 返回 token + user 信息 |
| 8 | `POST /auth/login` (假 code) | **通过** | 返回 400 + 详细错误信息 |
| 9 | `POST /readings/spread/three_card` | **部分通过** | 返回数据结构完整(含 drawn_cards)，但 interpretation 为 null (DeepSeek API 未配置或 Key 无效) |
| 10 | `GET /readings/history` | **通过** | 返回用户历史记录，含分页 |
| 11 | `POST /readings/{id}/chat` | **失败** | 返回 502 "AI回复生成失败" (DeepSeek API Key 无效) |
| 12 | `POST /diary/entries` | **通过** | 成功创建日记，附带当日塔罗牌 |
| 13 | `GET /diary/entries` | **通过** | 返回日记列表，含分页 |
| 14 | `GET /membership/products` | **通过** | 返回 5 个商品 (月度/年度/终身会员 + 单次深度占卜 + 年度报告) |
| 15 | `GET /membership/status` | **通过** | 返回 is_member=true |
| 16 | `POST /orders` | **部分通过** | product_type 传 membership_monthly 可成功创建订单；字段名 product_type 实际对应的是商品 ID(如 membership_monthly)而非类型分类(如 membership)，命名易产生混淆 |
| 17 | `GET /report/annual` | **失败** | 500 Internal Server Error (DeepSeek API Key 无效，未捕获异常) |

### 统计

| 状态 | 数量 |
|------|------|
| **通过** | 12 个 |
| **部分通过** | 2 个 (Test 9, 16) |
| **失败** | 2 个 (Test 11, 17) |
| **需要前端注意** | 1 个 (Test 4 URL编码) |

---

### 后端 Bug 详情

#### Bug-B1: 年度报告 500 错误 [严重]
- **端点**: `GET /report/annual`
- **文件**: `backend/app/api/report.py`
- **问题**: 服务端日志显示 `openai.AuthenticationError: Error code: 401` — DeepSeek API Key 无效。但该端点未像 `generate_reading()` 那样做缺失 Key 的防护检查，导致未捕获异常冒泡为 500。
- **复现**: 任意会员用户访问此端点。
- **修复建议**: 在调用 DeepSeek API 前检查 `settings.DEEPSEEK_API_KEY`，返回友好提示而非 500。

#### Bug-B2: AI 追问 502 错误 [严重]
- **端点**: `POST /readings/{id}/chat`
- **文件**: `backend/app/api/chat.py`
- **问题**: DeepSeek API Key 无效导致 `client.chat.completions.create()` 失败，catch 块返回 502 "AI回复生成失败"。
- **修复建议**: 在 chat 端点的 `onLoad` 加载阶段检查 API Key 配置，或返回更友好的提示。

#### Bug-B3: AI 解读为空 [中]
- **端点**: `POST /readings/spread/three_card`
- **文件**: `backend/app/services/ai_engine.py`
- **问题**: `generate_reading()` 在 `settings.DEEPSEEK_API_KEY` 为空时返回 `None`，导致 `reading.interpretation` 为 null。前端显示"解读生成失败"但用户首次使用时无上下文说明。
- **修复建议**: 在 endpoints/create_reading 中增加检查，首次失败时提示用户。

#### Bug-B4: 订单字段命名混淆 [低]
- **端点**: `POST /orders`
- **文件**: `backend/app/schemas/order.py` + `backend/app/services/payment.py`
- **问题**: `CreateOrderRequest` 中字段名 `product_type` 实际映射的是 PRODUCTS 字典的 key (如 `membership_monthly`)，而非商品类型分类 (如 `membership`)。这与 `/membership/products` 返回的 `type` 字段含义不同，非常容易混淆。
- **修复建议**: 将字段重命名为 `product_id`，或在文档中明确说明。

#### Bug-B5: /health 端点运行版本与代码不一致 [提示]
- **文件**: `backend/app/main.py`
- **问题**: 代码中已实现 `config_status` 返回，但当前运行的服务仅返回 `{"status":"ok"}`。可能是代码更新后服务未重启。
- **修复建议**: 重启 uvicorn 服务。

---

## Part 2: 前端代码审查（10 个页面）

### 审查范围

| 页面 | JS 文件 | WXML 文件 | 审查状态 |
|------|---------|-----------|----------|
| 首页 | index.js | index.wxml | 完成 |
| 牌详情 | card-detail.js | card-detail.wxml | 完成 |
| 占卜 | reading.js | reading.wxml | 完成 |
| 占卜结果 | reading-result.js | reading-result.wxml | 完成 |
| AI追问 | chat.js | chat.wxml | 完成 |
| 图鉴 | encyclopedia.js | encyclopedia.wxml | 完成 |
| 日记 | diary.js | diary.wxml | 完成 |
| 会员 | membership.js | membership.wxml | 完成 |
| 个人中心 | profile.js | profile.wxml | 完成 |
| 年度报告 | annual-report.js | annual-report.wxml | 完成 |

### 关键 Bug 汇总

| ID | 严重度 | 页面 | 问题描述 |
|----|--------|------|----------|
| F1 | **严重** | reading.js | 402 错误检测 `err.message.includes('402')` 永远无法匹配。API 客户端传递的是 `err.message` 含中文详情(如 "今日免费次数已用完")，不包含 "402" 子串，导致免费用户永远不会看到会员升级弹窗 |
| F2 | **严重** | 多处 | 当错误来自 api.js 第90行 `new Error(res.data?.detail)` 时，`err.message` 被设为中文详情字符串，但多个页面 try-catch 仅检查 `err.errMsg` (而非 `err.message`)，导致错误信息被静默吞没 |
| F3 | **高** | chat.js | `onLoad` catch 块未设置 `pageError`，错误状态无法渲染，用户看到误导性的空状态"对刚才的解读有什么想问的吗？" |
| F4 | **高** | encyclopedia.js | `loadCards()` 中 `data.cards` 应为 `data` 本身（API 返回的是数组而非 `{cards:[]}`），导致过滤始终在空数组上操作，图鉴页面永远显示 0 张牌 |
| F5 | **高** | encyclopedia.js | 搜索过滤中 `c.keywords.some()` 当 `keywords` 为字符串时抛出 `TypeError`，导致页面崩溃 |
| F6 | **高** | chat.js | `wx:if` 中使用 `inputText.trim()` — WXML 不支持方法调用，会静默失败 |
| F7 | **中** | diary.js | `loadMore()` 中 `page` 在 API 调用前递增，失败后无法回滚，分页永久跳过失败页 |
| F8 | **中** | membership.js | 无声明 `loading` 字段，在 data 块中未初始化 |
| F9 | **中** | profile.js | `historyTotal` 使用 `||` 而非 `??`，当 total=0 时错误地回退为 items.length |
| F10 | **中** | annual-report.js | 402 错误检测同样是基于 `err.message.includes('402')` 的字符串匹配，逻辑脆弱 |
| F11 | **中** | reading-result.js | WXML 中 `item.card.meaning_upright` 引用但后端 diary list 接口未返回 card 详情 |
| F12 | **中** | reading.js | `checkLogin` 被调用两次（`onSelectSpread` 和 `onStartReading`），冗余 |
| F13 | **低** | 首页(card-detail) | `wx.showToast` + `wx.navigateBack` 用户可能看不到 Toast |
| F14 | **低** | 首页 | `freeCount`、`user`、`drawingLoading` 三个 setData key 在 WXML 中未使用 |
| F15 | **低** | annual-report.js | `onShare()` 死代码，WXML 使用 `open-type="share"` 不触发 bindtap |
| F16 | **低** | annual-report.js | 未定义 `onShareAppMessage`，分享按钮使用默认内容 |
| F17 | **低** | api.js | `wx.request` 未设置 `timeout` 参数 |
| F18 | **低** | auth.js | `checkLogin()` token 存在但 user 缓存为空时，静默返回空值 |

### API 路径检查

所有 10 个页面的 API 调用路径均未使用 `/api` 前缀，直接使用后端裸路径：

```
request('/cards/daily')
request('/cards/${id}')
request('/readings/spread/${key}')
request('/readings/${id}')
request('/readings/${id}/chat')
request('/readings/${id}/reinterpret')
request('/readings/history')
request('/diary/entries')
request('/membership/products')
request('/membership/status')
request('/orders')
request('/report/annual')
request('/auth/login')
```

经实际测试验证，后端路由均注册在根路径（如 `@router.get("/cards")`），不带 `/api` 前缀，**当前路径配置在开发环境是正确的**。但如果后端将来添加 `/api` 前缀，所有路径将同时失效。

---

### WXML 函数绑定完整性

| 页面 | WXML bindtap 函数 | JS 中存在 | 状态 |
|------|-------------------|-----------|------|
| index | `drawDailyCard`, `navigateToReading`, `onRetry` | 全部存在 | OK |
| card-detail | `onTabTap`, `onRetry` | 全部存在 | OK |
| reading | `onSelectSpread`, `onQuestionInput`, `onThemeTap`, `onBackToSpreads`, `onStartReading`, `onRetry` | 全部存在 | OK |
| reading-result | `onCardSwiperChange`, `onCardTap`, `onToggleInterpretation`, `onReinterpret`, `onAskMore`, `onNewReading`, `onBackHome`, `onRetry` | 全部存在 | OK |
| chat | `onRetry`, `onInput`, `onSend` | 全部存在 | OK |
| encyclopedia | `onTabTap`, `onSearchInput`, `onCardTap`, `onRetry` | 全部存在 | OK |
| diary | `loadMore`, `showCreateModal`, `hideCreateModal`, `onMoodSelect`, `onReflectionInput`, `onCreateEntry`, `onRetry` | 全部存在 | OK |
| membership | `onRetry`, `onPurchase` | 全部存在 | OK |
| profile | `onRetry`, `onGoMembership`, `onViewReading`, `onGoDiary`, `onGoAnnualReport`, `onClearHistory`, `onScrollToBottom` | 全部存在 | OK |
| annual-report | `onGenerate`, `onRetry`, `onCardPreview`, `onBuySingle` | 全部存在 | OK |

**结论**: 所有 WXML 中绑定的函数在对应 JS 文件中均存在。无缺失绑定。

---

### setData Key 与 WXML 使用完整性

| 页面 | 未使用的 setData key |
|------|---------------------|
| index | `freeCount`, `user`, `drawingLoading` |
| card-detail | 无 |
| reading | 无 |
| reading-result | 无 |
| chat | 无 |
| encyclopedia | 无 |
| diary | 无 |
| membership | 无 (但 `loading` 未在 data 块初始化) |
| profile | `spreadTypeNames` (已由 JS 内联计算 `item.spreadTypeName` 替代) |
| annual-report | `generating` (WXML 中用 `wx:elif="{{generating}}"` 使用了) |

**结论**: 主要问题在 index 页有 3 个死数据字段，profile 页有 1 个。

---

### 错误处理完整性

| 页面 | API 错误处理 | 网络错误 | 402/会员提示 | 评价 |
|------|-------------|----------|-------------|------|
| index | try-catch + pageError | 有 | 不适用 | 良好 |
| card-detail | try-catch + pageError | 有 | 不适用 | 良好 |
| reading | try-catch + 402检测 | 有 | **402检测已损坏** | 需修复 402 检测 |
| reading-result | try-catch + pageError | 有 | 不适用 | 良好 |
| chat | try-catch (静默) | 有(静默) | 无 | **加载失败无提示，需修复** |
| encyclopedia | try-catch + pageError | 有 | 不适用 | 良好 |
| diary | try-catch + Toast | 有 | 不适用 | 良好 |
| membership | try-catch + Toast | 有 | 不适用 | 良好 |
| profile | try-catch + pageError | 有 | 不适用 | 良好 |
| annual-report | try-catch + 402检测 | 有 | **402检测已损坏** | 需修复 402 检测 |

---

## 总体统计

### 后端问题

| 严重度 | 数量 | ID |
|--------|------|----|
| 严重 | 2 | B1(年度报告500), B2(AI追问502) |
| 中 | 1 | B3(AI解读为空) |
| 低 | 1 | B4(订单字段命名混淆) |
| 提示 | 1 | B5(/health版本不一致) |

### 前端问题

| 严重度 | 数量 | ID |
|--------|------|----|
| 严重 | 2 | F1(402检测全损), F2(错误信息被吞) |
| 高 | 4 | F3(chat静默失败), F4(图鉴0牌), F5(keywords崩溃), F6(WXML方法调用) |
| 中 | 6 | F7-F12 |
| 低 | 6 | F13-F18 |

### 重点关注

1. **后端**: DeepSeek API Key 无效或未配置，导致 3 个 AI 相关功能全部失效（解读、追问、年度报告）
2. **前端**: 402 错误处理全链路损坏（从 api.js 到 reading.js / annual-report.js），免费用户的付费转化流程被阻断
3. **前端**: encyclopedia.js 的 `loadCards()` 对 API 返回结构理解错误，导致图鉴功能完全不可用
4. **前端**: chat.js 在 `onLoad` 失败时静默吞错误，用户被误导

---

## 建议修复优先级

1. **P0(立即修复)**: 配置或修复 DeepSeek API Key，重启后端服务 (影响 B1, B2, B3)
2. **P0(立即修复)**: 修复 api.js 中错误对象的字段传递，让 `err.message` 包含状态码 (影响 F1, F10)
3. **P1(高优)**: 修复 encyclopedia.js 的卡片加载逻辑 (影响 F4)
4. **P1(高优)**: 修复 chat.js 的静默失败问题 (影响 F3)
5. **P1(高优)**: 修复 WXML 中的方法调用 (影响 F6)
6. **P2(中优)**: 修复 diary.js 的分页状态管理 (影响 F7)
7. **P3(低优)**: 清理死代码、添加 timeout、完善分享功能
