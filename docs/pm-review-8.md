# 塔罗占卜小程序 - 第8轮产品审查报告

**审查日期**: 2026-07-11
**审查范围**: 后端API（9个端点） + 前端10个页面 + 3个工具函数 + 1个组件 + 付费流程 + 用户体验
**上轮评分**: 6/10
**本轮评分**: 7/10

---

## 一、上轮问题修复情况检查

| # | 问题 | 严重度 | 修复状态 |
|---|------|--------|----------|
| 1 | diary.wxml不展示卡牌信息 | important | ✅ 已修复（Line 46-49 显示 card.name_zh 和 meaning_upright） |
| 2 | chat.js不加载历史消息 | important | ✅ 已修复（onLoad 加载 reading.chat_messages） |
| 3 | readings.py免费次数对会员递增 | important | ✅ 已修复（移至 `if not user.is_member:` 内） |
| 4 | profile.wxml展示raw spread_type | important | ✅ 已修复（SPREAD_TYPE_NAMES 映射字典） |
| 5 | api.js基础URL为占位符 | important | ❌ 仍未修复（release 仍为 'https://your-domain.com'） |
| 6 | 付费次数在AI生成前扣减 | important | ✅ 已修复（移至第184-185行，AI生成后执行） |
| 7 | diary.js loadMore未绑定UI | important | ✅ 已修复（scroll-view 绑定 bindscrolltolower） |
| 8 | report.py重复导入 | minor | ❌ 仍未修复（第44行重复 import） |
| 9 | onShareAppMessage缺sharer_id | minor | ❌ 仍未修复（未在 path 中添加追踪参数） |
| 10 | tarot-card缺真实卡面图片 | minor | ❌ 仍未修复（纯CSS星空背景） |
| 11 | 测试覆盖不足 | minor | ❌ 仍未修复（仅1个health test） |

**修复统计**: 7/11 已修复，4个问题遗留

---

## 二、本轮新发现的问题

### 重要问题

#### 1. .env 配置全为占位符，AI引擎无法正常工作
- **文件**: `/mnt/e/tarot-miniapp/backend/.env`
- **问题**: DEEPSEEK_API_KEY=your-deepseek-api-key，WECHAT_APP_ID=your-wechat-app-id，JWT_SECRET=change-me-in-production。所有密钥均为占位符，部署后AI解读、微信登录、支付回调验证均会失败。generate_reading()检测到空API_KEY直接返回None，解读结果永远为空。
- **修复**: 在部署流程中加入.env替换步骤，从CI/CD密钥管理或环境变量注入真实值。

#### 2. 百科全书搜索功能局限
- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/encyclopedia/encyclopedia.js` (第74-78行)
- **问题**: filterCards 只搜索 name_zh 和 name_en，没有覆盖 meaning_upright、meaning_reversed、keywords 等字段。用户无法通过含义关键词搜索卡牌（例如搜"转变"找不到"死神"牌），降低了百科的实用性。
- **修复**: 在 filterCards 的 keyword 搜索分支中增加对 meaning_upright/meaning_reversed 的匹配。

#### 3. 首页每日一牌无 loading 防抖
- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/index/index.js` (第28-39行)
- **问题**: drawDailyCard 方法没有 loading 状态门控。用户快速点击多次会同时触发多个 API 请求，虽然 wx.showLoading 有 UI 阻塞，但用户关闭后再迅速点击仍可触发重复请求。
- **修复**: 增加 loading 状态变量，在请求开始时设为 true，完成后设为 false，结合 disabled 属性防止重复点击。

#### 4. 免费用户看到会员牌阵但无法使用
- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/reading/reading.js` (第6-16行)
- **问题**: SPREADS 数组中有 premium: true 标记（凯尔特十字、马蹄牌阵、关系牌阵、年度运势），但前端不检查用户身份。免费用户可看到、可选中这些牌阵，填写问题后点击"开始抽牌"才被后端402拒绝。流程浪费用户时间，影响体验。
- **修复**: 在 onSelectSpread 中检查 user.is_member，若为免费用户选择 premium 牌阵则提示开通会员，或直接在前端置灰/隐藏 premium 牌阵。

#### 5. 首页骨架屏后用户信息为空时无引导
- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/index/index.js` (第14-19行)
- **问题**: onLoad 只设置了 freeCount 但未区分登录失败和首次使用的空状态。首次用户看到的是空状态界面（没有引导提示），不如显示"开始你的塔罗之旅"等引导文案。
- **修复**: 在用户无历史记录时增加首次使用引导语或指引卡片。

### 次要问题

#### 6. report.py 重复导入（上轮遗留）
- **文件**: `/mnt/e/tarot-miniapp/backend/app/api/report.py` (第44行)
- **问题**: `from app.services.tarot import draw_cards` 在第20行已导入过，第44行重复导入。连续多轮审查均指出此问题仍未修复。
- **修复**: 删除第44行的重复 import 语句。

