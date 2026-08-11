"""Rate limiter for API endpoints.

Key strategy (H4 fix):
- Authenticated requests (valid ``Authorization: Bearer`` JWT) are keyed by
  ``user:{user_id}`` — limits follow the account, not the IP.
- Unauthenticated requests are keyed by IP: the FIRST value of the
  ``X-Forwarded-For`` header when present (reverse-proxy deployments),
  otherwise ``request.client.host``.

Storage:
- Redis (``redis.asyncio``) is used when ``REDIS_URL`` is reachable —
  recommended for production, works across multiple workers/processes.
- Otherwise an in-process sliding-window dict with lazy time-based cleanup
  (single-process only; counters reset on restart). In multi-worker
  deployments you MUST run Redis or the effective limit is per-process.

Dev bypass:
- When ``ENABLE_DEV_LOGIN`` is true the limiter is bypassed entirely. This is
  a convenience for local development ONLY. Production must set
  ``ENABLE_DEV_LOGIN=false`` so rate limiting is active.
"""
import logging
import time
from collections import defaultdict

import redis.asyncio as aioredis
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)


class _MemoryStore:
    """In-process sliding-window store with lazy cleanup (bounded memory)."""

    def __init__(self) -> None:
        self._store: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, max_requests: int, window_seconds: int) -> bool:
        now = time.time()
        cutoff = now - window_seconds
        self._store[key] = [t for t in self._store[key] if t > cutoff]
        if len(self._store[key]) >= max_requests:
            return False
        self._store[key].append(now)
        return True

    def cleanup(self) -> None:
        """Drop keys idle for >10 minutes so the dict stays bounded."""
        cutoff = time.time() - 600
        stale = [
            key for key, hits in self._store.items()
            if not hits or hits[-1] < cutoff
        ]
        for key in stale:
            del self._store[key]


class _RedisStore:
    """Fixed-window counter in Redis: INCR + EXPIRE (atomic)."""

    def __init__(self, url: str) -> None:
        self._client = aioredis.from_url(
            url, socket_connect_timeout=1, socket_timeout=1
        )

    async def ping(self) -> bool:
        try:
            return bool(await self._client.ping())
        except Exception:
            return False

    async def check(self, key: str, max_requests: int, window_seconds: int) -> bool:
        try:
            pipe = self._client.pipeline()
            pipe.incr(key)
            pipe.expire(key, window_seconds)
            count, _ = await pipe.execute()
            return int(count) <= max_requests
        except Exception as exc:
            logger.warning("Redis rate-limit check failed: %s", exc)
            return True  # fail-open on transient Redis errors


class RateLimiter:
    """Rate limiter that picks Redis (preferred) or the in-process store."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self._memory = _MemoryStore()
        self._redis: _RedisStore | None = None
        self._redis_resolved = False

    async def is_allowed(self, key: str) -> bool:
        if not self._redis_resolved:
            self._redis_resolved = True
            if settings.REDIS_URL:
                candidate = _RedisStore(settings.REDIS_URL)
                if await candidate.ping():
                    self._redis = candidate
                else:
                    logger.warning(
                        "Redis unreachable at %s — rate limiting with in-process store",
                        settings.REDIS_URL,
                    )
        if self._redis is not None:
            return await self._redis.check(key, self.max_requests, self.window)
        self._memory.cleanup()
        return self._memory.check(key, self.max_requests, self.window)


_limiter = RateLimiter(
    max_requests=settings.RATE_LIMIT_MAX_REQUESTS,
    window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
)


def _request_key(request: Request) -> str:
    """Build the rate-limit key for a request (user id > client IP)."""
    # Authenticated requests are keyed by account so IP rotation / shared NAT
    # can't be used to bypass the limit. Invalid tokens fall through to IP.
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            from app.utils.auth import decode_token
            payload = decode_token(auth[7:])
            sub = payload.get("sub")
            if sub:
                return f"user:{sub}"
        except Exception:
            pass
    # Unauthenticated: first X-Forwarded-For value (closest to the client),
    # else the direct peer IP. NOTE: only trust this header behind a reverse
    # proxy that overwrites it (e.g. nginx `proxy_set_header`).
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return f"ip:{first}"
    host = request.client.host if request.client else "unknown"
    return f"ip:{host}"


# ── Per-endpoint stricter limiter ───────────────────────────────────────
# The global middleware caps everything at 60 req/min, but public
# unauthenticated endpoints that confirm existence by guessable input get a
# tighter window to slow offline enumeration. /share/card-info confirms an
# account exists by invite code (STAR-XXXX, small search space) → 30/min.
_card_info_limiter = RateLimiter(max_requests=30, window_seconds=60)


async def card_info_rate_limit(request: Request) -> None:
    """FastAPI dependency: 30 req/min per client for GET /share/card-info.

    Keys by user id for authenticated requests, else client IP (same
    ``_request_key`` strategy as the global middleware; Redis when available,
    in-process sliding window otherwise).
    """
    key = f"card_info:{_request_key(request)}"
    if not await _card_info_limiter.is_allowed(key):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")


# ── /meet/public/{meet_id} 独立限流（T2-3）───────────────────────────────
# 仿 card_info_rate_limit：公开接口按可枚举输入（meet_id）确认记录存在 →
# 独立 30 次/分/IP 限流，在全局 60/分中间件之上进一步压低离线枚举。
_meet_info_limiter = RateLimiter(max_requests=30, window_seconds=60)


async def meet_info_rate_limit(request: Request) -> None:
    """FastAPI dependency: 30 req/min per client for GET /meet/public/{meet_id}.

    与 card_info_rate_limit 同策略（鉴权按 user、未鉴权按 IP；Redis 可用时
    用 Redis，否则进程内滑动窗口）；key 前缀 meet_info:。
    """
    key = f"meet_info:{_request_key(request)}"
    if not await _meet_info_limiter.is_allowed(key):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")


async def rate_limit_middleware(request: Request, call_next):
    """FastAPI middleware: reject clients exceeding 60 requests/min.

    Only ``/auth/dev-login`` is exempted (it is protected by the shared
    ``X-Dev-Key`` secret and is low-frequency), so rate limiting stays active
    for every other endpoint even with ``ENABLE_DEV_LOGIN=true``.
    """
    if request.url.path.rstrip("/") == "/auth/dev-login":
        return await call_next(request)

    key = _request_key(request)
    if not await _limiter.is_allowed(key):
        # NOTE: middleware raises don't go through FastAPI's exception
        # handlers, so return the 429 response directly instead of raising.
        return JSONResponse(
            status_code=429,
            content={"detail": "请求过于频繁，请稍后再试"},
        )
    return await call_next(request)
