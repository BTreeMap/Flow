"""Router output schema — structured routing decision (Pydantic)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RouteDecision(BaseModel):
    """Structured output from the coordinator router.

    The ``route`` field determines which specialist agent handles the turn.
    ``reason`` is log-only and must never be shown to the user.
    """

    route: Literal["INTAKE", "FEEDBACK", "COACH"] = Field(
        ..., description="Target specialist module: INTAKE, FEEDBACK, or COACH"
    )
    reason: str | None = Field(
        default=None,
        description="Log-only justification for the routing decision",
    )
