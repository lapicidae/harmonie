"""Initial schema.

Tracks table with embedding + descriptors + tags + library-relative
paths, plus the per-track styles classification table and all current
indexes.
"""

from __future__ import annotations

import sqlite3

_STATEMENTS = [
    """
    CREATE TABLE tracks (
        id                    INTEGER PRIMARY KEY AUTOINCREMENT,
        path                  TEXT    UNIQUE NOT NULL,
        -- Library-aware addressing for clients that mount paths differently.
        library_root          TEXT,
        relative_path         TEXT,
        size                  INTEGER NOT NULL,
        mtime                 REAL    NOT NULL,
        duration              REAL    NOT NULL,
        embedding             BLOB    NOT NULL,
        embedding_dim         INTEGER NOT NULL,
        model                 TEXT    NOT NULL,
        -- Versioning so a descriptor algo bump doesn't force re-running TF.
        descriptor_version    INTEGER NOT NULL,
        -- Musical descriptors. NULL = algorithm couldn't extract.
        bpm                   REAL,
        bpm_confidence        REAL,
        key                   TEXT,
        scale                 TEXT,
        key_strength          REAL,
        loudness           REAL,
        danceability          REAL,
        onset_rate            REAL,
        -- Tags from the file itself (mutagen). Used by external clients to
        -- match harmonie tracks back to their own catalog without
        -- filesystem walks.
        artist                TEXT,
        album                 TEXT,
        title                 TEXT,
        track_number          INTEGER,
        -- Full 400-d Discogs style activation vector (float32 BLOB) from
        -- the genre classifier head. Top-K labels broken out into the
        -- track_styles table for fast filtering. NULL = no styles extracted
        -- (e.g. musicextractor backend, or the head was unavailable at
        -- scan time).
        style_activations     BLOB,
        analyzed_at           REAL    NOT NULL
    )
    """,
    "CREATE INDEX idx_tracks_model       ON tracks(model)",
    "CREATE INDEX idx_tracks_bpm         ON tracks(bpm)",
    "CREATE INDEX idx_tracks_key_scale   ON tracks(key, scale)",
    "CREATE INDEX idx_tracks_dance       ON tracks(danceability)",
    "CREATE INDEX idx_tracks_loud        ON tracks(loudness)",
    "CREATE INDEX idx_tracks_descv       ON tracks(descriptor_version)",
    "CREATE INDEX idx_tracks_lib         ON tracks(library_root)",
    # Composite NOCASE index for the /tracks/lookup endpoint's tag triple.
    "CREATE INDEX idx_tracks_artist_album_title "
    "ON tracks(artist COLLATE NOCASE, album COLLATE NOCASE, title COLLATE NOCASE)",
    # Top-K style probabilities per track. Lookup by style is the common
    # filter direction; lookup by track is used to enrich track responses.
    """
    CREATE TABLE track_styles (
        track_id     INTEGER NOT NULL,
        style        TEXT    NOT NULL,
        probability  REAL    NOT NULL,
        PRIMARY KEY (track_id, style),
        FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX idx_track_styles_style ON track_styles(style)",
    "CREATE INDEX idx_track_styles_prob  ON track_styles(style, probability DESC)",
]


def upgrade(conn: sqlite3.Connection) -> None:
    for stmt in _STATEMENTS:
        conn.execute(stmt)
