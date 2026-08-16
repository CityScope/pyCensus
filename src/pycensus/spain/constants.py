"""Static Spain geography reference data shared by every Spain census source.

Technical aspects:
    Boundary files for Spain will be fetched from INE's geographic data.
    This module maps logical level names to the functions that fetch them,
    the geography hierarchy, and configuration for data loading.

    Spain's administrative divisions:
    - Nation (country level)
    - Autonomous Community (comunidad autónoma) - 17 autonomous communities + 2 autonomous cities
    - Province (provincia) - 50 provinces + 2 autonomous cities
    - Municipality (municipio) - equivalent to city/town
    - District (distrito) - within municipalities
    - Section (sección censal) - census section, equivalent to tract
    - Block (manzana) - city block

Source:
    https://www.ine.es/
"""

from typing import Dict, List

# Spain autonomous community codes (INE uses 2-digit codes)
AUTONOMOUS_COMMUNITY_CODES: Dict[str, str] = {
    "01": "Andalucía",
    "02": "Aragón",
    "03": "Asturias (Principado de Asturias)",
    "04": "Baleares (Islas Baleares)",
    "05": "Canarias",
    "06": "Cantabria",
    "07": "Castilla-La Mancha",
    "08": "Castilla y León",
    "09": "Cataluña",
    "10": "Comunidad Valenciana",
    "11": "Extremadura",
    "12": "Galicia",
    "13": "Madrid (Comunidad de Madrid)",
    "14": "Murcia (Región de Murcia)",
    "15": "Navarra (Comunidad Foral de Navarra)",
    "16": "País Vasco",
    "17": "La Rioja",
    "18": "Ceuta",  # Autonomous city
    "19": "Melilla",  # Autonomous city
}

# Abbreviations for autonomous communities
AUTONOMOUS_COMMUNITY_ABBR: Dict[str, str] = {
    "Andalucía": "AND",
    "Aragón": "ARA",
    "Asturias (Principado de Asturias)": "AST",
    "Baleares (Islas Baleares)": "IB",
    "Canarias": "CAN",
    "Cantabria": "CANT",
    "Castilla-La Mancha": "CLM",
    "Castilla y León": "CYL",
    "Cataluña": "CAT",
    "Comunidad Valenciana": "CV",
    "Extremadura": "EXT",
    "Galicia": "GAL",
    "Madrid (Comunidad de Madrid)": "MAD",
    "Murcia (Región de Murcia)": "MUR",
    "Navarra (Comunidad Foral de Navarra)": "NAV",
    "País Vasco": "PV",
    "La Rioja": "LR",
    "Ceuta": "CEU",
    "Melilla": "MEL",
}

# Province codes (50 provinces + 2 autonomous cities = 52 total)
# Format: "XX" where XX is the INE province code
PROVINCE_CODES: Dict[str, str] = {
    "01": "Álava",
    "02": "Albacete",
    "03": "Alicante",
    "04": "Almería",
    "05": "Ávila",
    "06": "Badajoz",
    "07": "Baleares (Islas Baleares)",
    "08": "Barcelona",
    "09": "Burgos",
    "10": "Cáceres",
    "11": "Cádiz",
    "12": "Castellón",
    "13": "Ciudad Real",
    "14": "Córdoba",
    "15": "Cuenca",
    "16": "Gerona",
    "17": "Granada",
    "18": "Guadalajara",
    "19": "Guipúzcoa",
    "20": "Huelva",
    "21": "Huesca",
    "22": "Jaén",
    "23": "La Coruña",
    "24": "La Rioja",
    "25": "Las Palmas",
    "26": "León",
    "27": "Lérida",
    "28": "Lugo",
    "29": "Madrid",
    "30": "Málaga",
    "31": "Murcia",
    "32": "Navarra",
    "33": "Orense",
    "34": "Palencia",
    "35": "Pontevedra",
    "36": "Salamanca",
    "37": "Santa Cruz de Tenerife",
    "38": "Segovia",
    "39": "Sevilla",
    "40": "Soria",
    "41": "Tarragona",
    "42": "Teruel",
    "43": "Toledo",
    "44": "Valencia",
    "45": "Valladolid",
    "46": "Vizcaya",
    "47": "Zamora",
    "48": "Zaragoza",
    "49": "Ceuta",
    "50": "Melilla",
}

