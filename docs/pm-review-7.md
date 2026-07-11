# 塔罗占卜小程序 - 第7轮产品审查报告

**审查日期**: 2026-07-11
**审查范围**: 后端API + 前端10个页面 + 付费流程 + 用户体验
**评分**: 6/10

---

## 一、本轮审查发现的问题

### 重要问题

#### 1. diary 页面不展示卡牌信息
- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/diary/diary.wxml` (第40-46行)
- **问题**: 后端 API 已修复并返回 card 字段（name_zh、meaning_upright），但日记列表模板只展示了日期、心情emoji和感悟文字，没有渲染 item.card 中的塔罗牌信息。用户看日记只看得到心情记录，看不到每天抽到的牌。
- **修复**: 在 entry-card 模板中增加卡牌展示区域，显示 item.card.name_zh 和 item.card.meaning_upright 截取。

#### 2. 聊天页面不加载历史消息
- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/chat/chat.js` (第16-23行)
- **问题**: onLoad 只加载了 reading 的 question 和 spread_type 作为上下文，没有加载之前的所有 chat_messages。用户离开聊天页再回来，消息记录全部消失，看到的是空白初始状态。后端完整返回历史消息，前端未利用。
- **修复**: onLoad 时同时加载 reading.chat_messages（新增 API 字段或单独请求），填充到 messages 数组中展示。

#### 3. readings.py 中 free_readings_today 对会员也递增
- **文件**: `/mnt/e/tarot-miniapp/backend/app/api/readings.py` (第182行)
- **问题**: `user.free_readings_today += 1` 在函数结尾无条件执行，即使会员也递增。虽然会员不受 FREE_DAILY_READINGS 限制，但这个数字会无限上涨，在 profile 页面显示为"今日占卜：15"等无意义数字，给用户造成困惑。
- **修复**: 将递增语句移到 `if not user.is_member:` 条件块内，类似于 chat.py 的处理方式。

#### 4. profile 页面展示原始 spread_type 键名
- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/profile/profile.wxml` (第101行)
- **问题**: `{{item.spread_type}}` 直接展示 API 返回的原始键值，如 "three_card"、"celtic_cross"。用户在历史列表中看到的是英文键名，而非可读的中文牌阵名称。
- **修复**: 新增 spread_type 到中文名称的映射字典（可复用 reading.js 中的 SPREADS 数据），在 template 中做转换。

#### 5. API 基础 URL 为占位符
- **文件**: `/mnt/e/tarot-miniapp/miniapp/utils/api.js` (第21行)
- **问题**: release 环境的 BASE_URL 是 `'https://your-domain.com'`，trial 环境也是占位域名。上线前必须配置真实域名，否则小程序无法连接后端。
- **修复**: 通过 extConfig 或 CI/CD 注入真实域名，或在部署流程中检查此项配置。

#### 6. 付费阅读次数在 AI 解读生成前扣减
- **文件**: `/mnt/e/tarot-miniapp/backend/app/api/readings.py` (第116-117行)
- **问题**: `user.paid_readings_balance -= 1` 在第117行执行，而 AI 解读生成在第175行之后。如果 AI 服务连续失败，用户的付费次数已被扣减但未获得完整解读服务。虽然可复用 reinterpret 端点重试，但扣减时机不符合"先服务后扣费"的业务原则。
- **修复**: 将 paid_readings_balance 扣减操作移到 AI 生成成功之后（第179行之后），或仅在确认返回有效 interpretation 后扣减。

#### 7. 日记列表无加载更多机制
- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/diary/diary.js` (第35-39行)
- **问题**: `loadMore` 方法存在（先递增 page 再异步请求有竞态风险），但在 diary.wxml 中没有绑定到任何 UI 事件（下拉触底或"加载更多"按钮）。用户有超过20条日记时将无法查看后续内容。
- **修复**: 在日记列表外层包裹 scroll-view 并绑定 bindscrolltolower="loadMore"，同时添加 loadingMore 门控防止重复请求。

### 次要问题

#### 8. report.py 重复导入
- **文件**: `/mnt/e/tarot-miniapp/backend/app/api/report.py` (第44行)
- **问题**: `from app.services.tarot import draw_cards` 在第20行已导入过，第44行重复导入。上一次审查已指出此问题，仍未修复。
- **修复**: 删除第44行的重复 import 语句。

