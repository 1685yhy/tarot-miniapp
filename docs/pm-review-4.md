# 塔罗占卜小程序 - 产品审查报告 #4

审查日期：2026-07-11  
审查轮次：第4轮  
审查人：AI 产品经理

---

## 总体评分：6/10

核心功能运作正常，上次的7个重要问题已修复，但分享奖励逻辑修复回退（代码仍是错误方向），且5个旧有次要问题无一修复。新增了用户旅程中断和功能缺失问题。**尚不能上架，需完成本次问题修复后至少再审查一轮。**

---

## 评分明细

| 维度 | 得分 | 说明 |
|------|------|------|
| 后端API完整性 | 7 | 接口设计合理，但分享奖励有方向性bug |
| 前端功能完整性 | 7 | 所有页面有骨架/空/错误状态，但搜索防抖缺失 |
| 付费闭环 | 6 | 支付流程完整，但分享裂变逻辑颠倒，奖励变惩罚 |
| 用户体验 | 6 | 年度报告不保存、每日一牌计数异常 |
| 工程基建 | 4 | 无迁移脚本、仅1个测试、sitemap缺失 |

---

## 上次问题修复状态

### 已修复（7个）

| # | 严重度 | 问题 | 文件 |
|---|--------|------|------|
| 1 | important | Reading页主题选择不生效 | reading.js → `this.data.theme` ✓ |
| 2 | important | AI解读全失败后前端空白 | reading-result.js reinterpret + 后端端点 ✓ |
| 3 | important | 会员过期检查缺失 | readings.py line 112-113 ✓ |
| 4 | important | 历史记录无分页 | profile.js onScrollToBottom / hasMore ✓ |
| 5 | important | 历史列表不展示卡牌 | profile.wxml first_card_name ✓ |
| 6 | important | 日记每日去重 | diary.py create_entry upsert ✓ |
| 7 | important | dev-login默认会员 | auth.py default member=False ✓ |

### 未修复（5个）

| # | 严重度 | 问题 | 文件 | 说明 |
|---|--------|------|------|------|
| 8 | minor | 百科搜索防抖 | encyclopedia.js | 每次输入立即过滤 |
| 9 | minor | sitemap.json缺失 | app.json line 48 | 引用文件不存在 |
| 10 | minor | 无数据库迁移 | main.py | 仍用create_all() |
| 11 | minor | 测试覆盖率低 | tests/ | 仅1个健康检查 |
| 12 | minor | 支付跳转目的地 | membership.js | 购买后跳到profile |

---

## 本期新发现的问题

### Critical（1个）

#### C1. 分享奖励逻辑方向颠倒

**文件**：`/mnt/e/tarot-miniapp/backend/app/services/share.py` lines 40-42  
**问题**：`free_readings_today` 记录的是当日已使用的占卜次数（readings.py line 182 `+=1`），但 share.py 的奖励代码做了 `min(free_readings_today + 1, FREE_DAILY_READINGS)`，将已用次数**增加**而非减少。效果：用户分享后，可用次数反而减少或不变（当已用=1时，min(2,1)=1），奖励变惩罚。  
**修复**：改为 `sharer.free_readings_today = max(0, sharer.free_readings_today - 1)`。
**备注**：此问题在上一轮"已修复"清单中（task #47），但实际代码仍是错误逻辑，疑似修复中途被覆盖。

### Important（2个）

#### I1. 首页每日一牌误用占卜计数

**文件**：`/mnt/e/tarot-miniapp/miniapp/pages/index/index.js` lines 28-44  
**问题**：drawDailyCard 使用 `freeCount >= 1`（即 backend 的 `free_readings_today`）来限流每日一牌。但每日一牌（`GET /cards/daily`）是不限次数的免费功能，不应消耗占卜配额。且成功抽取后将 freeCount `+1`，进一步占用有限配额，免费用户抽完每日一牌后会被错误阻挡使用占卜牌阵。  
**复现**：免费用户打开首页 → 抽每日一牌 → 跳转占卜页 → 后端正常（free_readings_today=0），但前端已显示"次数用完"行为不一致。  
**修复**：移除 drawDailyCard 中对 freeCount 的检查和自增逻辑。

#### I2. 年度报告不持久化

**文件**：`/mnt/e/tarot-miniapp/miniapp/pages/annual-report/annual-report.js` lines 12-14  
**问题**：每次进入年度报告页都显示 intro 界面，用户必须重新点击"生成"、重新调用 AI API、重新消耗 tokens。生成后的报告既不保存在本地 storage，也不保存在后端。对于已付费生成过报告的会员，这是明显的体验断层。  
**修复方案**：
1. 后端：`GET /report/annual` 增加缓存逻辑，首次生成后保存到 Reading/Report 表，再次访问时返回已有报告。
2. 前端：首次生成后保存 report 数据到 `wx.setStorageSync`，下次 onLoad 优先读取本地缓存。

### Minor（2个）

#### M1. 结果页卡牌组件英文名/编号为空

**文件**：`/mnt/e/tarot-miniapp/miniapp/pages/reading-result/reading-result.wxml` lines 70-74  
**问题**：`<tarot-card>` 传入 `nameEn="{{''}}"` `cardNumber="{{''}}"`，覆盖了组件的默认值（"The Wheel" / "X"），导致卡牌展示区域英文名和编号空白，影响视觉质感。  
**修复**：从 reading API 返回数据中读取 name_en 和 card_number 传给组件，或直接移除属性使用默认值。

