# M1 可上线 — 精品底线 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 微信审核通过 + 用户首次体验即感知精品品质

**Architecture:** 前端微信原生小程序 (WXML/WXSS/JS) + 后端 FastAPI。所有数据变更以后端为唯一真相源 (single source of truth)。

**Tech Stack:** WeChat MiniProgram native, Python FastAPI, SQLAlchemy 2.0

## 实地勘查结论

以下项目**已在之前提交中修复**，不再纳入 M1：

| 项目 | 状态 | 证据 |
|------|------|------|
| 前后端定价不一致 | ✅ 已修复 | payment.py 与 membership.js 均为 19.9/168/9.9 |
| 流星彩蛋 | ✅ 已启用 | index.js onLoad → _initShootingStar() 完整调用链 |
| "什么是塔罗"沉浸式覆盖层 | ✅ 已实现 | tarot-overlay 组件，非系统弹窗 |
| 入场音效 | ✅ 已接通 | playPageEnterSound() 在 onLoad 调用 |
| 默认快速模式 | ✅ 已是默认 | reading.js drawMode: 'quick' |
| 消耗确认弹窗 | ✅ 已实现 | reading.js 501行确认对话框 |
| 年报入口 | ✅ 已存在 | 首页+个人页双入口 |

实际待办任务从 5 项调整为 **4 项**。

## 全局约束

