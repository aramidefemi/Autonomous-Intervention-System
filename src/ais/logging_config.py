"""Structured-ish logging: correlation id from contextvars on every log record."""

from __future__ import annotations

import contextvars
import logging
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_CallNext = Callable[[Request], Awaitable[Response]]

correlation_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)

_configured = False


def get_correlation_id() -> str | None:
    return correlation_id_ctx.get()


def bind_correlation_id(cid: str | None) -> contextvars.Token[str | None]:
    return correlation_id_ctx.set(cid)


def reset_correlation_id(token: contextvars.Token[str | None]) -> None:
    correlation_id_ctx.reset(token)


def ensure_correlation_id() -> str:
    cid = get_correlation_id()
    if cid:
        return cid
    n = str(uuid.uuid4())
    bind_correlation_id(n)
    return n


class CorrelationIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "correlation_id"):
            record.correlation_id = get_correlation_id() or "-"
        return True


def configure_logging(level: int = logging.INFO) -> None:
    global _configured
    if _configured:
        return
    _configured = True
    root = logging.getLogger()
    root.setLevel(level)
    if not root.handlers:
        h = logging.StreamHandler()
        fmt = logging.Formatter(
            "%(levelname)s %(name)s [correlation_id=%(correlation_id)s] %(message)s"
        )
        h.setFormatter(fmt)
        h.addFilter(CorrelationIdFilter())
        root.addHandler(h)
    else:
        for h in root.handlers:
            if not any(isinstance(f, CorrelationIdFilter) for f in h.filters):
                h.addFilter(CorrelationIdFilter())


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach X-Correlation-ID (from client or generated) to request scope and response."""

    async def dispatch(self, request: Request, call_next: _CallNext) -> Response:
        hdr = (
            request.headers.get("x-correlation-id")
            or request.headers.get("x-request-id")
            or str(uuid.uuid4())
        )
        token = bind_correlation_id(hdr)
        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = hdr
            return response
        finally:
            reset_correlation_id(token)
