"""Tests for the worker-process initialization."""

from __future__ import annotations

import sys
import types

import pytest


@pytest.fixture
def stub_essentia(monkeypatch):
    """Install a fake ``essentia`` module on ``sys.modules``."""
    fake = types.ModuleType("essentia")
    fake.log = types.SimpleNamespace(warningActive=True)
    monkeypatch.setitem(sys.modules, "essentia", fake)
    return fake


@pytest.fixture
def stub_extractor(monkeypatch):
    """Replace ``EffnetExtractor`` with a sentinel-returning factory."""
    from harmonie import workers as workers_mod

    sentinel = object()
    monkeypatch.setattr(workers_mod, "EffnetExtractor", lambda: sentinel)
    return sentinel


def test_worker_init_silences_essentia_warnings_at_info(stub_essentia, stub_extractor):
    from harmonie.workers import _worker_init

    _worker_init("INFO")
    assert stub_essentia.log.warningActive is False


def test_worker_init_silences_essentia_warnings_at_warning(
    stub_essentia, stub_extractor
):
    from harmonie.workers import _worker_init

    _worker_init("WARNING")
    assert stub_essentia.log.warningActive is False


def test_worker_init_keeps_warnings_at_debug(stub_essentia, stub_extractor):
    from harmonie.workers import _worker_init

    _worker_init("DEBUG")
    assert stub_essentia.log.warningActive is True


def test_worker_init_debug_case_insensitive(stub_essentia, stub_extractor):
    from harmonie.workers import _worker_init

    _worker_init("debug")
    assert stub_essentia.log.warningActive is True


# ---------------------------------------------------------------------------
# Per-file progress logging
# ---------------------------------------------------------------------------


def test_do_full_logs_extracting_line(monkeypatch, caplog):
    from harmonie import workers as workers_mod

    class _FakeExtractor:
        name = "test-model"
        genre_labels = None

        def extract(self, path):
            raise RuntimeError("not real audio")

    monkeypatch.setattr(workers_mod, "_extractor", _FakeExtractor())

    job = workers_mod.FullJob(path="/lib/track-1.flac", size=1, mtime=1.0)
    with caplog.at_level("INFO", logger="harmonie.workers"):
        result = workers_mod._do_full(job)

    msgs = [r.getMessage() for r in caplog.records]
    assert any("extracting" in m and "/lib/track-1.flac" in m for m in msgs)
    assert isinstance(result, workers_mod.JobError)


def test_do_descriptors_logs_refreshing_line(monkeypatch, caplog):
    from harmonie import workers as workers_mod

    class _FakeExtractor:
        name = "test-model"
        genre_labels = None

        def extract_descriptors(self, path):
            raise RuntimeError("nope")

    monkeypatch.setattr(workers_mod, "_extractor", _FakeExtractor())

    job = workers_mod.DescriptorJob(path="/lib/track-2.flac")
    with caplog.at_level("INFO", logger="harmonie.workers"):
        result = workers_mod._do_descriptors(job)

    msgs = [r.getMessage() for r in caplog.records]
    assert any("refreshing descriptors" in m and "/lib/track-2.flac" in m for m in msgs)
    assert isinstance(result, workers_mod.JobError)
