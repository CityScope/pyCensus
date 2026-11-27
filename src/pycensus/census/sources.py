"""Every dataset a census load downloads, one entry per download, by country: what a notebook (or any front end) shows for the user to tick.

A source here is one dataset or file that is fetched separately (an agency can publish several: Spain's INE has its population register, the 2021 census,
the income atlas, tourism tables ...). Unticked sources are never downloaded. `base` marks the source that gives each place its population (the
census population): unticking it makes WorldPop's population grid the base. `bbox` (west, south, east, north) limits a source to places it covers (a city
survey, a regional agency): it is listed only for areas that touch the box.

    from pycensus.census import sources
    rows = sources.for_area("ESP", aoi)      # [{"key", "title", "description", "detail", "base", "default"}, ...]
    sources.keys("ESP")                      # every key of the country
"""
from __future__ import annotations

from typing import Dict, List, Optional

BASQUE = [-3.50, 42.40, -1.70, 43.50]


def _s(key: str, title: str, description: str, detail: str, base: bool = False, bbox: Optional[List[float]] = None) -> dict:
    return {"key": key, "title": title, "description": description, "detail": detail, "base": base, "bbox": bbox, "default": True}


COUNTRY_SOURCES: Dict[str, List[dict]] = {
    "USA": [
        _s("dhc", "Decennial census 2020 (DHC)", "US Census Bureau: population of every block, race and ethnicity, age, housing units.", "block", base=True),
        _s("acs5", "American Community Survey 5-year", "US Census Bureau: income, housing, education, commuting, jobs, health, with a block interpolation.", "block group"),
        _s("lodes", "Jobs by workplace (LODES WAC)", "US LEHD: jobs by workplace.", "block group"),
        _s("religion", "US Religion Census 2020", "Congregations and adherents by denomination.", "county"),
        _s("housing_history", "Housing in earlier periods", "Housing tenure, rent and home values of earlier census periods.", "tract"),
        _s("elections_precinct", "Election results by precinct", "City precinct files (Boston, San Francisco) and the 2024 nationwide precinct map, resampled to tracts.", "precinct"),
        _s("elections_county", "Last national election by county", "County results of the latest presidential election.", "county"),
    ],
    "ESP": [
        _s("es_padron", "INE Padrón (population register)", "INE: population by census section.", "section", base=True),
        _s("censo2021", "INE Census 2021", "Education, employment, migration, households, dwelling tenure, year built, floor area (separate INE API).", "section / district"),
        _s("adrh", "INE income atlas (ADRH)", "Income, Gini, poverty, age and household indicators.", "section / municipality"),
        _s("housing_rent", "SERPAVI rents", "Ministerio de Vivienda: rent per m2 of flats and houses.", "section"),
        _s("housing_value", "Appraised home value", "Ministerio de Vivienda: valor tasado of free housing, municipalities over 25,000 people.", "municipality"),
        _s("ine_tables", "Tourist dwellings and net migration", "INE experimental tourist-dwelling statistic and migration balance.", "municipality"),
        _s("eustat_housing", "Eustat housing and income (Basque Country)", "Eustat income and dwellings per section, EMAL rents.", "section / municipality", bbox=BASQUE),
        _s("eustat_municipal", "Eustat municipal indicators (Basque Country)", "Eustat municipal statistics.", "municipality", bbox=BASQUE),
        _s("elections", "Election results", "Ministerio del Interior (Infoelectoral): Congreso 2023, Municipales 2023; Basque government: Parlamento Vasco 2024.", "polling table to section"),
        _s("donostia_pmus", "Donostia mobility plan survey", "San Sebastian mobility plan survey on its own zones.", "zone", bbox=[-2.10, 43.25, -1.85, 43.38]),
        _s("em_capv", "Basque Country mobility survey", "Basque mobility survey on its own zones.", "zone", bbox=BASQUE),
    ],
    "MEX": [
        _s("inegi", "INEGI census", "INEGI: population, households, education, labour force, dwellings.", "block / AGEB", base=True),
        _s("mx_elections", "Election results", "2024 presidential result by casilla, resampled to AGEB and municipality.", "casilla to AGEB"),
        _s("imeplan_eod", "Guadalajara origin-destination survey", "IMEPLAN 2023 survey on its own zones.", "zone", bbox=[-103.75, 20.40, -103.05, 20.95]),
    ],
    "ISR": [
        _s("cbs_census", "CBS census", "Israel Central Bureau of Statistics: population and households by statistical area.", "statistical area", base=True),
        _s("cbs_commute", "CBS commute mode", "Mode of commuting to work by commute area.", "commute area"),
    ],
    "CAN": [
        _s("statcan_census", "Statistics Canada census", "Population, households, income, commuting.", "dissemination area", base=True),
        _s("toronto_profiles", "Toronto neighbourhood profiles", "City of Toronto neighbourhood profile tables.", "neighbourhood", bbox=[-79.70, 43.55, -79.10, 43.95]),
    ],
    "AND": [_s("estadisticaad", "Andorra statistics", "Estadistica d'Andorra: population by parish.", "parish", base=True)],
    "TWN": [
        _s("moi", "Ministry of the Interior population", "MOI household registration population.", "village", base=True),
        _s("taipei_mode", "Taipei mode-use survey", "Taipei mode use by district and traffic zone.", "district / zone", bbox=[121.40, 24.90, 121.70, 25.25]),
    ],
    "CHL": [
        _s("ine_cl", "INE census", "INE Chile census by district and zone.", "zone", base=True),
        _s("ine_manzana", "INE census blocks (manzanas)", "INE census block-level tables.", "manzana"),
        _s("casen", "CASEN poverty estimates", "CASEN small-area estimates of poverty by commune.", "commune"),
        _s("sii", "Jobs by workplace (SII)", "Servicio de Impuestos Internos: jobs by commune of the workplace.", "commune"),
    ],
    "DEU": [
        _s("zensus_grid", "Zensus 100 m population grid", "Census 2022 population on a 100 m grid (replaces the raster as the population base).", "100 m grid", base=True),
        _s("destatis", "Destatis census tables (GENESIS)", "Destatis GENESIS-Online: population, sex, foreign population by municipality / district.", "municipality / district"),
        _s("ba_jobs", "Jobs by workplace (BA)", "Bundesagentur fur Arbeit: employees by workplace (AMK).", "municipality / district"),
        _s("ba_pendler", "Commuter statistics (BA Pendlerstatistik)", "Bundesagentur fur Arbeit: commuters in, out and within each municipality.", "municipality"),
        _s("hamburg_elections", "Hamburg election results", "Latest national, state and municipal elections by polling district.", "Wahlbezirk", bbox=[9.70, 53.35, 10.40, 53.80]),
        _s("mid_hamburg", "Hamburg mobility survey (MiD)", "MiD survey for Hamburg districts.", "district", bbox=[9.70, 53.35, 10.40, 53.80]),
    ],
    "EUSKADI": [_s("eustat", "Eustat population", "Basque statistics office: population by section.", "section", base=True)],
}


def keys(country: str) -> List[str]:
    """Every source key of a country (empty for a country with no census source: WorldPop is its population)."""
    return [r["key"] for r in COUNTRY_SOURCES.get(country, [])]


def base_key(country: str) -> Optional[str]:
    """The source that gives the population of every place in the country."""
    return next((r["key"] for r in COUNTRY_SOURCES.get(country, []) if r["base"]), None)


def for_area(country: str, aoi=None) -> List[dict]:
    """The country's sources that apply to the area (those with a `bbox` only where the area touches it); each is a fresh dict."""
    out = []
    if aoi is not None:
        w, s, e, n = aoi.to_crs(4326).total_bounds
    for r in COUNTRY_SOURCES.get(country, []):
        b = r["bbox"]
        if aoi is not None and b and (w > b[2] or e < b[0] or s > b[3] or n < b[1]):
            continue
        out.append({k: v for k, v in r.items() if k != "bbox"})
    return out
