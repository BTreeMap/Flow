"""Test LoggingMiddleware functionality."""

import io
import logging

from app.middleware_logging import LoggingMiddleware
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from starlette.testclient import TestClient


def test_logging_middleware(caplog):
    """Test that requests and responses are logged."""
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    @app.post("/test")
    def test_endpoint(body: dict):
        return {"message": "success", "echo": body}

    client = TestClient(app)

    # Enable DEBUG logging for the middleware logger
    caplog.set_level(logging.DEBUG, logger="app.middleware_logging")

    # Test normal request
    body = {"key": "value", "secret": "hidden"}
    response = client.post("/test", json=body)

    assert response.status_code == 200
    assert response.json() == {"message": "success", "echo": body}

    # Verify logs
    logs = [r.message for r in caplog.records]

    # Check incoming request log
    assert any("Incoming request: POST" in msg for msg in logs)

    # Check request body log and redaction
    req_body_logs = [msg for msg in logs if "Request body:" in msg]
    assert req_body_logs
    assert "***REDACTED***" in req_body_logs[0]
    assert "hidden" not in req_body_logs[0]

    # Check response body log
    resp_body_logs = [msg for msg in logs if "Response body:" in msg]
    assert resp_body_logs
    assert "success" in resp_body_logs[0]


def test_logging_middleware_streaming(caplog):
    """Test that streaming responses are handled correctly (not buffered/logged)."""
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    @app.get("/stream")
    def stream_endpoint():
        def iter_content():
            yield b"data: hello\n\n"
            yield b"data: world\n\n"

        return StreamingResponse(iter_content(), media_type="text/event-stream")

    client = TestClient(app)
    caplog.set_level(logging.DEBUG, logger="app.middleware_logging")

    response = client.get("/stream")
    assert response.status_code == 200

    # Consume content to trigger middleware completion
    content = response.content
    assert content == b"data: hello\n\ndata: world\n\n"

    logs = [r.message for r in caplog.records]

    # Check request completed log
    assert any("Request completed: GET" in msg for msg in logs)

    # Check streaming body omission
    assert any("Response body: (streaming/binary - omitted)" in msg for msg in logs)


def test_logging_middleware_large_body(caplog):
    """Test handling of large bodies."""
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    @app.post("/large")
    def large_endpoint(request: dict):
        return {"size": len(str(request))}

    client = TestClient(app)
    caplog.set_level(logging.DEBUG, logger="app.middleware_logging")

    # Create body larger than 100KB
    large_data = {"data": "x" * (100 * 1024 + 1)}
    response = client.post("/large", json=large_data)

    assert response.status_code == 200

    logs = [r.message for r in caplog.records]

    # Check request body too large log
    assert any("Request body: (too large to log)" in msg for msg in logs)


def _echo_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    @app.get("/ping")
    def ping():
        logging.getLogger("app.test_handler").info("handler ran")
        return {"ok": True}

    return app


def test_request_id_is_generated_and_echoed():
    """Without a correlation id, a reported failure can only be found by guessing."""
    response = TestClient(_echo_app()).get("/ping")

    assert response.status_code == 200
    request_id = response.headers.get("X-Request-ID")
    assert request_id


def test_cloudflare_ray_is_adopted_as_the_request_id():
    """The ray id is the one handle the browser can also see, so prefer it."""
    response = TestClient(_echo_app()).get("/ping", headers={"cf-ray": "a25f6490-YYZ"})

    assert response.headers["X-Request-ID"] == "a25f6490-YYZ"


def test_explicit_request_id_wins_over_the_ray():
    response = TestClient(_echo_app()).get(
        "/ping", headers={"cf-ray": "a25f6490-YYZ", "x-request-id": "caller-supplied"}
    )

    assert response.headers["X-Request-ID"] == "caller-supplied"


def test_handler_logs_carry_the_request_id():
    """The point of the id: a line logged deep inside the request is greppable.

    Exercised through a real handler rather than by calling the filter after the
    fact, because the id is stamped at emit time — from inside the request's
    context — and is already reset by the time the response is returned.
    """
    from app.logging_conf import LOG_FORMAT, RequestIdFilter

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.addHandler(handler)
    previous_level = root.level
    root.setLevel(logging.INFO)
    try:
        TestClient(_echo_app()).get("/ping", headers={"cf-ray": "ray-for-grep"})
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)

    lines = [line for line in stream.getvalue().splitlines() if "handler ran" in line]
    assert lines, "the handler's own log line was never emitted"
    assert all("[ray-for-grep]" in line for line in lines)
