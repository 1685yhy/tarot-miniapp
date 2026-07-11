# 塔罗占卜小程序 - 产品审查报告 #5

审查日期：2026-07-11  
审查轮次：第5轮  
审查人：AI 产品经理

---

## 总体评分：7/10

核心功能运作正常，上次的3个重要问题（分享奖励、每日一牌计数、年度报告持久化）已全部修复。产品体验相比第4轮有实质性提升。但仍有6个旧有次要问题未修复，并新增了2个UI/UX问题。**可以有限上线试运营，但建议先修复本次列出的重要问题。**

---

## 评分明细

| 维度 | 得分 | 说明 |
|------|------|------|
| 后端API完整性 | 8 | 接口设计合理，付费闭环完整，分享奖励已修复 |
| 前端功能完整性 | 7 | 所有页面有骨架/空/错误状态，解读展开/收起功能故障 |
| 付费闭环 | 8 | 支付流程完整，分享裂变奖励已修复 |
| 用户体验 | 7 | 年度报告已持久化，但解读折叠失效、统计显示有误 |
| 工程基建 | 4 | 无迁移脚本、仅1个测试、sitemap缺失（连续5轮未修复） |

---

## 上次问题修复状态

### 已修复（3个）

| # | 严重度 | 问题 | 文件 | 状态 |
|---|--------|------|------|------|
| 1 | critical | 分享奖励逻辑方向颠倒 | services/share.py line 40-42 | ✅ `max(0, free_readings_today - 1)` 已修正 |
| 2 | important | 每日一牌误用占卜计数 | index/index.js | ✅ drawDailyCard 已移除 freeCount 限制和自增 |
| 3 | important | 年度报告不持久化 | report.py + annual-report.js | ✅ 后端缓存到 annual_report_data，前端用 wx.setStorageSync |

### 未修复（6个旧有次要问题）

| # | 严重度 | 问题 | 文件 | 首次发现 |
|---|--------|------|------|---------|
| 4 | minor | 卡牌组件传入空 nameEn/cardNumber | reading-result.wxml line 73-74 | 第4轮 |
| 5 | minor | 百科搜索防抖缺失 | encyclopedia.js onSearchInput | 第4轮 |
| 6 | minor | sitemap.json 缺失 | app.json line 48 | 第4轮 |
| 7 | minor | 无数据库迁移脚本 | main.py 仍用 create_all() | 第4轮 |
| 8 | minor | 测试覆盖率低 | tests/ 仅1个健康检查 | 第4轮 |
| 9 | minor | 支付跳转目的地不合理 | membership.js line 56 | 第4轮 |

---

## 本期新发现的问题

### Important（1个）

#### I1. 解读结果页"展开全文"功能无效

**文件**：`/mnt/e/tarot-miniapp/miniapp/pages/reading-result/reading-result.wxml` line 96  
**文件**：`/mnt/e/tarot-miniapp/miniapp/pages/reading-result/reading-result.wxss`（无对应规则）

**问题**：`showFullInterpretation` 切换时，WXML 将 `expanded` class 应用到 `<view class="interpretation-card">` 上，但 WXSS 中仅定义了 `.interpretation-scroll`（带 max-height + 渐变遮罩），没有 `.interpretation-card.expanded` 或 `.interpretation-card` 的 overflow 限制。点击"展开全文"后页面无任何视觉变化，收起功能同样失效。用户无法阅读超过300字的完整AI解读内容，属于核心功能的展示故障。

**修复方案**：
1. 将 WXML 中的 `interpretation-card` 改为 `interpretation-scroll`（与WXSS定义匹配），或
2. 在 WXSS 中为 `.interpretation-card` 添加 max-height + overflow + gradient 遮罩样式：
```css
.interpretation-card { max-height: 400rpx; overflow: hidden; position: relative; }
.interpretation-card.expanded { max-height: none; }
.interpretation-card:not(.expanded)::after {
  content: ''; position: absolute; bottom: 0; left: 0; right: 0;
  height: 120rpx; background: linear-gradient(transparent, var(--color-bg-card));
  pointer-events: none;
}
```

### Minor（4个）

#### M1. 每日一牌按钮标签误导

**文件**：`/mnt/e/tarot-miniapp/miniapp/pages/index/index.wxml` line 70  
**文件**：`/mnt/e/tarot-miniapp/miniapp/pages/index/index.js` line 17

**问题**：每日一牌是免费功能，不消耗每日占卜额度。但每日一牌按钮上显示 `{{freeCount}}/1 次免费`，freeCount 对应后端 `free_readings_today`（占卜已用次数）。用户看到"1/1"后以为每日一牌也受限，产生困惑。实际上用户点完每日一牌后可以立即使用占卜牌阵。

**修复**：将每日一牌区域按钮文案改为"点击抽取今日运势"（已存在）+ 移除"X/1 次免费"标签，或改为"每日运势 · 免费"。

#### M2. 个人中心历史记录总数显示不准确

