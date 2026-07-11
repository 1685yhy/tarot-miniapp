# 塔罗占卜小程序 - 最终交付报告

**报告日期**: 2026-07-11  
**交付负责人**: AI 产品经理  
**当前PM评分**: 7/10  
**当前状态**: 可有限上线试运营

---

## 1. 项目概况

### 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端框架 | Python FastAPI | 异步 API 服务 |
| 数据库 | MySQL 8.0 (SQLAlchemy async) | 用户、卡牌、解读、订单、日记数据 |
| 缓存 | Redis 7 | Session 存储、缓存 |
| AI 引擎 | DeepSeek/Claude API | 塔罗解读生成、AI 追问 |
| 支付 | 微信支付 V3 (wechatpayv3 SDK) | JSAPI 支付 |
| 前端 | 微信小程序原生 (WXML + WXSS + JS) | 10 个页面 + 1 个组件 |
| 容器化 | Docker Compose | MySQL + Redis + App 三服务编排 |
| 认证 | JWT (python-jose) | 微信登录换取 token |

### 功能清单

#### 已实现功能

| 功能 | 模块 | 状态 |
|------|------|------|
| 微信自动登录 | 全局 | ✅ |
| 每日一牌 (免费) | 首页 | ✅ |
| 78 张塔罗牌百科 | 百科页 | ✅ |
| 卡牌详情（正/逆位含义） | 卡牌详情页 | ✅ |
| 10 种牌阵选择 | 占卜页 | ✅ |
| 主题选择（综合/爱情/事业/财运） | 占卜页 | ✅ |
| AI 塔罗解读生成（含3次重试） | 解读结果页 | ✅ |
| 卡牌轮播展示（含 tarot-card 组件） | 解读结果页 | ✅ |
| AI 追问对话 | 追问页 | ✅ |
| 解读结果展开/收起 | 解读结果页 | ❌ 有故障（见剩余问题） |
| 历史记录（分页） | 个人中心 | ✅ |
| 清除历史记录 | 个人中心 | ✅ |
| 塔罗日记（含随机抽牌） | 日记页 | ✅ |
| 情绪记录 | 日记页 | ✅ |
| 微信支付接入 | 会员页 | ✅ |
| 会员商品购买（月/季/年/永久） | 会员页 | ✅ |
| 单次占卜购买 | 会员页 | ✅ |
| 年度运势报告（AI 生成，已持久化） | 年度报告页 | ✅ |
| 分享裂变奖励 | 解读结果页 | ✅ |
| 解读失败重新生成 | 解读结果页 | ✅ |
| 会员过期自动降级 | 后端 | ✅ |
| 环境感知 BASE_URL（dev/prod 自动切换） | 工具层 | ✅ |
| 金色神秘主题 UI（全套骨架屏/错误/空状态） | 全部页面 | ✅ |

#### 计划中但未实现

| 功能 | 说明 |
|------|------|
| 卡牌图片设计师精修 | 当前使用 tarot-card 组件文字展示，暂无专业卡面设计 |
| 运势卡片分享图生成 | 设计文档提到但未实现，当前使用标准小程序分享 |
| 用户首次使用引导 (onboarding) | 无引导流程 |
| 直播占卜/在线咨询 | 超出 MVP 范围 |
| 多语言支持 | 仅中文 |
| 数据库迁移脚本 (Alembic) | 当前依赖 `create_all()` |
| 自动化测试覆盖 | 仅 1 个健康检查测试 |
| 百科搜索防抖 | 每次输入立即过滤 |
| 微信搜索 sitemap | sitemap.json 缺失 |
| 支付后跳转优化 | 购买后跳到 profile 而非消费场景 |
| 年度报告单独购买入口 | 非会员无法从 UI 单独购买年度报告 |

---

## 2. 迭代记录

### 迭代轮次

| 轮次 | 审查报告 | 评分 | 状态 |
|------|----------|------|------|
| 第 1 轮 | pm-review-1.md | **3/10** | 不可上线 |
| 第 2 轮 | pm-review-2.md | **6/10** | 有条件内测，不可正式上线 |
| 第 3 轮 | pm-review-3.md | **7/10** | 接近内测条件，但不可正式上线 |
| 第 4 轮 | pm-review-4.md | **6/10** | 尚不能上架（分享奖励逻辑回退） |
| 第 5 轮 | pm-review-5.md | **7/10** | 可有限上线试运营 |

