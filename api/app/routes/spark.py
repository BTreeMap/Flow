"""Spark prototype generation and pseudonymous research telemetry routes.

Spark remains isolated from existing Flow conversation state and requires no
registration. The client carries remix state as before. Each request also
contains a browser-local pseudonymous identifier and optional ThumbmarkJS
fingerprint; raw values are immediately keyed-hashed and never persisted or logged.

Conditions A ("Random Spark") and B ("Spark Wheel") are non-adaptive control
groups: they are served entirely from a researcher-curated static library
(``app.services.spark_library``) and never call the LLM. Conditions C and D
are the adaptive, intake-informed conditions and proxy validated requests to
the configured LLM, returning structured Spark card payloads.

Choice model (why no condition asks for a vibe up front)
---------------------------------------------------------
Participants generally cannot name the vibe they want before seeing a Spark, so
no condition takes ``frame_preference`` as a *user* input any more. B and D are
the same shape — one Spark per vibe, five cards — and differ only in that B draws
randomly from the static library while D adapts each card to the intake and ranks
the five against each other. Holding the choice set constant is deliberate: it
leaves adaptation and ranking as the only variables between the two conditions.
D's coverage is a target rather than a guarantee — a model that returns four
usable vibes yields four options, never an error.
In both, the chosen vibe is derived from the card the participant actually picks.
``frame_preference`` survives only as an internal request field, carrying an
explicit "switch to X vibe" adjustment on a C/D remix.

Remix model (conditions C/D only)
----------------------------------
The endpoint is stateless. The *client* owns the remix history:
- First generate: ``base_card=None``, ``adjustment_history=[]``
- Each subsequent adjust: ``base_card=<current card>``,
  ``adjustment_history=[oldest, ..., newest]`` (capped at 20 items).

The system prompt instructs the model to transform ``base_card`` in-place when
it is present, applying all accumulated adjustments cumulatively so the card
evolves rather than resetting.

A remix is *always* a single card, in C and in D alike. D's ranked catalog is
the one-time selection artifact; once a participant has picked from it, "adjust"
means the same thing in both adaptive conditions. The card count is therefore
derived here (:func:`_requested_card_count`) and is not a client input: it used
to be decided in three places -- a client default, an unused schema default of
3, and a server-side catalog override -- which is two places too many for one
number.

Timer duration
---------------
The countdown is participant-configurable. Every response carries the study's
:class:`SparkTimerPolicy` so the client never hard-codes a default, and the
resolved duration plus who chose it is reported back on the ``timer_finished``
event. See :mod:`app.services.spark_duration`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_llm_model, get_openai_api_key
from app.db import get_db
from app.errors import AppError, Fault
from app.llm import describe_llm_error, make_chat_llm
from app.prompt_loader import prompt_version
from app.schemas.spark_research import SparkClientIdentity, SparkEventRequest
from app.services.spark_duration import (
    DEFAULT_DURATION_SECONDS,
    DURATION_CHOICES,
    MAX_DURATION_SECONDS,
    MIN_DURATION_SECONDS,
)
from app.services.spark_library import (
    ALL_FRAMES,
    SparkFrame,
    library_version,
    pick_one_spark_per_frame,
    pick_random_sparks,
)
from app.services.spark_research import (
    ResolvedSparkParticipant,
    SparkResearchConfigurationError,
    get_spark_interaction,
    persist_spark_interaction,
    resolve_spark_participant,
)

logger = logging.getLogger(__name__)

router = APIRouter()

PROMPT_NAME = "spark_proxy_system"
_MAX_HISTORY = 20
# Condition D's catalog is one adapted Spark per vibe, ranked against each other.
_D_CATALOG_SIZE = len(ALL_FRAMES)
# Cards any single response may carry.
_MAX_CARDS = 5
# Completion budget. The cap has to scale with the number of cards asked for:
# D's catalog is five cards in a single call, and a cap sized for one truncates
# the JSON mid-card, which fails to parse and costs the participant the whole
# response rather than one card. Sized from the prompt's per-field character
# ceilings (~1160 chars/card) with room for the JSON scaffolding.
_TOKENS_PER_CARD = 400
_TOKENS_RESPONSE_OVERHEAD = 200
# Wall-clock ceiling on one model round-trip.
_MODEL_TIMEOUT_SECONDS = 25


class SparkCard(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    frame: SparkFrame
    action: str = Field(min_length=1, max_length=600)
    reward: str = Field(min_length=1, max_length=300)
    why: str = Field(min_length=1, max_length=400)
    fit_score: int | None = Field(default=None, ge=0, le=100)


class SparkGenerateRequest(BaseModel):
    identity: SparkClientIdentity
    flow_id: UUID
    client_event_id: UUID
    condition: Literal["A", "B", "C", "D"]
    frame_preference: SparkFrame | None = None
    context: str | None = Field(default=None, max_length=800)
    # Remix fields -------------------------------------------------------
    # base_card: the card currently displayed to the user; None on first generate.
    base_card: SparkCard | None = None
    # adjustment_history: ordered list of free-text adjustments from oldest to newest.
    # The model applies them cumulatively to base_card when present.
    adjustment_history: Annotated[list[str], Field(default_factory=list)]

    @field_validator("adjustment_history", mode="before")
    @classmethod
    def _cap_history(cls, v: object) -> object:
        if isinstance(v, list):
            return [str(item)[:400] for item in v[-_MAX_HISTORY:]]
        return v


class SparkTimerPolicy(BaseModel):
    """What the client is allowed to offer for the countdown length.

    Served on every generate response rather than from a second endpoint: it is
    one small object on a payload the flow already fetches, it costs no extra
    round-trip, and it lands in the persisted ``generation_succeeded`` payload,
    so the policy in force is recorded per flow for free.
    """

    default_seconds: int = Field(
        default=DEFAULT_DURATION_SECONDS,
        ge=MIN_DURATION_SECONDS,
        le=MAX_DURATION_SECONDS,
    )
    choices: list[int] = Field(default_factory=lambda: list(DURATION_CHOICES))
    min_seconds: int = MIN_DURATION_SECONDS
    max_seconds: int = MAX_DURATION_SECONDS


class SparkGenerateResponse(BaseModel):
    condition: Literal["A", "B", "C", "D"]
    cards: list[SparkCard] = Field(min_length=1, max_length=_MAX_CARDS)
    model: str
    prompt_version: dict[str, str]
    timer: SparkTimerPolicy = Field(default_factory=SparkTimerPolicy)


def _prose_limits() -> dict[str, int]:
    """Read the per-field character ceilings straight off :class:`SparkCard`.

    Derived rather than restated so the trimming below cannot drift away from
    the contract it is meant to satisfy.
    """
    limits: dict[str, int] = {}
    for name, field in SparkCard.model_fields.items():
        for constraint in field.metadata:
            max_length = getattr(constraint, "max_length", None)
            if isinstance(max_length, int):
                limits[name] = max_length
    return limits


_PROSE_LIMITS = _prose_limits()


def _trim_to_limit(value: str, limit: int) -> str:
    """Shorten one over-long prose field to fit, at a word boundary if possible."""
    if len(value) <= limit:
        return value
    clipped = value[: limit - 1].rstrip()
    last_space = clipped.rfind(" ")
    if last_space > 0:
        clipped = clipped[:last_space]
    return clipped.rstrip(" ,;:-") + "…"


def _fit_prose(item: object) -> object:
    """Bring a candidate card's prose within the ``SparkCard`` length ceilings.

    Length is the one contract breach that is safe to repair: an over-long
    ``action`` is still a real, complete Spark, just wordier than the card can
    display. Dropping it instead costs the participant an entire Spark — and in
    condition C, where the response is a single card, the entire response. Every
    other breach (unknown vibe, missing field, non-string prose) is left alone so
    it still fails validation and the card is dropped.
    """
    if not isinstance(item, dict):
        return item
    return {
        key: (
            _trim_to_limit(value, _PROSE_LIMITS[key])
            if isinstance(value, str) and key in _PROSE_LIMITS
            else value
        )
        for key, value in item.items()
    }


def _parse_cards(payload: dict[str, object]) -> list[SparkCard]:
    """Validate the model's cards one at a time, dropping any with a bad shape.

    Validating the array as a block would let a single malformed card destroy an
    otherwise good response — the participant would get an error page instead of
    the four Sparks that were fine. Dropping is safe precisely because the check
    is per card: everything that survives has passed the full ``SparkCard``
    contract, so a card is either complete or absent, never half-populated.
    """
    items = payload.get("cards")
    if not isinstance(items, list):
        raise ValueError("Spark model output must contain a 'cards' array")

    cards: list[SparkCard] = []
    for item in items[:_MAX_CARDS]:
        try:
            cards.append(SparkCard.model_validate(_fit_prose(item)))
        except ValidationError as exc:
            logger.warning(
                "Dropping malformed Spark card: %s",
                exc.errors(include_url=False),
            )
    return cards


def _content_to_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text_val = item.get("text")
                if isinstance(text_val, str):
                    parts.append(text_val)
        return "\n".join(parts)
    return str(content)


def _extract_json_object(text: str) -> dict[str, object]:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text

    try:
        loaded = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        loaded = json.loads(candidate[start : end + 1])

    if not isinstance(loaded, dict):
        raise ValueError("Spark model output must be a JSON object")
    return loaded


def _build_user_prompt(
    body: SparkGenerateRequest,
    frame_preference: SparkFrame | None,
    count: int,
) -> str:
    """Serialize one model request.

    ``frame_preference`` and ``count`` are passed explicitly rather than read off
    ``body`` because the server, not the client, decides both: a condition D
    catalog asks for no vibe in particular and for exactly one card per vibe.
    """
    payload: dict[str, object] = {
        "condition": body.condition,
        "frame_preference": frame_preference,
        "context": body.context,
        "adjustment_history": body.adjustment_history,
        "count": count,
    }
    if body.base_card is not None:
        payload["base_card"] = body.base_card.model_dump()
    return json.dumps(payload, ensure_ascii=True)


async def _resolve_participant_or_500(
    db: AsyncSession, identity: SparkClientIdentity
) -> ResolvedSparkParticipant:
    """Resolve the pseudonymous participant, or fail as the infra fault it is.

    A missing crypto master key is a deployment defect, not something the caller
    can do anything about, so it is reported as a 5xx rather than dressed up as
    a client error.
    """
    try:
        return await resolve_spark_participant(
            db,
            installation_id=str(identity.installation_id),
            fingerprint=identity.fingerprint,
            fingerprint_version=identity.fingerprint_version,
            timezone=identity.timezone,
            locale=identity.locale,
        )
    except SparkResearchConfigurationError as exc:
        logger.error("Spark research identity is not configured")
        raise AppError(
            Fault.INTERNAL, "Spark research identity is not configured"
        ) from exc


def _generation_event_payload(
    body: SparkGenerateRequest, response: SparkGenerateResponse
) -> dict[str, object]:
    """Build persisted data without the raw browser identity inputs."""
    request_payload: dict[str, object] = {
        "condition": body.condition,
        "frame_preference": body.frame_preference,
        "context": body.context,
        "adjustment_history": body.adjustment_history,
    }
    if body.base_card is not None:
        request_payload["base_card"] = body.base_card.model_dump(mode="json")
    return {
        "request": request_payload,
        "response": response.model_dump(mode="json"),
    }


async def _persist_generation_response(
    db: AsyncSession,
    *,
    participant: ResolvedSparkParticipant,
    body: SparkGenerateRequest,
    response: SparkGenerateResponse,
) -> SparkGenerateResponse:
    await persist_spark_interaction(
        db,
        participant_id=participant.participant_id,
        flow_id=str(body.flow_id),
        client_event_id=str(body.client_event_id),
        condition=body.condition,
        event_type="generation_succeeded",
        payload=_generation_event_payload(body, response),
    )
    await db.commit()
    return response


async def _invoke_spark_model(
    llm: BaseChatModel,
    system_prompt: str,
    user_prompt: str,
) -> list[SparkCard]:
    """One bounded model round-trip → whichever cards came back well-formed.

    Every failure mode is mapped to an :class:`~app.errors.AppError` here so
    callers never have to re-classify provider errors. Individually malformed cards are dropped
    rather than raised on; only a response with *nothing* usable is a failure.
    """
    try:
        response = await asyncio.wait_for(
            llm.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ]
            ),
            timeout=_MODEL_TIMEOUT_SECONDS,
        )
        text = _content_to_text(response.content)
        cards = _parse_cards(_extract_json_object(text))
        if not cards:
            logger.warning("Spark model returned no well-formed cards")
            raise AppError(
                Fault.UPSTREAM_UNAVAILABLE,
                "Spark model produced invalid response shape",
            )
        return cards
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Spark response JSON parse failed: %s", exc)
        raise AppError(
            Fault.UPSTREAM_UNAVAILABLE, "Spark model did not return valid JSON"
        ) from exc
    except TimeoutError as exc:
        logger.warning("Spark LLM timeout after %ss", _MODEL_TIMEOUT_SECONDS)
        raise AppError(
            Fault.UPSTREAM_UNAVAILABLE, "Spark model request timed out"
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - network/provider dependent
        # The classified summary goes in the message *and* the detail: this is
        # the line that was missing when Spark's credits ran out, and the detail
        # is what finally puts the reason on the participant's screen instead of
        # a blanket "generation failed".
        failure = describe_llm_error(exc)
        logger.exception("Spark model request failed: %s", failure.summary())
        raise AppError(
            Fault.UPSTREAM_UNAVAILABLE,
            f"Spark model unavailable ({failure.summary()})",
        ) from exc


def _is_catalog(
    condition: Literal["A", "B", "C", "D"], base_card: SparkCard | None
) -> bool:
    """A condition D first generate -- the only request that wants many cards."""
    return condition == "D" and base_card is None


def _requested_card_count(
    condition: Literal["A", "B", "C", "D"], base_card: SparkCard | None
) -> int:
    """How many cards to ask the model for. The single place that decides.

    One card for condition C, one for any remix in either adaptive condition,
    and one per vibe for D's catalog.
    """
    return _D_CATALOG_SIZE if _is_catalog(condition, base_card) else 1


def _rank_catalog(cards: list[SparkCard]) -> list[SparkCard]:
    """Condition D's catalog: at most one Spark per vibe, best predicted fit first.

    The catalog is one model call, so vibe coverage cannot be pinned per request
    the way condition B's library sampler pins it. Full coverage is therefore a
    target, not a guarantee — and a *shortfall is not an error*: four real options
    serve the participant far better than an error page, and every card shown has
    passed the whole ``SparkCard`` contract either way. Repeats collapse to the
    better-scoring card so no vibe is offered twice.

    The shortfall is logged so model adherence is measurable; if it turns out to
    be common, a retry belongs here.
    """
    best: dict[SparkFrame, SparkCard] = {}
    for card in cards:
        incumbent = best.get(card.frame)
        if incumbent is None or (card.fit_score or 0) > (incumbent.fit_score or 0):
            best[card.frame] = card

    if len(best) < len(ALL_FRAMES):
        logger.warning(
            "Spark D catalog covered %d of %d vibes: %s",
            len(best),
            len(ALL_FRAMES),
            sorted(best),
        )
    return sorted(best.values(), key=lambda card: card.fit_score or 0, reverse=True)


@router.post("/spark/generate", tags=["spark"])
async def spark_generate(
    body: SparkGenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> SparkGenerateResponse:
    """Generate one or more Spark cards.

    Intentionally unauthenticated: Spark is a public, no-login prototype so
    anyone can try it without creating an account. The persisted research
    identity is pseudonymous and is never an authentication factor.

    Conditions A and B are served from the static, researcher-curated
    library and never touch the LLM. Conditions C and D proxy to the LLM.
    """
    participant = await _resolve_participant_or_500(db, body.identity)
    existing = await get_spark_interaction(
        db,
        participant_id=participant.participant_id,
        client_event_id=str(body.client_event_id),
    )
    if existing is not None:
        if existing.event_type != "generation_succeeded":
            raise AppError(
                Fault.CONFLICT, "Spark event id was already used for a different event"
            )
        stored_response = existing.payload_json.get("response")
        try:
            response = SparkGenerateResponse.model_validate(stored_response)
        except ValidationError as exc:  # pragma: no cover - persisted corruption guard
            logger.exception("Stored Spark generation response is invalid")
            raise AppError(
                Fault.INTERNAL, "Stored Spark generation response is invalid"
            ) from exc
        await db.commit()
        return response

    if body.condition in ("A", "B"):
        # A is exactly one random Spark; B is exactly one Spark per vibe. Both
        # selectors are total on a valid library, so the only failure left here
        # is the library itself being unavailable.
        try:
            resolved = (
                await pick_random_sparks(1)
                if body.condition == "A"
                else await pick_one_spark_per_frame()
            )
        except Exception as exc:
            logger.exception("Spark A/B library error")
            raise AppError(
                Fault.INTERNAL, "Spark library is temporarily unavailable"
            ) from exc

        cards = [
            SparkCard(
                title=entry.title,
                frame=entry.frame,
                action=entry.action,
                reward=entry.reward,
                why=entry.why,
            )
            for entry in resolved
        ]

        return await _persist_generation_response(
            db,
            participant=participant,
            body=body,
            response=SparkGenerateResponse(
                condition=body.condition,
                cards=cards,
                model="static-library",
                prompt_version=library_version(),
            ),
        )

    llm_key = get_openai_api_key()
    if not llm_key:
        logger.error("Spark generation requested but no OpenAI API key is configured")
        raise AppError(Fault.INTERNAL, "OpenAI API key not configured")

    from app.prompt_loader import load_prompt

    try:
        system_prompt = load_prompt(PROMPT_NAME)
    except Exception as exc:  # pragma: no cover - packaging/deployment defect
        logger.exception("Spark system prompt failed to load")
        raise AppError(Fault.INTERNAL, "Spark system prompt failed to load") from exc

    # A first D generate is the catalog: one Spark per vibe, no vibe requested.
    # Every other path -- condition C, and any remix in either condition -- is a
    # single card.
    is_catalog = _is_catalog(body.condition, body.base_card)
    requested_cards = _requested_card_count(body.condition, body.base_card)

    model_name = get_llm_model()
    llm = make_chat_llm(
        model=model_name,
        api_key=llm_key,
        temperature=0.6,
        max_tokens=_TOKENS_RESPONSE_OVERHEAD + _TOKENS_PER_CARD * requested_cards,
    )

    cards = await _invoke_spark_model(
        llm,
        system_prompt,
        _build_user_prompt(
            body,
            None if is_catalog else body.frame_preference,
            requested_cards,
        ),
    )

    # The catalog is ranked; everything else is one card. A D remix used to fall
    # through to a re-sorted list here, which put a participant who adjusted a
    # single Spark back in front of a ranked list of five.
    cards = _rank_catalog(cards) if is_catalog else cards[:1]

    if not cards:
        raise AppError(Fault.UPSTREAM_UNAVAILABLE, "Spark model returned no cards")

    return await _persist_generation_response(
        db,
        participant=participant,
        body=body,
        response=SparkGenerateResponse(
            condition=body.condition,
            cards=cards,
            model=model_name,
            prompt_version=prompt_version(PROMPT_NAME),
        ),
    )


@router.post("/spark/events", status_code=status.HTTP_204_NO_CONTENT, tags=["spark"])
async def spark_record_event(
    body: SparkEventRequest,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Persist a strictly typed, idempotent Spark interaction event."""
    participant = await _resolve_participant_or_500(db, body.identity)
    event_payload = body.event.model_dump(mode="json")
    await persist_spark_interaction(
        db,
        participant_id=participant.participant_id,
        flow_id=str(body.flow_id),
        client_event_id=str(body.client_event_id),
        condition=body.condition,
        event_type=event_payload["event_type"],
        payload=event_payload,
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
