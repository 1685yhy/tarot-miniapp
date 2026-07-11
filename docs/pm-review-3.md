# 塔罗占卜小程序 - 产品审查报告 V3

**审查日期**: 2026-07-11
**评分**: 7/10
**状态**: 接近内测条件，但不可正式上线

---

## 一、V2 问题修复验证

### Critical (3/3 已修复)

| 问题 | 状态 | 说明 |
|------|------|------|
| 支付回调签名验证形同虚设 | 已修复 | `orders.py` 第94-99行接入真实签名验证，`payment.py` 实现了证书验证 + AESGCM 解密 |
| single_reading 无权益处理 | 已修复 | 回调第148行正确增加 `paid_readings_balance`，`create_reading` 第114行使用该余额 |
| AI 解读失败无重试机制 | 已修复 | `ai_engine.py` 第136-164行实现了3次重试 + 退避；但全失败时前端仍展示空白（新问题） |

### Important (6/7 已修复)

| 问题 | 状态 | 说明 |
|------|------|------|
| 年度报告不展示13张月度牌 | 已修复 | `annual-report.wxml` 第46-68行用 `tarot-card` 组件滚动展示月度牌 |
| 清除历史记录无后端API | 已修复 | `readings.py` 第302-321行新增 DELETE 接口，`profile.js` 第70行调用 |
| tarot-card 组件未被引用 | 已修复 | `reading-result.wxml` 第69行、`annual-report.wxml` 第58行已引入 |
| BASE_URL 硬编码 | 已修复 | `api.js` 第9-33行按 `envVersion` 自动切换环境 |
| 会员页展示非会员商品 | 已修复 | `membership.js` 第18行过滤只展示 membership 类型 |
| AI解读无进度反馈 | 已修复 | `reading-result.wxml` 第27-42行增加阶段提示（抽牌完成→AI解读中→生成报告） |
| 百科搜索未做防抖 | **未修复** | `encyclopedia.js` 第47-51行依然直接调用 filterCards，无防抖 |

### Minor (1/4 修复)

| 问题 | 状态 | 说明 |
|------|------|------|
| 缺少 sitemap.json | **未修复** | app.json 引用但文件不存在 |
| 无数据库迁移脚本 | **未修复** | 仍依赖 `create_all` |
| 测试覆盖率低 | **未修复** | 仅一个健康检查测试 |

---

## 二、V2 遗留问题（本轮仍未修复）

### Minor

#### L1. 百科搜索无防抖
- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/encyclopedia/encyclopedia.js` 第47-51行
- **问题**: `onSearchInput` 每次输入直接调用 `filterCards` 进行全列表过滤。输入法快速打字会高频触发过滤操作，可能引起性能问题（尤其在低端机）。
- **影响**: 低
- **修复**: 使用 `setTimeout` 做300ms防抖

#### L2. sitemap.json 缺失
- **文件**: `/mnt/e/tarot-miniapp/miniapp/app.json` 第48行引用
- **问题**: `sitemapLocation: "sitemap.json"` 但文件不存在，微信开发者工具会有警告。
- **影响**: 低
- **修复**: 创建 `sitemap.json` 文件

#### L3. 无数据库迁移脚本
- **文件**: `/mnt/e/tarot-miniapp/backend/app/main.py` 第12行
- **问题**: 启动时调用 `create_all()` 创建表结构，而非通过 Alembic 迁移管理。生产环境存在表变更风险。
- **影响**: 中（生产部署风险）
- **修复**: 初始化 Alembic，生成迁移脚本

#### L4. 测试覆盖率低
- **文件**: `/mnt/e/tarot-miniapp/backend/tests/` 仅一个文件
- **问题**: 仅有一个健康检查测试。核心逻辑（reading/order/payment/chat）无任何测试覆盖。
- **影响**: 中
- **修复**: 为核心 API 添加 pytest 测试

---

## 三、本轮审查发现的新问题

### Important（必须修复）

#### N1. Reading 页主题选择功能不生效
- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/reading/reading.js` 第70-76行
- **问题**: `onStartReading` 发送请求时使用 `selectedSpread.theme`（从 SPREADS 定义读取），而非用户通过 `onThemeTap` 设置的 `this.data.theme`。用户点选"综合/爱情/事业/财运"任意选项均不生效，AI 解读永远按 SPREADS 定义的主题进行。
- **影响**: 高——用户每次花费精力选择主题，结果全部被忽略，AI 解读未按用户期望的侧重维度输出。
- **修复**: 将第74行 `theme: selectedSpread.theme || 'general'` 改为 `theme: this.data.theme || 'general'`

#### N2. AI 解读全失败后前端展示空白（V2修复残留）
- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/reading-result/reading-result.wxml` 第97行
- **问题**: 后端 `ai_engine.py` 已实现3次重试，但若全部失败依然返回 `None`，reading 的 `interpretation` 为 null。前端显示"正在生成解读..."（非 loading 状态），且没有任何重试按钮。用户看到的是停留在解读页面上的静态提示，无法触发重新生成。
- **影响**: 高——核心体验断层，用户永远拿不到这次占卜的结果。
- **修复**: (1) 增设 `/readings/{id}/reinterpret` API 端点，允许重新调用 AI；或 (2) 前端在 interpretation 为空时展示"AI解读遇到困难，点击重新生成"按钮

#### N3. 会员状态过期检查缺失
- **文件**: `/mnt/e/tarot-miniapp/backend/app/api/readings.py` 第112行
- **问题**: `create_reading` 仅检查 `user.is_member` 布尔值，未校验 `user.member_expires_at`。会员过期后 `is_member` 仍可能为 `True` 导致无限免费使用。支付回调中（`orders.py` 第151-165行）虽然正确设置了 `member_expires_at`，但没有定时任务或登录时检查来清理过期会员。
- **影响**: 高——可能导致会员权益被滥用
- **修复**: (1) 在 `get_current_user` 或 `create_reading` 中校验 `if user.member_expires_at and user.member_expires_at < now: user.is_member = False`；(2) 或添加定时任务定期清理

#### N4. 历史记录无分页加载
- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/profile/profile.js` 第24行
- **问题**: `readingHistory` 只加载第一页（20条），没有"加载更多"功能。重度用户的历史记录被截断。
- **影响**: 中
- **修复**: (1) 前端增加页号状态和滚动到底加载；(2) 或改为全量异步加载