### 问题修复统计

#### 累计发现问题

| 严重度 | 数量 | 说明 |
|--------|------|------|
| Critical (阻塞上线) | 6 | 共发现6个阻塞级问题，全部修复 |
| Important (必须修复) | 16 | 共发现16个重要问题，14个已修复，2个未修复 |
| Minor (建议修复) | 18+ | 持续累积中，部分修复 |

#### 各轮次问题统计

| 轮次 | 发现 Critical | 发现 Important | 发现 Minor | 修复 Critical | 修复 Important | 修复 Minor |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| V1 → V2 | 3 | 7 | 10 | 3 | 7 | 0 |
| V2 → V3 | 3 | 7 | 9 | 3 | 6 | 1 |
| V3 → V4 | 0 | 7 | 2 | 0 | 7 | 0 |
| V4 → V5 | 1 | 2 | 2 | 1 | 2 | 0 |
| V5 (当前) | 0 | 1 | 4 | - | - | - |

#### 逐轮评分变化趋势

```
评分
10 │
 9 │
 8 │
 7 │                              ●──●
 6 │                    ●
 5 │
 4 │
 3 │     ●
 2 │
 1 │
 0 └───────────────────────────────────────
     V1    V2    V3    V4    V5
```

- V1→V2: 3→6 (+3) — 修复了3个Critical + 7个Important，支付流程从断裂变为基本可用
- V2→V3: 6→7 (+1) — 修复了3个Critical + 6个Important，付费闭环完整
- V3→V4: 7→6 (-1) — 分享奖励逻辑回退（代码被覆盖），5个旧Minor未修复
- V4→V5: 6→7 (+1) — 修复分享奖励、每日一牌计数、年度报告持久化

### 已修复的关键问题 (按严重度)

#### Critical (6/6 已修复)
1. **`readings.py:127` is_paid 逻辑写反** — 会员标为未付费，免费用户标为已付费
2. **支付流程未接入微信支付** — 前端模拟弹窗，从未调用 `wx.requestPayment`
3. **前端免费用户被完全阻挡** — `index.js` 对所有非会员一票否决
4. **支付回调签名验证形同虚设** — 仅 `pass`，无微信 V3 证书验证
5. **`single_reading` 购买无权益处理** — 回调中 `pass`，付了钱拿不到权益
6. **AI 引擎无重试机制** — `generate_reading()` 失败返回 None，解读留空

#### Important (已修复典型)
- 全部页面 pageLoading/pageError 状态机修复
- reading-result.js 变量名 `loading` → `pageLoading` 统一
- 分享奖励逻辑从 `-1`（减少）改为增加可用次数
- chat.js 发送消息后调用 `scrollToBottom()`
- 日记随机抽牌从 `random.randint` 改为数据库随机排序
- payment.py 正确生成微信支付 JSAPI 参数
- .env API Key 替换为占位符
- Reading 页主题选择功能修复（使用 `this.data.theme` 而非 `selectedSpread.theme`）
- AI 解读全失败后前端空白修复（reinterpret API + 重试按钮）
- 会员过期检查修复（`create_reading` 中校验 `member_expires_at`）
- 历史记录分页加载
- 历史列表展示首张卡牌
- 日记每日去重 (upsert)
- dev-login 默认非会员
- 年度报告持久化（后端缓存 + 前端 storage）
- 分享奖励方向颠倒修复（V4 回退问题）
- 每日一牌误用占卜计数修复
- BASE_URL 环境感知自动切换

---

## 3. 质量评估

### 当前 PM 评分：7/10

| 维度 | 得分 | 说明 |
|------|:----:|------|
| 后端 API 完整性 | 8 | 接口设计合理，付费闭环完整 |
| 前端功能完整性 | 7 | 所有页面有骨架/空/错误状态，但解读展开/收起故障 |
| 付费闭环 | 8 | 支付流程完整，分享裂变奖励已修复 |
| 用户体验 | 7 | 年度报告已持久化，但解读折叠失效、统计显示有误 |
| 工程基建 | 4 | 无迁移脚本、仅1个测试、sitemap缺失（连续5轮未修复） |

