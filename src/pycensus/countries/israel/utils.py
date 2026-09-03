"""Small stateless helpers shared by every Israel census source module.

Technical aspects:
    Similar to USA.utils and Mexico.utils, this module provides helper functions
    for working with Israel-specific identifiers and naming conventions.
"""

from __future__ import annotations

from typing import Optional


def district_code(district: str) -> str:
    """Normalize a district name, abbreviation, or code to its CBS code.

    Args:
        district: District name, abbreviation, Hebrew name, or 1-digit code.

    Returns:
        One-digit CBS district code.

    Raises:
        ValueError: If ``district`` does not resolve to a known Israel district.
    """
    from .constants import DISTRICT_ABBR, DISTRICT_CODES, DISTRICT_HEBREW
    
    # Try as code first
    if district in DISTRICT_CODES:
        return district
    
    # Try as abbreviation
    for code, name in DISTRICT_CODES.items():
        if DISTRICT_ABBR.get(name) == district.upper():
            return code
        # Try case-insensitive match
        if name.lower().replace(" ", "").replace("(", "").replace(")", "") == \
                district.lower().replace(" ", "").replace("(", "").replace(")", ""):
            return code
    
    # Try Hebrew name
    for code, name in DISTRICT_CODES.items():
        if DISTRICT_HEBREW.get(name) == district:
            return code
    
    # Try as name
    for code, name in DISTRICT_CODES.items():
        if name.lower() == district.lower():
            return code
    
    raise ValueError(f"Unknown Israel district: '{district}'")


def district_abbr(district: str) -> str:
    """Normalize a district name or code to its abbreviation.

    Args:
        district: District name or 1-digit code.

    Returns:
        Abbreviation for the district.

    Raises:
        ValueError: If ``district`` does not resolve to a known Israel district.
    """
    from .constants import DISTRICT_ABBR, DISTRICT_CODES, DISTRICT_HEBREW
    
    if isinstance(district, str) and district in {v.upper() for v in DISTRICT_ABBR.values()}:
        return district.upper()
    
    # Try as code
    if district in DISTRICT_CODES:
        return DISTRICT_ABBR[DISTRICT_CODES[district]]
    
    # Try as Hebrew name
    for code, name in DISTRICT_CODES.items():
        if DISTRICT_HEBREW.get(name) == district:
            return DISTRICT_ABBR[name]
    
    # Try as name
    for code, name in DISTRICT_CODES.items():
        if name.lower() == district.lower():
            return DISTRICT_ABBR[name]
    
    raise ValueError(f"Unknown Israel district: '{district}'")


def subdistrict_code(subdistrict: str) -> str:
    """Normalize a sub-district name or code to its CBS code.
    
    Note: This is a partial implementation. In a real implementation, this would
    require a comprehensive mapping of all sub-districts.
    
    Args:
        subdistrict: Sub-district name or 2-digit code (district + sub-district).
        
    Returns:
        Two-digit CBS sub-district code.
        
    Raises:
        ValueError: If ``subdistrict`` does not resolve to a known Israel sub-district.
    """
    from .constants import SUBDISTRICT_CODES
    
    # Try as code first
    if subdistrict in SUBDISTRICT_CODES:
        return subdistrict
    
    # Try as name
    for code, name in SUBDISTRICT_CODES.items():
        if name.lower() == subdistrict.lower():
            return code
    
    raise ValueError(f"Unknown Israel sub-district: '{subdistrict}'. "
                     f"Please use the 2-digit CBS code.")


def locality_code(locality) -> str:
    """Normalize a locality name or code to its CBS ``SETL_CODE``/``CR_LAMAS`` code.

    A numeric code (``int`` or a digit-only ``str``) is passed through
    unchanged (as a string). A name is resolved via a real, live query
    against :data:`pycensus.israel.constants.CENSUS_SETL_2022_URL`
    (matching its ``ENG_NAME`` field case-insensitively) -- no hardcoded
    locality-name table, since CBS's own locality attribute layer is
    already the authoritative real source for this.

    Args:
        locality: Locality name, or numeric code (``int`` or ``str``).

    Returns:
        CBS locality code, as a string.

    Raises:
        ValueError: If ``locality`` does not resolve to a known Israel locality.
    """
    if isinstance(locality, int):
        return str(locality)

    locality = str(locality)
    if locality.isdigit():
        return locality

    from . import arcgis
    from .constants import CENSUS_SETL_2022_URL

    features = arcgis.query_features(
        CENSUS_SETL_2022_URL,
        where=f"UPPER(ENG_NAME) = '{locality.upper()}'",
        out_fields="SETL_CODE,ENG_NAME",
        return_geometry=False,
    )
    if not features:
        raise ValueError(
            f"Unknown Israel locality: '{locality}'. Use its exact English name "
            f"(CBS's ENG_NAME field) or a numeric CBS locality code."
        )

    return str(int(features[0]["attributes"]["SETL_CODE"]))


def pick_geoid_column(columns) -> Optional[str]:
    """Pick the most specific GEOID-like column present.

    Args:
        columns: Candidate column names.

    Returns:
        The best-matching column name, or ``None`` if none look like a
        GEOID column.
    """
    candidates = [c for c in columns if "GEOID" in c.upper() or "COD" in c.upper() or "CODE" in c.upper()]
    
    if not candidates:
        return None
    
    # Prefer exact GEOID match
    if "GEOID" in candidates:
        return "GEOID"
    
    # Prefer CBS code columns
    for c in ["DISTRICT_CODE", "DISTRICT_COD", "SUBDIST_CODE", "LOCALITY_CODE", "COD_DIST", "COD_SUBDIST", "COD_LOC"]:
        if c in candidates:
            return c
    
    return candidates[0]


__all__ = [
    "district_code",
    "district_abbr",
    "subdistrict_code",
    "locality_code",
    "pick_geoid_column",
]