**文件**：`/mnt/e/tarot-miniapp/miniapp/pages/profile/profile.wxml` line 66  
**文件**：`/mnt/e/tarot-miniapp/miniapp/pages/profile/profile.js` line 28

**问题**：历史记录统计显示 `readingHistory.length`（当前已加载的条数，最多20），而非后端返回的 `total` 字段。如果用户有50条记录，页面显示"历史记录 20"而非"50"。API 返回的 `total` 字段未被前端使用。

**修复**：在 loadData 中保存 `history.total`，WXML 中使用 `{{historyTotal}}` 而非 `{{readingHistory.length}}`。

#### M3. 解读结果页缺少 onShareAppMessage 处理

**文件**：`/mnt/e/tarot-miniapp/miniapp/pages/reading-result/reading-result.js`

**问题**：解读结果页使用 `open-type="share"` 的按钮，但页面未定义 `onShareAppMessage` 生命周期函数。微信小程序默认分享行为只会分享当前页面路径，无法自定义分享标题、图片、路径参数，也无法将 `sharer_id` 传递给分享链接。这导致分享追踪（`/share/track` API）无法正确归因，分享裂变奖励形同虚设。

**修复**：添加 `onShareAppMessage`：
```javascript
onShareAppMessage() {
  const reading = this.data.reading;
  return {
    title: `我抽到了${reading?.drawn_cards?.[0]?.card_name || '命运之轮'} - 塔罗占卜`,
    path: `/pages/reading-result/reading-result?id=${this.options?.id}&sharer_id=${getApp().globalData.user?.id}`,
  };
},
```

#### M4. 年度运势报告无法单独购买

**文件**：`/mnt/e/tarot-miniapp/miniapp/pages/membership/membership.js` line 18  
**文件**：`/mnt/e/tarot-miniapp/backend/app/services/payment.py` line 27

**问题**：后端定义了 `annual_report` 产品（29.90元，独立购买），但会员页面用 `.filter(p => p.type === 'membership')` 将其过滤掉。年度报告页面检查会员状态（非会员返回402），非会员无法通过UI购买年度报告，只能买会员。

**修复**：在 annual-report 页面对非会员增加"单独购买年度报告"的引导链接，或在membership页面增加非会员专用购买入口。

---

## 付费流程审计

| 步骤 | 状态 | 说明 |
|------|------|------|
| 商品列表展示 | ✓ | membership/products 返回齐全，前端过滤展示membership类型 |
| 创建订单 | ✓ | POST /orders 返回支付参数 |
| 调用微信支付 | ✓ | wx.requestPayment 带正确参数 |
| 支付回调 | ✓ | 验证签名+解密+处理，幂等设计 |
| 会员权益生效 | ✓ | 回调后更新 is_member + member_expires_at |
| 单次购买计次 | ✓ | paid_readings_balance +1 |
| 权益扣减 | ✓ | readings.py 优先消耗免费次数，次用付费余额 |
| 续费叠加 | ✓ | member_expires_at 延长而非覆盖 |
| 过期检查 | ✓ | readings.py 自动降级 |
| **分享裂变奖励** | **✓** | **已修复，分享后 free_readings_today -1** |
| **年度报告购买** | **✗** | **不可单独购买（M4）** |

---

## 用户体验断层审计

| 场景 | 状态 | 说明 |
|------|------|------|
| 首次打开 | ✓ | 自动微信登录，骨架屏加载 |
| 每日一牌 | ✓ | 不再消耗占卜额度 |
| 选择牌阵 | ✓ | 10种牌阵，含会员/热门标记 |
| 输入问题 | ✓ | 主题选择+字数统计 |
| AI解读中 | ✓ | 3阶段进度提示 |
| **解读结果展开/收起** | **✗** | **折叠功能完全失效（I1）** |
| 解读失败重试 | ✓ | reinterpret 按钮+API |
| 追问 | ✓ | 上下文保持+剩余次数提示 |
| **分享裂变** | **△** | **分享按钮存在但没有 onShareAppMessage (M3)** |
| 年度报告 | ✓ | 已支持缓存+持久化 |
| 支付失败 | ✓ | 取消/失败分别提示 |
| 个人中心统计 | ✗ | 历史总数只显示第一页数量（M2） |

---

## 建议修复优先级

1. **[Important]** reading-result 解读折叠功能修复 → 直接影响核心阅读体验
2. **[Minor]** index.wxml 每日一牌按钮文案修正 → 消除用户困惑
3. **[Minor]** profile 历史记录总数修复 → 数据准确性
4. **[Minor]** reading-result 添加 onShareAppMessage → 分享裂变闭环
5. **[Minor + 遗留]** reading-result card nameEn/cardNumber 填充 → 提升卡牌展示质感
6. **[Minor + 遗留]** encyclopedia 搜索防抖 → 300ms setTimeout
7. **[Minor + 遗留]** membership 支付跳转优化 → 根据product_type分流
8. **[Minor + 遗留]** sitemap.json 创建
9. **[Minor]** annual-report 单独购买入口 → 补全付费路径
10. **[工程]** Alembic 初始化 + 核心 API 测试