### 剩余问题

| 严重度 | 问题 | 文件 | 说明 |
|--------|------|------|------|
| **Important** | 解读结果页"展开全文"功能无效 | `/mnt/e/tarot-miniapp/miniapp/pages/reading-result/reading-result.wxml` 第96行 | `showFullInterpretation` 切换将 `expanded` class 加到 `.interpretation-card` 上，但 WXSS 中只定义了 `.interpretation-scroll` 的 `max-height` + 渐变遮罩，`.interpretation-card.expanded` 无任何对应 CSS 规则，导致展开/收起功能完全失效，用户无法阅读超过300字的完整 AI 解读。**修复**: 将 WXML 中的 `interpretation-card` 改为 `interpretation-scroll`，或为 `.interpretation-card` 添加 `max-height`/`overflow`/`::after` 渐变遮罩样式。 |
| Minor | 每日一牌按钮标签误导 | `index.wxml` | 免费功能显示 "X/1 次免费" 使被误以为受限 |
| Minor | 历史记录总数显示不准确 | `profile.wxml` | 显示当前加载条数而非 `total` 字段 |
| Minor | 解读结果页缺少 `onShareAppMessage` | `reading-result.js` | 分享按钮存在但无法自定义分享内容 |
| Minor | 卡牌组件传入空 `nameEn`/`cardNumber` | `reading-result.wxml` | 覆盖了组件的默认值，卡牌英文名/编号空白 |
| Minor | 百科搜索防抖缺失 | `encyclopedia.js` | 每次输入立即过滤 |
| Minor | 支付跳转目的地不合理 | `membership.js` | 购买后跳到 profile 而非消费场景 |
| Minor | sitemap.json 缺失 | `app.json` | 引用文件不存在，微信开发者工具有警告 |
| Minor | 年度报告单独购买入口缺失 | `annual-report.js` / `membership.js` | 非会员无法从 UI 购买年度报告 |
| Minor | 无数据库迁移脚本 (Alembic) | 工程基建 | 生产环境依赖 `create_all()` |
| Minor | 测试覆盖率低 | `tests/` | 仅 1 个健康检查测试 |

### 已知限制

1. **卡牌无精美原画** — 当前使用文字 + 组件样式展示，非专业塔罗牌面设计
2. **AI 解读依赖第三方 API** — 如果 DeepSeek/Claude API 不可用，占卜功能将完全中断
3. **微信审核风险** — 塔罗占卜属于"宗教/玄学"类目，微信审核可能要求额外资质
4. **无离线能力** — 所有功能依赖网络连接
5. **单机部署** — 当前 Docker Compose 非高可用架构，不适合大流量
6. **无数据备份机制** — MySQL 数据卷无自动备份策略
7. **无监控告警** — 无日志聚合、性能监控、错误告警

---

## 4. 部署步骤

### 环境配置清单

| 资源 | 要求 | 说明 |
|------|------|------|
| 服务器 | Linux (Ubuntu 20.04+), 2C4G+ | 部署 Docker |
| Docker | 24+ | 运行容器化服务 |
| Docker Compose | 2.0+ | 编排多容器 |
| 域名 | 已备案域名 | 小程序要求 HTTPS |
| SSL 证书 | Let's Encrypt 或商业证书 | Nginx 反向代理 |
| 微信小程序 AppID | 已注册 | 替换 `project.config.json` 中的 `appid` |
| 微信支付商户号 | 已开通 | 配置到 `.env` |
| DeepSeek API Key | 已申请 | 配置到 `.env` |
| MySQL 8.0 | Docker 镜像 | 自动拉取 |
| Redis 7 | Docker 镜像 | 自动拉取 |

### 上线部署步骤

#### 第一步：准备生产配置

