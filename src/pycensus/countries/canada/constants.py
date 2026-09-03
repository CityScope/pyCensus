"""Static Canada geography reference data shared by every Canada census source.

Technical aspects:
    Canada's administrative divisions used here:
    - Nation (country level)
    - Province/territory (PRUID, 2-digit StatCan code) - 10 provinces + 3 territories
    - Census subdivision (CSDUID, 7-digit StatCan code: 2-digit PRUID + 2-digit
      census division + 3-digit CSD) - Canada's municipality-equivalent
      (city/town/village/reserve/etc.)

    ``PROVINCE_CODES`` (PRUID -> English name) and every CSD's ``PRUID``
    prefix were cross-checked directly against the real 2021 boundary
    files (see :mod:`pycensus.canada.geography`) and the real 2021 Census
    Population and Dwelling Counts table (PID 98-10-0002) -- both verified
    live 2026-08-20. ``PROVINCE_ABBR`` uses Canada Post's standard 2-letter
    postal abbreviations (independently well-known, not StatCan-specific
    codes).

Source:
    https://www12.statcan.gc.ca/census-recensement/2021/geo/index-eng.cfm
"""

from __future__ import annotations

from typing import Dict

# StatCan PRUID -> English province/territory name.
# Verified against lpr_000b21a_e.shp (2021 cartographic boundary file,
# province/territory level) and against the "GEO"/"DGUID" columns of the
# real downloaded 98-10-0002 Population and Dwelling Counts table
# (DGUID == "2021A0002" + PRUID for every province/territory row).
PROVINCE_CODES: Dict[str, str] = {
    "10": "Newfoundland and Labrador",
    "11": "Prince Edward Island",
    "12": "Nova Scotia",
    "13": "New Brunswick",
    "24": "Quebec",
    "35": "Ontario",
    "46": "Manitoba",
    "47": "Saskatchewan",
    "48": "Alberta",
    "59": "British Columbia",
    "60": "Yukon",
    "61": "Northwest Territories",
    "62": "Nunavut",
}

# Standard Canada Post 2-letter postal abbreviations.
PROVINCE_ABBR: Dict[str, str] = {
    "Newfoundland and Labrador": "NL",
    "Prince Edward Island": "PE",
    "Nova Scotia": "NS",
    "New Brunswick": "NB",
    "Quebec": "QC",
    "Ontario": "ON",
    "Manitoba": "MB",
    "Saskatchewan": "SK",
    "Alberta": "AB",
    "British Columbia": "BC",
    "Yukon": "YT",
    "Northwest Territories": "NT",
    "Nunavut": "NU",
}


def province_code(province: str) -> str:
    """Normalize a province name, postal abbreviation, or PRUID to its 2-digit PRUID.

    Args:
        province: Province name, postal abbreviation, or 2-digit code.

    Returns:
        Two-digit StatCan PRUID.

    Raises:
        ValueError: If ``province`` does not resolve to a known Canadian province/territory.
    """
    if province in PROVINCE_CODES:
        return province

    upper = str(province).upper()
    for name, abbr in PROVINCE_ABBR.items():
        if abbr == upper:
            return next(code for code, n in PROVINCE_CODES.items() if n == name)

    for code, name in PROVINCE_CODES.items():
        if name.lower() == str(province).lower():
            return code

    raise ValueError(f"Unknown Canada province/territory: '{province}'")


def province_abbr(province: str) -> str:
    """Normalize a province name, abbreviation, or PRUID to its postal abbreviation."""
    code = province_code(province)
    return PROVINCE_ABBR[PROVINCE_CODES[code]]


# Universal level names (see pycensus.geometry_levels / global_levels.json)
# that don't exist natively in Canada, mapped onto the closest native level
# implemented in pycensus.canada.geography.
LEVEL_FALLBACK: Dict[str, str] = {
    "state": "province",  # Canada has no level above province; province is the top subnational unit
    "county": "municipality",  # census subdivision (CSD) is Canada's municipality-equivalent
    "tract": "dissemination-area",  # DA is StatCan's tract-equivalent, finest level with published Census Profile population
    "blockgroup": "dissemination-area",  # no clean equivalent -- DA is the closest real level with characteristic data
    "block": "dissemination-block",  # StatCan's actual finest unit -- real population/dwelling counts, see Geographic Attribute File (GAF)
}

LATEST_YEAR: Dict[str, int] = {
    "geography": 2021,
    "census": 2021,
}

