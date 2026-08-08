"""Standard cross-country geometry level vocabulary and per-country fallback resolution.

Technical aspects:
    Every country module is expected to accept ``level`` values from this
    same fixed vocabulary, regardless of whether that geography natively
    exists there. A country declares a ``LEVEL_FALLBACK`` dict (e.g.
    ``USA.constants.LEVEL_FALLBACK``) mapping any level it lacks to the
    closest one it does have (e.g. the US has no "province", so
    ``"province" -> "county"``); :func:`resolve_level` walks that mapping
    until it lands on a level the country actually implements. This keeps
    calling code (loaders, notebooks, cross-country comparisons) written
    against one consistent set of level names.
"""

from __future__ import annotations

from typing import Dict, List

STANDARD_LEVELS: List[str] = [
    "block",
    "blockgroup",
    "tract",
    "place",
    "county",
    "province",
    "state",
    "nation",
]
"""Geometry levels every country census source should accept, finest to coarsest-ish."""


def resolve_level(level: str, fallback: Dict[str, str]) -> str:
    """Walk a country's fallback map until ``level`` names something it natively supports.

    Args:
        level: Requested standard level name.
        fallback: Country-specific ``{unsupported_level: substitute_level}`` map.

    Returns:
        ``level`` itself if not in ``fallback``, otherwise the level it
        ultimately resolves to (following chained fallbacks, without looping
        forever on a cycle).
    """
    seen = set()
    while level in fallback and level not in seen:
        seen.add(level)
        level = fallback[level]
    return level
