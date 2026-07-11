# 塔罗小程序上线前必查清单

> 部署前逐项核对，避免线上事故。每项标注影响等级。

---

## 1. 域名与网络

| # | 检查项 | 要求 | 影响 | 检查命令 |
|---|--------|------|------|----------|
| 1 | 小程序后台配置 request 合法域名 | 添加后端域名到微信公众平台 → 开发 → 开发设置 → 服务器域名 | **阻塞上线** | 打开 https://mp.weixin.qq.com → 开发管理 → 服务器域名 |
| 2 | HTTPS 证书有效 | 域名必须支持 HTTPS，证书未过期 | **阻塞上线** | `openssl s_client -connect your-domain.com:443 -servername your-domain.com 2>/dev/null | openssl x509 -noout -dates` |
| 3 | 后端 CORS 允许小程序域名 | 生产环境应将 allow_origins 从小程序域名改为白名单 | 影响功能 | 检查 `main.py` 中 `allow_origins` 配置 |
| 4 | extConfig 域名已配置（第三方平台） | 第三方平台托管的小程序需通过 extConfig 传入 BASE_URL | **阻塞上线** | 检查第三方平台配置中的 BASE_URL 参数 |
| 5 | 生产数据库连接串正确 | DATABASE_URL 非 SQLite 占位符，指向生产数据库 | **阻塞上线** | `grep DATABASE_URL backend/.env | grep -v '^#'` |

## 2. 密钥与API

| # | 检查项 | 要求 | 影响 | 检查命令 |
|---|--------|------|------|----------|
| 6 | DeepSeek API Key 已配置 | DEEPSEEK_API_KEY 非空，余额充足 | **阻塞上线** | `curl -s https://api.deepseek.com/v1/models -H "Authorization: Bearer $(grep DEEPSEEK_API_KEY backend/.env | cut -d= -f2)"` |
| 7 | DeepSeek API Key 未硬编码在前端 | API Key 必须在后端调用，不暴露在前端代码中 | **阻塞上线** | `grep -r 'sk-' miniapp/ --include='*.js' --include='*.wxml' --include='*.wxss' 2>/dev/null | grep -v node_modules` |
| 8 | DeepSeek 模型参数正确 | DEEPSEEK_MODEL 填写真实模型名（如 deepseek-chat） | 影响功能 | `grep DEEPSEEK_MODEL backend/.env` |

## 3. 微信支付

| # | 检查项 | 要求 | 影响 | 检查命令 |
|---|--------|------|------|----------|
| 9 | 微信商户号已申请 | WECHAT_MCH_ID 填写真实的商户号 | **阻塞上线** | `grep WECHAT_MCH_ID backend/.env | grep -v 'your' && echo "OK" || echo "MISSING"` |
| 10 | APIv3 密钥已配置 | WECHAT_API_KEY_V3 为 32 字节，非占位符 | **阻塞上线** | `grep WECHAT_API_KEY_V3 backend/.env` |
| 11 | 微信 AppID 与 AppSecret 一致 | WECHAT_APP_ID 和 WECHAT_APP_SECRET 配对，且非占位符 | **阻塞上线** | `grep -E 'WECHAT_(APP_ID|APP_SECRET)' backend/.env | grep -v your` |
| 12 | 支付通知回调 URL 已设置 | 商户平台 → 产品中心 → 开发配置 → 支付通知回调域名 | **阻塞上线** | 打开微信支付商户平台检查 |

## 4. 微信小程序配置

| # | 检查项 | 要求 | 影响 | 检查命令 |
|---|--------|------|------|----------|
| 13 | AppID 已替换真实值 | project.config.json 中的 appid 非占位符 | **阻塞上线** | `grep '"appid"' miniapp/project.config.json` |
| 14 | app.json 页面路径完整 | 所有页面已注册且路径正确 | **阻塞上线** | `jq '.pages[]' miniapp/app.json | while read p; do test -f "miniapp/$p.js" || echo "MISSING: $p"; done` |
| 15 | 体验版二维码可访问 | 提交体验版后能正常进入首页 | 影响功能 | 微信扫码 → 打开小程序 → 观察首屏 |
| 16 | 云开发/云函数已关闭（如果未使用） | 未使用的云服务应关闭，避免触发额度 | 可选 | `grep cloud miniapp/app.json` |

