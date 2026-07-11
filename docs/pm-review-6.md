# 塔罗占卜小程序 - 产品审查报告 #6

审查日期：2026-07-11
审查轮次：第6轮
审查人：AI 产品经理

---

## 总体评分：6/10

上一轮评分 7/10。本轮发现了一个**全局性关键数据Bug**（所有模型created_at使用同一时间戳），以及多个重要逻辑问题。大部分旧有次要问题已修复，但新发现的问题涉及数据完整性和付费流逻辑，严重程度超过上次。**不建议上线，必须先修复本轮发现的Critical和Important问题。**

---

## 评分明细

| 维度 | 得分 | 说明 |
|------|------|------|
| 后端API完整性 | 6 | 接口设计合理，但模型层created_at存在全局数据Bug，支付回调测试缺失 |
| 前端功能完整性 | 7 | 所有页面有骨架/空/错误状态，上一轮解读折叠已修复，但年度报告卡牌仍传空属性 |
| 付费闭环 | 7 | 支付流程完整，会员过期检查和自动降级正常，年度报告可单独购买 |
| 用户体验 | 7 | 搜索防抖、历史统计、分享回调、解读折叠均已修复，但追问计数逻辑有问题 |
| 工程基建 | 3 | 仅1个测试、无迁移脚本、无CI配置（连续6轮未改善） |

---

## 上一轮问题修复状态

### 已修复（8个）

| # | 严重度 | 问题 | 状态 |
|---|--------|------|------|
| I1 | important | 解读结果页"展开全文"功能无效 | ✅ WXSS已正确定义.interpretation-scroll.expanded |
| M1 | minor | 每日一牌按钮标签误导"X/1次免费" | ✅ 改为"今日免费" |
| M2 | minor | 个人中心历史记录总数显示不准确 | ✅ 使用historyTotal = history.total |
| M3 | minor | 解读结果页缺少onShareAppMessage处理 | ✅ 已定义，但路径未传递sharer_id（新问题） |
| M4 | minor | 年度运势报告无法单独购买 | ✅ annual-report页增加了"单独购买"按钮，membership页支持product=annual_report参数 |
| M5 | minor | 卡牌组件传入空nameEn/cardNumber（reading-result） | ✅ 对应位置已移除空属性 |
| M6 | minor | 百科搜索防抖缺失 | ✅ 已实现300ms防抖 |
| M7 | minor | sitemap.json缺失 | ✅ 已创建 |

### 部分修复（1个）

| # | 严重度 | 问题 | 状态 |
|---|--------|------|------|
| M8 | minor | 卡牌组件传入空nameEn/cardNumber（annual-report） | ❌ annual-report.wxml第63-64行仍存在nameEn="{{''}}"和cardNumber="{{''}}"，导致卡牌英文名和编号显示空白 |

---

## 本期新发现的问题

### Critical（1个）

#### C1. 所有模型的 created_at 字段默认值为import时刻，所有记录共享同一时间戳

**文件**：所有模型文件（6个）
- `/mnt/e/tarot-miniapp/backend/app/models/user.py` line 25-26
- `/mnt/e/tarot-miniapp/backend/app/models/reading.py` line 19
- `/mnt/e/tarot-miniapp/backend/app/models/order.py` line 20
- `/mnt/e/tarot-miniapp/backend/app/models/diary.py` line 18
- `/mnt/e/tarot-miniapp/backend/app/models/share_log.py` line 21-22

**问题**：所有模型使用 `default=datetime.now(timezone.utc)`（带括号），该表达式在**Python类定义时**被求值一次，结果作为标量默认值。后续ORM创建的所有记录的 `created_at` 都是同一个时间戳（模块导入时间），而非每条记录的实际创建时间。这在生产环境中会完全破坏数据排序、用户时间线展示、订单时间记录等核心功能。

示例：
```python
# user.py line 25 — BUG: 括号导致立即求值
created_at: Mapped[datetime] = mapped_column(
    DateTime, default=datetime.now(timezone.utc)
)
# 修正: 使用无括号的 callable
# DateTime, default=lambda: datetime.now(timezone.utc)
```

**修复**：将所有模型的 `default=datetime.now(timezone.utc)` 改为 `default=lambda: datetime.now(timezone.utc)`（lambda延迟求值）或至少 `default=datetime.now`（函数引用）。

---

### Important（3个）

#### I1. 追问次数计数器对会员也递增，导致remaining_free显示不准确

**文件**：`/mnt/e/tarot-miniapp/backend/app/api/chat.py` line 98

**问题**：成员检查 `if not user.is_member` 正确阻止了会员的402错误，但第98行 `user.free_chats_today += 1` **无条件执行**。会员每次追问后计数器都递增，虽然会员不会被限流，但 `/readings/{id}/chat` 返回的 `remaining_free` 值会越来越小（`FREE_CHAT_MESSAGES - inflated_counter`）。前端聊天页的"今日剩余追问X次"提示对会员用户会显示误导性数字（如-5），且无法正确回零。

**修复**：将 `user.free_chats_today += 1` 移到 `if not user.is_member` 块内部，或在成员不满足条件时跳过后自增。

