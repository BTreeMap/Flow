# Database & migration discipline

**Premise: data integrity is guaranteed at all efforts.** Refactoring is encouraged, but
"free to refactor" never means "free to break persisted data." Every change to the
database schema or ORM models ships with an Alembic migration in the same change.

## Hard rule
If you add, remove, rename, or retype any column/table/index — or change any SQLAlchemy
model under [`api/app/models/`](../../api/app/models/) — you **must**:

1. Generate a matching Alembic revision under
   [`api/app/db_migrations/versions/`](../../api/app/db_migrations/versions/).
2. Provide both `upgrade()` and a correct `downgrade()`.
3. Preserve existing rows — backfill/transform data rather than dropping it. If a column
   is being replaced, migrate values across before removing the old column.
4. Keep the migration runnable on **both** SQLite (`sqlite+aiosqlite`) and Postgres
   (`postgresql+asyncpg`) — tests use SQLite, prod/CI use Postgres.
5. Update or add a test in [`api/tests/test_migrations.py`](../../api/tests/test_migrations.py).

Do not rely on `init_db()`/`create_all` to absorb schema drift — that path is a
test-environment fallback only and does not migrate existing data.

## How migrations work here
- **Migration dir:** `api/app/db_migrations/` (separate Alembic env from h4ckath0n).
- **Version table:** `flow_alembic_version`.
- **Runner:** [`api/app/db_migrations/migrate.py`](../../api/app/db_migrations/migrate.py)
  exposes `upgrade_to_head()` and `stamp_head()`.
- **Startup:** the app lifespan runs `upgrade_to_head()` automatically (with an
  `init_db()` fallback for tests).
- **URL normalization:** async driver prefixes are converted to sync for Alembic
  (`sqlite+aiosqlite`→`sqlite`, `postgresql+asyncpg`→`postgresql+psycopg`).
- **Naming:** zero-padded sequential prefix matching the latest file, e.g. the next
  revision after `0012_add_daily_summaries_table.py` is `0013_<slug>.py`.

## Authoring a revision
Run Alembic against a sync URL (use `get_sync_url()` semantics). Autogenerate, then
**review and hand-edit** — autogenerate misses data backfills and some constraint
renames.

```bash
cd api
uv run alembic -c app/db_migrations/alembic.ini revision \
  --autogenerate -m "0013 <short description>"
# review the generated file, add data backfill + a real downgrade(), then verify:
uv run pytest tests/test_migrations.py -v
```

## Postgres-vs-SQLite gotcha (read before writing DB code)
Postgres aborts the whole transaction after a caught statement error; SQLite does not.
A `try/except` around a DB write that swallows the error without rolling back will pass
SQLite tests but 500 in prod ("current transaction is aborted"). Wrap each risky write
in a SAVEPOINT and roll back on failure:

```python
sp = await db.begin_nested()
try:
    db.add(obj)
    await db.flush()
    await sp.commit()
except Exception:
    await sp.rollback()
    raise
```

All database URLs must use async drivers (`aiosqlite` / `asyncpg`). No `psycopg2` or
sync Postgres drivers in application code.
