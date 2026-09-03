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
    use utils.state_code() instead for consistency with the usa implementation.
    """
    return _state_code_from_lookups(state_name_or_abbr)


def state_abbr(state_name_or_code: str) -> str:
    """Return the abbreviation for a state name or code.

    Note: This function is maintained for backward compatibility. New code should
    use utils.state_abbr() instead for consistency with the usa implementation.
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

# Data download URLs for INEGI Census 2020.
#
# Verified 2026-08-19 with `curl -sI` (real zip Content-Type/Content-Length,
# not INEGI's generic ~2.3KB "file not found" HTML page that a lot of
# plausible-looking guessed URLs on this site quietly 200-OK to).
#
# ITER (Iter por localidad -- population/household counts down to locality,
# with municipality-total and state-total rows mixed in at LOC="0000"):
#   https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/iter/iter_{state:02d}_cpv2020_csv.zip
#   e.g. iter_01_cpv2020_csv.zip (Aguascalientes, ~330KB) confirmed real.
#
# Marco Geoestadistico (state/municipality/AGEB/block boundary shapefiles),
# one zip per state, 2018 vintage (INEGI's per-state MGN download; a newer
# 2020 "integrated" national file also exists but is ~250MB, too big for a
# routine per-state fetch):
#   https://www.inegi.org.mx/contenidos/productos/prod_serv/contenidos/espanol/bvinegi/productos/geografia/marcogeo/889463674658/{state:02d}_{state_slug}.zip
#   e.g. .../889463674658/01_aguascalientes.zip confirmed real (~40MB).
#   Inside "conjunto de datos/": {state:02d}ent.shp (state), {state:02d}mun.shp
#   (municipality), {state:02d}a.shp/{state:02d}ar.shp (urban/rural AGEB).
CENSUS_2020_URLS: Dict[str, str] = {
    "iter_template": "https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/iter/iter_{state}_cpv2020_csv.zip",
    "resageburb_template": "https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/ageb_manzana/ageb_mza_urbana_{state}_cpv2020_csv.zip",
    "microdata": "https://www.inegi.org.mx/programas/ccpv/2020/?ps=microdatos",
    "mass_download": "https://www.inegi.org.mx/app/descarga/default.html",
    "tables": "https://www.inegi.org.mx/programas/ccpv/2020/#Tabulados",
}

# Marco Geoestadistico per-state boundary zip URLs. INEGI's URL path
# includes a state name slug (not just the code), so the mapping has to be
# spelled out explicitly rather than templated. Verified for "01" (see
# CENSUS_2020_URLS docstring above); the rest follow the same catalog
# listing pattern (https://www.inegi.org.mx/app/mapas/ -> Marco Geoestadistico
# -> Descarga por entidad) but have not all been individually curl-verified.
_MARCO_GEO_BASE = (
    "https://www.inegi.org.mx/contenidos/productos/prod_serv/contenidos/"
    "espanol/bvinegi/productos/geografia/marcogeo/889463674658"
)
MARCO_GEOESTADISTICO_URLS: Dict[str, str] = {
    "01": f"{_MARCO_GEO_BASE}/01_aguascalientes.zip",
    "02": f"{_MARCO_GEO_BASE}/02_bajacalifornia.zip",
    "03": f"{_MARCO_GEO_BASE}/03_bajacaliforniasur.zip",
    "04": f"{_MARCO_GEO_BASE}/04_campeche.zip",
    "05": f"{_MARCO_GEO_BASE}/05_coahuiladezaragoza.zip",
    "06": f"{_MARCO_GEO_BASE}/06_colima.zip",
    "07": f"{_MARCO_GEO_BASE}/07_chiapas.zip",
    "08": f"{_MARCO_GEO_BASE}/08_chihuahua.zip",
    "09": f"{_MARCO_GEO_BASE}/09_ciudaddemexico.zip",
    "10": f"{_MARCO_GEO_BASE}/10_durango.zip",
    "11": f"{_MARCO_GEO_BASE}/11_guanajuato.zip",
    "12": f"{_MARCO_GEO_BASE}/12_guerrero.zip",
    "13": f"{_MARCO_GEO_BASE}/13_hidalgo.zip",
    "14": f"{_MARCO_GEO_BASE}/14_jalisco.zip",
    "15": f"{_MARCO_GEO_BASE}/15_mexico.zip",
    "16": f"{_MARCO_GEO_BASE}/16_michoacandeocampo.zip",
    "17": f"{_MARCO_GEO_BASE}/17_morelos.zip",
    "18": f"{_MARCO_GEO_BASE}/18_nayarit.zip",
    "19": f"{_MARCO_GEO_BASE}/19_nuevoleon.zip",
    "20": f"{_MARCO_GEO_BASE}/20_oaxaca.zip",
    "21": f"{_MARCO_GEO_BASE}/21_puebla.zip",
    "22": f"{_MARCO_GEO_BASE}/22_queretaro.zip",
    "23": f"{_MARCO_GEO_BASE}/23_quintanaroo.zip",
    "24": f"{_MARCO_GEO_BASE}/24_sanluispotosi.zip",
    "25": f"{_MARCO_GEO_BASE}/25_sinaloa.zip",
    "26": f"{_MARCO_GEO_BASE}/26_sonora.zip",
    "27": f"{_MARCO_GEO_BASE}/27_tabasco.zip",
    "28": f"{_MARCO_GEO_BASE}/28_tamaulipas.zip",
    "29": f"{_MARCO_GEO_BASE}/29_tlaxcala.zip",
    "30": f"{_MARCO_GEO_BASE}/30_veracruzdeignaciodelallave.zip",
    "31": f"{_MARCO_GEO_BASE}/31_yucatan.zip",
    "32": f"{_MARCO_GEO_BASE}/32_zacatecas.zip",
}