#### I2. 追问计数器仅在占卜时重置，纯追问次日无重置机会

**文件**：`/mnt/e/tarot-miniapp/backend/app/api/readings.py` lines 46-61  
**文件**：`/mnt/e/tarot-miniapp/backend/app/api/chat.py`

**问题**：`_reset_daily_count_if_new_day()` 函数检查 `user.last_reading_date` 来判断是否为新的一天，并同时重置 `free_readings_today` 和 `free_chats_today`。但 `last_reading_date` **只在 create_reading 中更新**，chat端点完全不更新。所以如果一个用户在某天做了占卜+追问（消耗3次追问额度），第二天只打开聊天页追问（不做新占卜），`last_reading_date` 仍是昨天，计数器不会被重置，用户将看到"剩余0次追问"无法使用。

**修复**：在 `chat.py` 的 `chat_followup` 函数开头也调用 `_reset_daily_count_if_new_day(user)`，或将 `last_chat_date` 作为独立字段管理。

#### I3. 年度报告页仍传入空 nameEn/cardNumber 属性给 tarot-card 组件

**文件**：`/mnt/e/tarot-miniapp/miniapp/pages/annual-report/annual-report.wxml` lines 63-64

**问题**：上一轮reading-result.wxml的空属性问题已修复，但annual-report.wxml第63-64行仍然存在 `nameEn="{{''}}" cardNumber="{{''}}"`。tarot-card组件有默认值（nameEn='The Wheel', cardNumber='X'），但传入空字符串 `''` 会覆盖默认值，导致年度报告页的卡牌展示只有中文名，英文名和编号空白。此问题在阅读结果页已修复，但在年度报告页被遗漏。

**修复**：移除 `nameEn="{{''}}"` 和 `cardNumber="{{''}}"` 属性，让组件使用默认值。

#### I4. 日记列表不返回卡牌信息，用户看不到每日抽取的牌

**文件**：`/mnt/e/tarot-miniapp/backend/app/api/diary.py` lines 78-106  
**文件**：`/mnt/e/tarot-miniapp/backend/app/schemas/diary.py` lines 30-43

**问题**：创建日记条目（POST /diary/entries）时，响应中包含完整的卡牌信息（`DiaryCardBrief`），但日记列表（GET /diary/entries）只返回 `DiaryEntryBrief`（无card字段）。前端日记页因此只显示日期和心情图标，用户看不到每天抽取的塔罗牌是什么。这削弱了"塔罗日记"的核心价值——记录每天与某张牌的连接。

**修复**：
1. 在 `api/diary.py` list_entries 中，为每个条目查询关联的卡牌信息
2. 将 `DiaryEntryBrief` 添加 `card: DiaryCardBrief | None = None` 字段
3. 前端 diary.wxml 展示卡牌名称和正逆位

---

### Minor（5个）

#### M1. 分享参数未传递用户ID，分享追踪仍无法归因

**文件**：`/mnt/e/tarot-miniapp/miniapp/pages/reading-result/reading-result.js` lines 63-74

**问题**：`onShareAppMessage` 已定义，但 `path` 仅包含 `id` 参数，未附加 `sharer_id=${user.id}`。`onShareAppMessage` 中无法直接通过 `getApp().globalData` 获取当前用户（该数据可能尚未初始化），但仍然可以尝试通过 `wx.getStorageSync('user')` 读取。缺少 sharer_id 导致 `/share/track` API 无法将分享点击归因到原分享者，分享裂变奖励（减一次免费阅读）无法生效。

**修复**：
```javascript
onShareAppMessage() {
  const user = wx.getStorageSync('user');
  const sharerParam = user?.id ? `&sharer_id=${user.id}` : '';
  return {
    title: `我抽到了 ${cardNames} —— 来看看塔罗的解读吧`,
    path: `/pages/reading-result/reading-result?id=${reading.id}${sharerParam}`,
  };
}
```
同时需要在 reading-result.js 的 onLoad 中处理 `options.sharer_id` 参数并调用 `/share/track` API。

#### M2. 日记分页可能跳过数据

**文件**：`/mnt/e/tarot-miniapp/miniapp/pages/diary/diary.js` lines 35-39

**问题**：`loadMore()` 先 `this.setData({ page: page + 1 })`，然后调用 `loadEntries()`。如果用户快速连续触底多次，page 会在异步请求返回前被多次递增，导致跳页。应该在请求完成后才递增 page。

**修复**：将 `this.setData({ page: page + 1 })` 移到 `loadEntries()` 成功回调中，或使用 loadingMore 标志防止并发。

#### M3. 测试覆盖率仍只有单个健康检查

**文件**：`/mnt/e/tarot-miniapp/backend/tests/test_health.py`

**问题**：核心API（readings、orders、chat、share等）完全没有测试覆盖。连续6轮审查均指出此问题但未改善。

**修复**：为核心API添加pytest测试，至少覆盖：
- 创建解读（需mock AI）
- 历史记录分页
- 追问、会员状态检查
- 订单创建和支付回调

#### M4. report.py 存在重复 import