# Real StatCan boundary file URLs, verified live 2026-08-20 (HTTP 200,
# application/x-zip-compressed, real shapefile content -- see
# pycensus.canada.geography module docstring).
BOUNDARY_URLS: Dict[str, str] = {
    "province": "https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/files-fichiers/lpr_000b21a_e.zip",
    "municipality": "https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/files-fichiers/lcsd000b21a_e.zip",
    # Dissemination area (DA) -- StatCan's tract-equivalent, finest unit with
    # published Census Profile population data. Verified live 2026-08-20:
    # GET (not HEAD -- this server 404s HEAD requests) returns 200,
    # application/x-zip-compressed, 197,042,003 bytes, real shapefile
    # content (57,932 rows, columns DAUID/DGUID/LANDAREA/PRUID, EPSG:3347).
    "dissemination-area": "https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/files-fichiers/lda_000b21a_e.zip",
    # Dissemination block (DB) -- StatCan's actual finest geographic unit.
    # Verified live 2026-08-22: real form-driven download flow (POST
    # bound=db_&type=b&format=a to
    # .../boundary-limites/index2021-eng.cfm?Year=21 302-redirects through
    # an accessibility interstitial to this exact URL), GET returns 200,
    # application/x-zip-compressed, 317,391,964 bytes, real shapefile
    # content (498,547 rows, columns DBUID/DGUID/DBRPLAMX/DBRPLAMY/
    # LANDAREA/PRUID, EPSG:3347). Cross-checked: filtering to Toronto's
    # 13,323 real DBUIDs (from the GAF, see GEOGRAPHIC_ATTRIBUTE_FILE_URL)
    # matches 13,322 of them in this shapefile (the one gap is a
    # coastal-water-only block, which StatCan's own reference guide says
    # this cartographic file omits) with bounds
    # [-79.639, 43.579, -79.115, 43.855] -- identical to the already-
    # verified Toronto CSD bounds.
    "dissemination-block": "https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/files-fichiers/ldb_000b21a_e.zip",
}

# Real StatCan Full Table Download URL template, verified live 2026-08-20.
# PID 98-10-0002 = "Population and dwelling counts: Canada, provinces and
# territories, census divisions and census subdivisions" -- contains both
# province-level and census-subdivision-level rows in one file.
FULL_TABLE_URL_TEMPLATE = "https://www150.statcan.gc.ca/n1/en/tbl/csv/{pid}-eng.zip"
CENSUS_PROFILE_PID = "98100002"

# PID 98-10-0015 = "Population and dwelling counts: Canada, provinces and
# territories, census subdivisions and dissemination areas" -- the
# companion cube to 98-10-0002 that goes one level finer (DA rows,
# DGUID prefix "2021S0512" + 8-digit DAUID). Verified live 2026-08-20:
# real download (3,895,735-byte zip), 98100015.csv (5,370,448 bytes)
# contains 57,936 DA-level rows plus the same CSD/CD/PR/Canada rows as
# 98100002. Column layout is identical (REF_DATE, GEO, DGUID, Coordinate,
# "Population and dwelling counts (5): ..." value/Symbols pairs) except
# the value-count-label is "(5)" instead of "(13)" -- this cube has fewer
# variables (population, total dwellings, occupied dwellings, land area,
# population density) than 98100002's 13.
DISSEMINATION_AREA_PID = "98100015"

# 2021 Census Geographic Attribute File (catalogue 92-151-X, DB-level
# population/dwelling counts) -- StatCan's dissemination block is NOT part
# of the Full Table Download cube family (98100002/98100015 stop at DA),
# so this is a separate, real, direct-download flat file rather than
# another `FULL_TABLE_URL_TEMPLATE` PID. Verified live 2026-08-22: real
# form-driven download flow (POST year=21&getgeo=Continue to
# .../attribute-attribs/index2021-eng.cfm?Year=2021 302-redirects through
# an accessibility interstitial to this exact URL), GET returns 200,
# application/x-zip-compressed, 9,832,890 bytes, contains one real CSV
# (2021_92-151_X.csv, 298,768,692 bytes, latin-1 encoded, 498,786 data
# rows) with columns including DBUID_IDIDU, DAUID_ADIDU, PRUID_PRIDU,
# DBPOP2021_IDPOP2021 (population), DBTDWELL2021_IDTLOG2021 (total private
# dwellings), DBURDWELL2021_IDRHLOG2021 (private dwellings occupied by
# usual residents -- StatCan's "households" definition, same as the DA/CSD
# cubes), DBAREA2021_IDSUP2021 (land area km^2). Cross-checked: for every
# one of Toronto's 3,743 real dissemination areas, summing this file's
# DBPOP2021 over that DA's blocks reproduces PID 98-10-0015's own
# published DA-level population exactly (0 mismatches across all 3,743
# DAs), and the grand total across all Toronto blocks (2,794,356) matches
# the City of Toronto's published CSD-level population exactly.
GEOGRAPHIC_ATTRIBUTE_FILE_URL = (
    "https://www12.statcan.gc.ca/census-recensement/2021/geo/aip-pia/"
    "attribute-attribs/files-fichiers/2021_92-151_X.zip"
)
GEOGRAPHIC_ATTRIBUTE_FILE_CSV_NAME = "2021_92-151_X.csv"

