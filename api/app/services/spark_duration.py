"""The Spark countdown duration domain.

The countdown used to be the literal ``60`` in ``SparkTimer.tsx`` plus the
phrase "one minute" scattered through card copy, the static library and the
system prompt. Making it participant-configurable means exactly one of those
may name a duration -- the resolved value -- so this module owns the number and
every consumer asks it.

Two things can choose a duration, and they are a closed set:

``study_default``
    The researcher-configured constant every flow starts from.
``participant``
    An explicit pick from :data:`DURATION_CHOICES`.

There is deliberately no "the model chose it" variant. Nothing populates one
today, and a dead variant is a state the analysis has to defend against for no
benefit. Adding it later is a compiler-guided edit: every ``match`` over
:data:`DurationSource` fails until it is handled.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Self

# Absolute bounds on any duration the domain will admit. Below 15s the ring
# animation and the "move until it ends" framing stop meaning anything; above
# 300s it is no longer a micro-break, which is the whole intervention.
MIN_DURATION_SECONDS = 15
MAX_DURATION_SECONDS = 300

#: The study default, and the value every pre-configurable-duration research
#: row should be read as carrying.
DEFAULT_DURATION_SECONDS = 60

#: What a participant may pick from. A presentation policy, deliberately
#: narrower than the domain bounds: the type admits any valid second count, the
#: UI offers a short row of chips.
DURATION_CHOICES: tuple[int, ...] = (30, 60, 90, 120, 180, 300)

DurationSource = Literal["study_default", "participant"]


@dataclass(frozen=True, slots=True)
class SparkDuration:
    """A countdown length in whole seconds, known to be within bounds.

    Construct through :meth:`parse`. ``__post_init__`` re-checks because Python
    cannot hide the constructor, so direct construction raises rather than
    admitting an out-of-range value to the domain.
    """

    seconds: int

    def __post_init__(self) -> None:
        if not _in_domain(self.seconds):
            raise ValueError(
                f"Spark duration must be a whole number of seconds in "
                f"[{MIN_DURATION_SECONDS}, {MAX_DURATION_SECONDS}]: {self.seconds!r}"
            )

    @classmethod
    def parse(cls, raw: object) -> Self | None:
        """Admit an untrusted value, or ``None`` when it is not a duration.

        ``bool`` is rejected explicitly: it is an ``int`` subclass in Python, so
        ``SparkDuration.parse(True)`` would otherwise be a 1-second countdown.
        """
        if isinstance(raw, bool) or not isinstance(raw, int):
            return None
        return cls(raw) if _in_domain(raw) else None


def _in_domain(seconds: int) -> bool:
    return MIN_DURATION_SECONDS <= seconds <= MAX_DURATION_SECONDS


@dataclass(frozen=True, slots=True)
class ResolvedDuration:
    """A duration paired with who chose it.

    Both halves travel together because neither is interpretable alone: a
    research row recording 180 seconds without recording that the participant
    asked for it cannot be separated from a study whose default was 180.
    """

    duration: SparkDuration
    source: DurationSource


def resolve_duration(
    study_default: SparkDuration,
    participant_choice: SparkDuration | None,
) -> ResolvedDuration:
    """Total: participant choice wins, otherwise the study default."""
    if participant_choice is None:
        return ResolvedDuration(study_default, "study_default")
    return ResolvedDuration(participant_choice, "participant")


def study_default_duration() -> SparkDuration:
    """The configured study default as a parsed domain value."""
    return SparkDuration(DEFAULT_DURATION_SECONDS)
