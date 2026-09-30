"""Load and deterministically sample static intervention templates."""

from __future__ import annotations

import json
from functools import lru_cache

from app.config_loader import resolve_config_path
from app.services.crypto import content_hexdigest

_INTERVENTION_CONFIG_FILENAME = "interventions.json"


@lru_cache(maxsize=1)
def _load_interventions_config() -> dict[str, list[str]]:
    config_path = resolve_config_path(_INTERVENTION_CONFIG_FILENAME)
    with config_path.open(encoding="utf-8") as config_file:
        raw = json.load(config_file)

    if not isinstance(raw, dict):
        raise ValueError("Intervention config must be a JSON object")

    parsed: dict[str, list[str]] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            raise ValueError("Intervention config keys must be strings")
        # Allow leading-underscore keys (e.g. "_comment") as JSON-friendly
        # metadata that the loader ignores.
        if key.startswith("_"):
            continue
        if not isinstance(value, list):
            raise ValueError(f"Intervention config key '{key}' must map to a list")
        parsed[key] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError(
                    f"Intervention config key '{key}' must contain string items"
                )
            parsed[key].append(item)
    return parsed


def _condition_key(condition: str) -> str:
    normalized = condition.strip().upper()
    if normalized in {"A", "CONDITION_A"}:
        return "condition_A"
    if normalized in {"B", "CONDITION_B"}:
        return "condition_B"
    return f"condition_{normalized}"


def get_static_intervention(
    condition: str,
    participation_id: int,
    day_index: int,
    salt: str = "static_nudge",
) -> str:
    config = _load_interventions_config()
    key = _condition_key(condition)
    condition_array = config.get(key)
    if not condition_array:
        raise ValueError(f"No interventions configured for condition '{condition}'")

    hash_hex = content_hexdigest(f"{participation_id}:{day_index}:{salt}".encode())
    array_index = int(hash_hex, 16) % len(condition_array)
    return condition_array[array_index]
