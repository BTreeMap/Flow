"""Schemas for the messaging turn pipeline (debug envelope)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DebugInfo(BaseModel):
    """Diagnostic envelope returned alongside an assistant turn.

    Carries the routing/agent metadata the frontend debug panel renders.
    ``extra="allow"`` keeps it forward-compatible: new diagnostic keys can be
    attached without a schema migration, while the well-known fields below stay
    strongly typed for the common read paths (``condition`` especially).
    """

    model_config = ConfigDict(extra="allow")

    agent: str
    condition: str
    prompt_args: dict[str, Any] = Field(default_factory=dict)
    tools: list[str] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