#### 9. onShareAppMessage 缺乏分享追踪参数
- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/reading-result/reading-result.js` (第63-74行)
- **问题**: share 消息中没有 `path` 字段携带 sharer_id，后端分享裂变系统无法追踪到分享带来的新用户。
- **修复**: 从 wx.getStorageSync('user') 读取用户ID，在 path 中添加 `sharer_id=` 参数。

#### 10. 卡牌组件缺乏真实卡面图片
- **文件**: `/mnt/e/tarot-miniapp/miniapp/components/tarot-card/tarot-card.wxml`
- **问题**: 组件使用纯 CSS 星空背景和 glyph 装饰来代表卡面，没有实际的塔罗牌面图片。对于付费塔罗应用，卡牌视觉呈现是核心体验之一。
- **修复**: 考虑集成 DALL-E/Stable Diffusion 生成的78张卡面图片，或使用高质SVG占位图形。

#### 11. 测试覆盖率仍然不足
- **文件**: `/mnt/e/tarot-miniapp/backend/tests/`
- **问题**: 仍然只有1个 health 健康检查测试，核心API（readings、orders、chat、diary、share）均无 pytest 测试覆盖。连续多轮审查均指出此问题。
- **修复**: 为核心API编写 pytest 测试，至少覆盖正常的占卜流程和付费流程。

---

## 二、上一轮问题修复情况检查

| 问题 | 严重度 | 修复状态 |
|------|--------|----------|
| 所有模型 datetime 使用带括号的 default | critical | ✅ 已修复（使用 lambda） |
| chat.py free_chats_today 无条件递增 | important | ✅ 已修复 |
| chat.py 未调用 _reset_daily_count_if_new_day | important | ✅ 已修复 |
| annual-report.wxml nameEn/cardNumber 覆盖默认值 | important | ✅ 已修复 |
| diary API 不返回卡牌信息 | important | ✅ API 已修复，但前端未展示 |
| reading-result.js onShareAppMessage 无 sharer_id | minor | ❌ 仍未修复 |
| diary.js loadMore 先递增page再请求 | minor | ⚠️ 代码仍存在，同时该函数未绑定UI |
| 测试覆盖率仅1个 | minor | ❌ 仍未修复 |
| report.py 重复导入 | minor | ❌ 仍在（第44行） |
| payment.py 解密异常处理不完善 | minor | ✅ 已修复（orders callback 中已包裹 try/except） |

---

## 三、产品整体评估

### 优势
- **付费闭环完整**: 从商品列表 → 创建订单 → 微信支付 → 回调处理 → 权益发放，全流程打通
- **UI 系统统一**: 至尊神秘主题样式系统完善，10个页面均有加载骨架和错误状态
- **核心占卜流程流畅**: 选择牌阵 → 输入问题 → AI 解读 → 追问，主链路体验良好
- **AI 解读质量**: DeepSeek + 专业提示词工程，解读有结构化输出，支持重生成

### 不足
- **聊天无历史记录**: 这是最影响用户体验的问题——用户离开聊天页回来就看到空白界面
- **日记不展示卡牌**: API 给了数据但前端不用，功能只做了一半
- **数据展示不够用户友好**: raw key（spread_type）直接展示给用户
- **运营准备不足**: 分享追踪、测试覆盖、API 域名配置等上线前的准备工作尚未完成
- **卡牌视觉缺失**: 没有实际卡面图片，对塔罗产品的调性和诚意有影响

### 用户旅程评分
1. 首页 → 选择牌阵 → 开始占卜: ⭐⭐⭐⭐⭐
2. 抽牌 → AI解读 → 查看结果: ⭐⭐⭐⭐⭐
3. 追问 → 多轮对话: ⭐⭐⭐⭐（无历史记录扣一星）
4. 付费 → 开通会员 → 权益生效: ⭐⭐⭐⭐
5. 日记 → 记录心情: ⭐⭐⭐（不展示卡牌扣两星）
6. 百科 → 查看卡牌详情: ⭐⭐⭐⭐⭐
7. 个人中心 → 历史记录: ⭐⭐⭐（raw key + 无分享归因）
8. 年度报告 → 生成: ⭐⭐⭐⭐

### 是否可上线判断
**不能上线**。虽然核心功能完整，但存在多项重要UX缺陷（聊天无历史、日记无卡牌、spread_type 展示原始键名）需要修复。这些不是技术阻断性问题，但会显著影响用户留存和口碑传播。预计修复全部问题后可达 7-8 分，接近上线标准。
