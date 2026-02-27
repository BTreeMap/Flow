import asyncio
import os
import sys
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Add api directory to path to import app modules if needed
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.models import Project, ProjectInvite
import hashlib
from datetime import datetime, timedelta, timezone

DATABASE_URL = os.environ.get(
    "H4CKATH0N_DATABASE_URL", "sqlite+aiosqlite:////tmp/flow-e2e.db"
)


async def seed():
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with async_session() as session:
        # Valid Project ID: p + 31 chars from [a-z2-7] (base32)
        # 31 chars: testproject12345678901234567890
        project_id = "ptestproject123456789012345678901"

        print(f"Seeding DB at {DATABASE_URL}...")

        # Create Project
        project = Project(
            id=project_id,
            display_name="E2E Project",
            status="active",
            created_at=datetime.now(timezone.utc),
        )
        session.add(project)

        # Create Invite
        invite_code = "test-invite-code-123"
        code_hash = hashlib.sha256(invite_code.encode()).hexdigest()

        invite = ProjectInvite(
            project_id=project_id,
            invite_code_hash=code_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            max_uses=10,
            uses=0,
            label="e2e-test",
        )
        session.add(invite)

        try:
            await session.commit()
            print(f"SEED_SUCCESS: {project_id} {invite_code}")
        except Exception as e:
            print(f"SEED_ERROR: {e}")
            await session.rollback()
            # If unique constraint violation, maybe it already exists?
            pass

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
