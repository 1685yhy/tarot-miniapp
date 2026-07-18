# 星光映照 — 优化设计文档

**日期**: 2026-07-18
**类型**: 质量优化（三轮分层推进）
**基线**: 131 commits, master @ 432534d

---

## 概述

对"星光映照"微信小程序进行全面质量优化，覆盖代码架构、视觉一致性、交互体验三个维度。采用三轮分层推进策略，每轮独立验证。

---

## 第一轮：基础重构（代码质量 + 系统一致性）

### 1.1 消除代码重复

**问题**: 78张卡牌注册表在 `tarot-card.js` 和 `profile.js` 中完全重复（~80行），`computeImagePath()` 逻辑在5个文件中重复。

**方案**:
- 抽取 `CARD_REGISTRY` 到 `utils/cards.js`，作为唯一数据源
- 抽取 `computeImagePath()` 到 `utils/cards.js`，统一导出
- 抽取 `SUIT_ZH`、`THEME_LABELS` 等常量到 `utils/constants.js`
- 所有页面和组件从 utils 导入，删除本地副本

**文件变更**:
- 新建: `utils/cards.js` — 卡牌注册表 + 图片路径计算
- 新建: `utils/constants.js` — 花色映射、主题标签等常量
- 修改: `components/tarot-card/tarot-card.js` — 从 utils 导入
- 修改: `pages/profile/profile.js` — 删除重复注册表，从 utils 导入
- 修改: `pages/reading-result/reading-result.js` — 使用统一 computeImagePath
- 修改: `pages/card-detail/card-detail.js` — 使用统一 computeImagePath
- 修改: `pages/encyclopedia/encyclopedia.js` — 使用统一 computeImagePath

**验收**: 所有 `computeImagePath` 调用点指向同一个函数；`CARD_REGISTRY` 唯一定义在 `utils/cards.js`

### 1.2 统一CSS变量体系

**问题**: 4套不同的CSS变量命名空间（`--color-*`、`--gold`、`--sl-*`、`--ds-*`），大量硬编码颜色值。

**方案**:
- 以 `common.wxss` 的 `--color-*` 体系为唯一标准
- 将所有页面的硬编码颜色替换为 CSS 变量引用
- 移除各页面自定义的局部变量（`--gold`、`--sl-gold`、`--ds-gold`），统一使用 `--color-gold`
- 保留 `card-detail` 页面的深色背景风格意图，但使用 CSS 变量 override 而非独立命名空间

**文件变更**:
- 修改: `pages/reading/reading.wxss` — 替换局部变量为全局变量
- 修改: `pages/reading-result/reading-result.wxss` — 替换所有硬编码颜色
- 修改: `pages/card-detail/card-detail.wxss` — 统一到全局变量，保留深色风格通过变量覆盖
- 修改: `pages/diary/diary.wxss` — 替换 `--ds-*` 为全局变量
- 修改: `pages/chat/chat.wxss` — 替换局部变量
- 修改: `pages/membership/membership.wxss` — 替换局部变量
- 修改: `components/tarot-card/tarot-card.wxss` — 替换硬编码颜色

**验收**: `grep -r "#[0-9a-fA-F]\{6\}" pages/ components/` 仅在定义CSS变量的 `common.wxss` 中出现颜色值

### 1.3 修复死链接和WXSS兼容性

**问题**: `encyclopedia.js` 中导航到不存在的 `/pages/home/home`；`reading.wxss` 中使用WXSS不支持的 `rotateY()`。

**方案**:
- 修复 `encyclopedia.js:145` 的导航路径为 `/pages/index/index`
- 将洗牌动画从 `rotateY()` 改为 `scaleX()` + `opacity` 模拟（与 `tarot-card` 的翻转方案一致）

**文件变更**:
- 修改: `pages/encyclopedia/encyclopedia.js`
- 修改: `pages/reading/reading.wxss`

**验收**: 百科页"今日一牌"入口点击后正确跳转首页；洗牌动画在微信开发者工具中正常渲染

### 1.4 抽取内联样式

**问题**: `index.wxml` 和 `reading.wxml` 中存在大量内联 `style="..."`。

**方案**:
- 将重复的内联样式模式提取为 CSS 类
- 保留需要动态绑定数据的样式在模板中

**文件变更**:
- 修改: `pages/index/index.wxml` + `index.wxss`
- 修改: `pages/reading/reading.wxml` + `reading.wxss`

---

## 第二轮：视觉打磨（Typography + 动效 + 空间）

### 2.1 字体比例数学化

**问题**: typography scale已定义（22/28/34/44/60 rpx），但页面中使用不一致的字体大小（出现 20rpx、24rpx、30rpx、40rpx、48rpx、52rpx、58rpx 等非标值）。

