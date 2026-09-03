"""Small stateless helpers shared by every Mexico census source module.

Technical aspects:
    Similar to USA.utils, this module provides helper functions for
    working with Mexico-specific identifiers and naming conventions.
"""

from __future__ import annotations

from typing import Optional


def state_abbr(state: str) -> str:
    """Normalize a state name, abbreviation, or code to its INEGI abbreviation.

    Args:
        state: State name, abbreviation, or 2-digit code.

    Returns:
        INEGI state abbreviation (2-4 characters).

    Raises:
        ValueError: If ``state`` does not resolve to a known Mexico state.
    """
    from .constants import STATE_ABBR, STATE_CODES
    
    # Try as abbreviation first
    if isinstance(state, str) and state.upper() in {v.upper() for v in STATE_ABBR.values()}:
        return state.upper()
    
    # Try as code first
    if state in STATE_CODES:
        return STATE_ABBR[STATE_CODES[state]]
    
    # Try as name
    for code, name in STATE_CODES.items():
        if name.lower() == state.lower():
            return STATE_ABBR[name]
    
    raise ValueError(f"Unknown Mexico state: '{state}'")


def state_code(state: str) -> str:
    """Normalize a state name, abbreviation, or code to its INEGI 2-digit code.

    Args:
        state: State name, abbreviation, or 2-digit code.

    Returns:
        Two-digit INEGI state code.

    Raises:
        ValueError: If ``state`` does not resolve to a known Mexico state.
    """
    from .constants import STATE_ABBR, STATE_CODES
    
    # Try as code first
    if state in STATE_CODES:
        return state
    
    # Try as abbreviation
    for code, name in STATE_CODES.items():
        if STATE_ABBR.get(name) == state.upper():
            return code
        # Try case-insensitive match
        if name.lower().replace(" ", "").replace("de", "").replace("del", "") == \
                state.lower().replace(" ", "").replace("de", "").replace("del", ""):
            return code
    
    # Try as name
    for code, name in STATE_CODES.items():
        if name.lower() == state.lower():
            return code
    
    raise ValueError(f"Unknown Mexico state: '{state}'")


def pick_geoid_column(columns) -> Optional[str]:
    """Pick the most specific GEOID-like column present.

    Args:
        columns: Candidate column names.

    Returns:
        The best-matching column name, or ``None`` if none look like a
        GEOID column.
    """
    candidates = [c for c in columns if "GEOID" in c.upper() or "CVE" in c.upper()]
    
    if not candidates:
        return None
    
    # Prefer exact GEOID match
    if "GEOID" in candidates:
        return "GEOID"
    
    # Prefer CVE_ENT (state code) as it's the most common ID
    for c in ["CVE_ENT", "ENTIDAD", "CVE_ENTIDAD"]:
        if c in candidates:
            return c
    
    return candidates[0]
