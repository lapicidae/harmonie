"""Deterministic fixture database for snapshot tests.

Builds a small (~35 track) library across four genre neighbourhoods —
techno/IDM, ambient, rock, and jazz — with multiple artists per genre,
varied BPM/key, style activations, and a few intentional same-song
duplicates. Same numpy seed everywhere, so the database is byte-for-
byte reproducible and snapshot diffs reflect playlist-algorithm
changes only.

Embeddings are 8-D vectors centred on per-genre orthogonal centroids
plus per-track Gaussian noise. Within a genre cosine similarity is
typically 0.85–0.97; cross-genre is roughly 0.0–0.4. That spread is
deliberately picked to mimic the Discogs-Effnet distribution we see
on the production library.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from harmonie.db import Database
from harmonie.features import DESCRIPTOR_VERSION, Descriptors
from harmonie.tags import Tags

# Orthogonal centroids in 8-D. Pairwise dot products are zero — genres
# are well-separated in cosine space.
_CENTROIDS: dict[str, np.ndarray] = {
    "techno": np.array([1, 1, 0, 0, 0, 0, 0, 0], dtype=np.float32),
    "ambient": np.array([0, 0, 1, 1, 0, 0, 0, 0], dtype=np.float32),
    "rock": np.array([0, 0, 0, 0, 1, 1, 0, 0], dtype=np.float32),
    "jazz": np.array([0, 0, 0, 0, 0, 0, 1, 1], dtype=np.float32),
}

# Magnitude of per-track noise around the genre centroid. Picked so
# cosine similarities between same-genre tracks land in the 0.85–0.97
# band; lower → tracks more similar to each other, higher → more spread.
_NOISE_SIGMA = 0.3

# (genre, artist, title, bpm, key, scale, danceability, top_styles)
# Multiple artists per genre, multiple tracks per artist where it
# matters for diversity / cooldown tests.
_TRACKS: list[tuple[str, str, str, float, str, str, float, list[tuple[str, float]]]] = [
    # --- techno / IDM ---------------------------------------------------
    (
        "techno",
        "Aphex Twin",
        "Xtal",
        128.0,
        "A",
        "minor",
        1.6,
        [("Electronic---Techno", 0.90), ("Electronic---IDM", 0.55)],
    ),
    (
        "techno",
        "Aphex Twin",
        "Tha",
        132.0,
        "F",
        "minor",
        1.5,
        [("Electronic---Techno", 0.85), ("Electronic---IDM", 0.50)],
    ),
    (
        "techno",
        "Aphex Twin",
        "Heliosphan",
        126.0,
        "C",
        "minor",
        1.4,
        [("Electronic---IDM", 0.85)],
    ),
    (
        "techno",
        "Aphex Twin",
        "Pulsewidth",
        122.0,
        "G",
        "minor",
        1.5,
        [("Electronic---Techno", 0.78)],
    ),
    (
        "techno",
        "Boards of Canada",
        "Roygbiv",
        95.0,
        "D",
        "minor",
        1.2,
        [("Electronic---IDM", 0.85), ("Electronic---Ambient", 0.40)],
    ),
    (
        "techno",
        "Boards of Canada",
        "Olson",
        80.0,
        "F",
        "major",
        1.0,
        [("Electronic---IDM", 0.80)],
    ),
    (
        "techno",
        "Boards of Canada",
        "Aquarius",
        115.0,
        "A",
        "major",
        1.3,
        [("Electronic---IDM", 0.78)],
    ),
    (
        "techno",
        "Burial",
        "Archangel",
        138.0,
        "C",
        "minor",
        1.5,
        [("Electronic---Dubstep", 0.85)],
    ),
    (
        "techno",
        "Burial",
        "Ghost Hardware",
        140.0,
        "F",
        "minor",
        1.4,
        [("Electronic---Dubstep", 0.88)],
    ),
    (
        "techno",
        "Autechre",
        "Acroyear2",
        130.0,
        "A",
        "minor",
        1.3,
        [("Electronic---IDM", 0.92)],
    ),
    (
        "techno",
        "Autechre",
        "Cipater",
        128.0,
        "B",
        "minor",
        1.2,
        [("Electronic---IDM", 0.93)],
    ),
    (
        "techno",
        "Plastikman",
        "Spastik",
        130.0,
        "A",
        "minor",
        1.7,
        [("Electronic---Techno", 0.95)],
    ),
    # --- ambient --------------------------------------------------------
    (
        "ambient",
        "Brian Eno",
        "1/1",
        70.0,
        "C",
        "major",
        0.6,
        [("Electronic---Ambient", 0.95)],
    ),
    (
        "ambient",
        "Brian Eno",
        "2/1",
        65.0,
        "D",
        "major",
        0.5,
        [("Electronic---Ambient", 0.93)],
    ),
    (
        "ambient",
        "Brian Eno",
        "Discreet Music",
        72.0,
        "E",
        "major",
        0.6,
        [("Electronic---Ambient", 0.90)],
    ),
    (
        "ambient",
        "Stars of the Lid",
        "Down",
        60.0,
        "C",
        "major",
        0.4,
        [("Electronic---Ambient", 0.95), ("Electronic---Drone", 0.45)],
    ),
    (
        "ambient",
        "Stars of the Lid",
        "Articulate Silences",
        65.0,
        "D",
        "minor",
        0.5,
        [("Electronic---Ambient", 0.92)],
    ),
    (
        "ambient",
        "Tim Hecker",
        "In the Air",
        75.0,
        "F",
        "minor",
        0.7,
        [("Electronic---Ambient", 0.88)],
    ),
    (
        "ambient",
        "Tim Hecker",
        "Black Refraction",
        80.0,
        "G",
        "minor",
        0.6,
        [("Electronic---Ambient", 0.86)],
    ),
    # --- rock -----------------------------------------------------------
    (
        "rock",
        "Radiohead",
        "Idioteque",
        100.0,
        "G",
        "minor",
        1.1,
        [("Rock---Alternative", 0.85), ("Electronic---IDM", 0.45)],
    ),
    (
        "rock",
        "Radiohead",
        "Pyramid Song",
        80.0,
        "F",
        "major",
        0.8,
        [("Rock---Alternative", 0.90)],
    ),
    (
        "rock",
        "Radiohead",
        "Karma Police",
        75.0,
        "A",
        "minor",
        0.9,
        [("Rock---Alternative", 0.92)],
    ),
    (
        "rock",
        "Pink Floyd",
        "Time",
        115.0,
        "F",
        "major",
        1.0,
        [("Rock---Progressive", 0.95)],
    ),
    (
        "rock",
        "Pink Floyd",
        "Money",
        125.0,
        "B",
        "minor",
        1.1,
        [("Rock---Progressive", 0.92)],
    ),
    (
        "rock",
        "Pink Floyd",
        "Echoes",
        110.0,
        "C",
        "major",
        0.9,
        [("Rock---Progressive", 0.90)],
    ),
    (
        "rock",
        "Led Zeppelin",
        "Kashmir",
        85.0,
        "D",
        "minor",
        1.2,
        [("Rock---Hard Rock", 0.95)],
    ),
    (
        "rock",
        "Led Zeppelin",
        "No Quarter",
        90.0,
        "C",
        "minor",
        1.0,
        [("Rock---Hard Rock", 0.90)],
    ),
    # --- jazz -----------------------------------------------------------
    (
        "jazz",
        "Miles Davis",
        "So What",
        135.0,
        "D",
        "minor",
        1.0,
        [("Jazz---Modal", 0.95)],
    ),
    (
        "jazz",
        "Miles Davis",
        "Kind of Blue",
        132.0,
        "B",
        "minor",
        1.0,
        [("Jazz---Modal", 0.93)],
    ),
    (
        "jazz",
        "John Coltrane",
        "Naima",
        90.0,
        "F",
        "major",
        0.7,
        [("Jazz---Hard Bop", 0.92)],
    ),
    (
        "jazz",
        "John Coltrane",
        "Giant Steps",
        280.0,
        "B",
        "major",
        1.4,
        [("Jazz---Hard Bop", 0.94)],
    ),
    (
        "jazz",
        "Bill Evans",
        "Peace Piece",
        60.0,
        "C",
        "major",
        0.5,
        [("Jazz---Cool", 0.91)],
    ),
]

# Same (artist, title) on a different "compilation" path — exercises
# the dedup logic.
_DUPLICATES: list[tuple[str, str, str]] = [
    # (genre, artist, title)
    ("techno", "Aphex Twin", "Xtal"),
]


def build_fixture_db(db_path: str | Path) -> Database:
    """Create the fixture database at ``db_path`` and return it open."""
    db = Database(db_path)
    for idx, (genre, artist, title, bpm, key, scale, dance, styles) in enumerate(
        _TRACKS
    ):
        _insert_track(
            db,
            idx=idx,
            path=f"/lib/{genre}/{artist}/{title}.flac",
            genre=genre,
            artist=artist,
            title=title,
            bpm=bpm,
            key=key,
            scale=scale,
            danceability=dance,
            styles=styles,
        )

    # Lookup table for duplicate insertion: (genre, artist, title) -> source row.
    _by_id = {
        (g, a, t): row for row in _TRACKS for g, a, t in [(row[0], row[1], row[2])]
    }

    # Duplicates: same (artist, title) on different paths.
    for d_idx, (genre, artist, title) in enumerate(_DUPLICATES):
        try:
            orig = _by_id[(genre, artist, title)]
        except KeyError as e:
            raise LookupError(f"original missing: {artist}/{title}") from e
        _insert_track(
            db,
            idx=1000 + d_idx,
            path=f"/compilations/best-of-{genre}/{title}.flac",
            genre=genre,
            artist=artist,
            title=title,
            bpm=orig[3],
            key=orig[4],
            scale=orig[5],
            danceability=orig[6],
            styles=orig[7],
        )

    return db


def _insert_track(
    db: Database,
    *,
    idx: int,
    path: str,
    genre: str,
    artist: str,
    title: str,
    bpm: float,
    key: str,
    scale: str,
    danceability: float,
    styles: list[tuple[str, float]],
) -> int:
    """Insert one track. Embedding is deterministic in ``idx``."""
    rng = np.random.default_rng(idx)
    embedding = _CENTROIDS[genre] + rng.normal(0, _NOISE_SIGMA, 8).astype(np.float32)
    return db.upsert_track(
        path=path,
        size=1,
        mtime=1.0,
        duration=180.0,
        embedding=embedding,
        model="m1",
        descriptors=Descriptors(
            bpm=bpm,
            bpm_confidence=2.0,
            key=key,
            scale=scale,
            key_strength=0.7,
            loudness=-12.0,
            danceability=danceability,
            onset_rate=4.0,
        ),
        descriptor_version=DESCRIPTOR_VERSION,
        tags=Tags(artist=artist, title=title),
        top_styles=styles,
    )


def find_id(db: Database, artist: str, title: str, *, primary: bool = True) -> int:
    """Look up a fixture track by (artist, title). When ``primary`` is
    true, excludes the compilation duplicate path so callers always
    get the canonical insertion."""
    sql = "SELECT id FROM tracks WHERE artist = ? AND title = ? AND model = 'm1'"
    params: list[object] = [artist, title]
    if primary:
        sql += " AND path NOT LIKE '/compilations/%'"
    sql += " ORDER BY id LIMIT 1"
    cur = db._conn.execute(sql, params)
    row = cur.fetchone()
    if row is None:
        raise LookupError(f"fixture track {artist!r} – {title!r} not found")
    return int(row["id"])
