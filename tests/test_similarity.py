"""Tests for cosine similarity ranking via the EmbeddingIndex."""

from __future__ import annotations

import numpy as np

from harmonie.db import TrackFilter
from harmonie.features import DESCRIPTOR_VERSION
from harmonie.similarity import find_similar_to_id


def _insert(db, path, emb, descriptors, model="m1"):
    return db.upsert_track(
        path=path,
        size=1,
        mtime=1.0,
        duration=1.0,
        embedding=emb,
        model=model,
        descriptors=descriptors,
        descriptor_version=DESCRIPTOR_VERSION,
    )


def test_identical_vectors_score_one(make_db, fake_descriptors):
    db, index = make_db()
    v = np.ones(4, dtype=np.float32)
    a = _insert(db, "/a", v, fake_descriptors())
    _insert(db, "/b", v, fake_descriptors())
    _insert(db, "/c", -v, fake_descriptors())

    matches = find_similar_to_id(db, index, a, n=10)
    assert len(matches) == 2
    assert matches[0].path == "/b"
    assert matches[0].score > 0.999
    assert matches[1].path == "/c"
    assert matches[1].score < -0.999


def test_filter_restricts_results(make_db, fake_descriptors):
    db, index = make_db()
    v = np.ones(4, dtype=np.float32)
    seed = _insert(db, "/seed", v, fake_descriptors(bpm=128))
    _insert(db, "/fast", v, fake_descriptors(bpm=160))
    _insert(db, "/slow", v, fake_descriptors(bpm=90))

    matches = find_similar_to_id(
        db, index, seed, n=10, filter=TrackFilter(bpm_min=120, bpm_max=140)
    )
    # Only /seed has bpm in range, and it's excluded as the query.
    assert matches == []


def test_include_self(make_db, fake_descriptors):
    db, index = make_db()
    v = np.ones(4, dtype=np.float32)
    a = _insert(db, "/a", v, fake_descriptors())
    matches = find_similar_to_id(db, index, a, n=5, include_self=True)
    assert any(m.track_id == a for m in matches)


def test_404_for_missing_track(make_db):
    db, index = make_db()
    import pytest

    with pytest.raises(KeyError):
        find_similar_to_id(db, index, 9999, n=5)
