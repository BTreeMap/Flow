import asyncio
import sys
import os

# Add api directory to sys.path
sys.path.append(os.getcwd())

from sqlalchemy import text
from app.db import init_db, engine


async def main():
    print("Initializing DB...")
    await init_db()

    print("Verifying tables...")
    async with engine.connect() as conn:
        # Check dialect
        if engine.dialect.name == "sqlite":
            query = "SELECT name FROM sqlite_master WHERE type='table';"
        else:
            # Postgres
            query = "SELECT table_name FROM information_schema.tables WHERE table_schema='public';"

        result = await conn.execute(text(query))
        tables = [row[0] for row in result.all()]
        print("Tables found:", tables)

        # Verify unified notification engine tables exist
        required = [
            "notifications",
            "notification_rules",
            "notification_rule_state",
            "notification_deliveries",
            "push_subscriptions",
        ]
        missing = [t for t in required if t not in tables]
        if missing:
            print(f"FAILURE: Missing tables: {missing}")
            sys.exit(1)
        # Verify legacy tables have been dropped
        legacy = [t for t in ["outbox_events", "nudge_schedules"] if t in tables]
        if legacy:
            print(f"WARNING: Legacy tables still present: {legacy}")
        print("SUCCESS: Unified notification tables found.")


if __name__ == "__main__":
    asyncio.run(main())
