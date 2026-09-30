"""Router output schema — structured routing decision (Pydantic)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RouteDecision(BaseModel):
    """Structured output from the coordinator router.

    The ``route`` field determines which specialist agent handles the turn.
    ``reason`` is log-only and must never be shown to the user.

    ``INTAKE``/``FEEDBACK``/``COACH`` are the three specialist routes the
    Router LLM may emit. ``STATIC_TEMPLATE`` and ``STATIC_FEEDBACK`` are
    synthetic post-routing markers the engine assigns when an experimental
    control condition (A or B) bypasses the LLM with a deterministic
    nudge or scripted feedback turn. The Router LLM never emits these.
    """

    route: Literal[
        "INTAKE",
        "FEEDBACK",
        "COACH",
        "STATIC_TEMPLATE",
        "STATIC_FEEDBACK",
    ] = Field(..., description="Target specialist module or static-condition marker")
    reason: str | None = Field(
        default=None,
        description="Log-only justification for the routing decision",
    )
