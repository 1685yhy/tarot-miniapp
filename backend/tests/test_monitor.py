"""埋点落库 / JS 错误上报 / 聚合统计 / Prometheus 指标 测试。

覆盖：
- POST /performance 前端数组格式与旧单条格式均落库
- POST /monitor/error 以 metric='js_error' 落库
- GET /monitor/performance/summary 按 metric 聚合 count/avg，且尊重 days 窗口
- 30 天保留期清理（插入时惰性删除旧数据）
- /metrics 返回 Prometheus 文本格式且包含错误数指标
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.main import app
from app.db.database import async_session
from app.models.performance import PerformanceEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_events() -> None:
    async def _go():
        async with async_session() as s:
            await s.execute(delete(PerformanceEvent))
            await s.commit()
    asyncio.run(_go())


def _fetch_rows() -> list[dict]:
    async def _go():
        async with async_session() as s:
            rows = (await s.execute(select(PerformanceEvent))).scalars().all()
            return [
                {
                    "page": r.page,
                    "metric": r.metric,
                    "value": r.value,
                    "extra": r.extra,
                    "created_at": r.created_at,
                }
                for r in rows
            ]
    return asyncio.run(_go())


@pytest.fixture(autouse=True)
def _clean_events_fixture():
    """每个用例前后清空 performance_events，避免用例间数据串扰。"""
    _clean_events()
    yield
    _clean_events()


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides.clear()
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# POST /performance —— 落库
# ---------------------------------------------------------------------------

def test_performance_frontend_array_shape_persists(client):
    """前端实际上报格式 {metrics:[{metric,durationMs}], platform, timestamp, sdk} 落库。"""
    resp = client.post(
        "/performance",
        json={
            "metrics": [
                {"metric": "firstPageReady", "durationMs": 321},
                {"metric": "pageReady:pages/index/index", "durationMs": 456},
            ],
            "platform": "wechat",
            "timestamp": 1750000000000,
            "sdk": "develop",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["persisted"] == 2

    rows = _fetch_rows()
    assert len(rows) == 2
    by_metric = {r["metric"]: r for r in rows}
    assert by_metric["firstPageReady"]["value"] == 321
    assert by_metric["firstPageReady"]["extra"]["platform"] == "wechat"
    assert by_metric["firstPageReady"]["extra"]["sdk"] == "develop"
    assert by_metric["pageReady:pages/index/index"]["value"] == 456
    assert all(r["created_at"] is not None for r in rows)


def test_performance_legacy_shape_persists(client):
    """旧格式 {page, metric, value} 仍兼容。"""
    resp = client.post(
        "/performance",
        json={"page": "pages/index/index", "metric": "loadTime", "value": 99},
    )
    assert resp.status_code == 200
    assert resp.json()["persisted"] == 1

    rows = _fetch_rows()
    assert len(rows) == 1
    assert rows[0]["metric"] == "loadTime"
    assert rows[0]["value"] == 99
    assert rows[0]["page"] == "pages/index/index"


def test_performance_empty_payload_ok(client):
    """空/不可解析 payload 不影响响应。"""
    resp = client.post("/performance", json={})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["persisted"] == 0


# ---------------------------------------------------------------------------
# POST /monitor/error —— JS 错误落库
# ---------------------------------------------------------------------------

def test_js_error_persists_with_stack(client):
    resp = client.post(
        "/monitor/error",
        json={
            "message": "Cannot read property 'x' of undefined",
            "stack": "TypeError: ...\n  at pages/index/index.js:12:5",
            "page": "pages/index/index",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    rows = _fetch_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row["metric"] == "js_error"
    assert row["value"] is None
    assert row["page"] == "pages/index/index"
    assert row["extra"]["message"] == "Cannot read property 'x' of undefined"
    assert "index.js:12:5" in row["extra"]["stack"]


# ---------------------------------------------------------------------------
# GET /monitor/performance/summary —— 聚合统计
# ---------------------------------------------------------------------------

def _insert_event(metric: str, value: float | None, days_ago: int, page: str | None = None):
    async def _go():
        async with async_session() as s:
            s.add(
                PerformanceEvent(
                    page=page,
                    metric=metric,
                    value=value,
                    extra={"message": f"old-{metric}"},
                    created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
                )
            )
            await s.commit()
    asyncio.run(_go())


def test_summary_groups_by_metric_with_count_and_avg(client):
    _insert_event("firstPageReady", 100, 0)
    _insert_event("firstPageReady", 300, 0)
    _insert_event("pageReady:pages/readings/index", 250, 0)

    resp = client.get("/monitor/performance/summary?days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert data["days"] == 7
    assert data["total"] == 3
    metrics = data["metrics"]
    assert metrics["firstPageReady"]["count"] == 2
    assert metrics["firstPageReady"]["avg"] == 200.0
    assert metrics["firstPageReady"]["min"] == 100
    assert metrics["firstPageReady"]["max"] == 300
    assert metrics["pageReady:pages/readings/index"]["count"] == 1


def test_summary_respects_days_window(client):
    _insert_event("oldMetric", 1, 10)   # 10 天前 —— days=7 之外
    _insert_event("recentMetric", 1, 2)  # 2 天前

    resp = client.get("/monitor/performance/summary?days=7")
    data = resp.json()
    assert "oldMetric" not in data["metrics"]
    assert data["metrics"]["recentMetric"]["count"] == 1

    resp30 = client.get("/monitor/performance/summary?days=30")
    assert "oldMetric" in resp30.json()["metrics"]


def test_summary_defaults_to_7_days(client):
    resp = client.get("/monitor/performance/summary")
    assert resp.status_code == 200
    assert resp.json()["days"] == 7


# ---------------------------------------------------------------------------
# 30 天保留期清理
# ---------------------------------------------------------------------------

def test_retention_cleanup_removes_rows_older_than_30_days(client):
    _insert_event("ancient", 1, 31)  # 31 天前 —— 应被清理

    resp = client.post(
        "/performance",
        json={"metrics": [{"metric": "freshMetric", "durationMs": 5}]},
    )
    assert resp.status_code == 200

    rows = _fetch_rows()
    metrics = [r["metric"] for r in rows]
    assert "ancient" not in metrics
    assert "freshMetric" in metrics


def test_retention_keeps_rows_within_30_days(client):
    _insert_event("stillValid", 1, 29)  # 29 天前 —— 应保留

    client.post(
        "/performance",
        json={"metrics": [{"metric": "freshMetric", "durationMs": 5}]},
    )
    metrics = [r["metric"] for r in _fetch_rows()]
    assert "stillValid" in metrics
    assert "freshMetric" in metrics


# ---------------------------------------------------------------------------
# /metrics —— Prometheus 文本格式
# ---------------------------------------------------------------------------

def test_metrics_endpoint_returns_prometheus_text(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    body = resp.text
    assert "# HELP http_requests_total" in body
    assert "# HELP http_request_duration_seconds" in body
    assert "# HELP http_errors_total" in body


def test_metrics_error_counter_increments_on_4xx(client):
    client.get("/nonexistent-metrics-test-404")  # 404 -> http_errors_total
    body = client.get("/metrics").text
    assert 'http_errors_total{endpoint="/nonexistent-metrics-test-404",method="GET",status="404"} 1.0' in body
