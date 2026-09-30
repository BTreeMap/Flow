"""Tests for the Spark countdown duration domain and its wire contract."""

from __future__ import annotations

import pytest
from app.schemas.spark_research import SparkEventRequest
from app.services.spark_duration import (
    DEFAULT_DURATION_SECONDS,
    DURATION_CHOICES,
    MAX_DURATION_SECONDS,
    MIN_DURATION_SECONDS,
    ResolvedDuration,
    SparkDuration,
    resolve_duration,
    study_default_duration,
)
from pydantic import ValidationError

_EVENT_CONTEXT = {
    "identity": {"installation_id": "00000000-0000-4000-8000-000000000001"},
    "flow_id": "00000000-0000-4000-8000-000000000002",
    "client_event_id": "00000000-0000-4000-8000-000000000003",
    "condition": "C",
}


# ---------------------------------------------------------------------------
# Smart constructor
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "seconds", [MIN_DURATION_SECONDS, DEFAULT_DURATION_SECONDS, MAX_DURATION_SECONDS]
)
def test_parse_admits_every_in_domain_value(seconds: int) -> None:
    parsed = SparkDuration.parse(seconds)
    assert parsed is not None
    assert parsed.seconds == seconds


@pytest.mark.parametrize(
    "raw",
    [
        MIN_DURATION_SECONDS - 1,
        MAX_DURATION_SECONDS + 1,
        0,
        -60,
        60.0,  # a float is not a whole number of seconds
        "60",
        None,
        True,  # bool is an int subclass: must not become a 1-second countdown
        False,
    ],
)
def test_parse_rejects_out_of_domain_values(raw: object) -> None:
    assert SparkDuration.parse(raw) is None


def test_direct_construction_still_enforces_the_invariant() -> None:
    """Python cannot hide the constructor, so it re-checks rather than trusting."""
    with pytest.raises(ValueError, match="whole number of seconds"):
        SparkDuration(MAX_DURATION_SECONDS + 1)


def test_duration_is_immutable() -> None:
    from dataclasses import FrozenInstanceError

    with pytest.raises(FrozenInstanceError):
        SparkDuration(60).seconds = 30  # type: ignore[misc]


def test_every_offered_choice_is_in_domain() -> None:
    """The UI's choice set is a subset of the domain, not a parallel truth."""
    assert all(SparkDuration.parse(c) is not None for c in DURATION_CHOICES)
    assert DEFAULT_DURATION_SECONDS in DURATION_CHOICES


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def test_resolve_falls_back_to_the_study_default() -> None:
    assert resolve_duration(study_default_duration(), None) == ResolvedDuration(
        SparkDuration(DEFAULT_DURATION_SECONDS), "study_default"
    )


def test_participant_choice_wins_and_is_attributed() -> None:
    resolved = resolve_duration(study_default_duration(), SparkDuration(180))
    assert resolved == ResolvedDuration(SparkDuration(180), "participant")


def test_participant_choice_equal_to_the_default_is_still_attributed() -> None:
    """Source is who chose, not whether the number differs.

    A participant who deliberately picks 60 is not the same research row as one
    who never touched the control, even though both ran a 60-second countdown.
    """
    resolved = resolve_duration(
        study_default_duration(), SparkDuration(DEFAULT_DURATION_SECONDS)
    )
    assert resolved.source == "participant"


# ---------------------------------------------------------------------------
# Wire contract
# ---------------------------------------------------------------------------


def _timer_event(**overrides: object) -> dict[str, object]:
    event = {
        "event_type": "timer_finished",
        "completion": "completed",
        "duration_seconds": DEFAULT_DURATION_SECONDS,
        "elapsed_ms": 60_000,
        "duration_source": "study_default",
    }
    return {**_EVENT_CONTEXT, "event": {**event, **overrides}}


def test_timer_finished_event_accepts_a_complete_payload() -> None:
    request = SparkEventRequest.model_validate(_timer_event())
    assert request.event.event_type == "timer_finished"


@pytest.mark.parametrize(
    "missing", ["duration_seconds", "elapsed_ms", "duration_source"]
)
def test_timer_finished_requires_all_three_duration_fields(missing: str) -> None:
    """Any one of them alone is uninterpretable, so none of them is optional."""
    payload = _timer_event()
    event = dict(payload["event"])  # type: ignore[arg-type]
    del event[missing]
    with pytest.raises(ValidationError):
        SparkEventRequest.model_validate({**payload, "event": event})


@pytest.mark.parametrize(
    "overrides",
    [
        {"duration_seconds": MIN_DURATION_SECONDS - 1},
        {"duration_seconds": MAX_DURATION_SECONDS + 1},
        {"elapsed_ms": -1},
        {"duration_source": "card"},  # no such variant today
        {"duration_source": "model"},
    ],
)
def test_timer_finished_rejects_out_of_domain_values(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        SparkEventRequest.model_validate(_timer_event(**overrides))


def test_skipped_runs_report_the_duration_they_abandoned() -> None:
    """A skip is only interpretable next to the length it was measured against."""
    request = SparkEventRequest.model_validate(
        _timer_event(completion="skipped", duration_seconds=300, elapsed_ms=4_200)
    )
    event = request.event
    assert event.event_type == "timer_finished"
    assert (event.completion, event.duration_seconds, event.elapsed_ms) == (
        "skipped",
        300,
        4_200,
    )
