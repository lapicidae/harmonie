"""Tests for the SQLite layer."""

from __future__ import annotations

import numpy as np

from harmonie.db import Database, TrackFilter
from harmonie.features import DESCRIPTOR_VERSION


def _insert(db, *, path, embedding, descriptors, model="m1", size=100, mtime=1.0):
    return db.upsert_track(
        path=path,
        size=size,
        mtime=mtime,
        duration=180.0,
        embedding=embedding,
        model=model,
        descriptors=descriptors,
        descriptor_version=DESCRIPTOR_VERSION,
    )


def test_upsert_and_get(tmp_db_path, random_embedding, fake_descriptors):
    db = Database(tmp_db_path)
    try:
        emb = random_embedding(dim=8)
        tid = _insert(db, path="/a.flac", embedding=emb, descriptors=fake_descriptors())
        assert isinstance(tid, int) and tid > 0

        row = db.get_track_by_id(tid)
        assert row is not None
        assert row["path"] == "/a.flac"
        assert row["bpm"] == 128.0
        assert row["key"] == "C"
        assert row["scale"] == "major"
        assert row["embedding_dim"] == 8

        emb_back = db.get_embedding_by_id(tid)
        assert emb_back is not None
        v, model = emb_back
        assert model == "m1"
        np.testing.assert_allclose(v, emb)
    finally:
        db.close()


def test_upsert_replaces_existing(tmp_db_path, random_embedding, fake_descriptors):
    db = Database(tmp_db_path)
    try:
        e1 = random_embedding(dim=4, seed=1)
        e2 = random_embedding(dim=4, seed=2)
        tid1 = _insert(
            db, path="/a.flac", embedding=e1, descriptors=fake_descriptors(bpm=120)
        )
        tid2 = _insert(
            db, path="/a.flac", embedding=e2, descriptors=fake_descriptors(bpm=140)
        )
        assert tid1 == tid2  # same row, same id
        row = db.get_track_by_id(tid1)
        assert row["bpm"] == 140
    finally:
        db.close()


def test_filter_by_bpm_range(tmp_db_path, random_embedding, fake_descriptors):
    db = Database(tmp_db_path)
    try:
        for i, bpm in enumerate([100, 120, 128, 140, 160]):
            _insert(
                db,
                path=f"/{i}.flac",
                embedding=random_embedding(dim=4, seed=i),
                descriptors=fake_descriptors(bpm=bpm),
            )
        rows, total = db.list_tracks(filter=TrackFilter(bpm_min=120, bpm_max=140))
        assert total == 3
        bpms = sorted(r["bpm"] for r in rows)
        assert bpms == [120, 128, 140]
    finally:
        db.close()


def test_filter_by_key_set(tmp_db_path, random_embedding, fake_descriptors):
    db = Database(tmp_db_path)
    try:
        for i, key in enumerate(["C", "G", "D", "A"]):
            _insert(
                db,
                path=f"/{key}.flac",
                embedding=random_embedding(dim=4, seed=i),
                descriptors=fake_descriptors(key=key),
            )
        rows, total = db.list_tracks(filter=TrackFilter(key=["C", "G"]))
        assert total == 2
        assert sorted(r["key"] for r in rows) == ["C", "G"]
    finally:
        db.close()