**文件**：`/mnt/e/tarot-miniapp/backend/app/api/report.py` line 44

**问题**：第44行 `from app.services.tarot import draw_cards` 是重复导入，同一文件第20行已经导入了该函数。虽然不影响运行，但代码重复，有损可维护性。

**修复**：删除第44行的重复导入。

#### M5. payment.py 中 API Key 直接作为 AESGCM 密钥，可能不符合长度要求

**文件**：`/mnt/e/tarot-miniapp/backend/app/services/payment.py` lines 248-263

**问题**：`decrypt_wechat_v3_resource` 函数中，`api_v3_key.encode("utf-8")` 直接用作 AESGCM 的密钥，但 AES-256-GCM 要求密钥**必须是32字节**。WeChat Pay V3 的 APIv3 密钥是32字节的十六进制字符串（如 `abcdef123456...`），编码后是32字节，所以长度恰好符合要求。但如果用户配置了一个不同格式的密钥，AESGCM会抛异常。代码在 `except Exception` 中捕获并转为 `ValueError`，但调用方 `orders.py` 的 callback 没有妥善处理这个异常，可能导致500错误而非友好的错误提示。

**修复**：在 callback 中添加 try/except 捕获解密异常，返回更具体的错误信息，或至少记录日志后返回 SUCCESS（防重复通知）。

---

## 付费流程审计

| 步骤 | 状态 | 说明 |
|------|------|------|
| 商品列表展示 | ✓ | membership/products 返回齐全，支持annual_report参数 |
| 创建订单 | ✓ | POST /orders 返回支付参数 |
| 调用微信支付 | ✓ | wx.requestPayment 带正确参数 |
| 支付回调 | ✓ | 验证签名+解密+处理，幂等设计 |
| 会员权益生效 | ✓ | 回调后更新 is_member + member_expires_at |
| 单次购买计次 | ✓ | paid_readings_balance +1 |
| 权益扣减 | ✓ | readings.py 优先消耗免费次数，次用付费余额 |
| 续费叠加 | ✓ | member_expires_at 延长而非覆盖 |
| 过期检查 | ✓ | readings.py 自动降级（line 112-113） |
| 分享裂变奖励 | ✓ | 已完成修复，分享后 free_readings_today -1（需M1修复才生效） |
| 年度报告购买 | ✓ | 可在annual-report页单独购买¥29.90 |
| **模型时间戳** | **✗** | **所有created_at使用同一时间（C1）** |

## 用户体验断层审计

| 场景 | 状态 | 说明 |
|------|------|------|
| 首次打开 | ✓ | 自动微信登录，骨架屏加载 |
| 每日一牌 | ✓ | 不再消耗占卜额度，文案修正为"今日免费" |
| 选择牌阵 | ✓ | 10种牌阵，含会员/热门标记 |
| 输入问题 | ✓ | 主题选择+字数统计 |
| AI解读中 | ✓ | 3阶段进度提示 |
| 解读结果展开/收起 | ✓ | 已修复（第5轮I1） |
| 解读失败重试 | ✓ | reinterpret 按钮+API |
| 追问 | △ | 上下文保持，但会员追问计数有误（I1），次日重置有bug（I2） |
| 分享裂变 | △ | onShareAppMessage已定义但未传sharer_id（M1） |
| 年度报告 | △ | 卡牌展示缺英文名/编号（I3），新设备不自动加载后端缓存（I4） |
| 个人中心统计 | ✓ | 历史总数现在显示正确的total值 |
| 日记 | △ | 列表不显示每日抽取的牌（I4） |
| 搜索防抖 | ✓ | 已修复 |
| 支付失败 | ✓ | 取消/失败分别提示 |

---

## 建议修复优先级

### 发布阻断（必须修复）
1. **[Critical]** 所有模型created_at字段 → `default=datetime.now()` 改为 `default=lambda: datetime.now(timezone.utc)` — 影响数据完整性
2. **[Important]** chat.py 会员追问计数器计入 → 仅对非会员+1
3. **[Important]** chat端点也需调用_daily_count_reset — 确保次日追问重置

### 用户体验（建议本轮修复）
4. **[Important]** annual-report.wxml 移除空nameEn/cardNumber属性 — 与reading-result一致性
5. **[Important]** diary API 返回列表附带卡牌信息 — 增强日记页价值
6. **[Minor]** onShareAppMessage 传递 sharer_id — 补全分享裂变闭环

### 工程基建（长期）
7. **[Minor]** 添加核心API测试
8. **[Minor]** 初始化Alembic迁移工具
9. **[Minor]** 日记loadMore防并发
10. **[Minor]** 移除report.py重复import

---

## 与上一轮对比总结

| 指标 | 第5轮 | 第6轮 | 变化 |
|------|-------|-------|------|
| 总分 | 7/10 | 6/10 | ↓ |
| 待修复严重问题 | 1重要+4次要+4遗留 | 1关键+4重要+5次要 | 新发现更多底层问题 |
| 修复效率 | 8个修复 | 8个旧问题已修 | 执行良好 |
| 主要风险 | 功能展示故障 | **数据完整性** | 风险级别上升 |
