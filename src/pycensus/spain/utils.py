"""Small stateless helpers shared by every Spain census source module.

Technical aspects:
    Similar to USA.utils and Mexico.utils, this module provides helper functions
    for working with Spain-specific identifiers and naming conventions.
"""

from __future__ import annotations

from typing import Optional


def autonomous_community_abbr(ac: str) -> str:
    """Normalize an autonomous community name, abbreviation, or code to its INE abbreviation.

    Args:
        ac: Autonomous community name, abbreviation, or 2-digit code.

    Returns:
        INE autonomous community abbreviation (2-4 characters).

    Raises:
        ValueError: If ``ac`` does not resolve to a known Spain autonomous community.
    """
    from .constants import AUTONOMOUS_COMMUNITY_ABBR, AUTONOMOUS_COMMUNITY_CODES
    
    # Try as abbreviation first
    if isinstance(ac, str) and ac.upper() in {v.upper() for v in AUTONOMOUS_COMMUNITY_ABBR.values()}:
        return ac.upper()
    
    # Try as code first
    if ac in AUTONOMOUS_COMMUNITY_CODES:
        return AUTONOMOUS_COMMUNITY_ABBR[AUTONOMOUS_COMMUNITY_CODES[ac]]
    
    # Try as name
    for code, name in AUTONOMOUS_COMMUNITY_CODES.items():
        if name.lower() == ac.lower():
            return AUTONOMOUS_COMMUNITY_ABBR[name]
    
    raise ValueError(f"Unknown Spain autonomous community: '{ac}'")


def autonomous_community_code(ac: str) -> str:
    """Normalize an autonomous community name, abbreviation, or code to its INE 2-digit code.

    Args:
        ac: Autonomous community name, abbreviation, or 2-digit code.

    Returns:
        Two-digit INE autonomous community code.

    Raises:
        ValueError: If ``ac`` does not resolve to a known Spain autonomous community.
    """
    from .constants import AUTONOMOUS_COMMUNITY_ABBR, AUTONOMOUS_COMMUNITY_CODES
    
    # Try as code first
    if ac in AUTONOMOUS_COMMUNITY_CODES:
        return ac
    
    # Try as abbreviation
    for code, name in AUTONOMOUS_COMMUNITY_CODES.items():
        if AUTONOMOUS_COMMUNITY_ABBR.get(name) == ac.upper():
            return code
        # Try case-insensitive match
        if name.lower().replace(" ", "").replace("(", "").replace(")", "") == \
                ac.lower().replace(" ", "").replace("(", "").replace(")", ""):
            return code
    
    # Try as name
    for code, name in AUTONOMOUS_COMMUNITY_CODES.items():
        if name.lower() == ac.lower():
            return code
    
    raise ValueError(f"Unknown Spain autonomous community: '{ac}'")


def province_abbr(province: str) -> str:
    """Normalize a province name, abbreviation, or code to its INE abbreviation.

    Args:
        province: Province name, abbreviation, or 2-digit code.

    Returns:
        INE province abbreviation (1-2 characters).

    Raises:
        ValueError: If ``province`` does not resolve to a known Spain province.
    """
    from .constants import PROVINCE_ABBR, PROVINCE_CODES
    
    # Try as abbreviation first
    if isinstance(province, str) and province.upper() in {v.upper() for v in PROVINCE_ABBR.values()}:
        return province.upper()
    
    # Try as code first
    if province in PROVINCE_CODES:
        return PROVINCE_ABBR[PROVINCE_CODES[province]]
    
    # Try as name
    for code, name in PROVINCE_CODES.items():
        if name.lower() == province.lower():
            return PROVINCE_ABBR[name]
    
    raise ValueError(f"Unknown Spain province: '{province}'")


def province_code(province: str) -> str:
    """Normalize a province name, abbreviation, or code to its INE 2-digit code.

    Args:
        province: Province name, abbreviation, or 2-digit code.

    Returns:
        Two-digit INE province code.

    Raises:
        ValueError: If ``province`` does not resolve to a known Spain province.
    """
    from .constants import PROVINCE_ABBR, PROVINCE_CODES
    
    # Try as code first
    if province in PROVINCE_CODES:
        return province
    
    # Try as abbreviation
    for code, name in PROVINCE_CODES.items():
        if PROVINCE_ABBR.get(name) == province.upper():
            return code
        # Try case-insensitive match
        if name.lower().replace(" ", "").replace("(", "").replace(")", "") == \
                province.lower().replace(" ", "").replace("(", "").replace(")", ""):
            return code
    
    # Try as name
    for code, name in PROVINCE_CODES.items():
        if name.lower() == province.lower():
            return code
    
    raise ValueError(f"Unknown Spain province: '{province}'")


def pick_geoid_column(columns) -> Optional[str]:
    """Pick the most specific GEOID-like column present.

    Args:
        columns: Candidate column names.

    Returns:
        The best-matching column name, or ``None`` if none look like a
        GEOID column.
    """
    candidates = [c for c in columns if "GEOID" in c.upper() or "COD" in c.upper() or "CVE" in c.upper()]
    
    if not candidates:
        return None
    
    # Prefer exact GEOID match
    if "GEOID" in candidates:
        return "GEOID"
    
    # Prefer COD_PROV (province code) or COD_AUT (autonomous community code)
    for c in ["COD_AUT", "COD_PROV", "COD_MUN", "COD_SEC", "COD_MZA"]:
        if c in candidates:
            return c
    
    return candidates[0]


def municipality_code(mun_name_or_code: str) -> str:
    """Normalize a municipality name or code to its INE code.
    
    Note: This is a placeholder function. In a real implementation, this would
    require a comprehensive mapping of municipality names to codes, which is
    quite large (over 8,000 municipalities in Spain).
    
    For now, this returns the input if it looks like a code, or raises an error.
    
    Args:
        mun_name_or_code: Municipality name or 5-digit code (COD_MUN).
        
    Returns:
        5-digit INE municipality code.
        
    Raises:
        ValueError: If the input does not resolve to a known municipality code.
    """
    # INE municipality codes are 5 digits: first 2 are province code, last 3 are municipality code within province
    if isinstance(mun_name_or_code, str) and mun_name_or_code.isdigit() and len(mun_name_or_code) == 5:
        return mun_name_or_code
    
    # For now, we can't resolve municipality names without a comprehensive mapping
    raise ValueError(f"Municipality code lookup not implemented for: '{mun_name_or_code}'. "
                     f"Please use the 5-digit INE municipality code.")


__all__ = [
    "autonomous_community_abbr",
    "autonomous_community_code",
    "province_abbr",
    "province_code",
    "pick_geoid_column",
    "municipality_code",
]
