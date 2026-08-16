"""Static Mexico geography reference data shared by every Mexico census source.

Technical aspects:
    Boundary files for Mexico will be fetched from INEGI's geographic data.
    This module maps logical level names to the functions that fetch them,
    the geography hierarchy, and configuration for data loading.

    Mexico's administrative divisions:
    - Nation (country level)
    - State (estado) - 32 states (31 estados + Ciudad de Mexico)
    - Municipality (municipio) - equivalent to county
    - Locality (localidad) - equivalent to place/city
    - Ageb (Area Geoestadistica Basica) - equivalent to tract/blockgroup
    - Block (manzana)

Source:
    https://www.inegi.org.mx/temas/geografia/
"""

from typing import Dict, List

# Mexico state codes (INEGI uses 2-digit codes)
STATE_CODES: Dict[str, str] = {
    "01": "Aguascalientes",
    "02": "Baja California",
    "03": "Baja California Sur",
    "04": "Campeche",
    "05": "Coahuila de Zaragoza",
    "06": "Colima",
    "07": "Chiapas",
    "08": "Chihuahua",
    "09": "Ciudad de Mexico",  # Federal entity (Distrito Federal)
    "10": "Durango",
    "11": "Guanajuato",
    "12": "Guerrero",
    "13": "Hidalgo",
    "14": "Jalisco",
    "15": "Mexico",  # Estado de Mexico
    "16": "Michoacan de Ocampo",
    "17": "Morelos",
    "18": "Nayarit",
    "19": "Nuevo Leon",
    "20": "Oaxaca",
    "21": "Puebla",
    "22": "Queretaro",
    "23": "Quintana Roo",
    "24": "San Luis Potosi",
    "25": "Sinaloa",
    "26": "Sonora",
    "27": "Tabasco",
    "28": "Tamaulipas",
    "29": "Tlaxcala",
    "30": "Veracruz de Ignacio de la Llave",
    "31": "Yucatan",
    "32": "Zacatecas",
}

STATE_ABBR: Dict[str, str] = {
    "Aguascalientes": "AGS",
    "Baja California": "BC",
    "Baja California Sur": "BCS",
    "Campeche": "CAMP",
    "Coahuila de Zaragoza": "COAH",
    "Colima": "COL",
    "Chiapas": "CHIS",
    "Chihuahua": "CHIH",
    "Ciudad de Mexico": "CDMX",
    "Durango": "DUR",
    "Guanajuato": "GTO",
    "Guerrero": "GRO",
    "Hidalgo": "HGO",
    "Jalisco": "JAL",
    "Mexico": "MEX",
    "Michoacan de Ocampo": "MICH",
    "Morelos": "MOR",
    "Nayarit": "NAY",
    "Nuevo Leon": "NL",
    "Oaxaca": "OAX",
    "Puebla": "PUE",
    "Queretaro": "QRO",
    "Quintana Roo": "Q ROO",
    "San Luis Potosi": "SLP",
    "Sinaloa": "SIN",
    "Sonora": "SON",
    "Tabasco": "TAB",
    "Tamaulipas": "TAMS",
    "Tlaxcala": "TLAX",
    "Veracruz de Ignacio de la Llave": "VER",
    "Yucatan": "YUC",
    "Zacatecas": "ZAC",
}

# Reverse mapping for state code lookup
# For backward compatibility with code that might import these from constants
# The canonical versions are in utils.py
def _state_code_from_lookups(state_name_or_abbr: str) -> str:
    """Internal function to lookup state code without circular imports."""
    # Try direct lookup in STATE_CODES
    if state_name_or_abbr in STATE_CODES:
        return state_name_or_abbr
    
    # Try abbreviation lookup
    for code, name in STATE_CODES.items():
        if STATE_ABBR.get(name) == state_name_or_abbr.upper():
            return code
        if name.lower().replace(" ", "").replace("de", "").replace("del", "") == \
                state_name_or_abbr.lower().replace(" ", "").replace("de", "").replace("del", ""):
            return code
    
    # Try full name lookup (case-insensitive)
    for code, name in STATE_CODES.items():
        if name.lower() == state_name_or_abbr.lower():
            return code
    
    raise ValueError(f"Unknown Mexico state: {state_name_or_abbr}")


def state_code(state_name_or_abbr: str) -> str:
    """Return the 2-digit INEGI code for a state name or abbreviation.
    
    Note: This function is maintained for backward compatibility. New code should
    use utils.state_code() instead for consistency with the USA implementation.
    """
    return _state_code_from_lookups(state_name_or_abbr)


