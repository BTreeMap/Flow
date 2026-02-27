"""Test LoggingMiddleware functionality."""

import logging

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from starlette.testclient import TestClient

from app.middleware_logging import LoggingMiddleware


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
