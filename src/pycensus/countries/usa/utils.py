"""Small stateless helpers shared by every US census source module.

Technical aspects:
    GEOID columns are named inconsistently across TIGER/Line vintages
    (``GEOID``, ``GEOID20``, ``GEOID10``, ...); :func:`pick_geoid_column`
    picks the best match deterministically. Every pygris call this package
    makes uses ``cache=False`` -- persistence is pyCensus' own parquet
    cache (:mod:`pycensus.cache`), not pygris' internal shapefile cache.
"""

from __future__ import annotations

from typing import Iterable, Optional

import us


def pick_geoid_column(columns: Iterable[str]) -> Optional[str]:
    """Pick the most specific ``GEOID*`` column present.

    Args:
        columns: Candidate column names.

    Returns:
        The best-matching column name, or ``None`` if none look like a
        GEOID column.
    """

    def priority(col: str) -> int:
        c = col.upper()
        if c == "GEOID":
            return 0
        if c == "GEOID20":
            return 1
        if c == "GEOID10":
            return 2
        if "GEOID" in c:
            return 3
        return 999

    candidates = [c for c in columns if "GEOID" in c.upper()]
    return min(candidates, key=priority, default=None)


def state_abbr(state: str) -> str:
    """Normalize a state name, abbreviation, or FIPS code to its USPS abbreviation.

    Args:
        state: State name, abbreviation, or FIPS code.

    Returns:
        Two-letter USPS state abbreviation.

    Raises:
        ValueError: If ``state`` does not resolve to a known US state.
    """
    resolved = us.states.lookup(state)
    if resolved is None:
        raise ValueError(f"Unknown US state: '{state}'")
    return resolved.abbr


def state_fips(state: str) -> str:
    """Normalize a state name, abbreviation, or FIPS code to its FIPS code.

    Args:
        state: State name, abbreviation, or FIPS code.

    Returns:
        Two-digit FIPS code.

    Raises:
        ValueError: If ``state`` does not resolve to a known US state.
    """
    resolved = us.states.lookup(state)
    if resolved is None:
        raise ValueError(f"Unknown US state: '{state}'")
    return resolved.fips
