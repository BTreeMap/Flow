"""Application entry point."""

import asyncio
import contextlib
import json
from datetime import UTC, datetime

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.middleware import add_csp_middleware
from h4ckath0n import create_app
from h4ckath0n.realtime import (
    AuthError,
    authenticate_sse_request,
    authenticate_websocket,
    sse_response,
)

app = create_app()
add_csp_middleware(app)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Readiness check for E2E and deployment probes."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Demo endpoints – prove that user-defined routes appear in the OpenAPI spec
# and can be consumed by the generated TypeScript client.
# ---------------------------------------------------------------------------


class PingResponse(BaseModel):
    ok: bool


class EchoRequest(BaseModel):
    message: str


class EchoResponse(BaseModel):
    message: str
    reversed: str


@app.get("/demo/ping", tags=["demo"])
def demo_ping() -> PingResponse:
    """Simple liveness ping for the demo namespace."""
    return PingResponse(ok=True)


@app.post("/demo/echo", tags=["demo"])
def demo_echo(body: EchoRequest) -> EchoResponse:
    """Echo back the message along with its reverse."""
    return EchoResponse(message=body.message, reversed=body.message[::-1])


# ---------------------------------------------------------------------------
# Demo: Authenticated WebSocket  (/demo/ws)
# ---------------------------------------------------------------------------


@app.websocket("/demo/ws")
async def demo_websocket(websocket: WebSocket) -> None:
    """Authenticated WebSocket demo with heartbeat and echo.

    Auth: ``?token=<device_jwt>`` with ``aud = h4ckath0n:ws``.
    """
    try:
        ctx = await authenticate_websocket(websocket)
    except AuthError:
        # Must accept before we can send a proper close frame with code 1008
        await websocket.accept()
        await websocket.close(code=1008, reason="auth_failed")
        return

    await websocket.accept()

    # Send welcome
    now = datetime.now(UTC).isoformat()
    await websocket.send_json(
        {"type": "welcome", "user_id": ctx.user_id, "device_id": ctx.device_id, "server_time": now}
    )

    # Heartbeat task
    async def heartbeat() -> None:
        n = 0
        try:
            while True:
                await asyncio.sleep(2)
                n += 1
                await websocket.send_json(
                    {"type": "heartbeat", "n": n, "server_time": datetime.now(UTC).isoformat()}
                )
        except (WebSocketDisconnect, RuntimeError):
            pass

    hb_task = asyncio.create_task(heartbeat())

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if "message" in msg:
                text = str(msg["message"])
                await websocket.send_json(
                    {
                        "type": "echo",
                        "message": text,
                        "reversed": text[::-1],
                        "server_time": datetime.now(UTC).isoformat(),
                    }
                )
    except WebSocketDisconnect:
        pass
    finally:
        hb_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await hb_task


# ---------------------------------------------------------------------------
# Demo: Authenticated SSE  (GET /demo/sse)
# ---------------------------------------------------------------------------


class SSEChunk(BaseModel):
    """Schema for SSE chunk data (for OpenAPI docs)."""

    i: int
    text: str
    server_time: str


class SSEDone(BaseModel):
    """Schema for SSE done event (for OpenAPI docs)."""

    ok: bool


@app.get("/demo/sse", tags=["demo"])
async def demo_sse(request: Request):  # type: ignore[no-untyped-def]
    """Authenticated SSE stream that simulates LLM-style output chunks.

    Auth: ``Authorization: Bearer <device_jwt>`` with ``aud = h4ckath0n:sse``.
    """
    try:
        ctx = authenticate_sse_request(request)
    except AuthError as exc:
        return JSONResponse({"detail": exc.detail}, status_code=401)

    chunks = [
        "Hello ",
        f"user {ctx.user_id[:8]}… ",
        "This is ",
        "a simulated ",
        "LLM stream. ",
        "Enjoy!",
    ]

    async def generate():  # type: ignore[no-untyped-def]
        for i, text in enumerate(chunks):
            if await request.is_disconnected():
                return
            yield {
                "event": "chunk",
                "data": json.dumps(
                    {"i": i, "text": text, "server_time": datetime.now(UTC).isoformat()}
                ),
            }
            await asyncio.sleep(0.15)
        yield {
            "event": "done",
            "data": json.dumps({"ok": True}),
        }

    return sse_response(generate())
