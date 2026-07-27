# 精品优化阶段 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** 4维度精品优化 — AI流式体验 + 微信推送 + 性能极致 + 转化优化

**Architecture:** 4条独立优化线，零交叉依赖，全部并行执行。

## 全局约束

- 定价：月19.9/年168/学生9.9/永久298
- 免费额度：3次解读/天 + 3次追问/天
- 设计系统：深靛蓝 #1a1a2e / 暖金 #C9A84C / 薰衣草紫 #9A95B8
- 73测试必须保持全绿，IDE编译零错误
- 微信小程序包体上限 2MB（主包），当前 ~759KB

---

### Task 1: AI 流式输出（WebSocket 打字机效果）

**竞品对标:** 万象有灵 AI 陪伴、ChatGPT 流式输出 — 这是"高级感"的关键差异

**Files:**
- Create: `backend/app/api/ws.py` — WebSocket 端点
- Modify: `backend/app/services/ai_engine.py` — 流式生成函数
- Modify: `backend/app/main.py` — 注册 WebSocket 路由
- Modify: `miniapp/pages/chat/chat.js` — WebSocket 接收 + 逐字渲染
- Modify: `miniapp/pages/chat/chat.wxml` — 打字光标动画
- Modify: `miniapp/pages/chat/chat.wxss` — 光标闪烁样式
- Modify: `miniapp/pages/reading-result/reading-result.js` — 解读结果流式展示

**实现:**
- FastAPI WebSocket `/ws/chat/{reading_id}` — 流式转发 DeepSeek stream
- DeepSeek API `stream=True` → `AsyncGenerator` → WebSocket `send_text()`
- 前端：`wx.connectSocket` → `onMessage` → 逐字追加到消息气泡
- 打字光标：闪烁 `|` 符号，收到 `[DONE]` 后移除
- 回退：WebSocket 失败 → 回退到当前 REST 轮询

---

### Task 2: 微信订阅消息推送

**目标:** 让用户感到"被记得" — 每日提醒 + 事件通知

**Files:**
- Create: `backend/app/api/notify.py` — 推送触发端点
- Create: `backend/app/services/push.py` — 微信订阅消息发送
- Modify: `miniapp/pages/index/index.js` — 收集订阅授权
- Modify: `miniapp/pages/index/index.wxml` — 订阅入口
- Modify: `miniapp/pages/profile/profile.js` — 推送设置页
- Modify: `miniapp/pages/profile/profile.wxml` — 推送开关 UI

**实现:**
- 订阅模板：每日一牌提醒、会员到期提醒、年报上线通知
- 后端：`POST /notify/subscribe` 收集 openid + template_id
- 后端：`POST /notify/send-daily` 定时任务推送
- 前端：`wx.requestSubscribeMessage` 请求授权
- 用户可在设置页管理所有推送开关

---

### Task 3: 性能极致优化

**目标:** 首屏 <1.5s，包体 <800KB，流畅 60fps

**Files:**
- Modify: `miniapp/app.json` — 分包配置优化
- Modify: `miniapp/pages/*/` — 图片懒加载
- Create: `miniapp/utils/performance.js` — 性能监控
- Modify: `miniapp/pages/index/index.js` — 首屏关键路径优化

**实现:**
- 图片懒加载：`lazy-load` 属性 + 低质量占位图
- 非首屏页面延迟加载（`componentPlaceholder`）
- 骨架屏覆盖所有页面加载状态
- 清理未使用代码和资源
- 性能埋点：首屏时间、可交互时间

---

### Task 4: 转化优化

**目标:** 免费→付费转折点感知清晰，会员价值可量化

**Files:**
- Modify: `miniapp/pages/membership/membership.js` — 强化价值感知
- Modify: `miniapp/pages/membership/membership.wxml` — 修改对比表
- Modify: `miniapp/pages/reading/reading.js` — 免费额度用完引导
- Modify: `miniapp/pages/profile/profile.js` — 会员权益可视化

**实现:**
- 会员对比表加 "已为你节省 ¥XX"
- 免费额度用完时展示 "今日已解读 3/3 次 · 明日0点重置" + 柔和解锁CTA
- 个人页会员权益可视化：解锁牌阵数、追问次数、专属角色
- 试用到期前 24h 提醒
- 支付成功页增加 "已解锁" 权益展示动画
