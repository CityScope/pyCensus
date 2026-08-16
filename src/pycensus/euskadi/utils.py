"""Small stateless helpers for Euskadi census."""

from __future__ import annotations
from typing import Optional


def territory_code(territory: str) -> str:
    """Normalize a territory name, abbreviation, or code to its code."""
    from .constants import TERRITORY_ABBR, TERRITORY_BASQUE, TERRITORY_CODES
    
    if territory in TERRITORY_CODES:
        return territory
    
    for code, name in TERRITORY_CODES.items():
        if TERRITORY_ABBR.get(name) == territory.upper():
            return code
        if name.lower() == territory.lower():
            return code
        if TERRITORY_BASQUE.get(name) == territory:
            return code
    
    raise ValueError(f"Unknown Euskadi territory: '{territory}'")


def territory_abbr(territory: str) -> str:
    """Normalize a territory name or code to its abbreviation."""
    from .constants import TERRITORY_ABBR, TERRITORY_CODES
    
    if isinstance(territory, str) and territory in {v.upper() for v in TERRITORY_ABBR.values()}:
        return territory.upper()
    
    if territory in TERRITORY_CODES:
        return TERRITORY_ABBR[TERRITORY_CODES[territory]]
    
    for code, name in TERRITORY_CODES.items():
        if name.lower() == territory.lower():
            return TERRITORY_ABBR[name]
    
    raise ValueError(f"Unknown Euskadi territory: '{territory}'")


def comarca_code(comarca: str) -> str:
    """Normalize a comarca name or code to its code.
    
    Note: This is a partial implementation.
    """
    from .constants import COMARCAS_CODES
    
    # Try as code first (format: territory_code + comarca_code)
    if len(comarca) == 3 and comarca[:2] in COMARCAS_CODES and comarca[2:] in COMARCAS_CODES[comarca[:2]]:
        return comarca
    
    # Try as code without territory prefix
    if len(comarca) == 3:
        for terr_code, comarcas in COMARCAS_CODES.items():
            if comarca in comarcas.values():
                # Find the first match
                for c, name in comarcas.items():
                    if name == comarca:
                        return f"{terr_code}{c}"
    
    # Try as name
    for terr_code, comarcas in COMARCAS_CODES.items():
        for c, name in comarcas.items():
            if name.lower() == comarca.lower():
                return f"{terr_code}{c}"
    
    raise ValueError(f"Comarca code lookup not implemented for: '{comarca}'. Please use the 3-digit code.")


def pick_geoid_column(columns) -> Optional[str]:
    """Pick the most specific GEOID-like column present."""
    candidates = [c for c in columns if "GEOID" in c.upper() or "COD" in c.upper() or "CODE" in c.upper()]
    
    if not candidates:
        return None
    
    if "GEOID" in candidates:
        return "GEOID"
    
    for c in ["TERRITORY_CODE", "COMARCA_CODE", "MUNICIPALITY_CODE", "COD_TERR", "COD_COM", "COD_MUN"]:
        if c in candidates:
            return c
    
    return candidates[0]


__all__ = [
    "territory_code",
    "territory_abbr",
    "comarca_code",
    "pick_geoid_column",
]
