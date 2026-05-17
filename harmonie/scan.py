"""Filesystem scanning for audio files."""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from pathlib import Path

AUDIO_EXTENSIONS = frozenset(
    {
        ".flac",
        ".mp3",
        ".wav",
        ".ogg",
        ".oga",
        ".m4a",
        ".aac",
        ".aiff",
        ".aif",
        ".wma",
        ".opus",
        ".alac",
    }
)


def is_audio_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS


def _is_skippable_file(name: str) -> bool:
    """True for filenames the walker should pretend don't exist.

    Currently this is any dot-prefixed name (``._track.flac``,
    ``.DS_Store``, etc.). The most common offenders are macOS
    AppleDouble files: when macOS writes to a non-HFS+ filesystem
    (SMB/CIFS, USB, NTFS, exFAT) it stores extended attributes and
    resource forks in a sibling file with a ``._`` prefix. Those
    sibling files share the audio extension of the real file but
    aren't audio themselves; trying to decode them is guaranteed to
    fail.
    """
    return name.startswith(".")


def _candidate_paths(root: Path) -> Iterator[Path]:
    """Yield every file path under ``root`` the walker should consider.

    A root that's itself a file is yielded as-is. A root that's a
    directory is walked recursively; symlinks are not followed and
    hidden directories are pruned. The caller still has to apply
    audio-extension and dedupe filters — this helper just produces
    candidates.
    """
    if root.is_file():
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            yield Path(dirpath) / name


def iter_audio_files(roots: Iterable[Path]) -> Iterator[Path]:
    """Yield audio files under each root, recursively. Roots may be files
    or directories. Hidden directories and dot-prefixed files (including
    macOS AppleDouble ``._*`` metadata) are skipped, symlinks are not
    followed, and results are de-duplicated by realpath.
    """
    seen: set[str] = set()
    for root in roots:
        root = Path(root).expanduser()
        if not root.exists():
            continue
        for path in _candidate_paths(root):
            if _is_skippable_file(path.name) or not is_audio_file(path):
                continue
            key = os.path.realpath(path)
            if key in seen:
                continue
            seen.add(key)
            yield path


def split_library_path(
    path: str, libraries: Iterable[Path]
) -> tuple[str | None, str | None]:
    """Find which configured library root contains ``path``.

    Returns ``(library_root, relative_path)`` as resolved absolute strings,
    or ``(None, None)`` if the path isn't under any of ``libraries``.

    The first matching library wins. Both inputs are resolved to absolute
    paths before comparison.
    """
    try:
        target = Path(path).expanduser().resolve()
    except Exception:
        return None, None
    for root in libraries:
        try:
            root_resolved = Path(root).expanduser().resolve()
        except Exception:
            continue
        try:
            rel = target.relative_to(root_resolved)
        except ValueError:
            continue
        return str(root_resolved), str(rel)
    return None, None
