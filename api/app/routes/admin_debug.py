"""Admin diagnostics: status and LLM connectivity routes."""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter
from h4ckath0n.auth.dependencies import require_admin
from h4ckath0n.auth.models import User

from app import config
from app.config import get_openai_api_key
from app.errors import AppError, Fault
from app.llm import make_chat_llm
from app.routes.schemas import (
    AdminDebugStatusResponse,
    AdminLLMConnectivityRequest,
    AdminLLMConnectivityResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/admin/debug/status", tags=["admin"])
async def admin_debug_status(
    _admin_user: User = require_admin(),
) -> AdminDebugStatusResponse:
    llm_key_present = bool(config.get_openai_api_key())
    vapid_public_present = bool(config.get_vapid_public_key())
    vapid_private_present = bool(config.get_vapid_private_key())
    warnings: list[str] = []
    if not llm_key_present:
        warnings.append("OpenAI API key missing: chat runs in stub mode")
    if not vapid_public_present or not vapid_private_present:
        warnings.append("VAPID keys missing: push notifications disabled")
    return AdminDebugStatusResponse(
        llm_mode="openai" if llm_key_present else "stub",
        openai_api_key_configured=llm_key_present,
        vapid_public_key_configured=vapid_public_present,
        vapid_private_key_configured=vapid_private_present,
        warnings=warnings,
    )


@router.post("/admin/debug/llm-connectivity", tags=["admin"])
async def admin_debug_llm_connectivity(
    body: AdminLLMConnectivityRequest,
    _admin_user: User = require_admin(),
) -> AdminLLMConnectivityResponse:
    llm_key = get_openai_api_key()
    if not llm_key:
        raise AppError(Fault.INTERNAL, "OpenAI API key not configured")

    started = time.perf_counter()
    try:
        llm = make_chat_llm(
            model=body.model,
            api_key=llm_key,
            max_tokens=body.max_tokens,
            temperature=body.temperature,
        )
        response = await asyncio.wait_for(
            llm.ainvoke(body.prompt),
            timeout=15,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        response_text = (
            response.content
            if isinstance(response.content, str)
            else str(response.content)
        )[:2000]
        return AdminLLMConnectivityResponse(
            ok=True,
            model=body.model,
            latency_ms=latency_ms,
            response_text=response_text,
        )
    except Exception as exc:  # pragma: no cover - depends on environment/network
        latency_ms = int((time.perf_counter() - started) * 1000)
        return AdminLLMConnectivityResponse(
            ok=False,
            model=body.model,
            latency_ms=latency_ms,
            error=str(exc),
        )
