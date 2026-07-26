# M3 可运维 + 竞争壁垒 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended).

**Goal:** 管理后台可独立运营 + CI/CD自动化 + 生产监控告警

**Architecture:** 3个新系统（管理后台Web、GitHub Actions CI/CD、Sentry+Prometheus监控）+ 3个已验证功能（社交裂变/音效/日记AI）

**Tech Stack:** FastAPI Admin, GitHub Actions, Sentry, Prometheus, Grafana

## 实地勘查：M3 功能完成度

| 功能 | 状态 | 证据 |
|------|------|------|
| 社交裂变 | ✅ 已完成 | 5个API端点 + 真实wxacode + 海报Canvas + 邀请码奖励体系 |
| 音效升级 | ✅ 已完成 | 12个函数，Web Audio合成，混响+立体声，零外部音频文件 |
| 日记AI周回顾 | ✅ 已完成 | M2确认 `GET /diary/review` 可用 |
| 管理后台 | ❌ 缺口 | 仅 config.py 有一个 `SUPER_ADMIN_IDS` 字段 |
| CI/CD | ❌ 缺口 | 无 .github/workflows/，有 Dockerfile 但未接入 CI |
| 监控告警 | ⚠️ 仅 /health | 无 Sentry、无 Prometheus、无告警通道 |

## 全局约束

- 定价：月19.9/年168/学生9.9/永久298
- 免费额度：3次解读/天 + 3次追问/天
- 设计系统：深靛蓝 #1a1a2e / 暖金 #C9A84C / 薰衣草紫 #9A95B8
- 所有后端变更需通过 73 项测试 + 服务器部署验证
- 管理后台仅限 SUPER_ADMIN_IDS 中的 UUID 访问

---

### Task 1: 管理后台 — FastAPI Admin 面板

**创建最快的实用管理后台**：用 FastAPI 原生路由 + Jinja2 模板，不引入重型框架。

**Files:**
- Create: `backend/app/api/admin.py` — 管理路由（用户/订单/解读/内容管理）
- Create: `backend/app/templates/admin/` — Jinja2 模板目录
- Create: `backend/app/templates/admin/dashboard.html` — 数据看板
- Create: `backend/app/templates/admin/users.html` — 用户列表
- Create: `backend/app/templates/admin/readings.html` — 解读质量抽查
- Create: `backend/app/templates/admin/orders.html` — 订单与收入
- Create: `backend/app/static/admin.css` — 管理后台样式
- Modify: `backend/app/main.py` — 注册 admin router + mount static

**功能清单：**
- `/admin` — 仪表盘：今日DAU、付费转化率、收入、AI调用量
- `/admin/users` — 用户列表 + 搜索 + 会员状态筛选
- `/admin/readings` — 解读记录 + AI质量抽查（展示 prompt + response）
- `/admin/orders` — 订单流水 + 收入汇总
- `/admin/content` — 卡牌内容管理（简单 CMS）

**安全：** 所有 `/admin/*` 路由检查 `x-admin-user-id` header 是否在 `SUPER_ADMIN_IDS` 中。

---

### Task 2: CI/CD — GitHub Actions 自动部署

**Files:**
- Create: `.github/workflows/ci.yml` — 测试 + 编译
- Create: `.github/workflows/deploy.yml` — 自动部署到服务器
- Create: `scripts/deploy.sh` — 部署脚本

**流水线：**
- PR → `ci.yml`: pytest 73项 + IDE auto-preview 编译验证
- Push master → `deploy.yml`: tests → scp 后端代码 → ssh systemctl restart → 健康检查

---

### Task 3: 监控告警 — Sentry + 企业微信通知

**Files:**
- Modify: `backend/app/main.py` — Sentry SDK 初始化
- Create: `backend/app/api/monitor.py` — `/metrics` Prometheus 端点
- Modify: `backend/requirements.txt` — 加 sentry-sdk, prometheus-client
- Create: `docs/monitoring-setup.md` — 监控配置文档

**实现：**
- Sentry: 自动捕获所有 5xx 错误 + 微信支付异常
- Prometheus `/metrics`: HTTP 请求计数 + 延迟 + AI 调用量 + 支付成功率
- 告警规则：API 5xx > 5%/min → 企业微信通知
- 脚本部署到服务器

---

## M3 完成验证门

```bash
# 1. 管理后台可访问
curl -H "x-admin-user-id: <SUPER_ADMIN_UUID>" http://localhost:8000/admin

# 2. CI 流水线
git push → GitHub Actions 自动运行 73 项测试 + 编译

# 3. 监控正常运行
curl http://localhost:8000/metrics | grep "http_requests_total"
```
