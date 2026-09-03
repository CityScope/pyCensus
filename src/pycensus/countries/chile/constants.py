"""Static Chile geography reference data shared by every Chile census source.

Technical aspects:
    Chile's administrative divisions (DIVIPOLA-style codes used throughout
    Chilean government open data):

    - Nation (Chile)
    - Region (region) -- 16 regions (I-XII, Metropolitana, Los Rios, Los
      Lagos was split off Ayesen/Arica-Parinacota etc.; today's 16 include
      "Region de Nuble" (16), split from Bio-Bio in 2018). 2-digit numeric
      code (``codregion`` in the real boundary file, ``Region`` column in
      INE's projection table).
    - Provincia (province) -- a real 2-digit ``Provincia`` code appears in
      INE's population table, but no verified, directly-downloadable
      provincia *boundary* file was found in this session (see
      :mod:`pycensus.chile.geography` module docstring) -- so ``province``
      is deliberately left unimplemented rather than guessed.
    - Comuna (municipality) -- 346 comunas (as of the real boundary file
      used here), the level at which mayors ("alcaldes") are elected.
      5-digit code (``cod_comuna`` in the boundary file / ``Comuna`` in
      INE's table): first 2 digits are the region code, last 3 are a
      per-region sequential comuna number (e.g. "13101" = Region 13
      [Metropolitana] + comuna 101 = Santiago; "08101" = Region 8
      [Bio-Bio] + comuna 101 = Concepcion).

    Region codes and names below were extracted directly from the real
    downloaded boundary file (see :mod:`pycensus.chile.geography`) --
    ``comunas.shp``'s ``codregion``/``Region`` columns, verified
    2026-08-20. Region "0" ("Zona sin demarcar" -- undemarcated maritime/
    Antarctic claim area with no comuna) is excluded here; it carries no
    population data and no real comuna geometry.

Source:
    https://www.ine.gob.cl/ (population), https://www.bcn.cl/siit/mapas_vectoriales (boundaries)
"""

from __future__ import annotations

from typing import Dict, Tuple

# Region codes -> Spanish name, extracted verbatim from the real BCN
# "comunas_final.zip" boundary file's Region column (verified 2026-08-20:
# 16 distinct codregion values 1-16, excluding the "0"/"Zona sin demarcar"
# placeholder row).
REGION_CODES: Dict[str, str] = {
    "01": "Región de Tarapacá",
    "02": "Región de Antofagasta",
    "03": "Región de Atacama",
    "04": "Región de Coquimbo",
    "05": "Región de Valparaíso",
    "06": "Región del Libertador Bernardo O'Higgins",
    "07": "Región del Maule",
    "08": "Región del Bío-Bío",
    "09": "Región de La Araucanía",
    "10": "Región de Los Lagos",
    "11": "Región de Aysén del Gral.Ibañez del Campo",
    "12": "Región de Magallanes y Antártica Chilena",
    "13": "Región Metropolitana de Santiago",
    "14": "Región de Los Ríos",
    "15": "Región de Arica y Parinacota",
    "16": "Región de Ñuble",
}

# Common abbreviations (roman-numeral regional identifiers used in everyday
# Chilean usage; Metropolitana and Nuble don't have roman numerals).
REGION_ABBR: Dict[str, str] = {
    "Región de Tarapacá": "I",
    "Región de Antofagasta": "II",
    "Región de Atacama": "III",
    "Región de Coquimbo": "IV",
    "Región de Valparaíso": "V",
    "Región del Libertador Bernardo O'Higgins": "VI",
    "Región del Maule": "VII",
    "Región del Bío-Bío": "VIII",
    "Región de La Araucanía": "IX",
    "Región de Los Lagos": "X",
    "Región de Aysén del Gral.Ibañez del Campo": "XI",
    "Región de Magallanes y Antártica Chilena": "XII",
    "Región Metropolitana de Santiago": "RM",
    "Región de Los Ríos": "XIV",
    "Región de Arica y Parinacota": "XV",
    "Región de Ñuble": "XVI",
}

