import asyncio
import os
import sys
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

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
        invite_code = "test-invite-code-123"
        code_hash = hashlib.sha256(invite_code.encode()).hexdigest()

        print(f"Seeding DB at {DATABASE_URL}...")

        # Ensure Project Exists
        project = await session.get(Project, project_id)
        if not project:
            project = Project(
                id=project_id,
                display_name="E2E Project",
                status="active",
                created_at=datetime.now(timezone.utc),
            )
            session.add(project)
            print(f"SEED_INFO: Created project {project_id}")
        else:
            print(f"SEED_INFO: Project {project_id} already exists")

        # Ensure Invite Exists and is Valid
        result = await session.execute(
            select(ProjectInvite).where(
                ProjectInvite.project_id == project_id,
                ProjectInvite.invite_code_hash == code_hash,
            )
        )
        invite = result.scalar_one_or_none()

        if not invite:
            invite = ProjectInvite(
                project_id=project_id,
                invite_code_hash=code_hash,
                expires_at=datetime.now(timezone.utc) + timedelta(days=365),
                max_uses=None,  # Unlimited uses
                uses=0,
                label="e2e-test",
            )
            session.add(invite)
            print(f"SEED_INFO: Created invite {invite_code}")
        else:
            # Reset existing invite to be valid
            invite.expires_at = datetime.now(timezone.utc) + timedelta(days=365)
            invite.max_uses = None  # Unlimited
            invite.revoked_at = None
            print(f"SEED_INFO: Reset existing invite {invite_code}")

        try:
            await session.commit()
            print(f"SEED_SUCCESS: {project_id} {invite_code}")
        except Exception as e:
            print(f"SEED_ERROR: {e}")
            await session.rollback()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
