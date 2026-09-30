"""Middleware for logging HTTP requests and responses."""

import json
import logging
import time
import uuid
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.logging_conf import request_id_var

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"

# Inbound headers that already identify this request, most trusted first. A
# Cloudflare ray id is preferred over a fresh uuid because it is the one
# identifier the *browser* can also see: a user reporting a failure can quote
# the id from their network tab and it will match a log line here. Without that
# shared handle, correlating a reported error to a server log means guessing
# from timestamps.
_INBOUND_ID_HEADERS = ("x-request-id", "cf-ray")


def _resolve_request_id(request: Request) -> str:
    for header in _INBOUND_ID_HEADERS:
        value = request.headers.get(header)
        if value:
            return value[:64]
    return uuid.uuid4().hex[:16]


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log request and response details."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Log request details, execute request, and log response details."""
        start_time = time.perf_counter()

        request_id = _resolve_request_id(request)
        token = request_id_var.set(request_id)

        # Capture request details
        method = request.method
        url = str(request.url)
        client_ip = request.client.host if request.client else "unknown"

        logger.info(f"Incoming request: {method} {url} from {client_ip}")

        if logger.isEnabledFor(logging.DEBUG):
            # Log headers
            headers = dict(request.headers)
            # Redact sensitive headers
            for key in ["authorization", "cookie", "x-api-key"]:
                if key in headers:
                    headers[key] = "***REDACTED***"
            logger.debug(f"Request headers: {json.dumps(headers)}")

            # Log body (with size limit and redaction)
            try:
                # Read body
                body = await request.body()
                if len(body) > 100 * 1024:  # 100KB limit
                    logger.debug("Request body: (too large to log)")
                elif len(body) > 0:
                    try:
                        # Try to parse as JSON for redaction
                        body_json = json.loads(body)
                        if isinstance(body_json, dict):
                            # Redact sensitive fields
                            for key in ["password", "token", "secret", "key"]:
                                if key in body_json:
                                    body_json[key] = "***REDACTED***"
                        logger.debug(f"Request body: {json.dumps(body_json)}")
                    except json.JSONDecodeError:
                        # Log as string if possible
                        try:
                            logger.debug(f"Request body: {body.decode('utf-8')}")
                        except UnicodeDecodeError:
                            logger.debug("Request body: (binary data)")
            except Exception as e:
                logger.debug(f"Failed to log request body: {e}")

        # Execute request
        try:
            response = await call_next(request)
        except Exception as e:
            duration = (time.perf_counter() - start_time) * 1000
            logger.error(f"Request failed: {method} {url} - {e} ({duration:.2f}ms)")
            request_id_var.reset(token)
            raise

        duration = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"Request completed: {method} {url} - {response.status_code} ({duration:.2f}ms)"
        )

        if logger.isEnabledFor(logging.DEBUG):
            # Log response headers
            headers = dict(response.headers)
            logger.debug(f"Response headers: {json.dumps(headers)}")

            # Log response body (if not streaming/large)
            content_type = response.headers.get("content-type", "")
            if (
                "text/event-stream" not in content_type
                and "application/octet-stream" not in content_type
                and "video/" not in content_type
                and "audio/" not in content_type
            ):
                # Only log body for non-streaming responses
                try:
                    # Capture response body
                    body_chunks = [chunk async for chunk in response.body_iterator]

                    body = b"".join(body_chunks)

                    # Reconstruct response for client
                    new_response = Response(
                        content=body,
                        status_code=response.status_code,
                        headers=dict(response.headers),
                        media_type=response.media_type,
                    )
                    # Preserve background tasks
                    new_response.background = response.background
                    response = new_response

                    if len(body) > 100 * 1024:  # 100KB limit
                        logger.debug("Response body: (too large to log)")
                    elif len(body) > 0:
                        try:
                            body_json = json.loads(body)
                            # Simple redaction for response too if needed
                            if isinstance(body_json, dict):
                                for key in ["token", "secret"]:
                                    if key in body_json:
                                        body_json[key] = "***REDACTED***"
                            logger.debug(f"Response body: {json.dumps(body_json)}")
                        except json.JSONDecodeError:
                            try:
                                logger.debug(f"Response body: {body.decode('utf-8')}")
                            except UnicodeDecodeError:
                                logger.debug("Response body: (binary data)")
                except Exception as e:
                    logger.debug(f"Failed to log response body: {e}")
            else:
                logger.debug("Response body: (streaming/binary - omitted)")

        # Echo the id so a client (or a bug report) can name the exact request.
        response.headers[REQUEST_ID_HEADER] = request_id
        request_id_var.reset(token)
        return response
