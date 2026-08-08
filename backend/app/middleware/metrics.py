import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.monitor import HTTP_REQUESTS, HTTP_LATENCY, HTTP_ERRORS


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware that counts HTTP requests and tracks latency for every request."""

    async def dispatch(self, request: Request, call_next):
        method = request.method
        path = request.url.path

        start = time.time()
        response = await call_next(request)
        duration = time.time() - start

        status = str(response.status_code)
        HTTP_REQUESTS.labels(method=method, endpoint=path, status=status).inc()
        if response.status_code >= 400:
            HTTP_ERRORS.labels(method=method, endpoint=path, status=status).inc()
        HTTP_LATENCY.observe(duration)

        return response
