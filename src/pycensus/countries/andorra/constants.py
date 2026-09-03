"""Static Andorra reference data shared by every Andorra census source.

Technical aspects:
    Andorra has 7 parishes ("parroquies" in Catalan; "comú" is their local
    government body). ``PARISH_CODES`` below uses the real ISO 3166-2:AD
    subdivision codes -- verified 2026-08-20 by cross-checking against the
    ``Codi`` field of the Departament d'Estadistica's own hosted parish
    boundary layer (see :mod:`pycensus.andorra.geography`), which returned
    exactly these 7 codes/names:
    ``https://www.estadistica.ad/server/rest/services/Estadistica/Cartografia_base/FeatureServer/3/query?where=1%3D1&outFields=*&outSR=4326&f=geojson``

    These also match the parish list and ordering documented on Wikipedia's
    "Parishes of Andorra" page and the ISO 3166-2:AD standard.
"""

from __future__ import annotations

from typing import Dict

# Real ISO 3166-2:AD parish codes, verified against
# estadistica.ad's own hosted "Parroquies_Pol_codi" boundary layer (Codi field).
PARISH_CODES: Dict[str, str] = {
    "AD-01": "Canillo",
    "AD-02": "Encamp",
    "AD-03": "Ordino",
    "AD-04": "La Massana",
    "AD-05": "Andorra la Vella",
    "AD-06": "Sant Julià de Lòria",
    "AD-07": "Escaldes-Engordany",
}

# The Departament d'Estadistica's population-by-locality layer
# (sig.govern.ad, see pycensus.andorra.estadisticaad.loader) spells this
# parish's name without the "i" ("Sant Julà de Lòria" instead of "Sant
# Julià de Lòria") -- verified live 2026-08-20 by fetching every distinct
# `parroquia` value from that layer. This is a real discrepancy in the
# source data, not a guess -- map both spellings to the same code rather
# than silently dropping that parish's population.
PARISH_NAME_ALIASES: Dict[str, str] = {
    "Sant Julà de Lòria": "Sant Julià de Lòria",
}

PARISH_NAME_TO_CODE: Dict[str, str] = {name: code for code, name in PARISH_CODES.items()}

# Andorra's native levels: nation, parish (comú). No finer subdivision
# (quart/veïnat) has a verified boundary or population source (see
# pycensus.andorra.geography module docstring).
LEVEL_FALLBACK: Dict[str, str] = {
    "state": "parish",
    "province": "parish",
    "county": "parish",
    "municipality": "parish",
    "tract": "parish",
    "blockgroup": "parish",
    "block": "parish",
    "place": "parish",
}

LATEST_YEAR: Dict[str, int] = {
    "geography": 2026,  # boundary layer fetched/verified live on this date
    "census": 2025,  # latest year column (pob_2025) in the population layer
}

# Default data directory for raw (pre-parquet-cache) downloads.
DEFAULT_DATA_DIR = "data/andorra"


def parish_code(name_or_code: str) -> str:
    """Return the ISO 3166-2:AD code for a parish name, alias, or code.

    Args:
        name_or_code: Parish name (Catalan, either the real spelling or the
            known ``PARISH_NAME_ALIASES`` variant), or an ``AD-0X`` code.

    Returns:
        The real ISO 3166-2:AD parish code (``"AD-01"``..``"AD-07"``).

    Raises:
        ValueError: If ``name_or_code`` does not resolve to a known parish.
    """
    if name_or_code in PARISH_CODES:
        return name_or_code
    canonical = PARISH_NAME_ALIASES.get(name_or_code, name_or_code)
    if canonical in PARISH_NAME_TO_CODE:
        return PARISH_NAME_TO_CODE[canonical]
    raise ValueError(f"Unknown Andorra parish: '{name_or_code}'")


__all__ = [
    "PARISH_CODES",
    "PARISH_NAME_ALIASES",
    "PARISH_NAME_TO_CODE",
    "LEVEL_FALLBACK",
    "LATEST_YEAR",
    "DEFAULT_DATA_DIR",
    "parish_code",
]