#### N5. 历史记录列表不展示卡牌信息
- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/profile/profile.wxml` 第98-103行
- **问题**: 后端 `readings.py` 第246-249行已正确返回 `first_card_name` 和 `first_card_is_reversed`，但前端模板只展示 `spread_type` 和 `theme`，没有展示首张卡牌的名称或正逆位。
- **影响**: 中——历史记录列表信息量不足，缺少让用户回忆的视觉线索
- **修复**: 在 history-item 中添加 `{{item.first_card_name}}` 和正逆位指示

#### N6. 日记 API 无每日去重
- **文件**: `/mnt/e/tarot-miniapp/backend/app/api/diary.py` 第16-46行
- **问题**: `create_entry` 不检查当天是否已有记录。用户可无限创建同一日期的日记条目，每篇都触发随机抽牌和写入。
- **影响**: 低-中
- **修复**: 创建前检查当日是否已有记录，若有则更新而非新建，或提示用户

#### N7. Dev-login 默认创建会员用户隐藏免费流程问题
- **文件**: `/mnt/e/tarot-miniapp/backend/app/api/auth.py` 第25行
- **问题**: `dev_login` 创建测试用户时默认 `is_member=True`。开发/测试人员在调试时永远走会员流程，无法发现免费用户的限流逻辑、402引导、次数用完等交互问题。
- **影响**: 中——直接导致免费流程未经充分测试
- **修复**: 改为默认 `is_member=False`，并提供手动切换会员的参数（如 `?member=true`）

---

### Minor

#### N8. 部分页面缺少下拉刷新
- **文件**: 多处（profile/diary/encyclopedia）
- **问题**: 用户在 `profile` 页购买会员后返回，或日记页新增条目后，页面不会自动刷新（虽然有 `onShow` 但数据已变化）。缺少 `enablePullDownRefresh` 和 `onPullDownRefresh`。
- **影响**: 低
- **修复**: 启用下拉刷新，或在关键操作后主动 reload

#### N9. 支付成功页面跳转回 profile 而非消费场景
- **文件**: `/mnt/e/tarot-miniapp/miniapp/pages/membership/membership.js` 第56行
- **问题**: 支付成功后跳转到 `profile` 而非回到触发付费的上下文（如 reading 页）。用户购买 single_reading 后不能继续占卜。
- **影响**: 低
- **修复**: 根据 product_type 决定跳转目标

#### N10. annual_report 购买后无权益处理注释
- **文件**: `/mnt/e/tarot-miniapp/backend/app/api/orders.py` 第168行
- **问题**: `# annual_report – no membership benefit, handled by report system` 但实际 report 系统也未做校验，用户购买后只是标记订单为已支付，报告页无任何权益检查之外的验证。
- **影响**: 低
- **修复**: 在 report 端增加订单支付校验

---

## 四、付费流程闭环评估

| 环节 | 状态 | 说明 |
|------|------|------|
| 商品展示 | ✅ 正常 | membership 页仅展示会员商品 |
| 下单 | ✅ 正常 | `/orders` 创建订单，生成微信支付参数 |
| 支付 | ✅ 正常 | JSAPI 参数完整，`wx.requestPayment` 可调用 |
| 回调签名验证 | ✅ 已修复 | 真实的 V3 证书校验 + AES GCM 解密 |
| 权益发放 | ✅ 正常 | membership/membership + single_reading 均已处理 |
| 权益使用 | ✅ 正常 | `create_reading` 检测会员和 purchased_balance |
| 会员过期 | ❌ 有风险 | 过期后 `is_member` 未清除 |

**结论**: 付费闭环基本完整，唯一漏洞是会员过期未自动降级（N3）。

---

## 五、用户体验评估

| 维度 | 分数 | 说明 |
|------|------|------|
| UI 视觉 | 8/10 | 金色神秘风格统一，动画丰富，design tokens 完善 |
| 交互流畅度 | 6/10 | 部分交互无效（主题选择），AI 失败无恢复路径 |
| 功能完整性 | 7/10 | 所有核心功能就绪，但细节有缺失 |
| 错误处理 | 5/10 | 核心路径有错误处理，但 AI 失败场景无恢复 |
| 付费体验 | 7/10 | 闭环基本完整，支付后跳转欠合理 |

---

## 六、总体评分和建议

**评分**: 7/10

**结论**: 相比 V2 有显著进步——三个 critical 问题全部修复，说明团队执行力不错。当前产品已具备**内测条件**，但**不可正式上线**。

**上线的阻塞项**:
1. 会员过期检查缺失（N3）——存在收益损失风险
2. AI 解读全失败后无恢复路径（N2）——核心体验断层
3. Reading 页主题选择无效（N1）——核心交互功能缺陷

**建议路线图**:
- **立即修复（1-2天）**: N1（主题选择）、N2（AI失败恢复）、N3（会员过期检查）
- **上线前（3-5天）**: N4（历史分页）、N5（卡牌展示）、N7（dev-login默认免费）、L3（Alembic迁移）、L4（核心测试）
- **上线后迭代**: L1（搜索防抖）、N6（日记去重）、N8（下拉刷新）、N9（支付跳转）、L2（sitemap）