## 5. 认证与安全

| # | 检查项 | 要求 | 影响 | 检查命令 |
|---|--------|------|------|----------|
| 17 | JWT_SECRET 已改为强密钥 | 至少 32 位随机字符，非 "change-me-in-production" | **阻塞上线** | `grep JWT_SECRET backend/.env | grep -v 'change-me' || echo "WEAK"` |
| 18 | JWT 过期时间合理 | 生产环境建议 7-30 天（10080-43200 分钟） | 影响功能 | `grep JWT_EXPIRE_MINUTES backend/.env` |
| 19 | 日志不输出密钥 | 代码中避免打印密钥、token 等内容 | 影响功能 | `grep -rn 'console.log.*JWT\|print.*SECRET\|logger.*API_KEY' backend/ --include='*.py'` |

## 6. 数据库与存储

| # | 检查项 | 要求 | 影响 | 检查命令 |
|---|--------|------|------|----------|
| 20 | 数据库已迁移到生产 | 正式上线不应使用 SQLite | **阻塞上线** | `grep DATABASE_URL backend/.env | grep -v sqlite || echo "SQLITE DETECTED"` |
| 21 | Redis 连接正常 | 生产 Redis 可达、密码已配置 | 影响功能 | `redis-cli -h <host> ping` |
| 22 | 免费额度表已核对 | FREE_DAILY_READINGS 和 FREE_CHAT_MESSAGES 数值符合运营需求 | 影响功能 | `grep -E 'FREE_(DAILY_READINGS|CHAT_MESSAGES)' backend/.env` |

## 7. 前端部署

| # | 检查项 | 要求 | 影响 | 检查命令 |
|---|--------|------|------|----------|
| 23 | BASE_URL 占位符已替换 | api.js 中 release URL 非 "your-domain" | **阻塞上线** | `grep 'your-domain' miniapp/utils/api.js || echo "OK"` |
| 24 | 所有 console.log 已清理 | 生产环境不应输出调试日志 | 可选 | `grep -r 'console.log' miniapp/ --include='*.js' | grep -v node_modules | grep -v '//'` |
| 25 | 代码已提交且打 Tag | 在 Git 上标记版本号以便回滚 | 可选 | `git tag -l | tail -5` |
| 26 | 构建产物体积检查 | 预览包体积应在微信限制内（主包 < 2MB） | 影响功能 | 微信开发者工具 → 详情 → 基本信息 → 代码包大小 |

---

## 快速一键检查

```bash
# 从项目根目录运行
echo "=== 域名检查 ===" && grep 'your-domain' miniapp/utils/api.js && echo "WARN: 还有占位符"

echo "=== DeepSeek Key ===" && grep DEEPSEEK_API_KEY backend/.env | grep -v '^#' | grep -q 'sk-' && echo "OK" || echo "MISSING"

echo "=== JWT ===" && grep JWT_SECRET backend/.env | grep -v 'change-me' && echo "OK" || echo "WARN: JWT_SECRET 为默认值"

echo "=== 微信商户号 ===" && grep WECHAT_MCH_ID backend/.env | grep -v 'your' && echo "OK" || echo "MISSING"

echo "=== AppID ===" && grep '"appid"' miniapp/project.config.json | grep -v 'your' | grep -v 'placeholder' && echo "OK" || echo "MISSING"

echo "=== 数据库 ===" && grep DATABASE_URL backend/.env | grep -v sqlite && echo "OK (production)" || echo "WARN: 使用 SQLite"
```

---

> 最后提醒：上线前务必在**体验版**走一遍完整支付 + 占卜 + AI 对话流程。通过后再提交审核。