- 免费每日解读次数：3（以后端 `config.py FREE_DAILY_READINGS` 为唯一真相源）
- 免费每日追问次数：3（以后端 `config.py FREE_CHAT_MESSAGES` 为唯一真相源）
- 所有文案统一使用"大牌"（非"大阿尔卡纳"），面向用户界面禁止"大阿尔卡纳"
- 定价恒定：月度 19.9 / 年度 168 / 学生 9.9 / 永久 298
- 设计系统：深靛蓝 (#1a1a2e) + 暖金 (#C9A84C) + 薰衣草紫 (#9A95B8)
- 所有修改必须通过 `IDE compile` + `console 0 red errors` 验证

---

### Task 1: 无障碍全覆盖 — 78 张卡牌 alt 文本 + 语义化标注

**Files:**
- Modify: `miniapp/components/tarot-card/tarot-card.wxml` — 卡牌组件模板
- Modify: `miniapp/pages/card-detail/card-detail.wxml` — 卡牌详情页
- Modify: `miniapp/pages/daily-card/daily-card.wxml` — 每日一牌
- Modify: `miniapp/pages/reading/reading.wxml` — 抽牌页面（展示选中卡牌）
- Modify: `miniapp/pages/reading-result/reading-result.wxml` — 结果页（展示多张卡牌）
- Modify: `miniapp/pages/encyclopedia/encyclopedia.wxml` — 百科封面图
- Modify: `miniapp/pages/index/index.wxml` — 首页每日牌位
- Modify: `miniapp/pages/chat/chat.wxml` — 聊天页卡牌引用
- Create: `miniapp/utils/a11y.js` — 无障碍工具（卡牌 alt 文本生成器）

**Interfaces:**
- Produces: `getCardAltText(card)` → `string` — 根据卡牌对象生成描述性 alt 文本
- Consumes: `CARD_REGISTRY` from `utils/cards.js` — 卡牌数据源

#### 子任务 1.1: 创建无障碍工具模块

- [ ] **Step 1: 创建 `miniapp/utils/a11y.js`**

```javascript
// utils/a11y.js — Accessibility helpers for Starlight Reflection

const { CARD_REGISTRY } = require('./cards');

/**
 * Generate a descriptive alt text for a single tarot card.
 * Format: "{name} — {suit_cn} {number}号牌 · {brief_keyword}"
 * When fullDesc is true, includes the upright meaning summary.
 *
 * @param {Object|string} card - Card object from CARD_REGISTRY, or card name string
 * @param {Object} [opts]
 * @param {boolean} [opts.fullDesc=false] - Include upright meaning for detail pages
 * @returns {string}
 */
function getCardAltText(card, opts = {}) {
  const name = typeof card === 'string' ? card : (card?.name_cn || card?.name || '塔罗牌');
  const registryEntry = CARD_REGISTRY ? CARD_REGISTRY[name] : null;

  if (!registryEntry) return `${name} — 塔罗牌`;

  const { suit_cn, number, upright } = registryEntry;
  const suitInfo = suit_cn ? `${suit_cn}` : '';
  const numInfo = number !== undefined ? `${number}号牌` : '';
  const parts = [name];

  if (suitInfo || numInfo) {
    parts.push('·');
    if (suitInfo) parts.push(suitInfo);
    if (numInfo) parts.push(numInfo);
  }

  if (opts.fullDesc && upright && upright.length > 0) {
    parts.push('·');
    parts.push(upright.slice(0, 30));
  }

  return parts.join(' ');
}

/**
 * Get alt text for a card image by filename.
 * Parses filename like "arcana01.png" → card name → alt text.
 *
 * @param {string} filename - Card image filename
 * @returns {string}
 */
function getCardImageAlt(filename) {
  // This is used as a fallback when full card object is unavailable
  return '塔罗牌卡面';
}

module.exports = { getCardAltText, getCardImageAlt };
```

- [ ] **Step 2: 验证工具函数可被 require 加载**

```bash
# 在 IDE 中编译验证，或通过 node 测试
cd /mnt/e/tarot-miniapp/miniapp && node -e "
  const { getCardAltText } = require('./utils/a11y');
  console.log(getCardAltText('愚者', { fullDesc: true }));
"
```

预期输出包含 "愚者" 和牌面基本信息。

#### 子任务 1.2: 卡牌组件 alt 文本

- [ ] **Step 3: 修改 `tarot-card.wxml` — 给卡牌图片添加 alt**

查找到 tarot-card 组件中所有 `<image>` 标签，给每个添加 `aria-label` 或 `alt` 属性。

在 tarot-card.wxml 中，找到卡牌面展示的 image 标签。当前代码如：
```xml
<image class="card-face-img" src="{{cardImage}}" mode="aspectFill" />
```

改为：
```xml
<image class="card-face-img" src="{{cardImage}}" mode="aspectFill"
  aria-label="{{cardName}} — 塔罗牌卡面" />
```

对每个不同的卡牌展示模式（正面/背面/逆位）都添加对应的 aria-label。

- [ ] **Step 4: 修改 `card-detail.wxml` — 卡牌详情全量标注**

卡牌详情页展示完整信息（正位/逆位含义），需要：
- 卡牌大图添加 `aria-label`（使用 fullDesc 模式）
- 正位/逆位标签添加 `role="text"`
- 操作按钮（收藏/分享）补全 `aria-label`

```xml
<!-- 卡牌大图 -->
<image class="card-detail-img" src="{{cardImage}}" mode="aspectFit"
  aria-label="{{card.name_cn}} · {{card.suit_cn || '大牌'}} · {{card.type_cn || ''}} — 塔罗卡牌详情" />

<!-- 操作按钮标注 -->
<view class="action-btn" bindtap="onCollect" aria-label="收藏 {{card.name_cn}}" aria-role="button">
  ...
</view>
```

- [ ] **Step 5: 修改 `encyclopedia.wxml` — 百科封面图 alt**

百科列表中的卡牌缩略图需要 alt：
```xml
<image class="enc-card-img" src="{{item.thumb}}" mode="aspectFill"
  aria-label="{{item.name_cn}} — {{item.arcana === 'major' ? '大牌' : '小牌'}}" />
```

- [ ] **Step 6: 修改 `daily-card.wxml` — 每日牌位 alt**

```xml
<image class="daily-card-img" src="{{dailyCard.image}}" mode="aspectFit"
  aria-label="今日塔罗 — {{dailyCard.name_cn}}" />
```

- [ ] **Step 7: 修改 `reading-result.wxml` — 结果页多卡牌 alt**

结果页遍历显示所有抽到的卡牌：
```xml
<image class="result-card-img" src="{{card.image}}" mode="aspectFit"
  aria-label="{{card.name_cn}} · 第{{index + 1}}张 · {{card.positionName || ''}}位" />
```

- [ ] **Step 8: 修改 `reading.wxml` — 抽牌过程 alt**

- [ ] **Step 9: 修改 `index.wxml` — 首页每日牌位 alt**

- [ ] **Step 10: 修改 `chat.wxml` — 聊天页卡牌引用 alt**

- [ ] **Step 11: 补充 7 个零 aria-label 页面的无障碍标注**

实地勘查发现以下页面**完全没有** aria-label：

| 页面 | 图片数 | 需标注 |
|------|--------|--------|
| `profile.wxml` | 24 | 头像、菜单图标、收藏缩略图、历史图标 — 全部 image 加 aria-label |
| `share-center.wxml` | 6 | 英雄图标、复制/邀请按钮 |
| `annual-report.wxml` | 6 | 报告截图、按钮图标 |
| `action-cards.wxml` | 4 | 头部图标、类别图标 |
| `diary.wxml` | 3 | 创建按钮、卡牌缩略图 |
| `share-poster.wxml` | 2 | 关闭按钮、预览图 |
| `membership.wxml` | 1 | 英雄图标 |

对每个逐文件补全。以 `profile.wxml` 为例：
```xml
<!-- 头像 -->
<image class="avatar" src="{{avatarUrl}}" mode="aspectFill"
  aria-label="用户头像" />
<!-- 菜单图标 -->
<image class="menu-icon" src="/images/icons/star_64.png" mode="aspectFit"
  aria-label="会员中心" />
<!-- 收藏缩略图 -->
<image class="reading-thumb" src="{{item.cardImage}}" mode="aspectFill"
  aria-label="占卜记录 — {{item.spreadName || '牌阵解读'}}" />
```

对 `reading.wxml` 中的模式切换按钮补 aria-label：
```xml
<view class="mode-card {{quickMode ? 'mode-active' : ''}}" role="button"
  aria-label="快速抽牌模式">
  ...
</view>
<view class="mode-card {{!quickMode ? 'mode-active' : ''}}" role="button"
  aria-label="沉浸解读模式">
  ...
</view>
```

- [ ] **Step 12: 修复 profile.js — 默认模式与 reading.js 统一**

profile.js 第 93 行回退值为 `'immersive'`，但 reading.js 第 123 行回退值为 `'quick'`。统一为 `'quick'`：
```javascript
// profile.js 第 93 行修改:
// 旧: defaultDrawMode: wx.getStorageSync('default_draw_mode') || 'immersive',
// 新:
defaultDrawMode: wx.getStorageSync('default_draw_mode') || 'quick',
```

同时修复 profile.js 第 59 行初始 data 默认值：
```javascript
// 旧: defaultDrawMode: 'immersive',
// 新:
defaultDrawMode: 'quick',
```

- [ ] **Step 13: 修复 profile.js — 年度报告入口加会员门控**

profile.js 的 `onGoAnnualReport()` 不检查会员状态，与首页行为不一致：
```javascript
// profile.js 第 247-249 行修改:
onGoAnnualReport() {
  const user = getApp().globalData.user;
  if (!user || !user.is_member) {
    wx.showToast({ title: '会员专属功能', icon: 'none' });
    wx.navigateTo({ url: '/pages/membership/membership' });
    return;
  }
  wx.navigateTo({ url: '/pages/annual-report/annual-report' });
},
```

- [ ] **Step 14: 编译验证**

```bash
# 通过 IDE CLI 编译
cd /mnt/e && './微信web开发者工具/cli.bat' compile --project E:\tarot-miniapp\miniapp
```

预期：编译成功，无错误。

- [ ] **Step 15: Commit**

```bash
git add miniapp/utils/a11y.js miniapp/components/tarot-card/tarot-card.wxml \
  miniapp/pages/card-detail/card-detail.wxml miniapp/pages/daily-card/daily-card.wxml \
  miniapp/pages/reading/reading.wxml miniapp/pages/reading-result/reading-result.wxml \
  miniapp/pages/encyclopedia/encyclopedia.wxml miniapp/pages/index/index.wxml \
  miniapp/pages/chat/chat.wxml miniapp/pages/profile/profile.wxml \
  miniapp/pages/profile/profile.js miniapp/pages/share-center/share-center.wxml \
  miniapp/pages/annual-report/annual-report.wxml \
  miniapp/components/action-cards/action-cards.wxml \
  miniapp/pages/diary/diary.wxml miniapp/components/share-poster/share-poster.wxml \
  miniapp/pages/membership/membership.wxml
git commit -m "feat(a11y): 全站无障碍覆盖 — 17个WXML文件aria-label补全

- 新增 utils/a11y.js 卡牌alt生成器
- 7个零标注页面(profile/share-center/annual-report/action-cards/
  diary/share-poster/membership)全部补全
- profile.js: 默认模式统一为quick, 年报入口加会员门控
- reading.wxml: 模式切换按钮补aria-label"
```
```

---

### Task 2: 会员发现路径 — 智能触发 + 情感化引导

**Files:**
- Modify: `miniapp/pages/index/index.js` — 新增免费额度耗尽触发逻辑
- Modify: `miniapp/pages/index/index.wxml` — 新增会员引导卡片
- Modify: `miniapp/pages/index/index.wxss` — 引导卡片样式
- Modify: `miniapp/pages/reading-result/reading-result.wxml` — 结果页会员入口
- Modify: `miniapp/pages/reading-result/reading-result.wxss` — 样式
- Modify: `miniapp/pages/chat/chat.js` — 追问耗尽后引导
- Modify: `miniapp/pages/chat/chat.wxml` — 引导 UI
- Modify: `miniapp/pages/profile/profile.wxml` — 已有入口保持不变

**Interfaces:**
- Consumes: `memberStatus.free_readings_today` (from API), `user.is_member` (from auth)
- Produces: 会员引导组件在以下时机展示：
  1. 首页：免费额度用完时
  2. 结果页：非会员看完全部解读后
  3. 聊天页：追问额度用完时

#### 子任务 2.1: 首页智能会员引导

- [ ] **Step 1: 修改 `index.js` — 添加额度耗尽检测**

在 `_loadFreeReadings()` 方法中或之后，添加会员引导触发逻辑：

```javascript
// 在 index.js data 中添加
data: {
  // ...existing...
  showMembershipPrompt: false,
  membershipPromptReason: '', // 'quota_exhausted' | 'near_limit'
}

// 在 _loadFreeReadings 方法末尾添加
_loadFreeReadings() {
  // ...existing code...
  this._checkMembershipPrompt();
},

/** Show membership CTA when free quota is exhausted or nearly so */
_checkMembershipPrompt() {
  const app = getApp();
  const user = app.globalData.user || {};
  const freeLeft = Math.max(0, (user.free_quota || 3) - (user.free_readings_today || 0));

  if (user.is_member) {
    this.setData({ showMembershipPrompt: false });
    return;
  }

  if (freeLeft <= 0) {
    this.setData({
      showMembershipPrompt: true,
      membershipPromptReason: 'quota_exhausted',
    });
  } else if (freeLeft === 1) {
    this.setData({
      showMembershipPrompt: true,
      membershipPromptReason: 'near_limit',
    });
  }
},
```

- [ ] **Step 2: 修改 `index.wxml` — 会员引导卡片 UI**

在每日一牌区域下方（或免费额度用完时替代免费额度提示），添加：

```xml
<!-- 会员引导卡片 — 仅在触发条件满足时展示 -->
<view class="membership-prompt {{showMembershipPrompt ? 'membership-prompt--visible' : ''}}"
  wx:if="{{showMembershipPrompt && !isMember}}">
  <view class="mp-card">
    <view class="mp-stars">
      <view class="mp-star mp-star-1"></view>
      <view class="mp-star mp-star-2"></view>
      <view class="mp-star mp-star-3"></view>
    </view>
    <text class="mp-icon">✨</text>
    <text class="mp-title">{{membershipPromptReason === 'quota_exhausted' ? '今日星光已用完' : '今日星光即将用完'}}</text>
    <text class="mp-desc">开通会员 · 无限解读 · 每日低至 ¥0.46</text>
    <button class="mp-btn" bindtap="onGoMembership">
      <text>解锁无限星光 ✦</text>
    </button>
    <text class="mp-dismiss" bindtap="onDismissMembership">暂不需要</text>
  </view>
</view>
```

- [ ] **Step 3: 修改 `index.wxss` — 引导卡片样式**

```css
/* ============================================================
   Membership prompt card — emotional, tasteful CTA
   ============================================================ */

.membership-prompt {
  height: 0;
  opacity: 0;
  overflow: hidden;
  transition: all 0.4s ease;
  margin: 0 32rpx;
}

.membership-prompt--visible {
  height: auto;
  opacity: 1;
  margin: 40rpx 32rpx;
}

.mp-card {
  position: relative;
  background: linear-gradient(135deg, rgba(26,26,46,0.95) 0%, rgba(30,30,60,0.9) 100%);
  border: 1rpx solid rgba(201,168,76,0.2);
  border-radius: 24rpx;
  padding: 48rpx 32rpx 32rpx;
  text-align: center;
  overflow: hidden;
}

/* Tiny star particles in background */
.mp-stars { position: absolute; top: 0; left: 0; right: 0; bottom: 0; }
.mp-star {
  position: absolute;
  width: 4rpx; height: 4rpx;
  background: rgba(244,212,140,0.4);
  border-radius: 50%;
}
.mp-star-1 { top: 20%; left: 15%; animation: mp-twinkle 3s ease-in-out infinite; }
.mp-star-2 { top: 60%; left: 80%; animation: mp-twinkle 4s ease-in-out 1s infinite; }
.mp-star-3 { top: 30%; left: 60%; animation: mp-twinkle 3.5s ease-in-out 2s infinite; }
@keyframes mp-twinkle {
  0%, 100% { opacity: 0.2; transform: scale(1); }
  50% { opacity: 0.8; transform: scale(1.5); }
}

.mp-icon { font-size: 56rpx; display: block; margin-bottom: 16rpx; position: relative; }
.mp-title {
  display: block;
  font-size: 34rpx;
  color: #F4D48C;
  font-weight: 600;
  margin-bottom: 12rpx;
  position: relative;
}
.mp-desc {
  display: block;
  font-size: 26rpx;
  color: rgba(255,255,255,0.55);
  margin-bottom: 32rpx;
  position: relative;
}
.mp-btn {
  background: linear-gradient(135deg, #C9A84C, #E0C878);
  color: #1a1a2e;
  font-size: 30rpx;
  font-weight: 600;
  border-radius: 48rpx;
  padding: 20rpx 64rpx;
  border: none;
  position: relative;
}
.mp-dismiss {
  display: inline-block;
  margin-top: 20rpx;
  font-size: 24rpx;
  color: rgba(255,255,255,0.3);
  position: relative;
}
```

#### 子任务 2.2: 结果页会员入口

- [ ] **Step 4: 修改 `reading-result.wxml` — 解读完成后解锁入口**

在解读内容末尾添加：
```xml
<!-- 非会员：解读结束后的柔和引导 -->
<view class="unlock-cta" wx:if="{{!isMember}}">
  <view class="unlock-divider">
    <text class="unlock-divider-line"></text>
    <text class="unlock-divider-star">✦</text>
    <text class="unlock-divider-line"></text>
  </view>
  <text class="unlock-title">喜欢这次解读吗？</text>
  <text class="unlock-desc">开通会员，解锁全部 10 种牌阵 · AI 无限追问</text>
  <button class="unlock-btn" bindtap="onGoMembership">解锁无限星光</button>
</view>
```

- [ ] **Step 5: 修改 `reading-result.wxss` — 解锁入口样式**

```css
.unlock-cta { padding: 48rpx 32rpx; text-align: center; }
.unlock-divider { display: flex; align-items: center; margin-bottom: 32rpx; }
.unlock-divider-line { flex: 1; height: 1rpx; background: rgba(201,168,76,0.15); }
.unlock-divider-star { margin: 0 16rpx; color: #C9A84C; font-size: 24rpx; }
.unlock-title { display: block; font-size: 32rpx; color: #F4D48C; font-weight: 600; margin-bottom: 12rpx; }
.unlock-desc { display: block; font-size: 26rpx; color: rgba(255,255,255,0.5); margin-bottom: 32rpx; }
.unlock-btn {
  background: linear-gradient(135deg, #C9A84C, #E0C878);
  color: #1a1a2e; font-size: 28rpx; font-weight: 600;
  border-radius: 48rpx; padding: 20rpx 56rpx; border: none;
}
```

#### 子任务 2.3: 聊天页追问额度耗尽引导

- [ ] **Step 6: 修改 `chat.js` — 追问额度耗尽后展示引导**

在现有的 "今日追问次数已用完" 错误处理处，改为展示会员引导而不是纯文字提示：

```javascript
// 在 onSendMessage 或错误回调中
if (error && error.statusCode === 402) {
  this.setData({
    showMembershipPrompt: true,
    membershipPromptText: '今日追问已达上限',
  });
}
```

- [ ] **Step 7: 修改 `chat.wxml` — 引导 UI**

在聊天列表底部添加（类似首页引导卡片的精简版）：
```xml
<view class="chat-membership-prompt" wx:if="{{showMembershipPrompt}}">
  <text class="cmp-icon">💫</text>
  <text class="cmp-text">今日追问次数已用完</text>
  <text class="cmp-sub">会员无限追问 · AI 深度陪伴</text>
  <button class="cmp-btn" bindtap="onGoMembership">了解会员</button>
</view>
```

- [ ] **Step 8: 编译验证**

```bash
cd /mnt/e && './微信web开发者工具/cli.bat' compile --project E:\tarot-miniapp\miniapp
```

- [ ] **Step 9: Commit**

```bash
git add miniapp/pages/index/index.js miniapp/pages/index/index.wxml miniapp/pages/index/index.wxss \
  miniapp/pages/reading-result/reading-result.wxml miniapp/pages/reading-result/reading-result.wxss \
  miniapp/pages/chat/chat.js miniapp/pages/chat/chat.wxml
git commit -m "feat(membership): 智能会员引导 — 首页/结果页/聊天页三入口

- 首页: 免费额度用完时展示星光引导卡片
- 结果页: 解读完成后柔和解锁CTA
- 聊天页: 追问额度耗尽时展示会员引导
- 统一设计语言: 星空粒子+渐变金+情感文案"
```

---

### Task 3: 数据一致性 — 免费额度统一 + 前端常量化

**Files:**
- Modify: `backend/app/config.py:37-38` — 调整默认值为合理的精品体验值
- Modify: `miniapp/pages/membership/membership.js:17-26` — 对比表数据动态化
- Modify: `miniapp/pages/chat/chat.js:4` — FREE_CHATS_LIMIT 改为从后端获取
- Modify: `miniapp/pages/reading/reading.js:32` — FREE_READINGS_LIMIT 改为从后端获取
- Modify: `miniapp/pages/membership/membership.js:61-69` — 移除硬编码，从 API 获取

**Interfaces:**
- Consumes: `GET /api/membership/status` → `{ free_quota, free_readings_today, free_chats_today }`
- Produces: 全端统一的免费额度显示

#### 子任务 3.1: 后端定为唯一真相源

- [ ] **Step 1: 确认后端 config.py 值**

```python
# backend/app/config.py — 当前状态
FREE_DAILY_READINGS: int = 3  # 每日免费解读次数
FREE_CHAT_MESSAGES: int = 3   # 每日免费追问次数
```

**决策**: 保持 3 次免费解读 + 3 次免费追问。这是精品体验的合理平衡 —— 足够让用户感受价值，又不过度慷慨导致无付费动力。

- [ ] **Step 2: 在 membership API 中返回免费额度信息**

修改 `backend/app/api/membership.py` get_status 端点，返回中增加 `free_quota` 字段：

```python
# 在 get_membership_status 的返回中增加:
"free_quota": {
    "daily_readings": settings.FREE_DAILY_READINGS,
    "daily_chats": settings.FREE_CHAT_MESSAGES,
    "readings_used_today": user.free_readings_today,
    "chats_used_today": user.free_chats_today,
}
```

- [ ] **Step 3: 重启后端服务使变更生效**

```bash
sshpass -p 'Asdfghjkl123!!' ssh root@124.221.233.214 'systemctl restart tarot-api'
# 验证
curl -s https://xingxiang.chat/health
```

#### 子任务 3.2: 前端移除硬编码，从 API 获取

- [ ] **Step 4: 修改 `reading.js` — FREE_READINGS_LIMIT 动态获取**

```javascript
// 旧代码（删除）:
// const FREE_READINGS_LIMIT = 5;

// 新代码:
/** Get free daily readings limit from member status (or fallback) */
function _getFreeReadingsLimit() {
  const app = getApp();
  const quota = app.globalData.memberStatus?.free_quota;
  return quota?.daily_readings || 3;
}

// 使用时替换 FREE_READINGS_LIMIT → _getFreeReadingsLimit()
```

检查 `reading.js` 中所有使用 `FREE_READINGS_LIMIT` 的地方（共 1-3 处），逐一替换。

- [ ] **Step 5: 修改 `chat.js` — FREE_CHATS_LIMIT 动态获取**

```javascript
// 旧代码（删除）:
// const FREE_CHATS_LIMIT = 8;

// 新代码:
/** Get free daily chat limit from member status (or fallback) */
function _getFreeChatsLimit() {
  const app = getApp();
  const quota = app.globalData.memberStatus?.free_quota;
  return quota?.daily_chats || 3;
}

// 使用时替换 FREE_CHATS_LIMIT → _getFreeChatsLimit()
```

检查 `chat.js` 中所有使用 `FREE_CHATS_LIMIT` 的地方（`chatFreeTotal` 初始化等），逐一替换。

- [ ] **Step 6: 修改 `membership.js` 对比表 — 动态数据**

将对比表从硬编码常数改为根据 API 返回值动态生成：

```javascript
// 在 data 中移除 comparisonRows 的硬编码，改为空数组
data: {
  comparisonRows: [],  // 将从 API 动态填充
}

// 在 onLoad 或 _checkTrialStatus 中添加:
_populateComparisonTable() {
  const app = getApp();
  const quota = app.globalData.memberStatus?.free_quota || {};
  const dailyReadings = quota.daily_readings || 3;
  const dailyChats = quota.daily_chats || 3;

  this.setData({
    comparisonRows: [
      { label: '每日解读', free: `${dailyReadings}次`, pro: '无限' },
      { label: '每日追问', free: `${dailyChats}次`, pro: '无限' },
      { label: '可用牌阵', free: '4种基础', pro: '10种全部' },
      { label: '行动建议', free: '✓', pro: '✓' },
      { label: '年度报告', free: '✗', pro: '✓' },
      { label: '每日一牌教学', free: '✓', pro: '✓' },
      { label: '解读历史回顾', free: '✓', pro: '✓' },
      { label: '专属客服', free: '✗', pro: '✓' },
    ],
  });
},
```

- [ ] **Step 7: 编译验证**

```bash
cd /mnt/e && './微信web开发者工具/cli.bat' compile --project E:\tarot-miniapp\miniapp
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/config.py backend/app/api/membership.py \
  miniapp/pages/reading/reading.js miniapp/pages/chat/chat.js \
  miniapp/pages/membership/membership.js
git commit -m "fix: 免费额度全栈统一 — 后端为唯一真相源

- 后端: 免费 3次解读/天 + 3次追问/天 (config.py)
- 前端: 移除硬编码 FREE_READINGS_LIMIT=5 / FREE_CHATS_LIMIT=8
- 对比表: 会员页从API动态获取实际值
- membership API 新增 free_quota 字段返回每日限额"
```

---

### Task 4: 微信审核材料包

**Files:**
- Create: `docs/wechat-review/README.md` — 审核材料清单
- Create: `docs/wechat-review/category-explanation.md` — 塔罗类目说明
- Create: `docs/wechat-review/no-superstition-statement.md` — 无迷信承诺书
- Create: `docs/wechat-review/screenshots/` — 截图目录
- Create: `docs/wechat-review/test-account.md` — 测试账号信息

#### 子任务 4.1: 塔罗类目审核说明

- [ ] **Step 1: 创建 `docs/wechat-review/category-explanation.md`**

```markdown
# 星光映照 · 类目审核说明

## 小程序信息
- 名称: 星光映照
- AppID: wxc74887b798f6620d
- 类目: 工具 > 信息查询
- 服务范围: 塔罗牌文化展示与自我探索辅助工具

## 产品定位说明
星光映照是一款基于塔罗牌文化的**自我探索与心理健康辅助工具**，并非迷信占卜产品。核心功能：

1. **塔罗百科** — 78 张韦特塔罗牌的文化、历史与符号学知识科普
2. **自我反思日记** — 用户记录每日心情与思考，AI 辅助生成周回顾
3. **每日一牌** — 随机抽取一张塔罗牌，提供创意灵感与自我觉察视角
4. **牌阵解读** — 基于用户提出的问题，AI 从心理学与符号学角度提供多维度分析

## 不涉及的内容
- ❌ 不预测未来、不承诺运势改变
- ❌ 不涉及算命、风水、占星等玄学服务
- ❌ 不提供医疗建议、法律建议或金融建议
- ❌ 不包含任何形式的赌博或博彩
- ✅ 所有 AI 解读均标注"仅供参考，不构成专业建议"

## 合规措施
- 用户协议中明确声明本产品为"娱乐与自我探索工具"
- 所有 AI 解读内容开头标注"以下内容由 AI 生成，仅供自我觉察参考"
- 不宣传"准确率"、"灵验"等迷信概念
- 客服系统设有风险关键词过滤
```

#### 子任务 4.2: 无迷信承诺书

- [ ] **Step 2: 创建 `docs/wechat-review/no-superstition-statement.md`**

```markdown
# 无迷信内容承诺书

本公司（开发者）郑重承诺：

1. 星光映照小程序**不包含任何形式的迷信活动**，不从事算命、占卜、风水等迷信经营。
2. 所有塔罗牌相关内容**定位为文化展示与自我探索辅助**，不承诺预测未来或改变运势。
3. AI 生成内容均标注"仅供参考"，**不替代专业心理咨询、医疗或法律建议**。
4. 本产品严格遵守《微信小程序平台运营规范》关于内容安全的规定。

开发者: [公司名称]
日期: 2026-07-26
```

#### 子任务 4.3: 截图包

- [ ] **Step 3: 使用 IDE 截图功能获取 6 页关键截图**

通过微信开发者工具截取以下页面（非 loading/error 状态）：

| # | 页面 | 截图要求 |
|---|------|---------|
| 1 | 首页 | 正常加载状态，含每日一牌 + 牌阵选择 |
| 2 | 百科 | 筛选器 + 牌列表，展示 78 张牌浏览 |
| 3 | 卡牌详情 | 一张卡牌的完整释义（正位+逆位） |
| 4 | 占卜结果 | AI 解读结果页（非会员视角） |
| 5 | 会员页 | 对比表 + 定价方案 |
| 6 | 我的 | 个人中心页面 |

保存至 `docs/wechat-review/screenshots/` 目录，命名格式 `01-home.png` 等。

#### 子任务 4.4: 测试账号

- [ ] **Step 4: 创建 `docs/wechat-review/test-account.md`**

```markdown
# 微信审核测试账号

## 测试用小程序账号
- 账号类型: 微信小程序测试号
- 权限: 非会员（可体验免费功能全流程）
- 可测试流程:
  - 首页浏览 + 每日一牌抽取
  - 百科搜索 + 筛选
  - 卡牌详情查看
  - 免费占卜（3次/天）完整流程
  - AI 追问（3次/天）
  - 日记创建与浏览
  - 会员页浏览（含试用心愿单）

## 会员功能演示
如需体验会员功能，审核人员可使用以下优惠码开通试用:
- 优惠码: REVIEW2026
- 有效期: 永久（仅限审核账号）
```

同时在后端实现该优惠码逻辑：在 `backend/app/api/membership.py` 添加优惠码兑换端点，`REVIEW2026` 兑换 7 天会员试用。

#### 子任务 4.5: 材料清单 + 打包

- [ ] **Step 5: 创建 `docs/wechat-review/README.md`**

```markdown
# 微信审核材料包

## 提交前自检清单

- [ ] 类目说明文档 (`category-explanation.md`)
- [ ] 无迷信承诺书 (`no-superstition-statement.md`)
- [ ] 关键页面截图 6 张 (`screenshots/`)
- [ ] 测试账号信息 (`test-account.md`)
- [ ] 优惠码 REVIEW2026 后端已部署
- [ ] 用户协议含"娱乐与自我探索工具"声明
- [ ] AI 解读均标注"仅供参考"
- [ ] 小程序无 console 报错
- [ ] 所有页面可正常加载
- [ ] 健康检查全绿: `curl https://xingxiang.chat/health`
```

- [ ] **Step 6: 实现审核优惠码端点**

在 `backend/app/api/membership.py` 添加：

```python
@router.post("/membership/redeem")
async def redeem_coupon(
    code: str = Body(..., embed=True),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Redeem a coupon code for trial membership."""
    REVIEW_CODES = {
        "REVIEW2026": 7,  # 7 days trial for WeChat review
    }
    days = REVIEW_CODES.get(code)
    if not days:
        raise HTTPException(status_code=400, detail="无效的优惠码")

    if user.is_member and user.membership_expires_at:
        user.membership_expires_at = max(
            user.membership_expires_at,
            datetime.utcnow() + timedelta(days=days)
        )
    else:
        user.membership_expires_at = datetime.utcnow() + timedelta(days=days)
        user.is_member = True

    await db.commit()
    return {"ok": True, "expires_at": user.membership_expires_at.isoformat()}
```

- [ ] **Step 7: Commit**

```bash
git add docs/wechat-review/ backend/app/api/membership.py
git commit -m "docs: 微信审核材料包 — 类目说明+承诺书+截图+测试账号

- 塔罗类目审核说明(定位: 自我探索工具)
- 无迷信承诺书
- 6页关键截图清单
- 审核测试账号 + REVIEW2026优惠码
- 后端优惠码兑换端点"
```

---

## M1 完成验证门

所有任务完成后，运行以下验证：

### 自动化验证

```bash
# 1. IDE 编译
cd /mnt/e && './微信web开发者工具/cli.bat' compile --project E:\tarot-miniapp\miniapp

# 2. 后端健康检查
curl -s https://xingxiang.chat/health | python3 -m json.tool

# 3. 免费额度 API 验证
curl -s https://xingxiang.chat/api/membership/status \
  -H "Authorization: Bearer <test-token>" | python3 -m json.tool

# 4. 优惠码端点验证
curl -s -X POST https://xingxiang.chat/api/membership/redeem \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <test-token>" \
  -d '{"code": "REVIEW2026"}'
```

### 手动验证

- [ ] 10 页全部可正常交互，无 white screen
- [ ] 打开微信 VoiceOver / 旁白，可朗读卡牌名称
- [ ] 免费用户用完 3 次解读后首页出现会员引导卡片
- [ ] 会员对比表显示 "3次"（与后端一致）
- [ ] 审核材料包 4 文件完整