# Approximate per-region bounding boxes (min_lon, min_lat, max_lon, max_lat)
# in EPSG:4326, computed directly from the real BCN comuna boundary file's
# actual geometry (per-region total_bounds over its member comunas),
# verified 2026-08-20 -- not a guessed/hand-drawn extent. Region 5
# (Valparaiso) legitimately spans to ~-109.4 because it includes Isla de
# Pascua (Easter Island) and Juan Fernandez. Used only as a cheap
# pre-filter in :func:`pycensus.chile.geography.regions_in_aoi` before
# loading the real comuna geometries.
REGION_BBOX: Dict[str, Tuple[float, float, float, float]] = {
    "01": (-70.28, -21.63, -68.40, -18.94),
    "02": (-70.74, -26.06, -66.99, -20.93),
    "03": (-71.53, -29.54, -68.26, -25.29),
    "04": (-71.72, -32.28, -69.81, -29.04),
    "05": (-109.45, -33.96, -69.99, -26.29),
    "06": (-72.06, -35.01, -70.01, -33.85),
    "07": (-72.79, -36.54, -70.31, -34.68),
    "08": (-73.96, -38.49, -70.98, -36.44),
    "09": (-73.52, -39.64, -70.83, -37.58),
    "10": (-74.85, -44.07, -71.58, -40.24),
    "11": (-75.65, -49.21, -71.09, -43.64),
    "12": (-75.72, -55.98, -66.42, -48.60),
    "13": (-71.71, -34.29, -69.77, -32.92),
    "14": (-73.72, -40.68, -71.59, -39.29),
    "15": (-70.38, -19.23, -68.91, -17.50),
    "16": (-72.88, -37.20, -71.01, -36.01),
}

# Padding (degrees) applied to REGION_BBOX before testing AOI intersection,
# to absorb both bbox coarseness and ordinary AOI/CRS jitter. Chosen to
# match Mexico's STATE_BBOX_PADDING_DEG convention.
REGION_BBOX_PADDING_DEG = 0.35

# Chile's native levels: nation, region, comuna (municipality). "province"
# exists in INE's own data (a Provincia code/name column) but has no
# verified boundary source, so it is not a native level implemented here --
# any request for it falls back to "region" below, same pattern as
# Mexico's LEVEL_FALLBACK["province"] = "state" (no province level there
# either).
LEVEL_FALLBACK: Dict[str, str] = {
    "state": "region",
    "province": "region",
    "county": "comuna",
    "municipality": "comuna",
    "place": "comuna",
    "tract": "comuna",
    "blockgroup": "comuna",
    "block": "comuna",
}

# Most recent vintage year for data.
#
# Boundaries: BCN's "comunas_final.zip" (2018-vintage division comunal,
# see geography.py module docstring).
#
# Census/population: INE's real "Estimaciones y Proyecciones de la
# Poblacion de Chile 2002-2035, Base 2017" communal table (see
# ine/loader.py module docstring) publishes single-year-of-age population
# by sex, per comuna, for every year 2002-2035. 2024 is used as the
# default "latest" year here -- the most recent year INE's own
# methodology treats as a post-2017-census-informed estimate rather than
# a longer-horizon projection, and it aligns with the 2024 Census that INE
# has separately been publishing results for (censo2024.ine.gob.cl) but
# whose communal microdata was not available as a verified downloadable
# file in this session.
LATEST_YEAR: Dict[str, int] = {
    "geography": 2018,
    "census": 2024,
}

# Default data directory for raw (non-parquet-cache) downloads.
DEFAULT_DATA_DIR = "data/chile"

# Alias used by utils.py/geography.py -- REGION_CODES *is* the code->name
# lookup (its name refers to "codes" being the keys, not the values); kept
# as a second name so call sites reading "REGION_NAMES" (a name->somthing
# lookup) aren't misleading. Both names point at the same real dict.
REGION_NAMES: Dict[str, str] = REGION_CODES

__all__ = [
    "REGION_CODES",
    "REGION_NAMES",
    "REGION_ABBR",
    "REGION_BBOX",
    "REGION_BBOX_PADDING_DEG",
    "LEVEL_FALLBACK",
    "LATEST_YEAR",
    "DEFAULT_DATA_DIR",
]
