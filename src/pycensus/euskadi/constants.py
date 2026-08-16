"""Static Euskadi (Basque Country) geography reference data.

Technical aspects:
    The Basque Country (Euskadi) is an autonomous community in Spain with its own
    statistical office (Eustat) that publishes census data separately from INE.
    
    Euskadi's administrative divisions:
    - Autonomous Community (Euskadi)
    - Historical Territories (Foru Aldundiak): Araba, Bizkaia, Gipuzkoa
    - Comarcas (Regional districts)
    - Municipalities (Udalerriak)
    - Districts/Quarters (Barrutiak/Auzoak)
    - Statistical Areas
    
    Note: The Basque Country has special autonomy status and collects its own
    census data through Eustat (Basque Statistics Office).

Source:
    https://www.eustat.eus/
"""

from typing import Dict, List

# Historical Territories (Foru Aldundiak) - equivalent to provinces
TERRITORY_CODES: Dict[str, str] = {
    "01": "Araba",
    "48": "Bizkaia",
    "20": "Gipuzkoa",
}

# Territory abbreviations
TERRITORY_ABBR: Dict[str, str] = {
    "Araba": "AR",
    "Bizkaia": "BI",
    "Gipuzkoa": "GI",
}

# Basque names for territories
TERRITORY_BASQUE: Dict[str, str] = {
    "Araba": "Araba",
    "Bizkaia": "Bizkaia",
    "Gipuzkoa": "Gipuzkoa",
}

# Comarcas (regional districts) - simplified list
COMARCAS_CODES: Dict[str, Dict[str, str]] = {
    "01": {  # Araba
        "011": "Añana",
        "012": "Ayala",
        "013": "Campezo-Montaña Alavesa",
        "014": "Ebro",
        "015": "Entzia",
        "016": "Gorbeialdea",
        "017": "Laguardia-Rioja Alavesa",
        "018": "Salvatierra-Aguirre",
        "019": "Vitoria-Gasteiz",
    },
    "48": {  # Bizkaia
        "481": "Arratia-Nervion",
        "482": "Bilbao",
        "483": "Busturialdea-Urdaibai",
        "484": "Durangaldea",
        "485": "Eskualdeko Barrualdea",
        "486": "Ezkialdea-Especificacia",
        "487": "Greater Bilbao",
        "488": "Lea-Artibai",
        "489": "Mungialdea",
    },
    "20": {  # Gipuzkoa
        "201": "Bidasoa-Txingudi",
        "202": "Debabarrena",
        "203": "Debagoiena",
        "204": "Donostialdea",
        "205": "Goierri",
        "206": "Oarsoaldea",
        "207": "Tolosaldea",
        "208": "Urola Costa",
        "209": "Urola Erdiala",
    },
}


def territory_code(territory_name_or_abbr: str) -> str:
    """Return the 2-digit code for a territory name, abbreviation, or code.
    
    Args:
        territory_name_or_abbr: Territory name, abbreviation, or 2-digit code.
        
    Returns:
        Two-digit territory code.
        
    Raises:
        ValueError: If the input does not resolve to a known Euskadi territory.
    """
    # Try as code first
    if territory_name_or_abbr in TERRITORY_CODES:
        return territory_name_or_abbr
    
    # Try as abbreviation
    for code, name in TERRITORY_CODES.items():
        if TERRITORY_ABBR.get(name) == territory_name_or_abbr.upper():
            return code
        # Try case-insensitive match
        if name.lower() == territory_name_or_abbr.lower():
            return code
        # Try Basque name
        if TERRITORY_BASQUE.get(name) == territory_name_or_abbr:
            return code
    
    raise ValueError(f"Unknown Euskadi territory: '{territory_name_or_abbr}'")


def territory_abbr(territory_name_or_code: str) -> str:
    """Return the abbreviation for a territory name or code.
    
    Args:
        territory_name_or_code: Territory name or 2-digit code.
        
    Returns:
        Abbreviation for the territory.
        
    Raises:
        ValueError: If the input does not resolve to a known Euskadi territory.
    """
    if isinstance(territory_name_or_code, str) and territory_name_or_code in {v.upper() for v in TERRITORY_ABBR.values()}:
        return territory_name_or_code.upper()
    
    # Try as code
    if territory_name_or_code in TERRITORY_CODES:
        return TERRITORY_ABBR[TERRITORY_CODES[territory_name_or_code]]
    
    # Try as name
    for code, name in TERRITORY_CODES.items():
        if name.lower() == territory_name_or_code.lower():
            return TERRITORY_ABBR[name]
    
    raise ValueError(f"Unknown Euskadi territory: '{territory_name_or_code}'")


# Geometry level configuration
# Euskadi's native levels: autonomous_community, territory, comarca, municipality, district
LEVEL_FALLBACK: Dict[str, str] = {
    "state": "autonomous_community",  # Euskadi as a whole
    "province": "territory",  # Territories are equivalent to provinces
    "county": "comarca",  # Comarcas are equivalent to counties
    "tract": "district",  # Districts are equivalent to tracts
    "blockgroup": "district",
    "place": "municipality",
}

# Most recent vintage year for data
LATEST_YEAR: Dict[str, int] = {
    "geography": 2021,
    "census": 2021,
}

# Data download URLs for Eustat Census 2021
# Eustat (Euskadi Statistics Office) provides census data at:
# https://www.eustat.eus/
CENSUS_2021_URLS: Dict[str, str] = {
    "microdata": "https://www.eustat.eus/temas/12001/tema_12001/es_definiciones.html",
    "tables": "https://www.eustat.eus/temas/12001/tema_12001/es_definiciones.html",
    "boundaries": "https://www.eustat.eus/geoservicios/descargas.html",
}

# Default data directory (kept for backward compatibility, but cache is preferred)
DEFAULT_DATA_DIR = "data/euskadi"

__all__ = [
    "TERRITORY_CODES",
    "TERRITORY_ABBR",
    "TERRITORY_BASQUE",
    "COMARCAS_CODES",
    "territory_code",
    "territory_abbr",
    "LEVEL_FALLBACK",
    "LATEST_YEAR",
    "CENSUS_2021_URLS",
    "DEFAULT_DATA_DIR",
]
