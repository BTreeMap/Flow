"""Profile and memory persistence services — Router single-writer path."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    FlowUserProfile,
    MemoryItem,
    ParticipantContact,
    PatchAuditLog,
    ProjectMembership,
    UserProfileStore,
)
from app.schemas.patches import (
    COACH_ALLOWED_FIELDS,
    CONFIDENCE_THRESHOLDS,
    FEEDBACK_ALLOWED_FIELDS,
    INTAKE_ALLOWED_FIELDS,
    MemoryItemData,
    MemoryPatchProposal,
    ProfilePatchProposal,
    UserProfileData,
)

logger = logging.getLogger(__name__)

MAX_MEMORY_ITEM_LENGTH = 500


async def load_user_profile(db: AsyncSession, membership_id: int) -> UserProfileData:
    """Load the user profile for a membership, or return defaults.

    Merges structured JSON profile (Store A) with display name from
    FlowUserProfile or ParticipantContact.
    """
    # Load JSON profile
    result = await db.execute(
        select(UserProfileStore).where(UserProfileStore.membership_id == membership_id)
    )
    if (row := result.scalar_one_or_none()) is None:
        profile = UserProfileData()
    else:
        profile = UserProfileData.model_validate_json(row.profile_json)

    # Fetch display name
    # Priority: ParticipantContact (latest) > FlowUserProfile (global)
    contact_res = await db.execute(
        select(ParticipantContact)
        .where(ParticipantContact.membership_id == membership_id)
        .order_by(ParticipantContact.created_at.desc())
        .limit(1)
    )
    if (contact := contact_res.scalar_one_or_none()) and contact.email_raw:
        # If we had a display name in contact, we'd use it, but we don't.
        # So we look up FlowUserProfile via membership.
        pass

    # Join membership to get user_id
    mem_res = await db.execute(
        select(ProjectMembership.user_id).where(ProjectMembership.id == membership_id)
    )

    if user_id := mem_res.scalar_one_or_none():
        user_res = await db.execute(
            select(FlowUserProfile).where(FlowUserProfile.user_id == user_id)
        )
        if (
            user_profile := user_res.scalar_one_or_none()
        ) and user_profile.display_name:
            profile.display_name = user_profile.display_name

    return profile


async def save_user_profile(
    db: AsyncSession,
    membership_id: int,
    profile: UserProfileData,
    flush: bool = True,
) -> None:
    """Upsert the user profile (Router-only write path)."""
    result = await db.execute(
        select(UserProfileStore).where(UserProfileStore.membership_id == membership_id)
    )
    # Exclude display_name from persistence in JSON store as it's transient/derived
    profile_json = profile.model_dump_json(exclude={"display_name"})
    if (row := result.scalar_one_or_none()) is None:
        row = UserProfileStore(
            membership_id=membership_id,
            profile_json=profile_json,
        )
        db.add(row)
    else:
        row.profile_json = profile_json

    if flush:
        await db.flush()


async def load_memory_items(
    db: AsyncSession, membership_id: int, limit: int = 50
) -> list[MemoryItemData]:
    """Load recent memory items for a membership."""
    result = await db.execute(
        select(MemoryItem)
        .where(MemoryItem.membership_id == membership_id)
        .order_by(MemoryItem.created_at.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    items = []
    for row in rows:
        try:
            source_ids = json.loads(row.source_message_ids)
        except (json.JSONDecodeError, TypeError):
            source_ids = []
        tags = row.tags.split(",") if row.tags else []
        items.append(
            MemoryItemData(
                content=row.content,
                source_message_ids=source_ids,
                tags=tags,
                created_at=row.created_at,
            )
        )
    return list(reversed(items))


async def add_memory_item(
    db: AsyncSession,
    membership_id: int,
    item: MemoryItemData,
    flush: bool = True,
) -> None:
    """Add a single memory item (Router-only write path)."""
    row = MemoryItem(
        membership_id=membership_id,
        content=item.content,
        source_message_ids=json.dumps(item.source_message_ids),
        tags=",".join(item.tags) if item.tags else None,
    )
    db.add(row)
    if flush:
        await db.flush()


async def log_patch_audit(
    db: AsyncSession,
    membership_id: int,
    proposal_type: str,
    source_bot: str,
    patch_json: str,
    confidence: float,
    evidence_json: str,
    decision: str,
    committed_at: datetime | None = None,
    flush: bool = True,
) -> None:
    """Record a patch proposal and its decision in the audit log."""
    row = PatchAuditLog(
        membership_id=membership_id,
        proposal_type=proposal_type,
        source_bot=source_bot,
        patch_json=patch_json,
        confidence=confidence,
        evidence_json=evidence_json,
        decision=decision,
        committed_at=committed_at,
    )
    db.add(row)
    if flush:
        await db.flush()


def get_allowed_fields(source_bot: str) -> set[str]:
    """Return the set of profile fields a bot is allowed to propose changes to."""
    if source_bot == "INTAKE":
        return INTAKE_ALLOWED_FIELDS
    if source_bot == "FEEDBACK":
        return FEEDBACK_ALLOWED_FIELDS
    if source_bot == "COACH":
        return COACH_ALLOWED_FIELDS
    return set()


def validate_profile_patch(
    proposal: ProfilePatchProposal,
    recent_message_ids: list[int],
) -> tuple[bool, str]:
    """Validate a profile patch proposal. Returns (valid, reason)."""
    # 1. Confidence threshold
    threshold = CONFIDENCE_THRESHOLDS.get(proposal.source_bot, 0.8)
    if proposal.confidence < threshold:
        return False, f"Confidence {proposal.confidence} below threshold {threshold}"

    # 2. Field-level permissions
    allowed = get_allowed_fields(proposal.source_bot)
    for field in proposal.patch:
        if field not in allowed:
            return (
                False,
                f"Bot {proposal.source_bot} not allowed to set field '{field}'",
            )

    # 3. Evidence span validation
    if not proposal.evidence.message_ids:
        return False, "Evidence must reference at least one message"
    for mid in proposal.evidence.message_ids:
        if mid not in recent_message_ids:
            return False, f"Evidence message_id {mid} not in recent context"

    return True, "ok"


def validate_memory_patch(
    proposal: MemoryPatchProposal,
    recent_message_ids: list[int],
) -> tuple[bool, str]:
    """Validate a memory patch proposal. Returns (valid, reason)."""
    # 1. Confidence threshold
    threshold = CONFIDENCE_THRESHOLDS.get(proposal.source_bot, 0.8)
    if proposal.confidence < threshold:
        return False, f"Confidence {proposal.confidence} below threshold {threshold}"

    # 2. Coach cannot write memory directly
    if proposal.source_bot == "COACH":
        return False, "Coach bot cannot directly write memory"

    # 3. Evidence span validation
    if not proposal.evidence.message_ids:
        return False, "Evidence must reference at least one message"
    for mid in proposal.evidence.message_ids:
        if mid not in recent_message_ids:
            return False, f"Evidence message_id {mid} not in recent context"

    # 4. Conservative memory write rules
    for item in proposal.items:
        if len(item.content) > MAX_MEMORY_ITEM_LENGTH:
            return (
                False,
                f"Memory items must be short (max {MAX_MEMORY_ITEM_LENGTH} chars)",
            )

    return True, "ok"


def apply_profile_patch(
    profile: UserProfileData,
    patch: dict[str, Any],
) -> UserProfileData:
    """Apply a validated patch to a profile, returning the updated profile."""
    data = profile.model_dump()
    for key, value in patch.items():
        if key in UserProfileData.model_fields:
            data[key] = value
    return UserProfileData.model_validate(data)
