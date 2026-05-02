"""Structured-ish logging: correlation + ingest trace id from contextvars on every record."""

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
trace_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "trace_id", default=None
)

_configured = False


def get_correlation_id() -> str | None:
    return correlation_id_ctx.get()


def bind_correlation_id(cid: str | None) -> contextvars.Token[str | None]:
    return correlation_id_ctx.set(cid)


def reset_correlation_id(token: contextvars.Token[str | None]) -> None:
    correlation_id_ctx.reset(token)


def get_trace_id() -> str | None:
    return trace_id_ctx.get()


def bind_trace_id(tid: str | None) -> contextvars.Token[str | None]:
    return trace_id_ctx.set(tid)


def reset_trace_id(token: contextvars.Token[str | None]) -> None:
    trace_id_ctx.reset(token)


def ensure_correlation_id() -> str:
    cid = get_correlation_id()
    if cid:
        return cid
    n = str(uuid.uuid4())
    bind_correlation_id(n)
    return n


class RequestContextFilter(logging.Filter):
    """Sets correlation_id and trace_id for the log formatter (defaults \"-\" when unset)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "correlation_id"):
            record.correlation_id = get_correlation_id() or "-"
        if not hasattr(record, "trace_id"):
            record.trace_id = get_trace_id() or "-"
        return True


# Backwards compatibility
CorrelationIdFilter = RequestContextFilter


_LOG_FMT = (
    "%(levelname)s %(name)s "
    "[correlation_id=%(correlation_id)s trace_id=%(trace_id)s] %(message)s"
)


def configure_logging(level: int = logging.INFO) -> None:
    global _configured
    if _configured:
        return
    _configured = True
    root = logging.getLogger()
    root.setLevel(level)
    if not root.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter(_LOG_FMT))
        h.addFilter(RequestContextFilter())
        root.addHandler(h)
    else:
        # Uvicorn (or other hosts) already attached root handlers; do not replace their formatters.
        # Route `ais.*` through a single handler with correlation + trace in the line.
        ais = logging.getLogger("ais")
        if not ais.handlers:
            h = logging.StreamHandler()
            h.setFormatter(logging.Formatter(_LOG_FMT))
            h.addFilter(RequestContextFilter())
            ais.addHandler(h)
            ais.propagate = False


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
