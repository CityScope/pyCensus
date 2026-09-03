"""Small stateless helpers shared by every Canada census source module.

Technical aspects:
    Region-code resolution itself lives on
    :mod:`pycensus.canada.constants` (``province_code``/``province_abbr``)
    since Canada's code tables are small and it avoids an import cycle
    with :mod:`pycensus.canada.geography`; this module re-exports them
    (mirroring where ``pycensus.mexico.geography``/``pycensus.mexico.inegi.loader``
    reach for ``pycensus.mexico.utils.state_code``) plus small
    format-agnostic helpers used by more than one source.
"""

from __future__ import annotations

from typing import Optional

from .constants import province_abbr, province_code


def pick_geoid_column(columns) -> Optional[str]:
    """Pick the most specific GEOID-like column present.

    Args:
        columns: Candidate column names.

    Returns:
        The best-matching column name, or ``None`` if none look like a
        GEOID column.
    """
    candidates = [c for c in columns if "GEOID" in c.upper() or "DGUID" in c.upper()]
    if not candidates:
        return None
    if "GEOID" in candidates:
        return "GEOID"
    return candidates[0]


__all__ = ["province_code", "province_abbr", "pick_geoid_column"]
