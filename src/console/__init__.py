"""Static review console (src/console/static) and security headers.

The console is plain HTML/JS served from this application, so it can use a strict Content-Security-Policy:
no inline scripts or styles, no third-party origins. API keys stay in the browser tab's sessionStorage.
"""

from __future__ import annotations

import pathlib
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = pathlib.Path(__file__).with_name("static")
CONSOLE_CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; "
    "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)


async def security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    if request.url.path.startswith("/console"):
        response.headers["Content-Security-Policy"] = CONSOLE_CSP
        response.headers["Cache-Control"] = "no-store"
    return response


def mount_console(app: FastAPI) -> None:
    app.mount("/console/static", StaticFiles(directory=STATIC_DIR), name="console-static")

    @app.get("/console", include_in_schema=False)
    def console() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html")
