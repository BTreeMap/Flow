"""Thin loader for prompt text files with in-memory caching."""

from hashlib import sha256
from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_cache: dict[str, str] = {}


def load_prompt(name: str) -> str:
    """Return the content of ``prompts/{name}.txt``, cached after first read."""
    if name not in _cache:
        path = _PROMPTS_DIR / f"{name}.txt"
        _cache[name] = path.read_text(encoding="utf-8")
    return _cache[name]


def prompt_hash(name: str) -> str:
    """Return the SHA-256 hex digest of the prompt content."""
    return sha256(load_prompt(name).encode("utf-8")).hexdigest()


def prompt_version(name: str) -> dict:
    """Return ``{"prompt_file": name, "prompt_sha256": hash}``."""
    return {"prompt_file": name, "prompt_sha256": prompt_hash(name)}
