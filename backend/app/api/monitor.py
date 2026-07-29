from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import Counter, Histogram, generate_latest
import logging

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
AI_CALLS = Counter(
    "ai_calls_total",
    "Total AI API calls",
    ["model", "status"],
)
PAYMENT_SUCCESS = Counter(
    "payment_success_total",
    "Successful payments",
)


@router.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type="text/plain")


@router.post("/performance")
async def log_performance(data: dict):
    """Receive frontend performance metrics (non-critical, fire-and-forget)."""
    # Log performance data for future analysis — no persistence yet
    page = data.get("page", "unknown")
    metric = data.get("metric", "")
    value = data.get("value", 0)
    logger.info("perf|%s|%s|%s", page, metric, value)
    return {"ok": True}
