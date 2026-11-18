"""Small stateless helpers for Germany census."""

from __future__ import annotations
from typing import Optional


def state_code(state: str) -> str:
    """Normalize a state name or abbreviation to its 2-letter code.

    Args:
        state: State name, abbreviation or code.

    Returns:
        The 2-letter code.

    Raises:
        ValueError: For an unknown state.
    """
    from .constants import STATE_ABBR, STATE_CODES
    if state in STATE_CODES:
        return state
    for code, name in STATE_CODES.items():
        if STATE_ABBR.get(name) == state.upper() or name.lower() == state.lower():
            return code
    raise ValueError(f"Unknown Germany state: '{state}'")


def state_abbr(state: str) -> str:
    """Normalize a state name or code to its abbreviation.

    Args:
        state: State name or code.

    Returns:
        The abbreviation.

    Raises:
        ValueError: For an unknown state.
    """
    from .constants import STATE_ABBR, STATE_CODES
    if isinstance(state, str) and state in {v for v in STATE_ABBR.values()}:
        return state
    if state in STATE_CODES:
        return STATE_ABBR[STATE_CODES[state]]
    for code, name in STATE_CODES.items():
        if name.lower() == state.lower():
            return STATE_ABBR[name]
    raise ValueError(f"Unknown Germany state: '{state}'")


def pick_geoid_column(columns) -> Optional[str]:
    """Pick the most specific GEOID-like column present.

    Args:
        columns: Column names.

    Returns:
        The column, or None.
    """
    candidates = [c for c in columns if "GEOID" in c.upper() or "AGS" in c.upper() or "CODE" in c.upper()]
    if not candidates:
        return None
    if "GEOID" in candidates:
        return "GEOID"
    for c in ["AGS", "STATE_CODE", "DISTRICT_CODE"]:
        if c in candidates:
            return c
    return candidates[0]


__all__ = ["state_code", "state_abbr", "pick_geoid_column"]
