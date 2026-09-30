"""Deterministic daily condition assignment for 4-condition experiments."""

from __future__ import annotations

from datetime import date, datetime

from app.services.crypto import keyed_digest

CONDITION_PERMUTATIONS: tuple[tuple[str, str, str, str], ...] = (
    ("A", "B", "C", "D"),
    ("A", "B", "D", "C"),
    ("A", "C", "B", "D"),
    ("A", "C", "D", "B"),
    ("A", "D", "B", "C"),
    ("A", "D", "C", "B"),
    ("B", "A", "C", "D"),
    ("B", "A", "D", "C"),
    ("B", "C", "A", "D"),
    ("B", "C", "D", "A"),
    ("B", "D", "A", "C"),
    ("B", "D", "C", "A"),
    ("C", "A", "B", "D"),
    ("C", "A", "D", "B"),
    ("C", "B", "A", "D"),
    ("C", "B", "D", "A"),
    ("C", "D", "A", "B"),
    ("C", "D", "B", "A"),
    ("D", "A", "B", "C"),
    ("D", "A", "C", "B"),
    ("D", "B", "A", "C"),
    ("D", "B", "C", "A"),
    ("D", "C", "A", "B"),
    ("D", "C", "B", "A"),
)


def get_daily_condition(
    participation_id: int,
    study_start_date: datetime,
    current_date: date,
    key: bytes,
) -> str:
    """Return the deterministic condition assignment for a given study day."""
    day_index = (current_date - study_start_date.date()).days
    block_index = day_index // 4
    intra_block_step = day_index % 4
    digest = keyed_digest(key, f"{participation_id}:{block_index}".encode())
    permutation_index = int.from_bytes(digest, "big") % 24
    return CONDITION_PERMUTATIONS[permutation_index][intra_block_step]
