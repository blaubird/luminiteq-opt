import logging
import json
import time
import traceback
from typing import Dict, Any, Optional, Callable, Awaitable

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from contextvars import ContextVar

# -----------------------------------------------------------------------------
# Context variable: хранит метаданные текущего запроса (безопасно для async)
# -----------------------------------------------------------------------------
request_context: ContextVar[Dict[str, Any]] = ContextVar("request_context", default={})


# -----------------------------------------------------------------------------
# Structured JSON logger (stdout‑friendly для Railway / Grafana Loki)
# -----------------------------------------------------------------------------
class StructuredLogger:
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def _log(self, level: int, msg: str, extra: Optional[Dict[str, Any]] = None, exc_info=None):
        ctx = request_context.get()
        payload: Dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "level": logging.getLevelName(level),
            "message": msg,
        }
        if ctx:
            payload.update(ctx)
        if extra:
            payload.update(extra)
        if exc_info:
            payload["exception"] = {
                "type": exc_info.__class__.__name__,
                "message": str(exc_info),
                "traceback": traceback.format_exc(),
            }
        self.logger.log(level, json.dumps(payload))

    # convenience wrappers
    def debug(self, msg: str, **kw):
        self._log(logging.DEBUG, msg, **kw)

    def info(self, msg: str, **kw):
        self._log(logging.INFO, msg, **kw)

    def warning(self, msg: str, **kw):
        self._log(logging.WARNING, msg, **kw)

    def error(self, msg: str, **kw):
        self._log(logging.ERROR, msg, **kw)

    def critical(self, msg: str, **kw):
        self._log(logging.CRITICAL, msg, **kw)


def get_logger(name: str) -> StructuredLogger:
    return StructuredLogger(name)


# -----------------------------------------------------------------------------
# Middleware: добавляет контекст запроса и логирует время ответа
# Исправлено двойное reset()  → RuntimeError more
# -----------------------------------------------------------------------------
class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:  # type: ignore[override]
        request_id = f"{int(time.time() * 1000)}-{id(request)}"
        ctx = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "client_ip": request.client.host if request.client else None,
        }
        token = request_context.set(ctx)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            ctx["status_code"] = response.status_code
            ctx["process_time_ms"] = duration_ms
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception as exc:
            logger = get_logger("middleware")
            logger.error("Unhandled exception in request", exc_info=exc)
            raise
        finally:
            # Сбрасываем контекст один раз; защищаемся от повторного вызова.
            try:
                request_context.reset(token)
            except RuntimeError:
                pass


# -----------------------------------------------------------------------------
# Global exception handler → JSON + лог
# -----------------------------------------------------------------------------
class GlobalExceptionHandler:
    def __init__(self, app: FastAPI):
        @app.exception_handler(Exception)  # noqa: ANN401
        async def handle_exception(request: Request, exc: Exception):  # type: ignore[override]
            logger = get_logger("exception_handler")
            logger.error("Unhandled exception", exc_info=exc)
            from fastapi.responses import JSONResponse
            from fastapi import status

            status_code = getattr(exc, "status_code", status.HTTP_500_INTERNAL_SERVER_ERROR)
            return JSONResponse(
                status_code=status_code,
                content={
                    "error": exc.__class__.__name__,
                    "detail": str(exc),
                    "request_id": request_context.get().get("request_id", "unknown"),
                },
            )


# -----------------------------------------------------------------------------
# Helper called from main.py
# -----------------------------------------------------------------------------

def setup_logging(app: FastAPI):
    app.add_middleware(RequestContextMiddleware)
    GlobalExceptionHandler(app)
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[logging.StreamHandler()])
    return get_logger
