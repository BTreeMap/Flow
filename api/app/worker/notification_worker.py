"""Unified notification worker: rule polling → instance creation → delivery sending.

Single worker process — no legacy outbox events.

This module is the worker *orchestrator*. The nudge/prompt generation lives in
:mod:`app.worker.nudge` and the push-delivery sending lives in
:mod:`app.worker.delivery`. The dependencies that tests monkeypatch on
``app.worker.notification_worker`` — ``async_session_factory`` and
``_generate_condition_nudge`` — are imported into this module's globals on
purpose, so that ``monkeypatch.setattr(worker_module, ...)`` continues to affect
the orchestration functions defined here.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError

from app import config
from app import healthcheck as health
from app.db import async_session_factory
from app.id_utils import generate_server_msg_id
from app.logging_conf import configure_logging
from app.models import (
    Conversation,
    Message,
    Notification,
    NotificationDelivery,
    NotificationRule,
    NotificationRuleState,
    Participation,
    ProjectMembership,
    ScheduledTask,
)
from app.services.event_service import persist_event
from app.services.notification_engine import (
    claim_due_rules,
    compute_local_date_for_rule,
    get_user_timezone,
    recompute_rule_due_time,
)
from app.worker.delivery import MAX_ATTEMPTS, _process_due_deliveries
from app.worker.nudge import _generate_condition_nudge
from app.worker.tasks import _create_feedback_request

logger = logging.getLogger(__name__)

FAILED_EVENT_POSTPONE_DAYS = 3650
LOCK_DURATION_SECONDS = 300


def _write_heartbeat() -> None:
    """Refresh the worker heartbeat file used by the container healthcheck.

    The heartbeat lives in a container-local temp path (``health.HEARTBEAT_PATH``),
    never on the shared data volume, so only this worker container observes it.

    Best-effort: a failure to write must never crash the worker loop, so it is
    logged at WARNING and the loop continues. A persistently unwritable heartbeat
    will surface as an unhealthy container, which is the intended signal.
    """
    path = health.HEARTBEAT_PATH
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(datetime.now(UTC).isoformat())
    except OSError as exc:
        logger.warning("Failed to write worker heartbeat to %s: %s", path, exc)


def _make_worker_id() -> str:
    base = config.get_worker_id()
    return f"{base}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Rule processing
# ---------------------------------------------------------------------------


async def _evaluate_due_rules(worker_id: str) -> int:
    """Claim and evaluate due notification rules. Returns count processed."""
    processed = 0
    async with async_session_factory() as db:
        pairs = await claim_due_rules(db, worker_id)
        await db.commit()

    for rule, _state in pairs:
        try:
            await _process_rule(rule.id, worker_id)
            processed += 1
        except Exception as exc:
            logger.error("Failed processing rule %s: %s", rule.id, exc)
    return processed


async def _process_rule(rule_id: int, worker_id: str) -> None:
    """Evaluate a single notification rule: create instance + delivery, advance state."""
    async with async_session_factory() as db:
        rule_result = await db.execute(
            select(NotificationRule).where(NotificationRule.id == rule_id)
        )
        rule = rule_result.scalar_one_or_none()
        state_result = await db.execute(
            select(NotificationRuleState).where(
                NotificationRuleState.rule_id == rule_id,
                NotificationRuleState.locked_by == worker_id,
            )
        )
        state = state_result.scalar_one_or_none()
        if not rule or not state:
            return

        if not rule.is_active:
            state.locked_by = None
            state.claimed_at = None
            state.locked_until = None
            state.next_due_at_utc = None
            await db.commit()
            return

        try:
            config_data = json.loads(rule.config_json)
            topic = config_data.get("topic", "Daily Nudge")
            user_tz = await get_user_timezone(db, rule.membership_id)

            # Compute local date for idempotency
            fire_utc = state.next_due_at_utc or datetime.now(UTC)
            local_date = compute_local_date_for_rule(rule, user_tz, fire_utc)
            dedupe_key = f"rule:{rule.id}:{local_date.isoformat()}"

            # Idempotency check — advance if already fired
            existing = await db.execute(
                select(Notification).where(Notification.dedupe_key == dedupe_key)
            )
            if existing.scalar_one_or_none():
                await recompute_rule_due_time(db, rule, state)
                await db.commit()
                return

            # Get or create conversation
            conversation_result = await db.execute(
                select(Conversation).where(
                    Conversation.membership_id == rule.membership_id
                )
            )
            conversation = conversation_result.scalar_one_or_none()
            if not conversation:
                conversation = Conversation(membership_id=rule.membership_id)
                db.add(conversation)
                await db.flush()

            # Determine project_id
            mem_result = await db.execute(
                select(ProjectMembership).where(
                    ProjectMembership.id == rule.membership_id
                )
            )
            membership = mem_result.scalar_one()
            project_id = membership.project_id

            # Generate content (condition-aware)
            content, condition_source = await _generate_condition_nudge(
                db, rule.membership_id, topic
            )

            # Resolve participation for traceability (tagging messages).
            participation_result = await db.execute(
                select(Participation)
                .where(Participation.membership_id == rule.membership_id)
                .order_by(Participation.id.desc())
                .limit(1)
            )
            participation = participation_result.scalar_one_or_none()

            # Persist Message (idempotent via client_msg_id = dedupe_key)
            server_msg_id = generate_server_msg_id()
            message = Message(
                conversation_id=conversation.id,
                role="assistant",
                content=content,
                server_msg_id=server_msg_id,
                client_msg_id=dedupe_key,
                condition_source=condition_source or "SYSTEM",
                participation_id=participation.id if participation else None,
            )
            db.add(message)
            await db.flush()
            await persist_event(
                db,
                conversation.id,
                "message.final",
                {
                    "message_id": message.id,
                    "server_msg_id": message.server_msg_id,
                    "role": "assistant",
                    "content": message.content,
                    "created_at": message.created_at.isoformat()
                    if message.created_at
                    else datetime.now(UTC).isoformat(),
                },
            )

            # Persist notification instance
            notification = Notification(
                membership_id=rule.membership_id,
                title=topic,
                body=content,
                payload_json=json.dumps(
                    {
                        "rule_id": rule.id,
                        "server_msg_id": server_msg_id,
                        "project_id": project_id,
                    }
                ),
                rule_id=rule.id,
                local_date=local_date,
                dedupe_key=dedupe_key,
            )
            db.add(notification)
            await db.flush()

            # Create push delivery with proper payload conventions
            chat_url = f"/p/{project_id}/chat?nid={notification.id}"
            delivery = NotificationDelivery(
                instance_id=notification.id,
                membership_id=rule.membership_id,
                user_id=membership.user_id,
                channel="push_notify",
                payload_json=json.dumps(
                    {
                        "title": topic,
                        "body": content,
                        "url": chat_url,
                        "data": {
                            "notification_id": notification.id,
                            "project_id": project_id,
                            "membership_id": rule.membership_id,
                            "rule_id": rule.id,
                            "action": "notify",
                        },
                    }
                ),
                run_at_utc=datetime.now(UTC),
            )
            db.add(delivery)

            if config.is_feedback_loop_enabled():
                actions = config.build_feedback_actions()
                task = ScheduledTask(
                    membership_id=rule.membership_id,
                    rule_id=rule.id,
                    parent_instance_id=notification.id,
                    task_type="feedback_request",
                    payload_json=json.dumps(
                        {
                            "text": config.get_feedback_prompt_text(),
                            "actions": actions,
                        }
                    ),
                    run_at_utc=datetime.now(UTC)
                    + timedelta(minutes=config.get_feedback_delay_minutes()),
                )
                db.add(task)

            # Advance rule state to next occurrence
            await recompute_rule_due_time(db, rule, state)
            await db.commit()

            logger.info(
                "Rule %s fired: notification %s, message %s",
                rule.id,
                notification.id,
                message.id,
            )

        except IntegrityError:
            # Dedupe collision — another worker already fired this rule.
            # After rollback, the original db session's ORM objects are invalidated,
            # so we must open a fresh session (db2) to advance the rule state.
            await db.rollback()
            async with async_session_factory() as db2:
                rule_r = await db2.execute(
                    select(NotificationRule).where(NotificationRule.id == rule_id)
                )
                rule2 = rule_r.scalar_one_or_none()
                state_r = await db2.execute(
                    select(NotificationRuleState).where(
                        NotificationRuleState.rule_id == rule_id
                    )
                )
                state2 = state_r.scalar_one_or_none()
                if rule2 and state2:
                    await recompute_rule_due_time(db2, rule2, state2)
                    await db2.commit()
            logger.info("Rule %s: dedupe collision, advancing state", rule_id)

        except Exception as exc:
            await db.rollback()
            state_result = await db.execute(
                select(NotificationRuleState).where(
                    NotificationRuleState.rule_id == rule_id
                )
            )
            state = state_result.scalar_one_or_none()
            if state:
                state.attempts += 1
                state.last_error = str(exc)
                state.locked_by = None
                state.claimed_at = None
                state.locked_until = None
                if state.attempts >= MAX_ATTEMPTS:
                    state.next_due_at_utc = datetime.now(UTC) + timedelta(
                        days=FAILED_EVENT_POSTPONE_DAYS
                    )
                else:
                    state.next_due_at_utc = datetime.now(UTC) + timedelta(
                        minutes=2 ** min(state.attempts, 8)
                    )
                await db.commit()
            raise


# ---------------------------------------------------------------------------
# Scheduled task processing
# ---------------------------------------------------------------------------


async def _process_scheduled_tasks(worker_id: str) -> int:
    """Claim and process due delayed tasks."""
    processed = 0
    now = datetime.now(UTC)
    locked_until = now + timedelta(seconds=LOCK_DURATION_SECONDS)

    async with async_session_factory() as db:
        id_query = (
            select(ScheduledTask.id)
            .where(
                ScheduledTask.run_at_utc <= now,
                ScheduledTask.status == "pending",
                or_(
                    ScheduledTask.locked_until.is_(None),
                    ScheduledTask.locked_until < now,
                ),
            )
            .order_by(ScheduledTask.run_at_utc.asc())
            .limit(20)
        )
        if db.bind and db.bind.dialect.name == "postgresql":
            id_query = id_query.with_for_update(skip_locked=True)

        task_ids = [tid for (tid,) in (await db.execute(id_query)).all()]
        if not task_ids:
            return 0

        await db.execute(
            update(ScheduledTask)
            .where(ScheduledTask.id.in_(task_ids))
            .values(locked_by=worker_id, locked_until=locked_until)
        )

        tasks = (
            (
                await db.execute(
                    select(ScheduledTask).where(ScheduledTask.id.in_(task_ids))
                )
            )
            .scalars()
            .all()
        )

        for task in tasks:
            try:
                if task.rule_id is not None:
                    rule_result = await db.execute(
                        select(NotificationRule).where(
                            NotificationRule.id == task.rule_id
                        )
                    )
                    parent_rule = rule_result.scalar_one_or_none()
                    if parent_rule is None or not parent_rule.is_active:
                        logger.info(
                            "Cancelling scheduled task %s: parent rule is inactive",
                            task.id,
                        )
                        task.status = "cancelled"
                        task.locked_by = None
                        task.locked_until = None
                        continue

                if task.task_type == "feedback_request":
                    await _create_feedback_request(db, task, now)

                task.status = "completed"
                processed += 1
            except Exception as exc:
                logger.error("Task execution failed for %s: %s", task.id, exc)
                task.status = "failed"
                task.locked_by = None
                task.locked_until = None

        await db.commit()
    return processed


# ---------------------------------------------------------------------------
# Main worker loop
# ---------------------------------------------------------------------------


async def run_worker_loop(poll_seconds: int = 5) -> None:
    """Single unified worker loop: poll rules → process deliveries → sleep."""
    worker_id = _make_worker_id()
    logger.info("Notification worker started: %s", worker_id)

    while True:
        # Refresh the liveness heartbeat at the top of every iteration so a
        # wedged loop (e.g. a hung DB call) lets the heartbeat go stale and the
        # container is reported unhealthy.
        _write_heartbeat()

        # 1. Rule-based notification engine
        try:
            await _evaluate_due_rules(worker_id)
        except Exception as exc:
            logger.error("Rule evaluation error: %s", exc)

        # 2. Delivery processing
        try:
            await _process_scheduled_tasks(worker_id)
        except Exception as exc:
            logger.error("Scheduled task processing error: %s", exc)

        # 3. Delivery processing
        try:
            await _process_due_deliveries(worker_id)
        except Exception as exc:
            logger.error("Delivery processing error: %s", exc)

        await asyncio.sleep(poll_seconds)


def main() -> None:
    configure_logging()
    from app.diagnostics import log_startup_report

    log_startup_report("worker")
    asyncio.run(run_worker_loop())


if __name__ == "__main__":
    main()
