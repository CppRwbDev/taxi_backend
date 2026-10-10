"""Oddiy in-memory sliding-window rate limiter (qo'shimcha kutubxonasiz).

Talab: plan_and_docs/02_Architecture.md (Xavfsizlik bo'limi).
Bir process ichida ishlaydi; ko'p worker'li deploy uchun keyingi bosqichda
Redis/Cloudflare bilan almashtirish tavsiya etiladi.
"""
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._hits: dict[str, deque] = defaultdict(deque)

    def _allowed(self, key: str, limit: int, window: int = 60) -> bool:
        now = time.monotonic()
        q = self._hits[key]
        while q and q[0] <= now - window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True

    async def dispatch(self, request: Request, call_next):
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)

        client = request.client.host if request.client else "unknown"
        is_auth = path.startswith("/api/v1/auth")
        limit = settings.RATE_LIMIT_AUTH_PER_MINUTE if is_auth else settings.RATE_LIMIT_PER_MINUTE
        key = f"{client}:{'auth' if is_auth else 'api'}"

        if not self._allowed(key, limit):
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Juda ko'p so'rov. 1 daqiqa kutib qayta urinib ko'ring.",
                    "code": "TOO_MANY_REQUESTS",
                    "retry_after": 60,
                },
            )
        return await call_next(request)
