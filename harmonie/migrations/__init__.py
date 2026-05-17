"""Schema migrations.

Migrations live as one file per version in this package, named
``mNNN_description.py``. Each defines a top-level ``upgrade(conn)``
callable that issues whatever DDL is needed to bring the DB from
``NNN-1`` to ``NNN``. The runner discovers them on import, sorts by
version, and applies any that are pending.

The DB stores the version it has been migrated to in
``meta.schema_version``. Each migration runs in its own transaction; a
partial failure rolls back and leaves the DB at the previous version.

Opening a DB at a version newer than this binary supports raises
:class:`MigrationError`.

Adding a migration:

1. Create ``harmonie/migrations/mNNN_short_description.py`` where ``NNN``
   is the next version number, zero-padded to three digits.
2. Define ``def upgrade(conn: sqlite3.Connection) -> None:`` and put the
   DDL inside.
3. Update any code in ``db.py`` that depends on the new shape (column
   lists in upserts, etc.).

Existing migration files don't change after they've shipped. New
changes are new migrations.
"""

from __future__ import annotations

import contextlib
import importlib
import logging
import pkgutil
import re
import sqlite3
from typing import Callable

logger = logging.getLogger("harmonie.migrations")


class MigrationError(RuntimeError):
    """Raised when migrations cannot proceed (e.g. the DB is from a newer
    harmonie binary than the one trying to open it, or migration files
    are misnamed)."""


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

_MIGRATION_FILENAME_RE = re.compile(r"^m(\d{3})_[A-Za-z0-9_]+$")


def _discover_migrations() -> list[Callable[[sqlite3.Connection], None]]:
    """Scan this package for ``mNNN_*`` modules and return their ``upgrade``
    callables sorted by version. Versions must be contiguous starting at 1."""
    found: list[tuple[int, str, Callable[[sqlite3.Connection], None]]] = []
    for modinfo in pkgutil.iter_modules(__path__):
        match = _MIGRATION_FILENAME_RE.match(modinfo.name)
        if match is None:
            continue
        module = importlib.import_module(f"{__name__}.{modinfo.name}")
        upgrade = getattr(module, "upgrade", None)
        if not callable(upgrade):
            raise MigrationError(
                f"migration module {modinfo.name!r} has no callable "
                f"`upgrade(conn)` function"
            )
        found.append((int(match.group(1)), modinfo.name, upgrade))

    found.sort(key=lambda t: t[0])

    versions = [v for v, _, _ in found]
    expected = list(range(1, len(found) + 1))
    if versions != expected:
        raise MigrationError(
            f"migration versions must be a contiguous sequence starting at "
            f"1; found {versions}"
        )

    return [fn for _, _, fn in found]


# Discovered at import time. Tests may monkeypatch this list along with
# CURRENT_SCHEMA_VERSION to exercise the runner.
MIGRATIONS: list[Callable[[sqlite3.Connection], None]] = _discover_migrations()

CURRENT_SCHEMA_VERSION = len(MIGRATIONS)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def _migration_label(fn: Callable[..., object]) -> str:
    """Pretty name for logging. For migrations defined in this package the
    module's short name (``m001_initial``) is more useful than the generic
    ``upgrade``; for ad-hoc callables (e.g. in tests) ``__name__`` is fine."""
    mod = getattr(fn, "__module__", "") or ""
    if mod.startswith(f"{__name__}.") and mod != __name__:
        return mod.rsplit(".", 1)[-1]
    return getattr(fn, "__name__", "<unknown>")


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Return the version the DB has been migrated to. 0 for a fresh DB."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='meta'"
    )
    if cur.fetchone() is None:
        return 0
    row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    return int(row[0]) if row else 0


def _ensure_meta_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS meta ("
        "    key TEXT PRIMARY KEY,"
        "    value TEXT NOT NULL"
        ")"
    )
    conn.commit()


def run_migrations(conn: sqlite3.Connection) -> None:
    """Apply pending migrations. Idempotent.

    Raises :class:`MigrationError` if the DB is at a version this binary
    doesn't know about (i.e. it was written by a newer harmonie).
    """
    _ensure_meta_table(conn)
    current = get_schema_version(conn)

    if current > CURRENT_SCHEMA_VERSION:
        raise MigrationError(
            f"database is at schema version {current}, but this harmonie "
            f"binary only supports up to version {CURRENT_SCHEMA_VERSION}. "
            f"Refusing to run — upgrade the binary, or restore an older "
            f"snapshot of the database."
        )

    if current == CURRENT_SCHEMA_VERSION:
        logger.debug("schema up to date at version %d", current)
        return

    pending = list(range(current, CURRENT_SCHEMA_VERSION))
    logger.info(
        "applying %d migration(s): %s",
        len(pending),
        ", ".join(str(i + 1) for i in pending),
    )

    # Python's sqlite3 driver, in its default isolation mode, implicitly
    # commits any pending transaction *before* executing a DDL statement
    # (CREATE TABLE, ALTER, DROP, …). That means a `CREATE TABLE` inside a
    # migration that later fails is already committed — `conn.rollback()`
    # has nothing to undo. To get real transactional DDL we switch to
    # autocommit mode (isolation_level=None) for the duration of the
    # migration loop and bracket each migration with explicit BEGIN/COMMIT
    # /ROLLBACK statements.
    original_isolation = conn.isolation_level
    conn.isolation_level = None
    try:
        for i in pending:
            version = i + 1
            fn = MIGRATIONS[i]
            label = _migration_label(fn)
            logger.info("migration %d → applying %s", version, label)
            try:
                conn.execute("BEGIN")
                fn(conn)
                conn.execute(
                    "INSERT OR REPLACE INTO meta(key, value) "
                    "VALUES('schema_version', ?)",
                    (str(version),),
                )
                conn.execute("COMMIT")
            except Exception:
                with contextlib.suppress(sqlite3.OperationalError):
                    # No active transaction.
                    conn.execute("ROLLBACK")
                logger.exception(
                    "migration %d (%s) failed; rolled back to version %d",
                    version,
                    label,
                    version - 1,
                )
                raise
    finally:
        conn.isolation_level = original_isolation

    logger.info("schema migrated to version %d", CURRENT_SCHEMA_VERSION)
