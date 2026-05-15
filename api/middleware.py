"""
API Middleware — AEGIS-IMINT
Rate limiting and request logging.
"""
import time
import logging
from collections import defaultdict, deque
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("aegis.api")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiter: max N requests per window (per client IP).

    Uses a sliding-window approach: timestamps of recent requests are stored in
    a deque per client IP.  Entries older than *window_seconds* are evicted on
    each new request.  Thread-safety is best-effort for async single-process
    deployments; for multi-worker setups use a shared Redis backend instead.
    """

    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window = window_seconds
        self._buckets: dict = defaultdict(deque)

    def _client_ip(self, request: Request) -> str:
        """Extract client IP, respecting X-Forwarded-For if present."""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next) -> Response:
        client_ip = self._client_ip(request)
        now = time.time()
        bucket = self._buckets[client_ip]

        # Evict timestamps outside the current window
        while bucket and bucket[0] < now - self.window:
            bucket.popleft()

        if len(bucket) >= self.max_requests:
            logger.warning(
                "Rate limit exceeded for %s (%d/%d requests in %ds window)",
                client_ip, len(bucket), self.max_requests, self.window,
            )
            return Response(
                content='{"detail":"Rate limit exceeded. Try again later."}',
                status_code=429,
                media_type="application/json",
                headers={
                    "Retry-After": str(self.window),
                    "X-RateLimit-Limit": str(self.max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Window": str(self.window),
                },
            )

        bucket.append(now)
        remaining = self.max_requests - len(bucket)

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        # Attach rate-limit info headers to every successful response
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Window"] = str(self.window)

        logger.info(
            "%s %s %d %.1fms [%s] remaining=%d",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            client_ip,
            remaining,
        )
        return response