def test_prune_missing_under_roots(tmp_path, random_embedding, fake_descriptors):

    db_path = tmp_path / "test.db"
    db = Database(db_path)
    try:
        # Two libraries: /lib_a (reachable in this test) and /lib_b (would be
        # unreachable IRL — we simulate that by passing only /lib_a as a root).
        lib_a = tmp_path / "lib_a"
        lib_b = tmp_path / "lib_b"
        lib_a.mkdir()
        lib_b.mkdir()
        for sub, name in [
            (lib_a, "kept.flac"),
            (lib_a, "gone.flac"),
            (lib_b, "untouched.flac"),
        ]:
            _insert(
                db,
                path=str(sub / name),
                embedding=random_embedding(dim=4),
                descriptors=fake_descriptors(),
            )
        keep = {str(lib_a / "kept.flac")}
        # Only lib_a is "reachable" — lib_b should be untouched.
        removed = db.prune_missing_under_roots(roots=[lib_a], keep=keep)
        assert removed == 1
        paths = {r["path"] for r, _ in [(r, None) for r in db.list_tracks()[0]]}
        assert str(lib_a / "kept.flac") in paths
        assert str(lib_b / "untouched.flac") in paths
        assert str(lib_a / "gone.flac") not in paths
    finally:
        db.close()


def test_prune_with_no_roots_is_noop(tmp_path, random_embedding, fake_descriptors):
    db = Database(tmp_path / "test.db")
    try:
        _insert(
            db,
            path=str(tmp_path / "x.flac"),
            embedding=random_embedding(dim=4),
            descriptors=fake_descriptors(),
        )
        removed = db.prune_missing_under_roots(roots=[], keep=set())
        assert removed == 0
        _, total = db.list_tracks()
        assert total == 1
    finally:
        db.close()


def test_descriptor_version_split(tmp_db_path, random_embedding, fake_descriptors):
    db = Database(tmp_db_path)
    try:
        # Insert at descriptor_version-1 to force needs_descriptor_refresh.
        emb = random_embedding(dim=4)
        db.upsert_track(
            path="/a.flac",
            size=100,
            mtime=1.0,
            duration=120.0,
            embedding=emb,
            model="m1",
            descriptors=fake_descriptors(),
            descriptor_version=DESCRIPTOR_VERSION - 1 if DESCRIPTOR_VERSION > 0 else 0,
        )
        # If DESCRIPTOR_VERSION is 0 the test is trivially false, skip.
        if DESCRIPTOR_VERSION > 0:
            assert db.needs_descriptor_refresh("/a.flac", DESCRIPTOR_VERSION)
            assert not db.needs_embedding("/a.flac", 100, 1.0, "m1")
            ok = db.update_descriptors(
                "/a.flac",
                descriptors=fake_descriptors(bpm=99),
                descriptor_version=DESCRIPTOR_VERSION,
            )
            assert ok
            assert not db.needs_descriptor_refresh("/a.flac", DESCRIPTOR_VERSION)
            row = db.get_track_by_path("/a.flac")
            assert row["bpm"] == 99
    finally:
        db.close()


def test_tags_and_library_columns_round_trip(
    tmp_db_path, random_embedding, fake_descriptors
):
    """Tags + library_root + relative_path get stored and read back."""
    from harmonie.tags import Tags

    db = Database(tmp_db_path)
    try:
        tid = db.upsert_track(
            path="/lib/artist/album/01.flac",
            size=100,
            mtime=1.0,
            duration=180.0,
            embedding=random_embedding(dim=4),
            model="m1",
            descriptors=fake_descriptors(),
            descriptor_version=DESCRIPTOR_VERSION,
            tags=Tags(
                artist="Person",
                album="Record",
                title="Song",
                track_number=1,
            ),
            library_root="/lib",
            relative_path="artist/album/01.flac",
        )
        row = db.get_track_by_id(tid)
        assert row["artist"] == "Person"
        assert row["album"] == "Record"
        assert row["title"] == "Song"
        assert row["track_number"] == 1
        assert row["library_root"] == "/lib"
        assert row["relative_path"] == "artist/album/01.flac"
    finally:
        db.close()