```bash
# 1. 克隆项目
git clone <repo-url> /data/tarot-miniapp

# 2. 配置生产环境变量
cd /data/tarot-miniapp/backend
cp .env.example .env
# 编辑 .env，填写以下必填字段：
#   DATABASE_URL=mysql+asyncmy://tarot:tarot123@mysql:3306/tarot_db
#   REDIS_URL=redis://redis:6379/0
#   DEEPSEEK_API_KEY=sk-xxx
#   SECRET_KEY=<随机字符串>
#   WECHAT_APP_ID=wx-xxx
#   WECHAT_MCH_ID=商户号
#   WECHAT_API_KEY=微信支付API v3 密钥
#   WECHAT_SERIAL_NO=证书序列号
#   WECHAT_PRIVATE_KEY_PATH=/app/certs/apiclient_key.pem
```

#### 第二步：部署后端服务

```bash
# 3. 放置微信支付证书
mkdir -p /data/tarot-miniapp/backend/certs
# 将微信商户平台下载的 apiclient_key.pem 放入 certs/ 目录

# 4. 启动服务
cd /data/tarot-miniapp
docker compose up -d --build

# 5. 验证服务
curl http://localhost:8000/health
# 预期: {"status":"ok"}
```

#### 第三步：配置前端

```bash
# 6. 打开微信开发者工具 -> 导入 miniapp/ 目录
# 7. 修改 project.config.json 中的 appid 为真实 AppID
# 8. 注意：api.js 已实现环境自动切换，部署版会自动连接生产环境
# 9. 上传代码 -> 提交审核
```

#### 第四步：配置 Nginx 反向代理 (生产环境)

