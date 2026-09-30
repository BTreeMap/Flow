"""SQLAlchemy 2.x declarative models for the HCI research platform.

This package preserves the historical flat import surface: importing model
classes directly from ``app.models`` continues to work unchanged.
"""

from __future__ import annotations

from app.models.base import Base
from app.models.core import (
    Conversation,
    ParticipantContact,
    Project,
    ProjectInvite,
    ProjectMembership,
)
from app.models.experiment import (
    DailyInterventionLog,
    DailySummary,
    Participation,
)
from app.models.messaging import (
    ConversationEvent,
    ConversationRuntimeState,
    ConversationTurn,
    Message,
)
from app.models.notifications import (
    Notification,
    NotificationDelivery,
    NotificationRule,
    NotificationRuleState,
    PushSubscription,
    ScheduledTask,
)
from app.models.profile import (
    FlowUserProfile,
    MemoryItem,
    PatchAuditLog,
    UserProfileStore,
)
from app.models.spark_research import (
    SparkFingerprintObservation,
    SparkInteraction,
    SparkParticipant,
)

__all__ = [
    "Base",
    "Conversation",
    "ConversationEvent",
    "ConversationRuntimeState",
    "ConversationTurn",
    "DailyInterventionLog",
    "DailySummary",
    "FlowUserProfile",
    "MemoryItem",
    "Message",
    "Notification",
    "NotificationDelivery",
    "NotificationRule",
    "NotificationRuleState",
    "ParticipantContact",
    "Participation",
    "PatchAuditLog",
    "Project",
    "ProjectInvite",
    "ProjectMembership",
    "PushSubscription",
    "ScheduledTask",
    "SparkFingerprintObservation",
    "SparkInteraction",
    "SparkParticipant",
    "UserProfileStore",
]