def test_get_tracks_by_ids_bulk_lookup(tmp_db_path, random_embedding, fake_descriptors):
    from harmonie.tags import Tags

    db = Database(tmp_db_path)
    try:
        ids = []
        for i in range(3):
            tid = db.upsert_track(
                path=f"/{i}.flac",
                size=100,
                mtime=1.0,
                duration=120.0,
                embedding=random_embedding(dim=4, seed=i),
                model="m1",
                descriptors=fake_descriptors(),
                descriptor_version=DESCRIPTOR_VERSION,
                tags=Tags(title=f"Track {i}"),
            )
            ids.append(tid)
        rows = db.get_tracks_by_ids(ids)
        assert set(rows.keys()) == set(ids)
        assert rows[ids[0]]["title"] == "Track 0"
        assert rows[ids[2]]["title"] == "Track 2"

        # Empty input returns empty dict, not an error.
        assert db.get_tracks_by_ids([]) == {}
    finally:
        db.close()


def test_descriptor_refresh_updates_tags(
    tmp_db_path, random_embedding, fake_descriptors
):
    """A descriptor-only refresh should also pick up new tags from the file."""
    from harmonie.tags import Tags

    db = Database(tmp_db_path)
    try:
        db.upsert_track(
            path="/a.flac",
            size=100,
            mtime=1.0,
            duration=180.0,
            embedding=random_embedding(dim=4),
            model="m1",
            descriptors=fake_descriptors(),
            descriptor_version=DESCRIPTOR_VERSION,
            tags=Tags(title="Old Title"),
        )
        ok = db.update_descriptors(
            "/a.flac",
            descriptors=fake_descriptors(bpm=140),
            descriptor_version=DESCRIPTOR_VERSION,
            tags=Tags(title="New Title", artist="New Artist"),
        )
        assert ok
        row = db.get_track_by_path("/a.flac")
        assert row["title"] == "New Title"
        assert row["artist"] == "New Artist"
        assert row["bpm"] == 140
    finally:
        db.close()


# ---------------------------------------------------------------------------
# find_track (used by POST /tracks/lookup)
# ---------------------------------------------------------------------------


def _add_track(
    db,
    path,
    *,
    library_root=None,
    relative_path=None,
    artist=None,
    album=None,
    title=None,
    embedding=None,
):
    from harmonie.tags import Tags

    return db.upsert_track(
        path=path,
        size=1,
        mtime=1.0,
        duration=1.0,
        embedding=embedding if embedding is not None else np.zeros(4, dtype=np.float32),
        model="m1",
        descriptors=__import__(
            "harmonie.features", fromlist=["Descriptors"]
        ).Descriptors(),
        descriptor_version=DESCRIPTOR_VERSION,
        tags=Tags(artist=artist, album=album, title=title),
        library_root=library_root,
        relative_path=relative_path,
    )


def test_find_track_by_exact_path(tmp_db_path):
    db = Database(tmp_db_path)
    try:
        _add_track(db, "/lib/a.flac", library_root="/lib", relative_path="a.flac")
        row = db.find_track(path="/lib/a.flac")
        assert row is not None and row["path"] == "/lib/a.flac"
    finally:
        db.close()


def test_find_track_by_relative_path(tmp_db_path):
    """The caller may have a different mount point. If the path they send
    matches the harmonie-side relative_path, we still find the track."""
    db = Database(tmp_db_path)
    try:
        _add_track(
            db,
            "/srv/music/artist/song.flac",
            library_root="/srv/music",
            relative_path="artist/song.flac",
        )
        row = db.find_track(path="artist/song.flac")
        assert row is not None
        assert row["relative_path"] == "artist/song.flac"
    finally:
        db.close()


def test_find_track_by_tag_triple(tmp_db_path):
    db = Database(tmp_db_path)
    try:
        _add_track(db, "/a.flac", artist="Aphex Twin", album="SAW", title="Xtal")
        _add_track(db, "/b.flac", artist="Other", album="Other", title="Other")
        row = db.find_track(artist="Aphex Twin", album="SAW", title="Xtal")
        assert row is not None
        assert row["path"] == "/a.flac"
    finally:
        db.close()


