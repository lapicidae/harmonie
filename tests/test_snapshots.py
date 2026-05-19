"""Snapshot tests against the deterministic fixture DB.

Each test runs a known playlist request and compares the result to a
JSON snapshot in ``tests/snapshots/``. A regression in the picker or
diversity logic shows up as a snapshot diff.

To regenerate snapshots after intentional changes::

    SNAPSHOT_UPDATE=1 .venv/bin/pytest tests/test_snapshots.py

Review the resulting diff before committing.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from harmonie.db import Database, TrackFilter
from harmonie.index import EmbeddingIndex
from harmonie.playlist import (
    ChainedPlaylistRequest,
    SimilarPlaylistRequest,
    VibePlaylistRequest,
    _DiversityPolicy,
    generate_chained_playlist,
    generate_similar_playlist,
    generate_vibe_playlist,
)
from tests.fixtures.snapshot_db import build_fixture_db, find_id

SNAPSHOT_DIR = Path(__file__).parent / "snapshots"


@pytest.fixture(scope="module")
def fixture(tmp_path_factory):
    """Module-scoped fixture: builds the DB once and reuses it."""
    path = tmp_path_factory.mktemp("snapshot") / "fixture.db"
    db = build_fixture_db(path)
    idx = EmbeddingIndex(db)
    yield db, idx
    db.close()


def _render(db: Database, items) -> list[dict]:
    """Serialise a Match list as ``[{track_id, artist, title, score}, ...]``.
    Scores are rounded so float-ULP noise doesn't trip the diff."""
    out: list[dict] = []
    for m in items:
        row = db.get_track_by_id(m.track_id)
        out.append(
            {
                "track_id": m.track_id,
                "artist": row.get("artist") if row else None,
                "title": row.get("title") if row else None,
                "score": round(m.score, 4),
            }
        )
    return out


def _check_snapshot(name: str, payload: dict) -> None:
    """Compare ``payload`` to ``snapshots/<name>.json``.
    Set ``SNAPSHOT_UPDATE=1`` to overwrite snapshots instead of asserting."""
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    path = SNAPSHOT_DIR / f"{name}.json"
    actual = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if os.environ.get("SNAPSHOT_UPDATE"):
        path.write_text(actual)
        return
    if not path.exists():
        pytest.fail(
            f"snapshot {path.name} doesn't exist. Run with SNAPSHOT_UPDATE=1 to create."
        )
    expected = path.read_text()
    if expected != actual:
        pytest.fail(
            f"snapshot {path.name} differs from expected.\n"
            f"If the change is intentional, regenerate with "
            f"SNAPSHOT_UPDATE=1 and review the diff.\n\n"
            f"--- expected ---\n{expected}\n"
            f"--- actual ---\n{actual}"
        )


# ---------------------------------------------------------------------------
# Similar mode
# ---------------------------------------------------------------------------


def test_similar_techno_seed(fixture):
    """Default similar playlist anchored on a techno seed."""
    db, idx = fixture
    seed = find_id(db, "Aphex Twin", "Xtal")
    items = generate_similar_playlist(
        db, idx, SimilarPlaylistRequest(seed_ids=[seed], n=8)
    )
    _check_snapshot(
        "similar_techno_seed",
        {
            "request": "similar / Aphex Twin – Xtal / n=8",
            "items": _render(db, items),
        },
    )


def test_similar_with_bpm_drift(fixture):
    """BPM-drift constraint should keep picks within ±8 of the previous."""
    db, idx = fixture
    seed = find_id(db, "Aphex Twin", "Xtal")  # 128 BPM
    items = generate_similar_playlist(
        db, idx, SimilarPlaylistRequest(seed_ids=[seed], n=6, bpm_drift=8)
    )
    _check_snapshot(
        "similar_bpm_drift",
        {
            "request": "similar / Aphex Twin – Xtal / n=6 / bpm_drift=8",
            "items": _render(db, items),
        },
    )


def test_similar_harmonic_mix(fixture):
    """Harmonic-mix gate restricts picks to Camelot-compatible keys."""
    db, idx = fixture
    seed = find_id(db, "Aphex Twin", "Xtal")  # A minor (Camelot 8A)
    items = generate_similar_playlist(
        db, idx, SimilarPlaylistRequest(seed_ids=[seed], n=6, harmonic_mix=True)
    )
    _check_snapshot(
        "similar_harmonic_mix",
        {
            "request": "similar / Aphex Twin – Xtal / n=6 / harmonic_mix=True",
            "items": _render(db, items),
        },
    )


