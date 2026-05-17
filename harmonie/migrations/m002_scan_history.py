"""Scan history.

Adds the ``scans`` and ``scan_failures`` tables for persistent
scan-history bookkeeping.
"""

from __future__ import annotations

import sqlite3

_STATEMENTS = [
    """
    CREATE TABLE scans (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at         REAL    NOT NULL,
        finished_at        REAL,
        duration_sec       REAL,
        -- Counters mirroring ScanStatus, populated when the scan completes.
        discovered         INTEGER NOT NULL DEFAULT 0,
        full               INTEGER NOT NULL DEFAULT 0,
        descriptors_only   INTEGER NOT NULL DEFAULT 0,
        skipped            INTEGER NOT NULL DEFAULT 0,
        failed             INTEGER NOT NULL DEFAULT 0,
        removed            INTEGER NOT NULL DEFAULT 0,
        -- Configuration captured at scan start.
        workers            INTEGER NOT NULL,
        backend            TEXT    NOT NULL,
        model              TEXT    NOT NULL,
        forced             INTEGER NOT NULL DEFAULT 0,
        harmonie_version   TEXT    NOT NULL,
        descriptor_version INTEGER NOT NULL,
        -- Outcome. running | completed | crashed.
        state              TEXT    NOT NULL,
        last_error         TEXT
    )
    """,
    "CREATE INDEX idx_scans_started_at ON scans(started_at DESC)",
    """
    CREATE TABLE scan_failures (
        scan_id    INTEGER NOT NULL,
        path       TEXT    NOT NULL,
        error      TEXT    NOT NULL,
        failed_at  REAL    NOT NULL,
        size       INTEGER,
        mtime      REAL,
        FOREIGN KEY (scan_id) REFERENCES scans(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX idx_scan_failures_scan_id ON scan_failures(scan_id)",
    "CREATE INDEX idx_scan_failures_path    ON scan_failures(path)",
]


def upgrade(conn: sqlite3.Connection) -> None:
    for stmt in _STATEMENTS:
        conn.execute(stmt)