def test_find_track_tag_match_is_case_insensitive(tmp_db_path):
    db = Database(tmp_db_path)
    try:
        _add_track(db, "/a.flac", artist="Aphex Twin", album="SAW", title="Xtal")
        row = db.find_track(artist="aphex twin", album="saw", title="xtal")
        assert row is not None
        assert row["path"] == "/a.flac"
    finally:
        db.close()


def test_find_track_pair_fallback(tmp_db_path):
    """If only artist+title (no album) is given, we still match."""
    db = Database(tmp_db_path)
    try:
        _add_track(db, "/a.flac", artist="Aphex Twin", album="SAW", title="Xtal")
        row = db.find_track(artist="Aphex Twin", title="Xtal")
        assert row is not None
        assert row["path"] == "/a.flac"
    finally:
        db.close()


def test_find_track_path_takes_precedence_over_tags(tmp_db_path):
    """Path match is most specific. If the caller provides both, the path
    hit wins even if the tags would match a different row."""
    db = Database(tmp_db_path)
    try:
        a = _add_track(
            db,
            "/by-path.flac",
            artist="DifferentArtist",
            album="X",
            title="Y",
        )
        _add_track(db, "/by-tags.flac", artist="A", album="B", title="C")
        row = db.find_track(
            path="/by-path.flac",
            artist="A",
            album="B",
            title="C",
        )
        assert row is not None
        assert row["id"] == a
    finally:
        db.close()


def test_find_track_deterministic_on_duplicates(tmp_db_path):
    """When multiple tracks have identical tags, the one with the smallest
    id wins, every time."""
    db = Database(tmp_db_path)
    try:
        first = _add_track(db, "/a.flac", artist="A", album="B", title="C")
        _add_track(db, "/b.flac", artist="A", album="B", title="C")
        _add_track(db, "/c.flac", artist="A", album="B", title="C")
        for _ in range(3):
            row = db.find_track(artist="A", album="B", title="C")
            assert row["id"] == first
    finally:
        db.close()


def test_find_track_returns_none_on_no_match(tmp_db_path):
    db = Database(tmp_db_path)
    try:
        _add_track(db, "/a.flac", artist="A", album="B", title="C")
        assert db.find_track(path="/nope.flac") is None
        assert db.find_track(artist="X", album="Y", title="Z") is None
        assert db.find_track() is None
    finally:
        db.close()


def test_find_track_partial_tags_too_loose(tmp_db_path):
    """Title alone isn't enough — too ambiguous. We require title plus at
    least one of artist/album to fall back to the pair match."""
    db = Database(tmp_db_path)
    try:
        _add_track(db, "/a.flac", title="Common Title")
        _add_track(db, "/b.flac", title="Common Title")
        # Just title → no match (intentionally — no anchor field).
        assert db.find_track(title="Common Title") is None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Scan history (migration 002)
# ---------------------------------------------------------------------------


def _start_scan(db, **overrides):
    """Helper: insert a scan row with sensible defaults, return its id."""
    kwargs = {
        "workers": 4,
        "backend": "effnet",
        "model": "discogs-effnet-bs64-1",
        "forced": False,
        "harmonie_version": "0.0.0+test",
        "descriptor_version": 1,
    }
    kwargs.update(overrides)
    return db.start_scan(**kwargs)


def test_start_scan_inserts_running_row(tmp_db_path):
    db = Database(tmp_db_path)
    try:
        sid = _start_scan(db, workers=12, forced=True)
        row = db.get_scan(sid)
        assert row is not None
        assert row["state"] == "running"
        assert row["workers"] == 12
        assert row["forced"] == 1
        assert row["finished_at"] is None
        assert row["started_at"] > 0
    finally:
        db.close()