def state_abbr(state_name_or_code: str) -> str:
    """Return the abbreviation for a state name or code.
    
    Note: This function is maintained for backward compatibility. New code should
    use utils.state_abbr() instead for consistency with the USA implementation.
    """
    if isinstance(state_name_or_code, str) and state_name_or_code in STATE_ABBR.values():
        return state_name_or_code
    
    # Try as code
    if state_name_or_code in STATE_CODES:
        return STATE_ABBR[STATE_CODES[state_name_or_code]]
    
    # Try as name
    for code, name in STATE_CODES.items():
        if name.lower() == state_name_or_code.lower():
            return STATE_ABBR[name]
    
    raise ValueError(f"Unknown Mexico state: {state_name_or_code}")


# Geometry level configuration
# Mexico's native levels: nation, state, municipality, locality, ageb, block
# We map standard levels to Mexico's native levels
LEVEL_FALLBACK: Dict[str, str] = {
    "province": "state",  # No provinces in Mexico, use state
    "county": "municipality",  # Use municipality as county equivalent
    "tract": "ageb",  # Ageb is the closest to tract
    "blockgroup": "ageb",  # Ageb is the closest to blockgroup
    "place": "locality",  # Locality is closest to place
}

# Most recent vintage year for data
LATEST_YEAR: Dict[str, int] = {
    "geography": 2020,
    "census": 2020,
}

# Data download URLs for INEGI Census 2020
# These are the base URLs for downloading census data
CENSUS_2020_URLS: Dict[str, str] = {
    "microdata": "https://www.inegi.org.mx/programas/ccpv/2020/?ps=microdatos",
    "mass_download": "https://www.inegi.org.mx/app/descarga/default.html",
    "tables": "https://www.inegi.org.mx/programas/ccpv/2020/#Tabulados",
}

# Default data directory
DEFAULT_DATA_DIR = "data/mexico"

# Census 2020 dataset configuration
CENSUS_2020_DATASETS: Dict[str, Dict] = {
    "person": {
        "description": "Person-level microdata",
        "filename_pattern": "microdatos_personas_{state}.csv",
        "columns": [
            "ENTIDAD",  # State code
            "MUN",  # Municipality code
            "LOC",  # Locality code
            "AGEB",  # Ageb code
            "SEXO",  # Gender
            "EDAD",  # Age
            "LENGUA",  # Indigenous language
            "RELIGION",  # Religion
            "DERECHOHAB",  # Healthcare access
            "ASISTESC",  # School attendance
            "MAXGRADO",  # Education level
            "CONYUGE",  # Marital status
            "NACIM",  # Birthplace
            "MIGRACION",  # Migration status
            "DISCAP",  # Disability
        ]
    },
    "household": {
        "description": "Household-level microdata",
        "filename_pattern": "microdatos_hogares_{state}.csv",
        "columns": [
            "ENTIDAD",  # State code
            "MUN",  # Municipality code
            "LOC",  # Locality code
            "AGEB",  # Ageb code
            "HOGARES",  # Number of households
            "VIVPART",  # Occupied housing units
            "TAMHOG",  # Household size
            "JEFATURA",  # Household head characteristics
            "SEXJEF",  # Gender of household head
            "EDADJEF",  # Age of household head
            "INGRESO",  # Household income
            "FUENTEING",  # Income source
            "GASTOS",  # Household expenses
        ]
    },
    "housing": {
        "description": "Housing-level microdata",
        "filename_pattern": "microdatos_viviendas_{state}.csv",
        "columns": [
            "ENTIDAD",  # State code
            "MUN",  # Municipality code
            "LOC",  # Locality code
            "AGEB",  # Ageb code
            "TIPVIV",  # Housing type
            "MATPISO",  # Floor material
            "MATTECHO",  # Roof material
            "MATPAR",  # Wall material
            "AGUADENT",  # Water access
            "DRENAJE",  # Drainage/sewer
            "ENERGIA",  # Energy/electricity
            "COMBUST",  # Fuel type
            "INTERNET",  # Internet access
            "COMPUTADORA",  # Computer ownership
            "AUTO",  # Car ownership
            "MOTO",  # Motorcycle ownership
        ]
    },
    "employment": {
        "description": "Employment and economic activity",
        "filename_pattern": "microdatos_economicos_{state}.csv",
        "columns": [
            "ENTIDAD",  # State code
            "MUN",  # Municipality code
            "PEA",  # Economically active population
            "OCUPADOS",  # Employed
            "DESOCUPADOS",  # Unemployed
            "SECTOR",  # Economic sector
            "RAMA",  # Industry branch
            "POSOCUP",  # Occupation position
            "INGOCUP",  # Income from occupation
        ]
    }
}

__all__ = [
    "STATE_CODES",
    "STATE_ABBR",
    "state_code",
    "state_abbr",
    "LEVEL_FALLBACK",
    "LATEST_YEAR",
    "CENSUS_2020_URLS",
    "DEFAULT_DATA_DIR",
    "CENSUS_2020_DATASETS",
]