# Province abbreviations
PROVINCE_ABBR: Dict[str, str] = {
    "Álava": "AR",
    "Albacete": "AB",
    "Alicante": "A",
    "Almería": "AL",
    "Ávila": "AV",
    "Badajoz": "BA",
    "Baleares (Islas Baleares)": "PM",
    "Barcelona": "B",
    "Burgos": "BU",
    "Cáceres": "CC",
    "Cádiz": "CA",
    "Castellón": "CS",
    "Ciudad Real": "CR",
    "Córdoba": "CO",
    "Cuenca": "CU",
    "Gerona": "GI",
    "Granada": "GR",
    "Guadalajara": "GU",
    "Guipúzcoa": "SS",
    "Huelva": "H",
    "Huesca": "HU",
    "Jaén": "J",
    "La Coruña": "C",
    "La Rioja": "LO",
    "Las Palmas": "GC",
    "León": "LE",
    "Lérida": "L",
    "Lugo": "LU",
    "Madrid": "M",
    "Málaga": "MA",
    "Murcia": "MU",
    "Navarra": "NA",
    "Orense": "OR",
    "Palencia": "P",
    "Pontevedra": "PO",
    "Salamanca": "SA",
    "Santa Cruz de Tenerife": "TF",
    "Segovia": "SG",
    "Sevilla": "SE",
    "Soria": "SO",
    "Tarragona": "T",
    "Teruel": "TE",
    "Toledo": "TO",
    "Valencia": "V",
    "Valladolid": "VA",
    "Vizcaya": "BI",
    "Zamora": "ZA",
    "Zaragoza": "Z",
    "Ceuta": "CE",
    "Melilla": "ML",
}


def autonomous_community_code(ac_name_or_abbr: str) -> str:
    """Return the 2-digit INE code for an autonomous community name or abbreviation.
    
    Args:
        ac_name_or_abbr: Autonomous community name, abbreviation, or 2-digit code.
        
    Returns:
        Two-digit INE autonomous community code.
        
    Raises:
        ValueError: If the input does not resolve to a known autonomous community.
    """
    # Try as code first
    if ac_name_or_abbr in AUTONOMOUS_COMMUNITY_CODES:
        return ac_name_or_abbr
    
    # Try as abbreviation
    for code, name in AUTONOMOUS_COMMUNITY_CODES.items():
        if AUTONOMOUS_COMMUNITY_ABBR.get(name) == ac_name_or_abbr.upper():
            return code
    
    # Try as name (case-insensitive, handling parentheses)
    for code, name in AUTONOMOUS_COMMUNITY_CODES.items():
        if name.lower().replace("(", "").replace(")", "").replace(" ", "") == \
                ac_name_or_abbr.lower().replace("(", "").replace(")", "").replace(" ", ""):
            return code
    
    raise ValueError(f"Unknown Spain autonomous community: '{ac_name_or_abbr}'")


def autonomous_community_abbr(ac_name_or_code: str) -> str:
    """Return the abbreviation for an autonomous community name or code.
    
    Args:
        ac_name_or_code: Autonomous community name or 2-digit code.
        
    Returns:
        Abbreviation for the autonomous community.
        
    Raises:
        ValueError: If the input does not resolve to a known autonomous community.
    """
    if isinstance(ac_name_or_code, str) and ac_name_or_code in {v.upper() for v in AUTONOMOUS_COMMUNITY_ABBR.values()}:
        return ac_name_or_code.upper()
    
    # Try as code
    if ac_name_or_code in AUTONOMOUS_COMMUNITY_CODES:
        return AUTONOMOUS_COMMUNITY_ABBR[AUTONOMOUS_COMMUNITY_CODES[ac_name_or_code]]
    
    # Try as name
    for code, name in AUTONOMOUS_COMMUNITY_CODES.items():
        if name.lower() == ac_name_or_code.lower():
            return AUTONOMOUS_COMMUNITY_ABBR[name]
    
    raise ValueError(f"Unknown Spain autonomous community: '{ac_name_or_code}'")


def province_code(prov_name_or_abbr: str) -> str:
    """Return the 2-digit INE code for a province name or abbreviation.
    
    Args:
        prov_name_or_abbr: Province name, abbreviation, or 2-digit code.
        
    Returns:
        Two-digit INE province code.
        
    Raises:
        ValueError: If the input does not resolve to a known province.
    """
    # Try as code first
    if prov_name_or_abbr in PROVINCE_CODES:
        return prov_name_or_abbr
    
    # Try as abbreviation
    for code, name in PROVINCE_CODES.items():
        if PROVINCE_ABBR.get(name) == prov_name_or_abbr.upper():
            return code
    
    # Try as name (case-insensitive, handling parentheses)
    for code, name in PROVINCE_CODES.items():
        if name.lower().replace("(", "").replace(")", "").replace(" ", "") == \
                prov_name_or_abbr.lower().replace("(", "").replace(")", "").replace(" ", ""):
            return code
    
    raise ValueError(f"Unknown Spain province: '{prov_name_or_abbr}'")