**方案**:
- 将 typography scale 升级为 Major Third (1.25) 比例：
  - `--font-size-xs`: 20rpx（新增）
  - `--font-size-caption`: 24rpx（从22调整）
  - `--font-size-body`: 30rpx（从28调整）
  - `--font-size-subhead`: 36rpx（从34调整）
  - `--font-size-title`: 44rpx（不变）
  - `--font-size-display`: 56rpx（从60调整）
- 所有页面统一引用这些变量，不允许魔术数字

**文件变更**:
- 修改: `styles/common.wxss` — 更新 typography tokens
- 修改: 所有页面 WXSS — 统一使用 typography 变量

### 2.2 动效时机校准

**问题**: 动画 duration 分散在各处，缺乏系统性。

**方案**:
- 审核所有动画，确保遵循 motion design 原则:
  - Feedback: 50-150ms（按钮按下、toast出现）
  - Orientation: 200-400ms（页面切换、卡片入场）
  - Emphasis: 300-600ms（hero动画、特殊强调）
- 统一使用 `common.wxss` 的 `--duration-*` 和 `--ease-*` 变量
- 确保所有动画 `will-change` 策略一致

**文件变更**:
- 修改: 所有页面 WXSS — 统一动画参数
- 审查: `utils/animate.js` — 确保JS动画也遵循相同 timing

### 2.3 空间节奏统一

**问题**: spacing scale 中 `--spacing-2xl` ~ `--spacing-5xl` 全部是 64rpx，没有实际差异。

**方案**:
- 修复 spacing scale 为真实的递增序列：
  - `--spacing-xxs`: 8rpx
  - `--spacing-xs`: 12rpx
  - `--spacing-sm`: 16rpx
  - `--spacing-md`: 24rpx
  - `--spacing-lg`: 32rpx
  - `--spacing-xl`: 48rpx
  - `--spacing-2xl`: 64rpx（从64改为实际64）
  - `--spacing-3xl`: 80rpx（从64修复）
  - `--spacing-4xl`: 96rpx（从64修复）
  - `--spacing-5xl`: 128rpx（从64修复）
- 审核各页面 margin/padding 使用，确保引用正确的 spacing 级别

---

## 第三轮：体验补全（状态覆盖 + 韧性 + 无障碍）

### 3.1 统一骨架屏

**问题**: 每个页面定义了自己的 skeleton 样式和 shimmer 动画。

**方案**:
- 将骨架屏基础样式提升到 `common.wxss` 第12节
- 各页面只定义特定尺寸的 skeleton block

### 3.2 空状态和错误状态审核

**问题**: 部分页面错误状态缺少重试按钮，空状态缺少引导文案。

**方案**:
- 逐页审核：loading → error（含重试）→ empty（含引导CTA）→ 正常内容
- 确保错误信息对用户可理解（而非原始错误消息）

### 3.3 API韧性

**问题**: `api.js` 无重试机制，`checkLogin()` 无并发锁。

**方案**:
- 为 `request()` 添加自动重试（最多2次，指数退避）
- 为 `checkLogin()` 添加进行中锁，防止并发调用

### 3.4 低优先级修复

- 统一 timer 管理（全部使用 `_timers` 数组模式）
- `_destroyed` 标志移到实例属性而非 `this.data`
- 移除硬编码 `confirmColor: '#F4D48C'`
- 会员支付 `signType` 升级到 'HMAC-SHA256'

---

## 实施策略

每轮使用 Workflow 编排多个专业子代理并行工作：

```
第一轮: 4个代理并行
  Agent 1: 抽取 cards.js + constants.js，重构所有导入
  Agent 2: CSS变量统一（reading + reading-result + card-detail）
  Agent 3: CSS变量统一（diary + chat + membership + tarot-card）
  Agent 4: 修复死链接 + rotateY + 内联样式清理

第二轮: 3个代理并行
  Agent 5: Typography scale 升级
  Agent 6: 动效时机统一
  Agent 7: 空间节奏修复

第三轮: 3个代理并行
  Agent 8: 骨架屏统一
  Agent 9: 状态覆盖审核
  Agent 10: API韧性 + 低优先级修复
```

每轮结束后 commit，然后开始下一轮。

---

## 验收标准

1. `grep -r "computeImagePath"` 仅在一处定义
2. `grep -r "#1A1A3E\|#F4D48C\|#252550\|#B8A9E0" pages/ components/` 无硬编码颜色（除 common.wxss）
3. 微信开发者工具编译零错误零警告
4. 所有页面 skeleton → error → empty → content 四种状态完整
5. Typography 比例严格遵循 Major Third (1.25)
6. Spacing scale 值为真实递增序列
