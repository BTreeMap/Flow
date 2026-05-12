"""Tests for prompt context: default timezone, worker prompt, specialist prompt context, display name."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import clear_config_cache, get_default_timezone


# ---------------------------------------------------------------------------
# Default timezone fallback (config helper)
# ---------------------------------------------------------------------------


class TestDefaultTimezone:
    def setup_method(self) -> None:
        clear_config_cache()

    def teardown_method(self) -> None:
        os.environ.pop("TZ", None)
        clear_config_cache()

    def test_no_tz_env_defaults_to_america_toronto(self) -> None:
        os.environ.pop("TZ", None)
        clear_config_cache()
        assert get_default_timezone() == "America/Toronto"

    def test_valid_tz_env_is_used(self) -> None:
        os.environ["TZ"] = "Europe/Berlin"
        clear_config_cache()
        assert get_default_timezone() == "Europe/Berlin"

    def test_invalid_tz_env_defaults_to_america_toronto(self) -> None:
        os.environ["TZ"] = "Narnia/Lamppost"
        clear_config_cache()
        assert get_default_timezone() == "America/Toronto"

    def test_empty_tz_env_defaults_to_america_toronto(self) -> None:
        os.environ["TZ"] = ""
        clear_config_cache()
        assert get_default_timezone() == "America/Toronto"


# ---------------------------------------------------------------------------
# Worker prompt-context regression test
# ---------------------------------------------------------------------------


class TestWorkerPromptContext:
    """Prove the worker LLM gets the actual current time, not stale preferred_time."""

    @pytest.mark.asyncio
    async def test_worker_uses_actual_current_time_not_preferred_time(self) -> None:
        """Profile preferred_time=11:15, but actual fire time is 17:00 Toronto.
        Time and display_name should be baked directly into the SystemMessage —
        no ChatPromptTemplate involved."""
        from langchain_core.messages import HumanMessage, SystemMessage

        from app.schemas.patches import UserProfileData

        profile = UserProfileData(
            prompt_anchor="morning jog",
            preferred_time="11:15",
        )

        # Simulate unified prompt context (time + display_name)
        fake_prompt_ctx = {
            "display_name": "Alice",
            "timezone": "America/Toronto",
            "current_date": "2026-01-15",
            "current_time": "17:00",
            "current_datetime": "2026-01-15 17:00",
        }

        captured_messages: list = []

        async def fake_ainvoke(messages, **kwargs) -> MagicMock:
            captured_messages.extend(messages)
            m = MagicMock()
            m.content = "Time to run!"
            return m

        mock_llm = MagicMock()
        mock_llm.ainvoke = fake_ainvoke

        with (
            patch("app.worker.notification_worker.config") as mock_config,
            patch(
                "app.worker.notification_worker.load_user_profile",
                new_callable=AsyncMock,
            ) as mock_load,
            patch(
                "app.worker.notification_worker.ChatOpenAI",
                return_value=mock_llm,
            ),
            patch(
                "app.worker.notification_worker.get_prompt_context_for_membership",
                new_callable=AsyncMock,
                return_value=fake_prompt_ctx,
            ),
        ):
            mock_config.get_openai_api_key.return_value = "fake-key"
            mock_config.get_llm_model.return_value = "gpt-4o-mini"
            mock_load.return_value = profile

            from app.worker.notification_worker import _generate_custom_prompt

            fake_db = MagicMock()
            result = await _generate_custom_prompt(fake_db, 1, "Daily Nudge")

        assert result == "Time to run!"
        # Two messages: SystemMessage + HumanMessage
        assert len(captured_messages) == 2
        system_msg, human_msg = captured_messages
        assert isinstance(system_msg, SystemMessage)
        assert isinstance(human_msg, HumanMessage)
        # Time and display_name baked directly into system message content
        assert "17:00" in system_msg.content
        assert "America/Toronto" in system_msg.content
        assert "Alice" in system_msg.content
        # preferred_time must not appear in the human message
        assert "preferred_time" not in human_msg.content


# ---------------------------------------------------------------------------
# Specialist prompt context test
# ---------------------------------------------------------------------------


class TestSpecialistPromptContext:
    """Verify specialist prompts include localized time placeholders."""

    def test_coach_prompt_has_time_placeholders(self) -> None:
        from app.prompt_loader import load_prompt

        text = load_prompt("coach_system")
        assert "$current_date" in text
        assert "$current_time" in text
        assert "$timezone" in text

    def test_intake_prompt_has_time_placeholders(self) -> None:
        from app.prompt_loader import load_prompt

        text = load_prompt("intake_system")
        assert "$current_date" in text
        assert "$current_time" in text
        assert "$timezone" in text

    def test_feedback_prompt_has_time_placeholders(self) -> None:
        from app.prompt_loader import load_prompt

        text = load_prompt("feedback_system")
        assert "$current_date" in text
        assert "$current_time" in text
        assert "$timezone" in text

    def test_prompt_generator_has_authoritative_time_guidance(self) -> None:
        from app.prompt_loader import load_prompt

        text = load_prompt("prompt_generator_system")
        assert "$current_date" in text
        assert "$current_time" in text
        assert "$timezone" in text
        assert "$display_name" in text
        assert "authoritative" in text.lower()

    def test_specialist_agent_formats_time_into_prompt(self) -> None:
        """Verify _create_specialist_agent applies time context args to prompt text."""
        import string

        from app.prompt_loader import load_prompt

        raw = load_prompt("coach_system")
        args = {
            "display_name": "TestUser",
            "current_date": "2026-03-05",
            "current_time": "17:00",
            "timezone": "America/Toronto",
            "current_datetime": "2026-03-05 17:00",
        }
        formatted = string.Template(raw).safe_substitute(args)
        assert "17:00" in formatted
        assert "2026-03-05" in formatted
        assert "America/Toronto" in formatted
        assert "$current_time" not in formatted

    def test_format_survives_braces_in_display_name(self) -> None:
        """Regression: curly braces in display_name must not prevent time substitution."""
        import string

        from app.prompt_loader import load_prompt

        raw = load_prompt("coach_system")
        args = {
            "display_name": "User {test}",
            "current_date": "2026-03-05",
            "current_time": "17:00",
            "timezone": "America/Toronto",
            "current_datetime": "2026-03-05 17:00",
        }
        # format() would KeyError on {test}; string.Template must survive
        formatted = string.Template(raw).safe_substitute(args)
        assert "17:00" in formatted
        assert "$current_time" not in formatted
        # Unknown {test} is preserved harmlessly
        assert "{test}" in formatted

    def test_display_name_substituted_into_all_prompts(self) -> None:
        """Regression: display_name must appear in all specialist prompts."""
        import string

        from app.prompt_loader import load_prompt

        for prompt_name in (
            "intake_system",
            "coach_system",
            "feedback_system",
            "prompt_generator_system",
        ):
            raw = load_prompt(prompt_name)
            args = {
                "display_name": "Alice",
                "current_date": "2026-03-05",
                "current_time": "17:00",
                "timezone": "America/Toronto",
                "current_datetime": "2026-03-05 17:00",
            }
            formatted = string.Template(raw).safe_substitute(args)
            assert "Alice" in formatted, (
                f"{prompt_name} did not substitute display_name"
            )
            assert "$display_name" not in formatted, (
                f"{prompt_name} has unsubstituted $display_name"
            )


# ---------------------------------------------------------------------------
# Display name single source of truth (FlowUserProfile)
# ---------------------------------------------------------------------------


class TestDisplayNameFromFlowUserProfile:
    """Verify display_name is fetched from FlowUserProfile, not UserProfileData."""

    def test_user_profile_data_has_no_display_name_field(self) -> None:
        """UserProfileData must NOT have a display_name field (single source = FlowUserProfile)."""
        from app.schemas.patches import UserProfileData

        assert "display_name" not in UserProfileData.model_fields

    @pytest.mark.asyncio
    async def test_get_display_name_returns_name_from_flow_profile(self) -> None:
        """get_display_name_for_membership fetches from FlowUserProfile."""
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.id_utils import generate_project_id
        from app.models import (
            Base,
            FlowUserProfile,
            Project,
            ProjectMembership,
        )
        from app.services.profile_service import get_display_name_for_membership

        engine = create_async_engine("sqlite+aiosqlite://", echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as db:
            project = Project(id=generate_project_id(), display_name="Test")
            db.add(project)
            await db.flush()

            membership = ProjectMembership(
                project_id=project.id,
                user_id="u_testuser_000000000000000000",
                status="active",
            )
            db.add(membership)
            await db.flush()

            fp = FlowUserProfile(
                user_id="u_testuser_000000000000000000", display_name="Alice"
            )
            db.add(fp)
            await db.flush()

            name = await get_display_name_for_membership(db, membership.id)
            assert name == "Alice"

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    @pytest.mark.asyncio
    async def test_get_display_name_returns_none_when_no_profile(self) -> None:
        """get_display_name_for_membership returns None when FlowUserProfile is absent."""
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.id_utils import generate_project_id
        from app.models import Base, Project, ProjectMembership
        from app.services.profile_service import get_display_name_for_membership

        engine = create_async_engine("sqlite+aiosqlite://", echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as db:
            project = Project(id=generate_project_id(), display_name="Test")
            db.add(project)
            await db.flush()

            membership = ProjectMembership(
                project_id=project.id,
                user_id="u_testuser_000000000000000000",
                status="active",
            )
            db.add(membership)
            await db.flush()

            name = await get_display_name_for_membership(db, membership.id)
            assert name is None

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