# Shapefile basename suffixes within a Marco Geoestadistico state zip's
# "conjunto de datos/" folder, per boundary level (prefixed with the
# 2-digit state code, e.g. state "01" + "ent" -> "01ent.shp").
MARCO_GEO_SHAPEFILE_SUFFIX: Dict[str, str] = {
    "state": "ent",
    "municipality": "mun",
    "ageb": "a",
    "block": "m",
}

# Approximate geographic bounding boxes per state, (min_lon, min_lat, max_lon,
# max_lat) in EPSG:4326, sourced from general knowledge of each state's
# extent (not an INEGI file -- there's no cheap authoritative national
# boundary layer wired up, see geography.py module docstring). Intentionally
# a coarse heuristic, not intended as an exact boundary: used only to narrow
# ``states_in_aoi``'s candidate list before the real per-state Marco
# Geoestadistico download, with generous padding applied at use time so a
# state whose true (non-rectangular) boundary pokes past its bbox corner is
# still very unlikely to be missed for an AOI that's actually inside it.
STATE_BBOX: Dict[str, tuple] = {
    "01": (-102.87, 21.62, -101.83, 22.45),  # Aguascalientes
    "02": (-117.13, 22.75, -112.75, 32.72),  # Baja California
    "03": (-115.05, 22.87, -109.42, 28.00),  # Baja California Sur
    "04": (-92.46, 17.82, -89.15, 20.85),  # Campeche
    "05": (-103.97, 24.55, -100.14, 29.88),  # Coahuila de Zaragoza
    "06": (-104.70, 18.67, -103.47, 19.55),  # Colima
    "07": (-94.14, 14.53, -90.38, 17.98),  # Chiapas
    "08": (-109.13, 25.57, -103.30, 31.78),  # Chihuahua
    "09": (-99.36, 19.05, -98.94, 19.59),  # Ciudad de Mexico
    "10": (-107.19, 22.35, -102.46, 26.84),  # Durango
    "11": (-101.98, 19.92, -99.68, 21.86),  # Guanajuato
    "12": (-102.19, 16.31, -98.02, 18.99),  # Guerrero
    "13": (-99.87, 19.60, -97.96, 21.40),  # Hidalgo
    "14": (-105.70, 18.90, -101.50, 22.75),  # Jalisco
    "15": (-100.61, 18.37, -98.62, 20.29),  # Mexico
    "16": (-103.75, 17.92, -100.05, 20.40),  # Michoacan de Ocampo
    "17": (-99.50, 18.37, -98.64, 19.15),  # Morelos
    "18": (-105.94, 20.60, -103.72, 23.08),  # Nayarit
    "19": (-101.20, 23.15, -98.42, 27.80),  # Nuevo Leon
    "20": (-98.55, 15.66, -93.85, 18.70),  # Oaxaca
    "21": (-99.06, 17.88, -96.72, 20.85),  # Puebla
    "22": (-100.59, 20.01, -99.02, 21.65),  # Queretaro
    "23": (-89.15, 17.88, -86.71, 21.62),  # Quintana Roo
    "24": (-102.30, 21.10, -98.30, 24.50),  # San Luis Potosi
    "25": (-109.45, 22.50, -105.40, 27.05),  # Sinaloa
    "26": (-115.05, 26.30, -108.40, 32.55),  # Sonora
    "27": (-94.14, 17.25, -91.00, 18.65),  # Tabasco
    "28": (-100.15, 22.19, -97.14, 27.68),  # Tamaulipas
    "29": (-98.74, 19.06, -97.60, 19.73),  # Tlaxcala
    "30": (-98.65, 17.15, -93.60, 22.47),  # Veracruz de Ignacio de la Llave
    "31": (-90.42, 19.55, -87.53, 21.62),  # Yucatan
    "32": (-104.35, 21.05, -100.80, 25.20),  # Zacatecas
}

# Padding (degrees) applied to each state's STATE_BBOX before testing AOI
# intersection, to absorb both the coarseness of the hand-set bboxes above
# and ordinary AOI/CRS jitter. ~0.35 deg is roughly 35-40km at Mexico's
# latitudes -- generous relative to how irregular state borders actually
# are, favoring over-inclusion (a few extra states fetched) over the
# correctness risk of silently excluding a genuinely needed border state.
STATE_BBOX_PADDING_DEG = 0.35

# Default data directory
DEFAULT_DATA_DIR = "data/mexico"

__all__ = [
    "STATE_CODES",
    "STATE_ABBR",
    "state_code",
    "state_abbr",
    "LEVEL_FALLBACK",
    "LATEST_YEAR",
    "CENSUS_2020_URLS",
    "MARCO_GEOESTADISTICO_URLS",
    "MARCO_GEO_SHAPEFILE_SUFFIX",
    "STATE_BBOX",
    "STATE_BBOX_PADDING_DEG",
    "DEFAULT_DATA_DIR",
]
