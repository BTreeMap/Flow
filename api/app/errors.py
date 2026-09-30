"""The one place an HTTP failure status is decided.

The rule: a failure the caller can see and act on is 4xx; a failure in
infrastructure we control is 5xx. The 4xx choice is load-bearing — Cloudflare
replaces origin 5xx bodies with its own error page, stripping ``detail``, so a
5xx is a reason the client never receives.

Call sites name *what went wrong* and the status is derived, which makes
"business logic returning 5xx" unrepresentable rather than a review catch.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import assert_never

from fastapi import HTTPException


class Fault(Enum):
    """Closed set of ways a request can fail; caller-visible first, ours last."""

    UNAUTHENTICATED = auto()
    FORBIDDEN = auto()
    NOT_FOUND = auto()
    CONFLICT = auto()
    MALFORMED = auto()
    """Request refused as a whole — an invalid code, a nonsensical count."""

    UNPROCESSABLE = auto()
    """Well-formed, but a field's value is unacceptable."""

    UPSTREAM_UNAVAILABLE = auto()
    """A dependency we do not control failed. Caller-visible: we cannot fix it
    for them, and a 4xx is what survives the CDN with its detail intact."""

    INTERNAL = auto()
    """Ours to fix. Also the honest answer for an unexpected exception."""

    @property
    def is_caller_visible(self) -> bool:
        return self is not Fault.INTERNAL


def http_status(fault: Fault) -> int:
    """Total map from fault to status; ``assert_never`` makes a missing variant
    a type error rather than a request-time fallthrough."""
    match fault:
        case Fault.UNAUTHENTICATED:
            return 401
        case Fault.FORBIDDEN:
            return 403
        case Fault.NOT_FOUND:
            return 404
        case Fault.CONFLICT:
            return 409
        case Fault.MALFORMED:
            return 400
        case Fault.UNPROCESSABLE:
            return 422
        case Fault.UPSTREAM_UNAVAILABLE:
            # 424: this request failed because something it depends on did.
            return 424
        case Fault.INTERNAL:
            return 500
        case _ as unreachable:
            assert_never(unreachable)


class AppError(HTTPException):
    """A failure carrying its cause, from which its status is derived.

    No constructor accepts a status, so a call site cannot express "not found,
    but report 500". Subclasses ``HTTPException`` rather than replacing it:
    FastAPI's own handler renders it and existing ``except HTTPException``
    guards keep catching it, so this narrows how a status is chosen without
    inventing error machinery.
    """

    def __init__(self, fault: Fault, detail: str) -> None:
        super().__init__(status_code=http_status(fault), detail=detail)
        self.fault = fault

    def __repr__(self) -> str:
        return f"AppError({self.fault.name}, {self.detail!r})"
