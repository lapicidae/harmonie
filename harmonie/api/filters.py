"""Filter language for the HTTP API.

Two surfaces map to a single internal :class:`harmonie.db.TrackFilter`:

* **URL queries** (used by ``GET /tracks`` and ``GET /tracks/{id}/similar``):

  * Numeric ranges via ``..`` syntax::

      bpm=120..130     # closed range
      bpm=120..        # lower bound only
      bpm=..130        # upper bound only
      bpm=128          # exact value

  * Set membership: repeat the parameter (``key=A&key=B``).

  * Genre/style filtering uses two independent axes::

      genre=Electronic              # every Electronic---* label
      style=House                   # every *---House label, any genre
      genre=Electronic&style=House  # exact Electronic---House

    Either or both axes may be supplied, and either may be repeated for
    OR. ``style_min`` gates by minimum classifier probability;
    ``style_mode=any|all`` switches between OR and AND across all
    requested constraints.

* **JSON bodies** (used by ``POST /playlists`` under ``filter``)::

      {
        "bpm":      { "gte": 120, "lte": 130 },
        "loudness": { "lte": -10 },
        "key":      ["A", "B"],
        "scale":    "minor",
        "genre":    ["Electronic"],
        "style":    ["House"],
        "style_min": 0.5,
        "style_mode": "any"
      }

Both shapes build the same ``TrackFilter``.

Genre and style values must not contain ``---`` — the separator is an
internal label format. Use the two-parameter form for an exact label.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from ..db import TrackFilter

# ---------------------------------------------------------------------------
# Range objects (used in body filters)
# ---------------------------------------------------------------------------


class FloatRange(BaseModel):
    """Inclusive numeric range. Either bound may be omitted."""

    gte: float | None = None
    lte: float | None = None

    @model_validator(mode="after")
    def _check_bounds(self) -> FloatRange:
        if self.gte is not None and self.lte is not None and self.gte > self.lte:
            raise ValueError(f"gte ({self.gte}) must be <= lte ({self.lte})")
        return self

    def is_empty(self) -> bool:
        return self.gte is None and self.lte is None


# ---------------------------------------------------------------------------
# Genre/style validation
# ---------------------------------------------------------------------------


def _reject_separator(values: list[str] | None, field: str) -> list[str] | None:
    """Reject ``---`` in genre/style filter values. The separator is an
    internal label format; clients compose exact labels by passing both
    ``genre`` and ``style``."""
    if not values:
        return values
    for v in values:
        if "---" in v:
            raise ValueError(
                f"{field} values must not contain '---'; use genre and style "
                f"together for an exact label (got {v!r})"
            )
    return values


# ---------------------------------------------------------------------------
# Body filter
# ---------------------------------------------------------------------------


class FilterBody(BaseModel):
    """Body shape for ``filter`` blocks in playlist requests.

    Every field is optional. Missing fields mean "no constraint."
    """

    bpm: FloatRange | None = None
    danceability: FloatRange | None = None
    loudness: FloatRange | None = None
    key: list[str] | None = None
    scale: str | None = None
    genre: list[str] | None = Field(
        None,
        description=(
            "Genre filter — left side of a Discogs ``Genre---Style`` label. "
            "Each entry matches every ``Genre---*`` row."
        ),
    )
    style: list[str] | None = Field(
        None,
        description=(
            "Style filter — right side of a Discogs ``Genre---Style`` "
            "label. Each entry matches every ``*---Style`` row across "
            "genres. Combine with ``genre`` for an exact label."
        ),
    )
    style_min: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Minimum classifier probability for a style row to count.",
    )
    style_mode: str = Field(
        "any",
        pattern="^(any|all)$",
        description="``any`` (default) or ``all`` of the requested constraints.",
    )

    @field_validator("genre", "style")
    @classmethod
    def _no_separator(cls, v: list[str] | None, info) -> list[str] | None:
        return _reject_separator(v, info.field_name)

    def to_track_filter(self) -> TrackFilter:
        bpm = self.bpm or FloatRange()
        dance = self.danceability or FloatRange()
        loud = self.loudness or FloatRange()
        return TrackFilter(
            bpm_min=bpm.gte,
            bpm_max=bpm.lte,
            danceability_min=dance.gte,
            danceability_max=dance.lte,
            loudness_min=loud.gte,
            loudness_max=loud.lte,
            key=self.key,
            scale=self.scale,
            genres=self.genre,
            styles=self.style,
            style_min_probability=self.style_min,
            style_match=self.style_mode,
        )


# ---------------------------------------------------------------------------
# URL range parser
# ---------------------------------------------------------------------------


def parse_range(value: str | None) -> FloatRange:
    """Parse a query-string range into a :class:`FloatRange`.

    Accepts ``"120..130"`` (closed), ``"120.."`` (lower only), ``"..130"``
    (upper only), or a bare number ``"128"`` (treated as ``gte=lte=128``).
    Returns an empty range when ``value`` is ``None`` or empty.

    Raises ``ValueError`` on a malformed input — caller maps to HTTP 400.
    """
    if value is None or value == "":
        return FloatRange()
    if ".." in value:
        lo_str, hi_str = value.split("..", 1)
        lo = float(lo_str) if lo_str else None
        hi = float(hi_str) if hi_str else None
        return FloatRange(gte=lo, lte=hi)
    # Bare number = exact match (closed degenerate range).
    n = float(value)
    return FloatRange(gte=n, lte=n)


def build_track_filter(
    *,
    bpm: str | None = None,
    danceability: str | None = None,
    loudness: str | None = None,
    key: list[str] | None = None,
    scale: str | None = None,
    genre: list[str] | None = None,
    style: list[str] | None = None,
    style_min: float = 0.0,
    style_mode: str = "any",
) -> TrackFilter:
    """Compose a :class:`TrackFilter` from URL-style query parameters.

    Numeric range params accept the ``120..130`` / ``120..`` / ``..130`` /
    ``128`` shorthand documented in :func:`parse_range`. Set-membership params
    (``key``, ``genre``, ``style``) are passed through as lists.

    Genre and style values must not contain ``---``.
    """
    bpm_r = parse_range(bpm)
    dance_r = parse_range(danceability)
    loud_r = parse_range(loudness)
    genre = _reject_separator(genre, "genre")
    style = _reject_separator(style, "style")
    return TrackFilter(
        bpm_min=bpm_r.gte,
        bpm_max=bpm_r.lte,
        danceability_min=dance_r.gte,
        danceability_max=dance_r.lte,
        loudness_min=loud_r.gte,
        loudness_max=loud_r.lte,
        key=key,
        scale=scale,
        genres=genre,
        styles=style,
        style_min_probability=style_min,
        style_match=style_mode,
    )