#### M2. 首页每日一牌抽取成功后未做数据刷新（续）

**文件**：`/mnt/e/tarot-miniapp/miniapp/pages/index/index.js`  
**问题**：drawDailyCard 成功后仅更新了 dailyCard，未更新 freeCount。但结合 I1 的问题，此处的 freeCount 增量本身就不应存在。修复 I1 时一并处理即可。

---

## 付费流程审计

| 步骤 | 状态 | 说明 |
|------|------|------|
| 商品列表展示 | ✓ | membership/products 返回齐全 |
| 创建订单 | ✓ | POST /orders 返回支付参数 |
| 调用微信支付 | ✓ | wx.requestPayment 带正确参数 |
| 支付回调 | ✓ | POST /orders/callback 验证签名+解密+处理 |
| 会员权益生效 | ✓ | 回调后更新 is_member + member_expires_at |
| 单次购买计次 | ✓ | paid_readings_balance +1 |
| 权益扣减 | ✓ | readings.py 优先消耗免费次数，次用付费余额 |
| 续费叠加 | ✓ | member_expires_at 延长而非覆盖 |
| 过期检查 | ✓ | readings.py line 112-113 自动降级 |
| **分享裂变奖励** | **✗** | **方向颠倒，分享后可用次数不增反减** |

---

## 用户体验断层审计

| 场景 | 状态 | 说明 |
|------|------|------|
| 首次打开 | ✓ | 自动微信登录，骨架屏加载 |
| 选择牌阵 | ✓ | 支持10种牌阵，带会员/热门标记 |
| 输入问题 | ✓ | 包含主题选择和字数统计 |
| AI解读中 | ✓ | 3阶段进度提示 |
| 解读结果 | ✓ | 卡片轮播+AI解读+展开/收起 |
| 解读失败重试 | ✓ | reinterpret 按钮+API |
| 追问 | ✓ | 上下文保持+剩余次数提示 |
| 支付失败 | ✓ | 取消/失败分别提示 |
| **分享裂变** | **✗** | **分享后反受惩罚** |
| **年度报告** | **✗** | **每次重新生成，不保存** |
| **每日一牌** | **✗** | **误占占卜额度** |

---

## 附：全部文件审查清单

### 后端（18个文件）

| 文件 | 状态 | 备注 |
|------|------|------|
| api/auth.py | ✓ | dev-login 默认非会员 |
| api/readings.py | ✓ | 含过期检查+reinterpret+分页 |
| api/cards.py | ✓ | 含筛选+每日一牌 |
| api/membership.py | ✓ | 状态查询+产品列表 |
| api/orders.py | ✓ | 创建订单+支付回调 |
| api/chat.py | ✓ | 追问限制+历史上下文 |
| api/diary.py | ✓ | 每日去重 |
| api/report.py | ✓ | 会员限制 |
| api/share.py | ✗ **C1** | 奖励方向颠倒 |
| services/ai_engine.py | ✓ | 3次重试+主题含义 |
| services/tarot.py | ✓ | 11种牌阵 |
| services/payment.py | ✓ | V3+V2回调验证 |
| services/share.py | ✗ C1 | 同api |
| models/user.py | ✓ | 含过期+余额字段 |
| models/reading.py | ✓ | 含DrawnCard+ChatMessage |
| models/card.py | ✓ | 78张牌全字段 |
| schemas/* | ✓ | Pydantic模型完整 |
| config.py | ✓ | 环境变量配置 |

### 前端（10个页面 + 1个组件 + 3个工具）

| 文件 | 状态 | 备注 |
|------|------|------|
| index | ✗ **I1** | 每日一牌计数错误 |
| reading | ✓ | 主题选择已修复 |
| reading-result | ✗ **M1** | 卡牌组件空值 |
| chat | ✓ | 追问功能完整 |
| profile | ✓ | 分页+卡牌信息 |
| diary | ✓ | 创建+列表完整 |
| membership | ✗ M5(旧) | 支付跳转未优化 |
| encyclopedia | ✗ M2(旧) | 搜索防抖缺失 |
| card-detail | ✓ | 正/逆位完整 |
| annual-report | ✗ **I2** | 报告不持久化 |
| tarot-card 组件 | ✓ | 视觉设计优秀 |
| utils/api.js | ✓ | 环境感知+401处理 |
| utils/auth.js | ✓ | 自动登录 |
| app.json | ✗ M4(旧) | sitemap缺失 |

---

## 建议修复优先级

1. **[Critical]** share.py 分享奖励逻辑修正 → 立即修复，这是方向性bug
2. **[Important]** index.js 每日一牌计数修正 → 影响免费用户核心体验
3. **[Important]** annual-report 报告持久化 → 避免AI API费用浪费
4. **[Minor]** reading-result.wxml 卡牌组件属性填充 → 提升质感
5. **[Minor]** encyclopedia.js 搜索防抖 → 300ms setTimeout
6. **[Old Minor]** membership.js 支付跳转优化 → 根据product_type分流
7. **[Old Minor]** sitemap.json创建 → 消除app.json报错
8. **[Old Minor]** Alembic迁移初始化 → 数据库版本管理
9. **[Old Minor]** 增加核心API测试 → pytest覆盖readings/orders/chat
