"""Load and deterministically sample static intervention templates."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

_INTERVENTION_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "interventions.json"
)


@lru_cache(maxsize=1)
def _load_interventions_config() -> dict[str, list[str]]:
    with _INTERVENTION_CONFIG_PATH.open(encoding="utf-8") as config_file:
        raw = json.load(config_file)

    if not isinstance(raw, dict):
        raise ValueError("Intervention config must be a JSON object")

    parsed: dict[str, list[str]] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            raise ValueError("Intervention config keys must be strings")
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

    hash_hex = hashlib.sha256(
        f"{participation_id}:{day_index}:{salt}".encode("utf-8")
    ).hexdigest()
    array_index = int(hash_hex, 16) % len(condition_array)
    return condition_array[array_index]
