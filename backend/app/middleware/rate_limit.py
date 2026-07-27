"""In-memory rate limiter for API endpoints."""
import time
from collections import defaultdict

from fastapi import HTTPException, Request

from app.config import settings


class RateLimiter:
    """Sliding-window rate limiter keyed by client IP."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self._store: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        cutoff = now - self.window
        self._store[key] = [t for t in self._store[key] if t > cutoff]
        if len(self._store[key]) >= self.max_requests:
            return False
        self._store[key].append(now)
        return True


_limiter = RateLimiter(max_requests=60, window_seconds=60)  # 60 req/min


async def rate_limit_middleware(request: Request, call_next):
    """FastAPI middleware: reject clients exceeding 60 requests/min.

    Rate limiting is bypassed when ENABLE_DEV_LOGIN is true
    (local development / test environments).
    """
    if settings.ENABLE_DEV_LOGIN:
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    if not _limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
    return await call_next(request)
