from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import Counter, Histogram, generate_latest

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
