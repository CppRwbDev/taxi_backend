"""Yagona API xato shakli: {detail: str, code: str, ...qo'shimcha maydonlar}.

Hujjat: plan_and_docs/06_APISpec.md "Xato Kodlari".
Frontend `detail` (string) ga tayanadi — uni buzmaslik uchun code alohida qo'shiladi.
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


DEFAULT_CODES = {
    400: "VALIDATION_ERROR",
    401: "UNAUTHORIZED",
    402: "INSUFFICIENT_BALANCE",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "UNPROCESSABLE",
    429: "TOO_MANY_REQUESTS",
    500: "SERVER_ERROR",
}


class ApiError(StarletteHTTPException):
    """Kodli HTTP xato."""

    def __init__(self, status_code: int, detail: str, code: str | None = None, **extra):
        headers = extra.pop("headers", None)
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code or DEFAULT_CODES.get(status_code, "ERROR")
        self.extra = extra


def api_error(status_code: int, detail: str, code: str | None = None, **extra) -> ApiError:
    return ApiError(status_code, detail, code=code, **extra)


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error_handler(request: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "code": exc.code, **(exc.extra or {})},
            headers=exc.headers,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error_handler(request: Request, exc: StarletteHTTPException):
        detail = exc.detail
        if isinstance(detail, dict):
            body = dict(detail)
            code = body.pop("code", None) or DEFAULT_CODES.get(exc.status_code, "ERROR")
            return JSONResponse(status_code=exc.status_code, content={"detail": body, "code": code})
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": detail,
                "code": DEFAULT_CODES.get(exc.status_code, "ERROR"),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "detail": "So'rov ma'lumotlari noto'g'ri",
                "code": "UNPROCESSABLE",
                "errors": exc.errors(),
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"detail": "Server ichki xatosi", "code": "SERVER_ERROR"},
        )
