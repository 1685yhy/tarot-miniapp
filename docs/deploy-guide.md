# 塔罗占卜小程序部署指南

## 1. 服务器准备

### 1.1 硬件要求
- 云服务器 ECS（阿里云/腾讯云均可）
- 配置：2 核 4G 以上
- 操作系统：CentOS 7+ 或 Ubuntu 20.04+
- 开放端口：80、443（用户访问）、3306（MySQL，可选关闭）、6379（Redis，可选关闭）

### 1.2 安装 Docker
```bash
# CentOS
sudo yum install -y yum-utils
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl start docker
sudo systemctl enable docker

# Ubuntu
sudo apt update
sudo apt install -y docker.io docker-compose-plugin
```

验证安装：
```bash
sudo docker --version
sudo docker compose version
```

## 2. 上传代码

```bash
# 在本地打包（在项目根目录执行）
tar -czf tarot-app.tar.gz \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.env' \
  --exclude='venv' \
  --exclude='.venv' \
  backend/ docker-compose.yml data/

# 上传到服务器
scp tarot-app.tar.gz user@your-server-ip:/opt/tarot/

# 登录服务器并解压
ssh user@your-server-ip
cd /opt/tarot
tar -xzf tarot-app.tar.gz
```

## 3. 配置环境变量

```bash
cd /opt/tarot/backend
cp .env.example .env
vim .env  # 填入真实的 API 密钥
```

需要配置的关键字段：

| 变量 | 说明 | 获取方式 |
|------|------|----------|
| `ANTHROPIC_API_KEY` | Claude API 密钥 | [console.anthropic.com](https://console.anthropic.com) |
| `WECHAT_APP_ID` | 微信小程序 AppID | 微信公众平台 |
| `WECHAT_APP_SECRET` | 微信小程序 Secret | 微信公众平台 |
| `WECHAT_MCH_ID` | 微信商户号 | 微信商户平台 |
| `WECHAT_API_KEY_V3` | 微信支付 V3 密钥 | 微信商户平台 |
| `JWT_SECRET` | JWT 签名密钥 | 使用 `openssl rand -hex 32` 生成 |

> **注意**：`.env.example` 中的数据库和 Redis 地址已配置为 Docker 服务名（`mysql`、`redis`），无需修改。如使用外部数据库，请改为实际地址。

## 4. 启动服务

```bash
cd /opt/tarot

# 启动所有容器
sudo docker compose up -d

# 查看运行状态
sudo docker compose ps

# 查看日志
sudo docker compose logs -f app
```

### 4.1 导入塔罗牌数据

```bash
# 等待数据库就绪（约 10-20 秒）
sudo docker compose exec app python -m app.db.seed
```

### 4.2 验证服务

```bash
# 健康检查
curl http://localhost:8000/health

# 预期返回
# {"status": "ok"}
```

## 5. 配置 HTTPS + 域名

### 5.1 Nginx 反向代理

安装 Nginx：
```bash
sudo yum install -y nginx   # CentOS
sudo apt install -y nginx   # Ubuntu
```

创建 Nginx 配置文件 `/etc/nginx/conf.d/tarot.conf`：
```nginx
server {
    listen 80;
    server_name your-domain.com;

    # 申请 SSL 证书后改为以下配置
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    # WebSocket 支持（用于 AI 流式输出）
    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### 5.2 申请 SSL 证书

推荐使用 Let's Encrypt + Certbot：
```bash
sudo yum install -y certbot python3-certbot-nginx   # CentOS
sudo apt install -y certbot python3-certbot-nginx   # Ubuntu

sudo certbot --nginx -d your-domain.com
```

证书自动续期：
```bash
# 添加定时任务
echo "0 3 * * * root certbot renew --quiet" | sudo tee -a /etc/crontab
```

### 5.3 更新后的 Nginx 配置
```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

## 6. 配置微信小程序

1. 登录 [微信公众平台](https://mp.weixin.qq.com/)
2. 进入「开发」-「开发管理」-「服务器域名」
3. 添加以下域名白名单：

| 域名类型 | 域名 |
|---------|------|
| request 合法域名 | `https://your-domain.com` |
| socket 合法域名 | `wss://your-domain.com` |

4. 进入「开发」-「开发设置」，确认 AppID 和 AppSecret

## 7. 发布小程序

```bash
# 修改前端 API 地址
# 编辑 miniapp/utils/api.js，将 BASE_URL 改为你的域名
```

步骤：
1. 微信开发者工具打开 `miniapp/` 目录
2. 修改 `utils/api.js` 中的 `BASE_URL` 为你的 HTTPS 域名
3. 点击「上传」按钮上传代码
4. 登录微信公众平台 →「版本管理」→ 提交审核
5. 审核通过后点击「发布」

## 8. 运维命令速查

### 8.1 容器管理
```bash
# 查看所有容器状态
sudo docker compose ps

# 查看实时日志（app 服务）
sudo docker compose logs -f app

# 重启服务
sudo docker compose restart app

# 重新构建并启动（代码更新后）
sudo docker compose up -d --build app
```

### 8.2 数据库维护
```bash
# 数据库备份
sudo docker compose exec mysql mysqldump -utarot -ptarot123 tarot_db > backup.sql

# 数据库恢复
sudo docker compose exec -T mysql mysql -utarot -ptarot123 tarot_db < backup.sql
```

### 8.3 更新部署
```bash
# 上传新代码后
cd /opt/tarot
sudo docker compose down
# 替换代码文件
tar -xzf tarot-app-new.tar.gz
sudo docker compose up -d --build
```

## 9. 故障排查

### 9.1 容器无法启动
```bash
# 查看详细日志
sudo docker compose logs

# 检查数据库连接
sudo docker compose exec app python -c "from app.config import settings; print(settings.DATABASE_URL)"
```

### 9.2 数据库连接失败
- 确认 MySQL 容器已启动：`sudo docker compose ps`
- 确认 `.env` 中 `DATABASE_URL` 使用的是 `mysql` 服务名而非 `localhost`
- 首次启动后需等待 10-20 秒让数据库初始化完成

### 9.3 SSL 证书问题
```bash
# 手动续期
sudo certbot renew --force-renewal
# 重载 Nginx
sudo nginx -s reload
```
