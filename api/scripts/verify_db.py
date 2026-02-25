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

        if "nudge_schedules" in tables and "notifications" in tables:
            print("SUCCESS: New tables found.")
        else:
            print("FAILURE: New tables missing.")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
