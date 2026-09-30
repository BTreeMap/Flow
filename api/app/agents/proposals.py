"""Router commit logic — validate and commit specialist patch proposals."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    DailyInterventionLog,
    NotificationRule,
    NotificationRuleState,
    Participation,
    ScheduledTask,
)
from app.schemas.patches import (
    FEEDBACK_ALLOWED_FIELDS,
    INTAKE_ALLOWED_FIELDS,
    MemoryPatchProposal,
    ProfilePatchProposal,
    SchedulePatchProposal,
    UserProfileData,
)
from app.services.notification_engine import compute_next_due_utc, get_user_timezone
from app.services.profile_service import (
    add_memory_item,
    apply_profile_patch,
    log_patch_audit,
    save_user_profile,
    validate_memory_patch,
    validate_profile_patch,
)
from app.tools.proposal_tools import ProposalCollector

logger = logging.getLogger(__name__)


async def _process_proposals(
    db: AsyncSession,
    membership_id: int,
    profile: UserProfileData,
    collector: ProposalCollector,
    recent_message_ids: list[int],
    latest_user_message_id: int | None = None,
) -> UserProfileData:
    """Validate and commit proposals from the specialist. Returns updated profile."""
    now = datetime.now(UTC)
    profile_changed = False

    # Process profile proposals
    for raw in collector.profile_proposals:
        sp = None
        try:
            if latest_user_message_id and isinstance(raw, dict):
                evidence = raw.get("evidence", {})
                message_ids = (
                    evidence.get("message_ids", [])
                    if isinstance(evidence, dict)
                    else []
                )
                patch = raw.get("patch", {})
                source_bot = raw.get("source_bot")
                allowed_fields = (
                    INTAKE_ALLOWED_FIELDS
                    if source_bot == "INTAKE"
                    else FEEDBACK_ALLOWED_FIELDS
                    if source_bot == "FEEDBACK"
                    else set()
                )
                if (
                    not message_ids
                    and isinstance(patch, dict)
                    and set(patch).issubset(allowed_fields)
                ):
                    raw["evidence"] = {
                        "message_ids": [latest_user_message_id],
                        "quotes": evidence.get("quotes", [])
                        if isinstance(evidence, dict)
                        else [],
                    }
            try:
                proposal = ProfilePatchProposal.model_validate(raw)
            except Exception:
                logger.warning("Invalid profile proposal: %s", raw)
                continue

            valid, reason = validate_profile_patch(proposal, recent_message_ids)

            # Isolate the commit in a SAVEPOINT: on Postgres a failed statement
            # aborts the whole transaction, which would otherwise destroy the
            # user + assistant messages persisted by the caller.
            sp = await db.begin_nested()
            await log_patch_audit(
                db=db,
                membership_id=membership_id,
                proposal_type="profile",
                source_bot=proposal.source_bot,
                patch_json=json.dumps(proposal.patch),
                confidence=proposal.confidence,
                evidence_json=proposal.evidence.model_dump_json(),
                decision="committed" if valid else f"ignored: {reason}",
                committed_at=now if valid else None,
                flush=False,
            )
            await db.flush()
            await sp.commit()
            sp = None

            if valid:
                profile = apply_profile_patch(profile, proposal.patch)
                profile_changed = True
                logger.info("Committed profile patch from %s", proposal.source_bot)
        except Exception:
            if sp is not None:
                await sp.rollback()
            logger.exception("Failed to process profile proposal: %s", raw)

    # Process memory proposals
    for raw in collector.memory_proposals:
        sp = None
        try:
            if latest_user_message_id and isinstance(raw, dict):
                evidence = raw.get("evidence", {})
                message_ids = (
                    evidence.get("message_ids", [])
                    if isinstance(evidence, dict)
                    else []
                )
                source_bot = raw.get("source_bot")
                if not message_ids and source_bot in {"INTAKE", "FEEDBACK"}:
                    raw["evidence"] = {
                        "message_ids": [latest_user_message_id],
                        "quotes": evidence.get("quotes", [])
                        if isinstance(evidence, dict)
                        else [],
                    }
            try:
                proposal = MemoryPatchProposal.model_validate(raw)
            except Exception:
                logger.warning("Invalid memory proposal: %s", raw)
                continue

            valid, reason = validate_memory_patch(proposal, recent_message_ids)

            sp = await db.begin_nested()
            await log_patch_audit(
                db=db,
                membership_id=membership_id,
                proposal_type="memory",
                source_bot=proposal.source_bot,
                patch_json=json.dumps(
                    [i.model_dump(mode="json") for i in proposal.items]
                ),
                confidence=proposal.confidence,
                evidence_json=proposal.evidence.model_dump_json(),
                decision="committed" if valid else f"ignored: {reason}",
                committed_at=now if valid else None,
                flush=False,
            )

            if valid:
                for item in proposal.items:
                    await add_memory_item(db, membership_id, item, flush=False)
                logger.info(
                    "Committed %d memory items from %s",
                    len(proposal.items),
                    proposal.source_bot,
                )
            await db.flush()
            await sp.commit()
            sp = None
        except Exception:
            if sp is not None:
                await sp.rollback()
            logger.exception("Failed to process memory proposal: %s", raw)

    # Process schedule proposals
    for raw in collector.schedule_proposals:
        sp = None
        try:
            if latest_user_message_id and isinstance(raw, dict):
                evidence = raw.get("evidence", {})
                message_ids = (
                    evidence.get("message_ids", [])
                    if isinstance(evidence, dict)
                    else []
                )
                if not message_ids:
                    raw["evidence"] = {
                        "message_ids": [latest_user_message_id],
                        "quotes": evidence.get("quotes", [])
                        if isinstance(evidence, dict)
                        else [],
                    }
            try:
                proposal = SchedulePatchProposal.model_validate(raw)
            except Exception:
                logger.warning("Invalid schedule proposal: %s", raw)
                continue

            # Validate schedule proposal (basic checks for now)
            valid = True
            reason = ""
            if proposal.action == "create":
                if not proposal.topic or not proposal.time:
                    valid = False
                    reason = "Missing topic or time"
            elif proposal.action == "delete" and not proposal.rule_id:
                valid = False
                reason = "Missing rule_id"

            if valid and proposal.source_bot != "COACH":
                # Assuming only Coach should really be messing with schedules for now,
                # or at least that's where we exposed the tools.
                # But technically any bot could if we let it.
                # Let's keep it open but log it.
                pass

            sp = await db.begin_nested()
            await log_patch_audit(
                db=db,
                membership_id=membership_id,
                proposal_type="schedule",
                source_bot=proposal.source_bot,
                patch_json=json.dumps(
                    {
                        "action": proposal.action,
                        "topic": proposal.topic,
                        "time": proposal.time,
                        "rule_id": proposal.rule_id,
                    }
                ),
                confidence=proposal.confidence,
                evidence_json=proposal.evidence.model_dump_json(),
                decision="committed" if valid else f"ignored: {reason}",
                committed_at=now if valid else None,
                flush=False,
            )

            if valid:
                if proposal.action == "create":
                    rule = NotificationRule(
                        membership_id=membership_id,
                        kind="daily_local_time",
                        config_json=json.dumps(
                            {"topic": proposal.topic, "time": proposal.time}
                        ),
                        tz_policy="floating_user_tz",
                        is_active=True,
                    )
                    db.add(rule)
                    await db.flush()
                    user_tz = await get_user_timezone(db, membership_id)
                    next_due = compute_next_due_utc(rule, user_tz)
                    state = NotificationRuleState(
                        rule_id=rule.id,
                        next_due_at_utc=next_due,
                    )
                    db.add(state)
                    logger.info(
                        "Committed schedule creation from %s", proposal.source_bot
                    )
                elif proposal.action == "delete":
                    rule_result = await db.execute(
                        select(NotificationRule).where(
                            NotificationRule.id == proposal.rule_id,
                            NotificationRule.membership_id == membership_id,
                        )
                    )
                    rule = rule_result.scalar_one_or_none()
                    if rule:
                        rule.is_active = False
                        await db.execute(
                            update(ScheduledTask)
                            .where(
                                ScheduledTask.rule_id == rule.id,
                                ScheduledTask.status == "pending",
                            )
                            .values(status="cancelled")
                        )
                        logger.info(
                            "Committed schedule deletion from %s",
                            proposal.source_bot,
                        )
                    else:
                        logger.warning(
                            "Ignored schedule deletion from %s: "
                            "rule_id=%s not found for membership_id=%s "
                            "(out-of-scope or missing)",
                            proposal.source_bot,
                            proposal.rule_id,
                            membership_id,
                        )

            await db.flush()
            await sp.commit()
            sp = None
        except Exception:
            if sp is not None:
                await sp.rollback()
            logger.exception("Failed to process schedule proposal: %s", raw)

    # Process telemetry proposals (FEEDBACK bot only)
    for proposal in collector.telemetry_proposals:
        sp = None
        try:
            sp = await db.begin_nested()
            today = datetime.now(UTC).date()
            log_result = await db.execute(
                select(DailyInterventionLog)
                .join(
                    Participation,
                    DailyInterventionLog.participation_id == Participation.id,
                )
                .where(
                    Participation.membership_id == membership_id,
                    DailyInterventionLog.intervention_date == today,
                )
            )
            log = log_result.scalar_one_or_none()
            if log is not None:
                log.extracted_state = {
                    **(log.extracted_state or {}),
                    **proposal.get("state_updates", {}),
                }
                db.add(log)
            await db.flush()
            await sp.commit()
            sp = None
        except Exception:
            if sp is not None:
                await sp.rollback()
            logger.exception("Failed to process telemetry proposal: %s", proposal)

    if profile_changed:
        await save_user_profile(db, membership_id, profile, flush=False)

    # Final flush for all changes (audit logs, memory items, profile updates, schedules)
    await db.flush()

    return profile