def test_similar_diversity_off(fixture):
    """With diversity disabled, the picker is pure cosine ranking
    (modulo dedup, which the disabled policy also turns off)."""
    db, idx = fixture
    seed = find_id(db, "Aphex Twin", "Xtal")
    items = generate_similar_playlist(
        db,
        idx,
        SimilarPlaylistRequest(
            seed_ids=[seed],
            n=8,
            diversity=_DiversityPolicy.disabled(),
        ),
    )
    _check_snapshot(
        "similar_diversity_off",
        {
            "request": "similar / Aphex Twin – Xtal / n=8 / diversity=disabled",
            "items": _render(db, items),
        },
    )


def test_similar_dedupes_compilation_duplicate(fixture):
    """The fixture has Aphex Twin – Xtal on two paths. With dedup on,
    only one appears in the output."""
    db, idx = fixture
    seed = find_id(db, "Aphex Twin", "Tha")  # different song, same artist
    items = generate_similar_playlist(
        db, idx, SimilarPlaylistRequest(seed_ids=[seed], n=10)
    )
    titles = [db.get_track_by_id(m.track_id).get("title") for m in items]
    assert titles.count("Xtal") <= 1, "dedup should keep at most one Xtal"
    _check_snapshot(
        "similar_dedup_compilation",
        {
            "request": "similar / Aphex Twin – Tha / n=10",
            "items": _render(db, items),
        },
    )


# ---------------------------------------------------------------------------
# Drift mode
# ---------------------------------------------------------------------------


def test_drift_default(fixture):
    """Drift with chunk_size=3 walks gradually from the seed."""
    db, idx = fixture
    seed = find_id(db, "Aphex Twin", "Xtal")
    items = generate_chained_playlist(
        db, idx, ChainedPlaylistRequest(seed_ids=[seed], chunk_size=3, n=9)
    )
    _check_snapshot(
        "drift_default",
        {
            "request": "drift / Aphex Twin – Xtal / chunk_size=3 / n=9",
            "items": _render(db, items),
        },
    )


def test_drift_chunk_size_one(fixture):
    """chunk_size=1 re-anchors after every pick — drifts the fastest."""
    db, idx = fixture
    seed = find_id(db, "Aphex Twin", "Xtal")
    items = generate_chained_playlist(
        db, idx, ChainedPlaylistRequest(seed_ids=[seed], chunk_size=1, n=8)
    )
    _check_snapshot(
        "drift_chunk_one",
        {
            "request": "drift / Aphex Twin – Xtal / chunk_size=1 / n=8",
            "items": _render(db, items),
        },
    )


# ---------------------------------------------------------------------------
# Vibe mode
# ---------------------------------------------------------------------------


def test_vibe_techno_target(fixture):
    """Vibe with BPM filter and target — should land on techno tracks
    in the 120-140 range, near 128 BPM and high danceability."""
    db, _ = fixture
    items = generate_vibe_playlist(
        db,
        VibePlaylistRequest(
            n=6,
            shuffle=False,
            descriptor_filter=TrackFilter(bpm_min=120, bpm_max=140),
            target_bpm=128,
            target_danceability=1.5,
        ),
        model="m1",
    )
    _check_snapshot(
        "vibe_techno_target",
        {
            "request": "vibe / bpm 120-140 / target 128bpm dance 1.5",
            "items": _render(db, items),
        },
    )


def test_vibe_ambient_filter(fixture):
    """Slow tracks (BPM <90) — should be all ambient/Boards-of-Canada."""
    db, _ = fixture
    items = generate_vibe_playlist(
        db,
        VibePlaylistRequest(
            n=6,
            shuffle=False,
            descriptor_filter=TrackFilter(bpm_max=85),
            target_bpm=70,
        ),
        model="m1",
    )
    _check_snapshot(
        "vibe_ambient_filter",
        {
            "request": "vibe / bpm <=85 / target 70bpm",
            "items": _render(db, items),
        },
    )


def test_vibe_diversity_off(fixture):
    """Without the cooldown penalty, vibe is pure fitness ordering."""
    db, _ = fixture
    items = generate_vibe_playlist(
        db,
        VibePlaylistRequest(
            n=6,
            shuffle=False,
            descriptor_filter=TrackFilter(bpm_min=120, bpm_max=140),
            target_bpm=128,
            diversity=_DiversityPolicy.disabled(),
        ),
        model="m1",
    )
    _check_snapshot(
        "vibe_diversity_off",
        {
            "request": "vibe / bpm 120-140 / target 128 / diversity=disabled",
            "items": _render(db, items),
        },
    )
