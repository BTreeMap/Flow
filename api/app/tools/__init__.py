"""LangChain tools package — proposal tools for the new architecture."""

from __future__ import annotations

from app.tools.proposal_tools import (
    ProposalCollector,
    make_proposal_tools,
)

__all__ = [
    "ProposalCollector",
    "make_proposal_tools",
]
