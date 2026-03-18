import logging
import time
from typing import Callable
from fastapi import Request, Response
from app.config import settings

logger = logging.getLogger("api")


class LoggingMiddleware:
    """
    Har bir HTTP so'rovni log qiluvchi middleware.
    Format: [METHOD] /path → STATUS | Xms | user_id=X
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        start_time = time.perf_counter()

        # Response status ni olish uchun intercept
        status_code = 500
        original_send = send

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await original_send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)
            logger.info(
                "%s %s → %s | %sms",
                request.method,
                request.url.path,
                status_code,
                elapsed_ms,
            )