def province_abbr(prov_name_or_code: str) -> str:
    """Return the abbreviation for a province name or code.
    
    Args:
        prov_name_or_code: Province name or 2-digit code.
        
    Returns:
        Abbreviation for the province.
        
    Raises:
        ValueError: If the input does not resolve to a known province.
    """
    if isinstance(prov_name_or_code, str) and prov_name_or_code in {v.upper() for v in PROVINCE_ABBR.values()}:
        return prov_name_or_code.upper()
    
    # Try as code
    if prov_name_or_code in PROVINCE_CODES:
        return PROVINCE_ABBR[PROVINCE_CODES[prov_name_or_code]]
    
    # Try as name
    for code, name in PROVINCE_CODES.items():
        if name.lower() == prov_name_or_code.lower():
            return PROVINCE_ABBR[name]
    
    raise ValueError(f"Unknown Spain province: '{prov_name_or_code}'")


# Geometry level configuration
# Spain's native levels: nation, autonomous_community, province, municipality, 
# district, section (census section), block (manzana)
LEVEL_FALLBACK: Dict[str, str] = {
    "state": "autonomous_community",  # Use autonomous_community as state equivalent
    "province": "province",  # Direct mapping
    "county": "municipality",  # Municipality is closest to county
    "tract": "section",  # Section censal is closest to tract
    "blockgroup": "section",  # Section censal is closest to blockgroup
    "place": "municipality",  # Municipality is closest to place
}

# Most recent vintage year for data
LATEST_YEAR: Dict[str, int] = {
    "geography": 2021,
    "census": 2021,
}

# Data download URLs for INE Census 2021
# INE (Instituto Nacional de Estadística) provides census data at:
# https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736176780&menu=ultiDatos&idp=1254735573175
CENSUS_2021_URLS: Dict[str, str] = {
    "microdata": "https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736176780&menu=ultiDatos&idp=1254735573175",
    "tables": "https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736176780&menu=ultiDatos&idp=1254735573175",
    "boundaries": "https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736176780&menu=ultiDatos&idp=1254735573175",
}

# Default data directory
DEFAULT_DATA_DIR = "data/spain"

# Mapping of autonomous communities to their provinces
# Some autonomous communities have only one province (e.g., Madrid, Murcia)
# Others have multiple provinces
AUTONOMOUS_COMMUNITY_PROVINCES: Dict[str, List[str]] = {
    "01": ["01", "04", "11", "14", "18", "21", "23", "29", "41"],  # Andalucía: Almería, Cádiz, Córdoba, Granada, Huelva, Jaén, Málaga, Sevilla
    "02": ["22", "44", "50"],  # Aragón: Huesca, Teruel, Zaragoza
    "03": ["33"],  # Asturias: Oviedo (Asturias)
    "04": ["07"],  # Baleares: Islas Baleares
    "05": ["35", "38"],  # Canarias: Las Palmas, Santa Cruz de Tenerife
    "06": ["39"],  # Cantabria: Santander (Cantabria)
    "07": ["02", "05", "06", "10", "13", "16", "19", "20", "25", "26", "31", "32", "34", "36", "37", "40", "42", "45", "47", "48", "49"],  # Castilla-La Mancha: Albacete, Ávila, Ciudad Real, Cuenca, Guadalajara, Toledo
    "08": ["01", "05", "08", "09", "10", "12", "15", "16", "17", "18", "24", "26", "34", "36", "37", "40", "42", "45", "46", "47", "48"],  # Castilla y León
    "09": ["08", "17", "23", "43"],  # Cataluña: Barcelona, Gerona, Lérida, Tarragona
    "10": ["03", "12", "46"],  # Comunidad Valenciana: Alicante, Castellón, Valencia
    "11": ["06", "10"],  # Extremadura: Badajoz, Cáceres
    "12": ["15", "27", "32", "36"],  # Galicia: La Coruña, Lugo, Orense, Pontevedra
    "13": ["28", "29"],  # Madrid: Madrid (province and community)
    "14": ["30", "31"],  # Murcia: Murcia (province is same as community, but includes some areas)
    "15": ["31"],  # Navarra: Navarra
    "16": ["01", "20", "48"],  # País Vasco: Álava, Guipúzcoa, Vizcaya
    "17": ["26"],  # La Rioja: Logroño (La Rioja)
    "18": ["49"],  # Ceuta
    "19": ["50"],  # Melilla
}

__all__ = [
    "AUTONOMOUS_COMMUNITY_CODES",
    "AUTONOMOUS_COMMUNITY_ABBR",
    "PROVINCE_CODES",
    "PROVINCE_ABBR",
    "autonomous_community_code",
    "autonomous_community_abbr",
    "province_code",
    "province_abbr",
    "LEVEL_FALLBACK",
    "LATEST_YEAR",
    "CENSUS_2021_URLS",
    "DEFAULT_DATA_DIR",
    "AUTONOMOUS_COMMUNITY_PROVINCES",
]
