from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from prometheus_client import Counter, Histogram, generate_latest
from sqlalchemy import delete, func, select
import logging

from app.db.database import get_db
from app.models.performance import PerformanceEvent

logger = logging.getLogger(__name__)

router = APIRouter(tags=["监控"])

# ---- Prometheus metrics ----
HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
)
HTTP_ERRORS = Counter(
    "http_errors_total",
    "Total HTTP error responses (status >= 400)",
    ["method", "endpoint", "status"],
)
AI_CALLS = Counter(
    "ai_calls_total",
    "Total AI API calls",
    ["model", "status"],
)
PAYMENT_SUCCESS = Counter(
    "payment_success_total",
    "Successful payments",
)

# ---- 埋点保留策略：只保留最近 30 天，写入时惰性清理 ----
RETENTION_DAYS = 30


async def _persist_events(events: list[dict]) -> None:
    """Fire-and-forget 落库：独立会话 + 全量 try/except，写入失败绝不影响请求响应。

    顺带执行保留期清理：每次写入时删除 created_at 早于 30 天前的旧数据
    （created_at 上有索引，SQLite 下为 O(log n) 的区间删除）。
    """
    if not events:
        return
    try:
        from app.db.database import async_session

        async with async_session() as session:
            cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
            await session.execute(
                delete(PerformanceEvent).where(PerformanceEvent.created_at < cutoff)
            )
            for ev in events:
                session.add(PerformanceEvent(**ev))
            await session.commit()
    except Exception:
        logger.exception("failed to persist performance events (non-critical, ignored)")


def _parse_frontend_payload(data: dict) -> list[dict]:
    """把前端 /performance 上报归一化为 PerformanceEvent 构造参数。

    前端实际发送：{metrics: [{metric, durationMs}], platform, timestamp, sdk}
    兼容旧格式：{page, metric, value}
    """
    now = datetime.now(timezone.utc)
    page = str(data.get("page") or "")[:255] or None
    events: list[dict] = []
    metrics = data.get("metrics")

    if isinstance(metrics, list):
        # 前端新版数组格式
        for m in metrics:
            if not isinstance(m, dict):
                continue
            metric = str(m.get("metric") or "").strip()
            if not metric:
                continue
            value = m.get("durationMs", m.get("value"))
            events.append(
                {
                    "page": page,
                    "metric": metric[:64],
                    "value": value if isinstance(value, (int, float)) else None,
                    "extra": {
                        "platform": data.get("platform"),
                        "sdk": data.get("sdk"),
                        "ts": data.get("timestamp"),
                    },
                    "created_at": now,
                }
            )
    else:
        # 旧格式单条：{page, metric, value}
        metric = str(data.get("metric") or "").strip()
        if metric:
            value = data.get("value", 0)
            extra = {k: data.get(k) for k in ("platform", "sdk", "timestamp") if k in data}
            events.append(
                {
                    "page": page,
                    "metric": metric[:64],
                    "value": value if isinstance(value, (int, float)) else None,
                    "extra": extra or None,
                    "created_at": now,
                }
            )
    return events


@router.get("/metrics")
async def metrics():
    """Prometheus 文本格式指标（请求数 / 延迟 / 错误数，由 prometheus-client 生成）。"""
    return Response(content=generate_latest(), media_type="text/plain")


@router.post("/performance")
async def log_performance(data: dict):
    """Receive frontend performance metrics (non-critical, fire-and-forget)."""
    events = _parse_frontend_payload(data)
    await _persist_events(events)
    for ev in events:
        logger.info("perf|%s|%s|%s", ev["page"], ev["metric"], ev["value"])
    if not events:
        logger.warning("perf|empty or unparseable payload: %s", str(data)[:200])
    return {"ok": True, "persisted": len(events)}


@router.post("/monitor/error")
async def report_js_error(data: dict):
    """Receive frontend JS errors (App.onError / onUnhandledRejection), silent fire-and-forget.

    与性能埋点共用 performance_events 表：metric="js_error"，message/stack 存 extra。
    """
    message = str(data.get("message") or "")[:2000]
    stack = str(data.get("stack") or "")[:8000]
    page = str(data.get("page") or "")[:255] or None
    extra = {
        "message": message,
        "stack": stack,
        "platform": data.get("platform"),
        "ts": data.get("ts"),
    }
    ev = {
        "page": page,
        "metric": "js_error",
        "value": None,
        "extra": extra,
        "created_at": datetime.now(timezone.utc),
    }
    await _persist_events([ev])
    logger.info("perf|js_error|%s|%s", page, message[:120])
    return {"ok": True}


@router.get("/monitor/performance/summary")
async def performance_summary(
    days: int = Query(7, ge=1, le=365),
    db=Depends(get_db),
):
    """按 metric 聚合的埋点统计（供管理后台展示真实埋点）。

    GET /monitor/performance/summary?days=7
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        select(
            PerformanceEvent.metric,
            func.count(PerformanceEvent.id),
            func.avg(PerformanceEvent.value),
            func.min(PerformanceEvent.value),
            func.max(PerformanceEvent.value),
        )
        .where(PerformanceEvent.created_at >= cutoff)
        .group_by(PerformanceEvent.metric)
        .order_by(func.count(PerformanceEvent.id).desc())
    )
    rows = (await db.execute(stmt)).all()

    total = 0
    metrics: dict = {}
    for metric, count, avg, mn, mx in rows:
        total += int(count)
        metrics[metric] = {
            "count": int(count),
            "avg": round(float(avg), 2) if avg is not None else None,
            "min": mn,
            "max": mx,
        }
    return {"days": days, "total": total, "metrics": metrics}