```nginx
# /etc/nginx/sites-available/tarot-api
server {
    listen 443 ssl;
    server_name your-domain.com;
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 微信审核注意事项

1. **类目选择**: 塔罗占卜属于"信息查询 > 占卜/算命"类目，需提供相关资质（如宗教事务许可证等，视地区政策）。部分类目可能需要公司主体资质。
2. **避免敏感词**: 文案中避免"绝对准确""100%应验"等夸大宣传。使用"娱乐参考""心灵启发"等措辞。
3. **会员功能审核**: 微信对虚拟商品支付审核较严。确保：
   - 商品描述清晰明确
   - 用户协议中包含自动续费说明（如有）
   - 提供退款机制说明
4. **iOS 虚拟支付**: 小程序内购买虚拟商品在 iOS 端可能受 Apple IAP 限制。建议 iOS 端隐藏会员购买入口，或使用 H5 支付中转。
5. **数据合规**: 首次打开需有隐私协议弹窗，说明用户数据（微信昵称、头像、占卜记录）的使用范围。
6. **审核常见拒因**:
   - 功能不完整（如"展开全文"不可用）→ 建议先修复当前剩余问题再提交
   - 页面加载失败（空数据无容错）
   - 体验流程有断层

---

## 5. 商业化建议

### 定价策略

| 商品 | 当前定价 | 建议调整 | 理由 |
|------|----------|----------|------|
| 免费用户 | 每日1次免费占卜 | 不变 | 作为获客漏斗入口，留住用户 |
| 月度会员 | ¥19.90/月 | 建议 ¥14.90 | 降低首次付费门槛，促进转化 |
| 季度会员 | ¥49.90/季 | 建议 ¥39.90 | 培养使用习惯 |
| 年度会员 | ¥99.90/年 | 建议 ¥89.90 | 锁定长期用户 |
| 永久会员 | ¥199.90 | 不变 | 高价值用户收割 |
| 单次深度占卜 | ¥9.90 | 不变 | 非会员用户低门槛体验入口 |
| 年度运势报告 | ¥29.90 | 建议 ¥19.90 | 低频功能，薄利多销 |

**定价策略建议**:
- 首月优惠: 新用户首月 ¥6.90，快速建立付费习惯
- 分享裂变: 分享后获得 1 次额外免费占卜（已实现）
- 连续包月: ¥12.90/月（自动续费），降低用户决策成本

### 推广建议

1. **社交裂变**:
   - 解读结果页分享引导（当前已修复分享奖励逻辑）
   - 运势海报自动生成（需增加 Canvas 绘图）
   - 组队解锁（3 人分享各自获得 1 次占卜）

2. **内容运营**:
   - 每日运势推文（公众号导流小程序）
   - 星座/塔罗短视频带货（抖音/B站引导搜索小程序）
   - 朋友圈 H5 海报（带小程序码）

3. **节日营销**:
   - 新月/满月特惠
   - 生日免费测算
   - 情人节/七夕专题牌阵

4. **用户留存**:
   - 每日提醒（订阅消息）："今日运势已更新"
   - 7 天签到奖励：连续签到 7 天送 1 次深度占卜
   - 周报/月报推送：用户占卜数据回顾

### 下一步优化方向

| 优先级 | 方向 | 预期收益 | 工作量 |
|--------|------|----------|--------|
| **P0** | 修复"展开全文"功能 | 修复核心体验故障 | 低（1 行 WXSS） |
| **P1** | 增加数据库迁移脚本 (Alembic) | 生产环境安全 | 中 |
| **P1** | 增加核心 API 测试 | 防止回归 bug | 中 |
| **P1** | 完善分享裂变闭环 (onShareAppMessage) | 提升自然增长 | 低 |
| **P2** | 百科搜索防抖 | 提升低端机体验 | 低 |
| **P2** | 历史记录总数修复 | 数据准确性 | 低 |
| **P2** | 支付后跳转优化 | 提升转化率 | 低 |
| **P2** | 年度报告单独购买入口 | 新增付费路径 | 低 |
| **P3** | 卡牌原画设计 | 提升视觉吸引力 | 高（需设计师） |
| **P3** | 运势分享海报生成 | 社交传播利器 | 中 |
| **P3** | 用户引导 (onboarding) | 降低首次使用困惑 | 中 |
| **P3** | 订阅消息提醒 | 提升日活/留存 | 中 |
| **P3** | 统一网络错误重试 | 体验容错 | 中 |
| **P3** | 管理后台 | 数据分析/运营干预 | 高 |

---

## 附录：文件结构

```
/mnt/e/tarot-miniapp/
├── backend/                     # FastAPI 后端
│   ├── app/
│   │   ├── api/                 # API 路由
│   │   │   ├── auth.py          # 微信登录
│   │   │   ├── readings.py      # 占卜解读
│   │   │   ├── cards.py         # 卡牌百科
│   │   │   ├── membership.py    # 会员
│   │   │   ├── orders.py        # 订单支付
│   │   │   ├── chat.py          # AI追问
│   │   │   ├── diary.py         # 塔罗日记
│   │   │   ├── report.py        # 年度报告
│   │   │   └── share.py         # 分享奖励
│   │   ├── services/
│   │   │   ├── ai_engine.py     # AI 解读引擎
│   │   │   ├── tarot.py         # 塔罗逻辑
│   │   │   ├── payment.py       # 微信支付
│   │   │   └── share.py         # 分享服务
│   │   ├── models/              # SQLAlchemy 模型
│   │   ├── schemas/             # Pydantic 模型
│   │   ├── config.py            # 配置
│   │   └── main.py              # 入口
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
├── miniapp/                     # 微信小程序
│   ├── pages/
│   │   ├── index/               # 首页
│   │   ├── reading/             # 占卜选择
│   │   ├── reading-result/      # 解读结果
│   │   ├── chat/                # AI追问
│   │   ├── encyclopedia/        # 卡牌百科
│   │   ├── card-detail/         # 卡牌详情
│   │   ├── membership/          # 会员购买
│   │   ├── profile/             # 个人中心
│   │   ├── diary/               # 塔罗日记
│   │   └── annual-report/       # 年度报告
│   ├── components/
│   │   └── tarot-card/          # 塔罗牌组件
│   ├── utils/
│   │   ├── api.js               # 网络请求
│   │   └── auth.js              # 登录认证
│   └── app.json
├── docs/                        # 文档
│   ├── pm-review-1~5.md         # 5轮PM审查报告
│   ├── qa-round-1~5.md          # QA测试报告
│   ├── deploy-guide.md          # 部署指南
│   ├── UI_SPEC.md               # UI规范
│   └── DELIVERY-REPORT.md       # 本文件
└── docker-compose.yml
```
