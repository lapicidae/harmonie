"""Tests for the Analyzer._run_scan state machine."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from harmonie import analyzer as analyzer_mod
from harmonie.analyzer import Analyzer, ScanStatus
from harmonie.config import Settings
from harmonie.workers import FullJob


@pytest.fixture
def harness(tmp_path: Path, monkeypatch):
    """An Analyzer with the slow bits monkeypatched out. Returns
    ``(analyzer, observations)`` where ``observations`` is a list the
    patched callees append to."""
    lib = tmp_path / "library"
    lib.mkdir()
    settings = Settings(libraries=[lib], data_dir=tmp_path)
    analyzer = Analyzer(settings)

    observations: list[tuple[str, str]] = []

    def fake_iter(roots) -> Iterator[Path]:
        observations.append(("iter_audio_files", analyzer.status.phase))
        yield from [Path("/lib/a.flac"), Path("/lib/b.flac")]

    monkeypatch.setattr(analyzer_mod, "iter_audio_files", fake_iter)

    def fake_build_jobs(db, files, *, model_name, force, on_progress=None):
        observations.append(("build_jobs", analyzer.status.phase))
        if on_progress is not None:
            on_progress(len(files))
        jobs = [FullJob(path=str(f), size=1, mtime=1.0) for f in files]
        return jobs, [], 0

    monkeypatch.setattr(analyzer_mod, "build_jobs", fake_build_jobs)

    class FakePool:
        def map(self, jobs, *, chunksize=1):
            observations.append(("pool.map", analyzer.status.phase))
            return iter([])

        def close(self) -> None:
            pass

    analyzer.pool = FakePool()

    def fake_prune(*, roots, keep) -> int:
        observations.append(("prune", analyzer.status.phase))
        return 0

    monkeypatch.setattr(analyzer.db, "prune_missing_under_roots", fake_prune)

    yield analyzer, observations
    analyzer.stop()


# ---------------------------------------------------------------------------


def test_phase_transitions_in_order(harness):
    """Scan must transition through enumerating → classifying →
    extracting → pruning → idle, in that order."""
    analyzer, observations = harness
    analyzer.scan()

    assert observations == [
        ("iter_audio_files", "enumerating"),
        ("build_jobs", "classifying"),
        ("pool.map", "extracting"),
        ("prune", "pruning"),
    ]
    assert analyzer.status.state == "idle"
    assert analyzer.status.phase == "idle"


def test_status_starts_idle(harness):
    """Fresh Analyzer reports idle in state and phase with no leaked
    timing data."""
    analyzer, _ = harness
    snap = analyzer.status.snapshot()
    assert snap["state"] == "idle"
    assert snap["phase"] == "idle"
    assert snap["started_at"] is None
    assert snap["finished_at"] is None
    assert snap["discovered"] == 0


def test_discovered_counter_set_during_enumeration(harness):
    """``discovered`` reflects the file count the walker yielded."""
    analyzer, _ = harness
    analyzer.scan()
    assert analyzer.status.discovered == 2


def test_scan_with_no_jobs_skips_extracting(tmp_path, monkeypatch):
    """If build_jobs returns no work, _run_scan does not enter the
    extracting phase. Pruning still runs."""
    lib = tmp_path / "library"
    lib.mkdir()
    settings = Settings(libraries=[lib], data_dir=tmp_path)
    analyzer = Analyzer(settings)
    try:
        observations: list[str] = []

        monkeypatch.setattr(
            analyzer_mod,
            "iter_audio_files",
            lambda roots: iter([Path("/lib/a.flac")]),
        )

        def empty_jobs(db, files, *, model_name, force, on_progress=None):
            return [], [], 1

        monkeypatch.setattr(analyzer_mod, "build_jobs", empty_jobs)

        class TripwirePool:
            def map(self, *_a, **_kw):
                observations.append("pool.map called!")
                return iter([])

            def close(self) -> None:
                pass

        analyzer.pool = TripwirePool()
        monkeypatch.setattr(
            analyzer.db,
            "prune_missing_under_roots",
            lambda *, roots, keep: 0,
        )

        analyzer.scan()

        assert observations == []
        assert analyzer.status.skipped == 1
        assert analyzer.status.phase == "idle"
    finally:
        analyzer.stop()


def test_scan_records_started_and_finished(harness):
    """started_at, finished_at, and last_duration_sec populated after a
    run."""
    analyzer, _ = harness
    snap_before = analyzer.status.snapshot()
    assert snap_before["started_at"] is None

    analyzer.scan()

    snap_after = analyzer.status.snapshot()
    assert snap_after["started_at"] is not None
    assert snap_after["finished_at"] is not None
    assert snap_after["finished_at"] >= snap_after["started_at"]
    assert snap_after["last_duration_sec"] is not None
    assert snap_after["last_duration_sec"] >= 0


def test_scan_is_a_noop_when_already_running(harness):
    """A second call while the scan_lock is held returns the current
    status without restarting the scan."""
    analyzer, observations = harness
    # Pretend a scan is already underway by setting the state and
    # holding the lock without releasing.
    analyzer.status = ScanStatus(state="scanning", phase="extracting")
    acquired = analyzer._scan_lock.acquire(blocking=False)
    assert acquired

    # Second call should bail out without re-running.
    result = analyzer.scan()
    assert result.state == "scanning"
    assert result.phase == "extracting"
    assert observations == []  # no new work happened

    analyzer._scan_lock.release()


# ---------------------------------------------------------------------------
# Scan-history persistence (migration 002)
# ---------------------------------------------------------------------------


def test_scan_writes_scans_row(harness):
    """A successful scan inserts and finalizes one row in the ``scans``
    table with the expected counters and configuration."""
    analyzer, _ = harness
    analyzer.scan()

    rows, total = analyzer.db.list_scans(limit=10)
    assert total == 1
    row = rows[0]
    assert row["state"] == "completed"
    assert row["workers"] == analyzer.settings.worker_count
    assert row["backend"] == analyzer.settings.backend
    assert row["model"] == analyzer.model_name
    assert row["forced"] == 0
    assert row["finished_at"] is not None
    assert row["duration_sec"] is not None
    assert row["duration_sec"] >= 0
    assert row["discovered"] == 2
    assert row["last_error"] is None


def test_scan_records_each_failure(tmp_path, monkeypatch):
    """Every JobError yielded by the pool gets persisted to
    scan_failures with the right scan_id."""
    from harmonie.workers import JobError

    lib = tmp_path / "library"
    lib.mkdir()
    settings = Settings(libraries=[lib], data_dir=tmp_path)
    analyzer = Analyzer(settings)
    try:
        monkeypatch.setattr(
            analyzer_mod,
            "iter_audio_files",
            lambda roots: iter([Path("/lib/a.flac"), Path("/lib/b.flac")]),
        )

        def two_jobs(db, files, *, model_name, force, on_progress=None):
            from harmonie.workers import FullJob

            return (
                [FullJob(path=str(f), size=1, mtime=1.0) for f in files],
                [],
                0,
            )

        monkeypatch.setattr(analyzer_mod, "build_jobs", two_jobs)

        class FailingPool:
            def map(self, jobs, *, chunksize=1):
                for j in jobs:
                    yield JobError(path=j.path, error="not real audio")

            def close(self) -> None:
                pass

        analyzer.pool = FailingPool()
        monkeypatch.setattr(
            analyzer.db,
            "prune_missing_under_roots",
            lambda *, roots, keep: 0,
        )

        analyzer.scan()

        # One scan row, two failure rows under it.
        rows, _ = analyzer.db.list_scans(limit=10)
        assert len(rows) == 1
        sid = rows[0]["id"]
        assert rows[0]["failed"] == 2

        failures, total = analyzer.db.list_failures_for_scan(sid)
        assert total == 2
        paths = sorted(f["path"] for f in failures)
        assert paths == ["/lib/a.flac", "/lib/b.flac"]
        for f in failures:
            assert f["error"] == "not real audio"
    finally:
        analyzer.stop()


def test_orphaned_running_scans_marked_crashed_on_construction(tmp_path, caplog):
    """Constructing a fresh Analyzer cleans up any 'running' scan rows
    left behind by a previous process."""
    settings = Settings(libraries=[tmp_path], data_dir=tmp_path)
    # First Analyzer simulates a process that started a scan and died:
    # insert a 'running' row directly without finishing it.
    a1 = Analyzer(settings)
    sid = a1.db.start_scan(
        workers=1,
        backend="effnet",
        model="discogs-effnet-bs64-1",
        forced=False,
        harmonie_version="0.0.0+test",
        descriptor_version=1,
    )
    a1.db.close()  # don't call stop() — we want the row left as 'running'.

    # Second Analyzer should observe and clean it up.
    with caplog.at_level("WARNING", logger="harmonie.analyzer"):
        a2 = Analyzer(settings)
    try:
        row = a2.db.get_scan(sid)
        assert row["state"] == "crashed"
        assert "interrupted" in row["last_error"]
        assert row["finished_at"] is not None
        assert any(
            "marked" in r.getMessage() and "crashed" in r.getMessage()
            for r in caplog.records
        )
    finally:
        a2.stop()


def test_crashed_scan_persists_state_and_error(tmp_path, monkeypatch):
    """If _run_scan raises, the scan row is finalized with state='crashed'
    and last_error set."""
    lib = tmp_path / "library"
    lib.mkdir()
    settings = Settings(libraries=[lib], data_dir=tmp_path)
    analyzer = Analyzer(settings)
    try:

        def boom(roots):
            raise RuntimeError("filesystem on fire")

        monkeypatch.setattr(analyzer_mod, "iter_audio_files", boom)

        with pytest.raises(RuntimeError, match="filesystem on fire"):
            analyzer.scan()

        rows, _ = analyzer.db.list_scans(limit=1)
        assert len(rows) == 1
        assert rows[0]["state"] == "crashed"
        assert "filesystem on fire" in rows[0]["last_error"]
        assert rows[0]["finished_at"] is not None
    finally:
        analyzer.stop()