def test_record_scan_failure_writes_row(tmp_db_path):
    db = Database(tmp_db_path)
    try:
        sid = _start_scan(db)
        db.record_scan_failure(
            sid,
            path="/lib/broken.flac",
            error="boom",
            size=42,
            mtime=1.5,
        )
        rows, total = db.list_failures_for_scan(sid)
        assert total == 1
        assert rows[0]["path"] == "/lib/broken.flac"
        assert rows[0]["error"] == "boom"
        assert rows[0]["size"] == 42
        assert rows[0]["mtime"] == 1.5
    finally:
        db.close()


def test_finish_scan_updates_counters_and_state(tmp_db_path):
    db = Database(tmp_db_path)
    try:
        sid = _start_scan(db)
        db.finish_scan(
            sid,
            duration_sec=12.5,
            discovered=100,
            full=10,
            descriptors_only=2,
            skipped=85,
            failed=3,
            removed=0,
            state="completed",
        )
        row = db.get_scan(sid)
        assert row["state"] == "completed"
        assert row["duration_sec"] == 12.5
        assert row["full"] == 10
        assert row["failed"] == 3
        assert row["finished_at"] is not None
    finally:
        db.close()


def test_finish_scan_records_crash_state(tmp_db_path):
    db = Database(tmp_db_path)
    try:
        sid = _start_scan(db)
        db.finish_scan(
            sid,
            duration_sec=1.0,
            discovered=0,
            full=0,
            descriptors_only=0,
            skipped=0,
            failed=0,
            removed=0,
            state="crashed",
            last_error="kaboom",
        )
        row = db.get_scan(sid)
        assert row["state"] == "crashed"
        assert row["last_error"] == "kaboom"
    finally:
        db.close()


def test_mark_orphaned_scans_crashed(tmp_db_path):
    """Any 'running' rows from a previous process get marked 'crashed'
    with a synthetic finished_at and a default last_error."""
    db = Database(tmp_db_path)
    try:
        sid_running = _start_scan(db)
        sid_done = _start_scan(db)
        db.finish_scan(
            sid_done,
            duration_sec=1.0,
            discovered=0,
            full=0,
            descriptors_only=0,
            skipped=0,
            failed=0,
            removed=0,
            state="completed",
        )

        n = db.mark_orphaned_scans_crashed()
        assert n == 1

        running = db.get_scan(sid_running)
        assert running["state"] == "crashed"
        assert running["finished_at"] is not None  # synthesized from started_at
        assert "interrupted" in running["last_error"]

        done = db.get_scan(sid_done)
        assert done["state"] == "completed"  # untouched
    finally:
        db.close()


def test_list_scans_orders_newest_first(tmp_db_path):
    import time as _time

    db = Database(tmp_db_path)
    try:
        first = _start_scan(db)
        _time.sleep(0.01)
        second = _start_scan(db)
        rows, total = db.list_scans(limit=10)
        assert total == 2
        assert rows[0]["id"] == second
        assert rows[1]["id"] == first
    finally:
        db.close()


def test_list_failures_pagination(tmp_db_path):
    db = Database(tmp_db_path)
    try:
        sid = _start_scan(db)
        for i in range(7):
            db.record_scan_failure(
                sid,
                path=f"/lib/{i}.flac",
                error=f"err {i}",
            )
        rows, total = db.list_failures_for_scan(sid, limit=3, offset=0)
        assert total == 7
        assert len(rows) == 3
        rows2, _ = db.list_failures_for_scan(sid, limit=10, offset=5)
        assert len(rows2) == 2
    finally:
        db.close()


def test_scan_failures_cascade_on_scan_delete(tmp_db_path):
    """Deleting a scan row cascades to its scan_failures rows."""
    db = Database(tmp_db_path)
    try:
        sid = _start_scan(db)
        db.record_scan_failure(sid, path="/lib/a.flac", error="oops")
        with db.transaction() as cur:
            cur.execute("DELETE FROM scans WHERE id = ?", (sid,))
        rows, total = db.list_failures_for_scan(sid)
        assert total == 0
        assert rows == []
    finally:
        db.close()
