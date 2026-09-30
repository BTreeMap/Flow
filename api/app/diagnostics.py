"""Startup diagnostics that surface runtime configuration in the docker log.

The single most effective way to avoid blind troubleshooting is to make every
process announce — in plain stdout that ``docker logs`` captures — what it
actually resolved at boot: which database it is talking to, whether the LLM and
push are live or degraded, and exactly which prompt directories are in effect.

A degraded-but-running condition (missing LLM key, missing prompt directory,
push disabled) is logged at WARNING so it stands out without being fatal. None
of these lines ever contain secrets: the database URL is reduced to
scheme/host/name and credentials/keys are reported only as a boolean presence.
"""

from __future__ import annotations

import logging
from urllib.parse import urlsplit

from app import config, config_loader, prompt_loader

logger = logging.getLogger("app.diagnostics")

# A prompt that must always resolve; probing it at boot exercises the loader and
# emits its fallback/missing warnings before any request arrives.
_CANARY_PROMPT = "router_system"

# A config file that must always resolve; probed the same way as the canary
# prompt above so a missing/shadowed config mount is visible at boot.
_CANARY_CONFIG_FILE = "interventions.json"


def _redact_database_url(url: str) -> str:
    """Return a credential-free description of *url* (scheme/host/path only)."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "(unparseable)"
    # SQLite URLs carry the path in either netloc-less form or as the path.
    if parts.scheme.startswith("sqlite"):
        return f"{parts.scheme}:{parts.path or parts.netloc}"
    host = parts.hostname or "?"
    port = f":{parts.port}" if parts.port else ""
    db_name = parts.path.lstrip("/") or "?"
    return f"{parts.scheme}://{host}{port}/{db_name}"


def log_startup_report(component: str) -> None:
    """Log a concise, secret-free summary of the resolved runtime configuration.

    *component* is a short label such as ``"api"`` or ``"worker"`` so multiple
    processes sharing one log stream are distinguishable.
    """
    logger.info("── %s startup diagnostics ──", component)
    logger.info("environment: %s", config.get_env())
    logger.info("database: %s", _redact_database_url(config.get_database_url()))
    logger.info("data dir: %s", config.get_data_dir())
    logger.info("default timezone: %s", config.get_default_timezone())

    # LLM posture — degraded (stub) mode is a WARNING so it is visible.
    if config.get_openai_api_key():
        logger.info("LLM: live (model=%s)", config.get_llm_model())
    else:
        logger.warning(
            "LLM: stub mode — no OPENAI_API_KEY/H4CKATH0N_OPENAI_API_KEY set; "
            "LLM-backed endpoints will degrade or fail"
        )

    # Push posture — disabled push is a WARNING.
    if config.get_vapid_public_key() and config.get_vapid_private_key():
        logger.info("web push: enabled")
    else:
        logger.warning(
            "web push: disabled — VAPID_PUBLIC_KEY/VAPID_PRIVATE_KEY incomplete"
        )

    # Cryptographic master key — required by condition assignment and Spark
    # research telemetry. The validation helper never exposes key material.
    from app.services.crypto import is_crypto_master_key_configured

    if not is_crypto_master_key_configured():
        logger.warning(
            "FLOW_CRYPTO_MASTER_KEY missing or invalid — condition assignment "
            "and Spark telemetry unavailable"
        )

    # Prompt directories — the exact resolution order, with existence flags.
    for directory, exists in prompt_loader.describe_resolution():
        logger.info("prompt dir [%s]: %s", "ok" if exists else "absent", directory)

    # Probe a canary prompt so the loader's own fallback/missing warnings fire
    # at boot rather than at first request. Never fatal — a failure here is
    # logged and the process continues so the issue is visible but contained.
    try:
        prompt_loader.load_prompt(_CANARY_PROMPT)
        logger.info("prompt probe: '%s' resolved", _CANARY_PROMPT)
    except Exception:
        logger.exception(
            "prompt probe FAILED for '%s' — prompt directories are misconfigured",
            _CANARY_PROMPT,
        )

    # Config directories — same resolution order/visibility as prompts, for the
    # static JSON config (interventions.json, spark_library.json) read by
    # app/services/*.
    for directory, exists in config_loader.describe_resolution():
        logger.info("config dir [%s]: %s", "ok" if exists else "absent", directory)

    try:
        config_loader.resolve_config_path(_CANARY_CONFIG_FILE)
        logger.info("config probe: '%s' resolved", _CANARY_CONFIG_FILE)
    except Exception:
        logger.exception(
            "config probe FAILED for '%s' — config directories are misconfigured",
            _CANARY_CONFIG_FILE,
        )

    logger.info("── end %s startup diagnostics ──", component)
