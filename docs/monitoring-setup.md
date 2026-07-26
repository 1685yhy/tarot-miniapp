# 星光映照 生产监控与告警配置

> Starlight Tarot — Production Monitoring & Alerting Setup

---

## 1. Sentry 错误追踪

### 创建项目

1. 登录 [sentry.io](https://sentry.io) (或自建 Sentry 实例)
2. 创建一个 **Python (FastAPI)** 项目
3. 复制生成的 DSN 字符串

### 配置 DSN

在服务器 `.env` 文件中添加：

```env
SENTRY_DSN=https://xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx@oxxxxxx.ingest.sentry.io/xxxxxx
```

应用启动后会通过 `backend/app/main.py` 中的 `sentry_sdk.init()` 自动初始化。  
初始化失败不会导致应用崩溃（已包裹 try/except）。

### 已验证的集成点

| 集成点          | 文件                        |
|----------------|-----------------------------|
| SDK 初始化      | `backend/app/main.py`      |
| 配置字段        | `backend/app/config.py`    |
| 环境区分        | Dev: `development`, Prod: `production` |

---

## 2. Prometheus 指标采集

### 暴露的指标端点

```
GET /metrics
```

格式：标准 Prometheus text/plain。

### 自定义指标

| 指标名称                       | 类型      | 标签                               | 说明                      |
|-------------------------------|-----------|-----------------------------------|---------------------------|
| `http_requests_total`         | Counter   | `method`, `endpoint`, `status`    | 总 HTTP 请求数            |
| `http_request_duration_seconds` | Histogram | —                                 | HTTP 请求延迟分布         |
| `ai_calls_total`              | Counter   | `model`, `status`                 | AI API 调用次数           |
| `payment_success_total`       | Counter   | —                                 | 成功支付次数              |

### Prometheus 抓取配置 (`prometheus.yml`)

```yaml
scrape_configs:
  - job_name: "tarot-api"
    scrape_interval: 15s
    metrics_path: /metrics
    static_configs:
      - targets:
          - "localhost:8000"       # 后端 API 服务地址
    relabel_configs:
      - source_labels: [__address__]
        target_label: instance
        replacement: "tarot-api-prod"
```

### 指标采集流程图

```
[FastAPI app] --/metrics--> [Prometheus] --data source--> [Grafana]
                                |
                          [Alertmanager] --webhook--> [飞书/钉钉/企业微信]
```

---

## 3. Grafana 仪表盘

### 导入步骤

1. 登录 Grafana (默认 `http://localhost:3000`, 账号 `admin` / `admin`)
2. 左侧菜单 **+** → **Import**
3. 输入仪表盘 JSON 或 ID（如果有公开 ID）
4. 选择 Prometheus 数据源

### 推荐面板

| 面板标题               | 指标表达式                                                   |
|-----------------------|-------------------------------------------------------------|
| HTTP 请求速率 (RPS)    | `rate(http_requests_total[1m])`                             |
| 请求延迟 (p50/p95/p99) | `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[1m]))` |
| 错误率 (%)             | `(sum(rate(http_requests_total{status=~"5.."}[1m])) / sum(rate(http_requests_total[1m]))) * 100` |
| AI 调用次数            | `rate(ai_calls_total[1m])`                                  |
| 支付成功数             | `rate(payment_success_total[1m])`                           |

---

## 4. 告警规则

### Prometheus 告警规则 (`alerts.yml`)

```yaml
groups:
  - name: tarot-api-alerts
    rules:
      - alert: HighErrorRate
        expr: |
          (sum(rate(http_requests_total{status=~"5.."}[1m]))
           / sum(rate(http_requests_total[1m]))) * 100 > 5
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "5xx 错误率超过 5%"
          description: "过去 1 分钟 5xx 错误率 {{ $value | humanize }}%，请立即检查。"

      - alert: HighLatency
        expr: |
          histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[1m])) > 5
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "P95 延迟超过 5 秒"
          description: "P95 延迟 {{ $value | humanize }}s，请检查上游服务。"

      - alert: InstanceDown
        expr: up{job="tarot-api"} == 0
        for: 30s
        labels:
          severity: critical
        annotations:
          summary: "服务实例离线"
          description: "实例 {{ $labels.instance }} 已离线超过 30 秒。"
```

### Webhook 通知

Alertmanager 配置发送到飞书/钉钉/企业微信机器人：

```yaml
receivers:
  - name: "feishu-bot"
    webhook_configs:
      - url: "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
        send_resolved: true
```

也支持 `alertmanager-webhook-proxy` 转发到自定义端点。

---

## 5. 部署后验证

部署完成后在服务器执行：

```bash
# 检查指标端点是否可达
curl -s http://localhost:8000/metrics | head -20

# 触发一次健康检查
curl -s http://localhost:8000/health | python3 -m json.tool

# 样本输出示例
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
# http_requests_total{endpoint="/health",method="GET",status="200"} 42.0
```

---

## 6. 文件清单

| 文件                                              | 用途                  |
|--------------------------------------------------|-----------------------|
| `backend/app/main.py`                            | Sentry 初始化         |
| `backend/app/config.py`                          | `SENTRY_DSN` 配置项   |
| `backend/app/api/monitor.py`                     | `/metrics` 端点 + 指标定义 |
| `backend/app/middleware/metrics.py`              | 请求计数/延迟中间件    |
| `backend/requirements.txt`                       | 新增 sentry-sdk + prometheus-client |

---

*最后更新: 2026-07-26*