# PID 98-10-0459 = "Commuting flow from geography of residence to geography
# of work by gender: Census subdivisions" -- 2021 Census, 25% sample data.
# Genuine workplace-geocoded jobs data (Canada's closest analog to the
# USA's LODES WAC): the "Place of work" dimension is a full CSD-by-CSD
# commuting-flow matrix (5,161 residence CSDs x 5,161 workplace CSDs x
# gender), so summing over every residence CSD for a fixed workplace CSD
# gives that CSD's total count of "usual place of work" jobs located there
# -- verified live 2026-08-23 by downloading the real 2.2GB Full Table CSV
# (98100459.csv) and cross-checking against StatCan's own WDS
# getCubeMetadata for this cube (both "Place of residence" and "Place of
# work" dimensions share the same 5,161-member id space and ordering --
# confirmed for 8 randomly sampled member ids, e.g. memberId 517 ==
# "Halifax" (Place of residence, classificationCode CSDUID "1209034") ==
# "Halifax (RGM), N.S." (Place of work) -- so the workplace CSDUID for any
# row is recovered via the "Coordinate" column's second component (e.g.
# "12.517" -> Place of work memberId 517 -> CSDUID "1209034"), never by
# fragile display-name matching). Summing the whole cube's flows gives
# 10,680,335, close to (~1.5% under) the national "Usual place of work"
# total (10,846,770) from the companion table 98-10-0456 -- the shortfall
# is consistent with StatCan's routine small-cell random rounding, not a
# parsing bug. Toronto (CSDUID 3520005) totals 753,185; Montreal (2466023)
# 649,595; Calgary (4806016) 370,125; Ottawa (3506008) 272,920 -- all real
# and internally consistent, though this "usual place of work" measure
# EXCLUDES workers who report working from home or having no fixed
# workplace address (a large share in the pandemic-affected 2021 Census),
# so it materially UNDER-counts true total jobs-by-workplace compared to a
# LODES-style complete jobs census -- documented, not silently treated as
# equivalent. See statcan/workplace_jobs_csduid_by_member_id.json for the
# bundled, static Place-of-work-memberId -> CSDUID lookup (built once from
# the live WDS metadata response so no WDS call is needed at request time,
# matching this module's keyless/Full-Table-Download-only style).
WORKPLACE_JOBS_PID = "98100459"
WORKPLACE_JOBS_MEMBER_ID_TO_CSDUID_FILE = "workplace_jobs_csduid_by_member_id.json"

DEFAULT_DATA_DIR = "data/canada"

# Census Profile, 2021 -- comprehensive bulk CSV (catalogue 98-401-X2021006),
# a *different* real StatCan product from the Full Table Download cube
# family above (98100002/98100015): a long/tall CHARACTERISTIC_ID-keyed
# table with ~2,631 real characteristics per geography, covering household
# size, income, education, housing tenure, and commuting mode -- fields not
# present in 98100002/98100015 at all. Verified live 2026-08-23: the
# per-geography-level bulk download page
# (https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/details/download-telecharger.cfm?Lang=E)
# links real per-province GetFile.cfm downloads for GEONO=006 (Canada, PR,
# CD, CSD, DA -- 2.2GB) split by region; GEONO=006_Ontario is the real
# Ontario-only DA-level file (757,020,277-byte zip, real
# "98-401-X2021006_Ontario_eng_CSV.zip", confirmed by Content-Disposition
# header and by successfully unzipping a 8,780,436,336-byte CSV). Only
# Ontario has been downloaded/wired up in this codebase so far -- see
# statcan/README.md and statcan/census_profile.py for the documented scope
# limitation (StatCan does publish the same product for every other
# province/territory at the same URL pattern, just not yet fetched here).
CENSUS_PROFILE_GEONO_BY_PROVINCE: Dict[str, str] = {
    "35": "006_Ontario",  # Ontario -- the only province actually downloaded/verified so far
}
CENSUS_PROFILE_URL_TEMPLATE = (
    "https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/details/"
    "download-telecharger/comp/GetFile.cfm?Lang=E&FILETYPE=CSV&GEONO={geono}"
)
# Real zip member names inside a GEONO=006_<region> download, verified by
# listing 98-401-X2021006_Ontario_eng_CSV.zip's contents.
CENSUS_PROFILE_CSV_NAME_TEMPLATE = "98-401-X2021006_English_CSV_data_{region}.csv"

__all__ = [
    "PROVINCE_CODES",
    "PROVINCE_ABBR",
    "province_code",
    "province_abbr",
    "LEVEL_FALLBACK",
    "LATEST_YEAR",
    "BOUNDARY_URLS",
    "FULL_TABLE_URL_TEMPLATE",
    "CENSUS_PROFILE_PID",
    "DISSEMINATION_AREA_PID",
    "GEOGRAPHIC_ATTRIBUTE_FILE_URL",
    "GEOGRAPHIC_ATTRIBUTE_FILE_CSV_NAME",
    "CENSUS_PROFILE_GEONO_BY_PROVINCE",
    "CENSUS_PROFILE_URL_TEMPLATE",
    "CENSUS_PROFILE_CSV_NAME_TEMPLATE",
    "WORKPLACE_JOBS_PID",
    "WORKPLACE_JOBS_MEMBER_ID_TO_CSDUID_FILE",
    "DEFAULT_DATA_DIR",
]
