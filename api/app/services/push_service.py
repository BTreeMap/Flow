"""Single source of truth for the Web Push wire call.

Both the notification worker (production fan-out) and the admin push-test endpoint
send Web Push messages. They wrap this call with their own error handling, but the
``subscription_info`` shape, VAPID parameters, and timeout enforcement are shared and
live here so the on-the-wire contract cannot drift between callers.
"""

from __future__ import annotations

import asyncio

import pywebpush

from app import config

DEFAULT_PUSH_TIMEOUT_SECONDS = 10


async def send_webpush(
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    payload: str,
) -> None:
    """Send one Web Push message, blocking up to ``DEFAULT_PUSH_TIMEOUT_SECONDS``.

    Runs the synchronous ``pywebpush.webpush`` call in a thread. Raises
    ``TimeoutError`` on timeout and ``WebPushException`` on transport errors;
    callers are responsible for interpreting and recording those outcomes.

    ``pywebpush.webpush`` is resolved by attribute lookup at call time so tests
    can patch it via ``monkeypatch.setattr(pywebpush, "webpush", ...)``.
    """
    vapid_private_key = config.get_vapid_private_key()
    vapid_claims: dict[str, str | int] = {"sub": config.get_vapid_sub()}
    await asyncio.wait_for(
        asyncio.to_thread(
            pywebpush.webpush,
            subscription_info={
                "endpoint": endpoint,
                "keys": {"p256dh": p256dh, "auth": auth},
            },
            data=payload,
            vapid_private_key=vapid_private_key,
            vapid_claims=vapid_claims,
        ),
        timeout=DEFAULT_PUSH_TIMEOUT_SECONDS,
    )
