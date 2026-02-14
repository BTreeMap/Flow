"""Security middleware: CSP headers and device JWT verification."""

from __future__ import annotations

import os

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

ENV_VAR = "H4CKATH0N_ENV"


def add_csp_middleware(app: FastAPI) -> None:
    """Add Content-Security-Policy middleware to the FastAPI app."""
    app.add_middleware(CSPMiddleware)


class CSPMiddleware(BaseHTTPMiddleware):
    """Set Content-Security-Policy headers based on environment."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        env = os.getenv(ENV_VAR, "development")
        if env == "production":
            csp = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self'; "
                "img-src 'self' data:; "
                "font-src 'self'; "
                "connect-src 'self' wss:; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'"
            )
        else:
            # Development: allow Vite dev server
            csp = (
                "default-src 'self' http://localhost:*; "
                "script-src 'self' http://localhost:*; "
                "style-src 'self' 'unsafe-inline' http://localhost:*; "
                "img-src 'self' data: http://localhost:*; "
                "font-src 'self' http://localhost:*; "
                "connect-src 'self' http://localhost:* ws://localhost:*; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'"
            )
        response.headers["Content-Security-Policy"] = csp
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
