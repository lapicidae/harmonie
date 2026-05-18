"""FastAPI app factory + lifespan management."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from ..analyzer import Analyzer, scheduler_loop
from ..config import Settings, get_settings
from .routes import api_router, public_router

logger = logging.getLogger("harmonie.api")
access_logger = logging.getLogger("harmonie.api.requests")


# Paths logged at DEBUG instead of INFO. Liveness probes hit /health
# constantly.
_QUIET_PATHS = frozenset({"/health"})

# Methods whose body is worth logging at DEBUG. GET/HEAD/OPTIONS/DELETE
# may technically carry bodies but rarely do in practice.
_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})

# Cap how much of the body lands in the log line. Keeps a paste-bombed
# request from filling the journal.
_BODY_LOG_LIMIT_BYTES = 8 * 1024


def _format_body(body: bytes) -> str:
    """Best-effort, single-line debug rendering of a request body.

    Truncates to :data:`_BODY_LOG_LIMIT_BYTES`. JSON bodies are
    re-serialised compactly so they fit on one log line; non-UTF-8
    bodies show up as ``<N bytes binary>``.
    """
    if not body:
        return "(empty)"
    truncated = len(body) > _BODY_LOG_LIMIT_BYTES
    payload = body[:_BODY_LOG_LIMIT_BYTES]
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return f"<{len(body)} bytes binary>"
    with suppress(json.JSONDecodeError):
        text = json.dumps(json.loads(text), separators=(",", ":"), ensure_ascii=False)
    if truncated:
        return f"{text}... (truncated, {len(body)} total bytes)"
    return text


async def _log_requests(request: Request, call_next):
    """Log one line per HTTP request through the ``harmonie.api.requests``
    logger.

    Format: ``<client> <method> <path>[?<query>] -> <status> (<ms>ms)``.
    Logs even when the handler raises, with ``status=500`` as the
    fallback. For POST/PUT/PATCH at DEBUG level, the request body is
    logged on a follow-up line (``<- body: ...``); the body is otherwise
    not read so there's no overhead at higher log levels.
    """
    start = time.monotonic()
    status: int = 500

    # Read the body up front only when we'd actually log it. Reading
    # consumes the ASGI receive stream, so we patch request._receive to
    # replay the bytes for the downstream handler.
    body_for_log: bytes | None = None
    if (
        request.method in _BODY_METHODS
        and request.url.path not in _QUIET_PATHS
        and access_logger.isEnabledFor(logging.DEBUG)
    ):
        body_for_log = await request.body()

        async def _replay_receive():
            return {"type": "http.request", "body": body_for_log, "more_body": False}

        request._receive = _replay_receive  # type: ignore[attr-defined]

    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        duration_ms = (time.monotonic() - start) * 1000
        client = request.client.host if request.client else "-"
        path = request.url.path
        if request.url.query:
            path = f"{path}?{request.url.query}"
        level = logging.DEBUG if request.url.path in _QUIET_PATHS else logging.INFO
        access_logger.log(
            level,
            "%s %s %s -> %d (%.1fms)",
            client,
            request.method,
            path,
            status,
            duration_ms,
        )
        if body_for_log is not None:
            access_logger.debug("  <- body: %s", _format_body(body_for_log))


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        analyzer = Analyzer(settings)
        # Worker pool is created on demand at the start of the first scan
        # to avoid the multi-second TF model load at app startup.
        app.state.analyzer = analyzer
        app.state.settings = settings

        scheduler_task: asyncio.Task | None = None
        if settings.libraries:
            scheduler_task = asyncio.create_task(
                scheduler_loop(analyzer, settings),
                name="harmonie.scheduler",
            )
        else:
            logger.warning(
                "no libraries configured (HARMONIE_LIBRARIES) — scheduler not started"
            )

        try:
            yield
        finally:
            if scheduler_task is not None:
                scheduler_task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await scheduler_task
            # request_cancel signals workers and terminates the pool;
            # close drains the (terminated) pool and closes the DB. Both
            # are potentially slow so they run off the event loop —
            # otherwise uvicorn's signal handler can't respond to a
            # second Ctrl-C.
            analyzer.request_cancel()
            await asyncio.to_thread(analyzer.stop)

    app = FastAPI(
        title="harmonie",
        version="0.1.0",
        description="Audio similarity service.",
        lifespan=lifespan,
    )

    app.middleware("http")(_log_requests)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(public_router)
    app.include_router(api_router, prefix="/api/v1")

    return app