#### 7. 分享裂变无法溯源（上轮遗留）
- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/reading-result/reading-result.js` (第63-74行)
- **问题**: onShareAppMessage 返回的分享消息中没有 path 字段携带 sharer_id。后端 ShareLog 模型已准备好记录分享来源，但前端从未传递用户标识。
- **修复**: 从 wx.getStorageSync('user') 读取用户 ID，在 path 中添加 sharer_id 参数。

#### 8. API 域名配置为占位符（上轮遗留）
- **文件**: `/mnt/e/tarot-miniapp/miniapp/utils/api.js` (第21行)
- **问题**: trial 和 release 环境 BASE_URL 均为占位域名。上线前必须配置真实域名，否则小程序无法连接后端。
- **修复**: 通过 extConfig 或 CI/CD 注入真实域名，或在部署流程中检查此项配置。

#### 9. 卡牌组件无真实卡面（上轮遗留）
- **文件**: `/mnt/e/tarot-miniapp/miniapp/components/tarot-card/tarot-card.wxml`
- **问题**: 组件使用纯 CSS 星空背景和 glyph 装饰来代替卡面图片。对于付费塔罗应用，卡牌视觉呈现是核心体验，缺少真实牌面影响产品的专业感和付费意愿。
- **修复**: 考虑集成 78 张卡面图片（AI生成或专业设计），至少在高价位牌阵中使用真实卡面。

#### 10. 测试覆盖严重不足（上轮遗留）
- **文件**: `/mnt/e/tarot-miniapp/backend/tests/`
- **问题**: 仍然只有 1 个 health 健康检查测试。核心 API（readings、orders、chat、diary、share）均无 pytest 覆盖。连续多轮审查均指出此问题。
- **修复**: 为核心 API 编写 pytest 测试，至少覆盖正常占卜流程和付费流程的 happy path。

#### 11. 年度报告双重缓存可能展示过期数据
- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/annual-report/annual-report.js` (第14-18行)
- **问题**: onLoad 优先从 wx.getStorageSync('annual_report') 读取缓存，后端的 DB 缓存反而成了备用。如果用户在后台清除了年度报告缓存但未清除 localStorage，用户会看到过期的报告。
- **修复**: 移除 localStorage 缓存层，完全依赖后端的 DB 缓存（report.py 已有完善的缓存逻辑），或优先请求后端再 fallback 到本地。

#### 12. encyclopedia.js onShow 为空函数
- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/encyclopedia/encyclopedia.js` (第27-28行)
- **问题**: onShow 注释说 "Refresh when coming back from card detail" 但方法体为空。用户从卡牌详情页返回百科时，如果数据有变动也不会刷新。
- **修复**: 在 onShow 中添加数据刷新逻辑，或删除空方法体。

#### 13. reading.js 请求体包含冗余 spread_type 字段
- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/reading/reading.js` (第73行)
- **问题**: POST /readings/spread/{spread_type} 的请求体中包含 `spread_type: selectedSpread.key`，但该值已在 URL 路径中。虽然后端忽略冗余字段，但代码可读性差。同时 CreateReadingRequest schema 没有 spread_type 字段，说明该字段不在 schema 预期中。
- **修复**: 移除请求体中的 spread_type 字段，URL 路径已足够。

---

## 三、产品整体评估

### 优势
1. **核心占卜流程完整且体验良好**: 选择牌阵 → 输入问题 → AI解读 → 查看结果 → 追问，主链路已打磨成熟。
2. **UI 设计统一且高品质**: 至尊神秘主题样式系统完善，10个页面均有加载骨架和错误状态，视觉风格一致。
3. **付费闭环完整**: 商品列表 → 创建订单 → 微信支付 → 回调处理 → 权益发放，全流程打通且逻辑正确。
4. **AI 解读质量**: DeepSeek + 专业提示词工程，解读结构化输出（总览→逐牌→串联→建议），支持重新生成。
5. **会员体系完善**: 月度/年度/永久会员 + 单次购买 + 年度报告独立销售，产品线覆盖全面。

### 持续未解决的不足
1. **上轮遗留的4个问题未修复**: 尤其是 API 域名配置和分享追踪，是上线前的硬性要求。
2. **运营准备工作不足**: 无测试覆盖、无分享归因、无管理员后台。
3. **卡牌视觉体验缺失**: 没有真实卡面图片，对塔罗类产品感知影响较大。

### 用户旅程评分
1. 首页 → 每日一牌: ⭐⭐⭐⭐（无loading门控扣一星）
2. 选择牌阵 → 开始占卜: ⭐⭐⭐⭐（免费用户看到会员牌阵却不能用扣一星）
3. 抽牌 → AI解读 → 查看结果: ⭐⭐⭐⭐⭐
4. 追问 → 多轮对话: ⭐⭐⭐⭐⭐（历史消息问题已修复）
5. 付费 → 开通会员 → 权益生效: ⭐⭐⭐⭐
6. 日记 → 记录心情: ⭐⭐⭐⭐⭐（卡牌展示已修复）
7. 百科 → 查看卡牌详情: ⭐⭐⭐⭐（搜索功能有限扣一星）
8. 个人中心 → 历史记录: ⭐⭐⭐⭐（spread_type映射已修复）
9. 年度报告 → 生成: ⭐⭐⭐⭐

### 是否可上线判断
**不能上线**。虽然核心功能完善度显著提升（从6分到7分），但仍存在两项上线阻断性问题：(1) API域名占位符未配置；(2) 所有API密钥均为占位符。运营侧（无测试、无分享追踪）虽不阻断上线但影响长期健康。预计修复本轮所有问题后可达 8-8.5 分，达到上线标准。
