import time
import pytest
import pytest_asyncio
from unittest.mock import MagicMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.models import Base, PushSubscription, ProjectMembership, Project
from app.db import get_db
from app.id_utils import generate_project_id
from app.config import clear_config_cache
from h4ckath0n.auth.dependencies import _get_current_user
from h4ckath0n.auth.models import Base as H4ckath0nBase
from app.main import app

# Setup test DB
_test_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_test_session_factory = async_sessionmaker(_test_engine, expire_on_commit=False)


async def _override_get_db():
    async with _test_session_factory() as session:
        yield session


def _make_fake_user(user_id="u_admin", role="admin"):
    user = MagicMock()
    user.id = user_id
    user.role = role
    user.email = "admin@example.com"
    return user


def _override_require_admin():
    return _make_fake_user(role="admin")


@pytest_asyncio.fixture
async def client():
    # Clear VAPID cache before and after test
    clear_config_cache()

    # Override dependencies
    app.dependency_overrides[get_db] = _override_get_db
    # Override _get_current_user to return an admin user
    # Note: require_admin internally depends on _get_current_user
    app.dependency_overrides[_get_current_user] = _override_require_admin

    # Create tables
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(H4ckath0nBase.metadata.create_all)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    clear_config_cache()
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(H4ckath0nBase.metadata.drop_all)


@pytest.mark.asyncio
async def test_admin_push_test_performance(client, monkeypatch):
    # Mock vapid keys
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "public")
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "private")
    monkeypatch.setenv("VAPID_CLAIM_SUB", "mailto:admin@example.com")

    # Mock webpush to simulate latency
    mock_webpush = MagicMock()

    # We need to mock asyncio.to_thread to actually run the mock_webpush side_effect in a way that we can control or measure,
    # but the code uses asyncio.to_thread(webpush, ...).
    # Since asyncio.to_thread runs in a separate thread, we can just make the mock sleep.

    def slow_webpush(*args, **kwargs):
        time.sleep(0.1)  # Simulate 100ms latency
        return "ok"

    mock_webpush.side_effect = slow_webpush

    # We need to patch where webpush is imported in routes.py
    # But it is imported inside the function: from pywebpush import webpush
    # So we need to patch sys.modules or similar, or mock pywebpush before the function is called.

    import pywebpush

    monkeypatch.setattr(pywebpush, "webpush", slow_webpush)

    # Setup data: 10 subscriptions
    num_subs = 10
    project_id = generate_project_id()

    async with _test_session_factory() as db:
        project = Project(id=project_id, display_name="Test Project")
        db.add(project)
        await db.flush()

        sub_ids = []
        for i in range(num_subs):
            membership = ProjectMembership(
                project_id=project_id, user_id=f"u_user_{i}", status="active"
            )
            db.add(membership)
            await db.flush()

            sub = PushSubscription(
                user_id=f"u_test_{i:025d}",
                endpoint=f"https://example.com/push/{i}",
                p256dh="key",
                auth="auth",
                user_agent="TestAgent",
            )
            db.add(sub)
            await db.flush()
            sub_ids.append(sub.id)

        await db.commit()

    # Run the test
    start_time = time.time()
    resp = await client.post(
        "/admin/push/test",
        json={
            "project_id": project_id,
            "subscription_ids": sub_ids,
            "title": "Test",
            "body": "Body",
        },
    )
    end_time = time.time()

    assert resp.status_code == 200, f"Response: {resp.text}"
    data = resp.json()
    assert len(data["results"]) == num_subs
    assert all(r["ok"] for r in data["results"])

    duration = end_time - start_time
    print(f"\nDuration for {num_subs} subs: {duration:.4f}s")

    # If serial: ~1.0s (10 * 0.1)
    # If parallel: ~0.1s (plus overhead)
    # With 10 subs and 0.1s delay, concurrent execution should be much faster than 1s.
    assert duration < 0.5, f"Execution took too long: {duration:.4f}s"

    return duration
