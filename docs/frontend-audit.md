# 塔罗小程序前端代码审计报告

**审计时间**: 2026-07-12
**项目路径**: `/mnt/e/tarot-miniapp/miniapp/`
**审计范围**: app.json 完整性、JS 语法和引用、WXML 模板、WXSS 引用、API 调用

---

## 摘要

| 严重度 | 数量 | 说明 |
|--------|------|------|
| **P0 - 阻断 (Error)** | 2 | DevTools 会报错，阻止渲染或编译 |
| **P1 - 重要 (Warning)** | 3 | 不会硬报错，但逻辑错误或功能缺失 |
| **P2 - 轻微 (Info)** | 3 | 代码质量问题，建议清理 |

**总计: 8 个问题**

---

## P0 - 阻断级（会导致 DevTools 报错）

### 问题 1: WXML 中调用 .split() 方法（card-detail）

- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/card-detail/card-detail.wxml`
- **行号**: 52
- **问题描述**: WXML 的 `{{}}` 表达式不支持 JavaScript 方法调用。第 52 行在 `wx:for` 中使用了 `{{card.keywords_upright.split(',')}}`，这是方法调用，不是简单表达式。DevTools 在编译/渲染此 WXML 时会报错或静默失败，导致关键词列表区域无法渲染。
- **相关代码**:
  ```html
  <text class="badge badge-gold" wx:for="{{card.keywords_upright.split(',')}}" wx:key="*this" ...>{{item.trim()}}</text>
  ```
- **修复方案**: 在 JS 中使用 `computed` 属性（需 `enhance: true`）或在 `onLoad` 中预处理 `keywords_upright` 为数组存到 data 中：
  ```js
  // card-detail.js — onLoad 或 loadCard 中
  const card = await request(`/cards/${id}`);
  card.keywordsList = card.keywords_upright ? card.keywords_upright.split(',').map(s => s.trim()) : [];
  this.setData({ card, pageLoading: false });
  ```
  然后在 WXML 中改为：
  ```html
  <text class="badge badge-gold" wx:for="{{card.keywordsList}}" wx:key="*this" ...>{{item}}</text>
  ```

---

### 问题 2: WXML 中调用 .split() 方法（profile）

- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/profile/profile.wxml`
- **行号**: 47
- **问题描述**: 同样在 WXML 表达式中调用了 `.split('T')` 方法。
- **相关代码**:
  ```html
  有效期至 {{memberStatus.expires_at.split('T')[0]}}
  ```
- **修复方案**: 在 JS 中预处理日期格式，将格式化后的日期存入 data：
  ```js
  // profile.js — loadData() 中
  const formattedStatus = {
    ...status,
    expiresAtFormatted: status.expires_at ? status.expires_at.split('T')[0] : ''
  };
  ```
  然后在 WXML 中改为：
  ```html
  有效期至 {{memberStatus.expiresAtFormatted}}
  ```

---

## P1 - 重要级（功能异常或逻辑错误）

### 问题 3: annual-report 页面缺少 onShareAppMessage

- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/annual-report/annual-report.js`
- **行号**: 全文件（缺少该方法）
- **问题描述**: WXML 第 73 行使用了 `<button open-type="share">`，但页面没有定义 `onShareAppMessage` 生命周期函数。点击分享按钮后，WeChat 使用默认分享内容（只显示页面标题），无法自定义分享标题、描述和图片。
- **对比**: `reading-result.js` 已正确实现了 `onShareAppMessage`。
- **修复方案**: 添加 `onShareAppMessage` 方法：
  ```js
  onShareAppMessage() {
    return {
      title: '我的塔罗年度运势报告 —— 来看看未来12个月的运势吧',
      desc: 'AI塔罗年度运势报告',
    };
  },
  ```

---

### 问题 4: tarot-card 组件 data 与 properties 命名冲突

- **文件**: `/mnt/e/tarot-miniapp/miniapp/components/tarot-card/tarot-card.js`
- **行号**: 137-141 (data) 与 132-134 (properties)
- **问题描述**: 组件的 `data` 和 `properties` 都定义了 `cardType` 字段。Properties 默认值为 `''`，Data 初始值为 `'fool'`。在 WeChat 组件初始化中，properties 会覆盖同名的 data 初始值，因此 `data.cardType = 'fool'` 永远不生效，实际初始值为 `''`。虽然 `attached()` 生命周期会重新设置正确值，但第一次渲染时可能导致卡片 CSS 类名 `card-{{cardType}}` 为空字符串，使卡面样式丢失（flash of unstyled content）。
- **修复方案**: 删除 data 中与 properties 同名的 `cardType` 字段：
  ```js
  data: {
    // 删除 cardType: 'fool' ← 已在 properties 中定义
    cardNumberDisplay: '',
    displayNameEn: '',
    isMajor: true,
  },
  ```

---

### 问题 5: storage.js 工具模块未被任何页面引用

- **文件**: `/mnt/e/tarot-miniapp/miniapp/utils/storage.js`
- **行号**: 全文件（dead code）
- **问题描述**: `utils/storage.js` 提供了包装了 `wx.setStorageSync/getStorageSync/removeStorageSync/clearStorageSync` 的工具函数，并且定义了 `STORAGE_KEYS` 常量。但检查所有 10 个页面的 JS 文件以及 `app.js`，没有任何地方通过 `require` 引用 `storage.js`。所有代码直接使用 `wx.setStorageSync` / `wx.getStorageSync` 等原生 API。这是一个纯粹的死代码模块，不会报错但增加了代码体积和维护负担。
- **修复方案**: 方案 A：删除 `utils/storage.js`（如果确定不会使用）。方案 B：在相关页面（如 auth.js）中改用 storage.js 的工具函数统一管理缓存 key。

---

## P2 - 轻微级（代码质量问题，建议优化）

### 问题 6: app.json 中 release URL 仍为占位符

- **文件**: `/mnt/e/tarot-miniapp/miniapp/utils/api.js`
- **行号**: 36
- **问题描述**: `ENV_URLS.release` 的值仍为 `'https://your-domain.com'`，如果部署到正式环境前忘记修改，所有 API 请求将全部失败。虽然代码里有双重占位符检测（第 56-67 行），但检测逻辑只在 `console.error` 输出，不阻止应用运行，用户看到的是"加载失败"的错误提示，无法定位根因。
- **修复方案**: 在非 develop 环境下检测到占位符时，应使用 `wx.showModal` 或 `wx.showToast` 给用户更明显的提示，或在 `app.js onLaunch` 中增加阻断逻辑。但最终修复还是将 `release` URL 替换为真实域名。

---

### 问题 7: WXSS 中 clip-path:path() 兼容性问题

- **文件**: `/mnt/e/tarot-miniapp/miniapp/components/tarot-card/tarot-card.wxss`
- **行号**: 333
- **问题描述**: 恋人牌（lovers）使用了 `clip-path:path('M35,0 C17,0...')`。WeChat 的 WXSS 对 `clip-path: path()` 的支持在 Android 设备上有限，低版本 WebView 可能无法渲染该形状。DevTools 不会显示为错误，但真机上恋人牌的爱心形状无法显示。
- **修复方案**: 为 `clip-path: path()` 提供 `clip-path: url()` 或纯 CSS 形状的 fallback，或使用 `mask` 属性作为替代方案。

---

### 问题 8: encyclopedia.wxml 搜索结果为空时提示逻辑

- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/encyclopedia/encyclopedia.wxml`
- **行号**: 79-83
- **问题描述**: 空状态提示 `wx:if="{{filteredCards.length === 0}}"` 在页面**首次加载时**也会短暂显示（因为 `filteredCards` 初始为 `[]`），直到 `loadCards()` 返回数据将其覆盖。由于加载骨架屏 (`wx:if="{{pageLoading}}"`) 的存在，这段空白状态实际上被骨架屏覆盖了，所以不会对用户可见。但逻辑上，空状态应该是"搜索无结果"时的提示，应该在非加载状态下判断。
- **修复方案**: 改为 `wx:if="{{!pageLoading && filteredCards.length === 0}}"`，确保只在加载完成后显示空状态。

---

## 各审计维度总结

### 1. app.json 完整性 ✅
- pages 数组 10 个路径全部对应的 `.js/.wxml/.wxss/.json` 四个文件都存在。
- tabBar 6 个 icon 图片文件全部存在。
- 引用的组件 `tarot-card` 全部文件存在，且 `reading-result.json` 和 `annual-report.json` 的组件路径正确。

### 2. JS 语法和引用错误 ⚠️
- 所有 `require()` 路径正确，`utils/api.js`、`utils/auth.js`、`utils/storage.js` 均存在。
- 各页面的 WXML `bindtap` 绑定的函数都在 JS 中定义。
- `setData` 使用的变量都在 `data` 中声明。
- **问题**: `storage.js` 是死代码（未被任何页面引用）。

### 3. WXML 模板错误 ❌
- **P0 x 2**: `.split()` 和 `.trim()` 在 WXML 表达式中调用，不被标准 WXML 支持。
- 其他 `wx:for`、`wx:if`、`wx:elif` 使用的变量均已在 data 中声明。
- `wx:key` 的值均正确（属性名或 `*this`）。

### 4. WXSS 引用错误 ✅
- `app.wxss` 中 `@import "./styles/common.wxss"` 路径正确，文件存在。
- 所有页面 WXML 使用的 CSS 变量（`var(--color-gold)`、`var(--fs-body)` 等）都在 `common.wxss` 的 `page` 选择器中定义。
- `tarot-card.wxss` 使用硬编码值，不依赖外部 CSS 变量。

### 5. API 调用错误 ✅
- 所有 `request()` 调用的 URL 路径格式一致（`${BASE_URL}${url}`）。
- 错误处理覆盖了 401（自动跳转登录）、402（付费提示）和通用错误。
- 后端 API 端点路径与预期一致。

---
