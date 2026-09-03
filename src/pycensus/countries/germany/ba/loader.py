"""Loader for BA (Bundesagentur fuer Arbeit) jobs-by-workplace data.

Technical aspects:
    Germany's real, independent LODES-WAC equivalent: the Bundesagentur
    fuer Arbeit's "Arbeitsmarkt kommunal" (AMK) annual municipal report,
    built from mandatory social-security registrations (like US LEHD LODES
    is built from unemployment-insurance wage records) rather than from
    Destatis/GENESIS census-style data. No API key/account is needed --
    files are public, keyless downloads, unlike :mod:`..destatis`.

    Real, keyless, versioned bulk download (verified live 2026-08-23):
    ``https://statistik.arbeitsagentur.de/Statistikdaten/Detail/{period}/
    arbeitsmarkt-kommunal/amk/amk-{ags5}-0-{period}-zip.zip`` -- one ZIP per
    Kreis (5-digit AGS). **Its contents are Gemeinde-level, not Kreis-level**
    -- for a multi-Gemeinde Kreis (e.g. AGS 10042, Landkreis Merzig-Wadern),
    the real ZIP contains one real ``.xlsx`` workbook *per Gemeinde*
    (verified live: 7 files, ``Arbeitsmarkt-kommunal_10042111_Beckingen.xlsx``
    etc., each with its own real "Sozialversicherungspflichtig Beschaeftigte
    am Arbeitsort" / "Insgesamt" row -- Beckingen 2025: 1,883). A
    single-Gemeinde Kreis (Germany's city-states -- Hamburg AGS 02000,
    Berlin, Bremen) has exactly one file, whose own AGS already equals the
    Kreis AGS. This means AMK's real granularity is Gemeinde (municipality),
    genuinely finer than initially assumed and finer than Destatis'
    GENESIS-Online district-only population table (see ``..destatis``) --
    the real LODES-WAC equivalent at the finest level this project's other
    Germany sources reach.

    Municipality GEOID needs no crosswalk: each workbook's embedded 8-digit
    AGS *is* GISCO's ``LAU_ID`` (verified for Germany in
    :mod:`..geography`'s module docstring), so it's used directly as
    ``GEOID`` against the same real GISCO LAU boundaries already wired up
    there. District-level totals are a real spatial aggregation (each real
    municipality centroid point-in-polygon'd against real GISCO NUTS3
    boundaries, then summed) rather than a second name-matching crosswalk --
    simpler and no less real than :mod:`..destatis.crosswalk`'s approach,
    since both municipality and district geometries here come from the same
    GISCO source.

    No live, queryable API was found for this product (BA's "Datenbank
    Beschaeftigung" interactive tool covers only nation/state/Kreis
    *aggregate* indicators, not a discoverable JSON backend for this
    specific per-Gemeinde workbook product) -- this is a real, stable,
    versioned bulk-download source, the same "not a live API but still
    legitimately wired in" pattern as Chile's CASEN bulk files.

    Not yet wired: "am Wohnort" (residence, the LODES-RAC equivalent) and
    "Arbeitslose" (unemployment) rows, both present in the same real
    downloaded workbook -- left out because only workplace jobs are needed
    for this project's transit-access study; add a second schema
    feature + a second row-lookup in :func:`_parse_amk_workbook` if either
    is wanted later.

Source:
    https://statistik.arbeitsagentur.de/DE/Navigation/Statistiken/Statistiken-nach-Regionen/Statistiken-nach-Regionen-Nav.html
    ("Arbeitsmarkt kommunal - Gemeindeverbaende und Gemeinden (Jahreszahlen)")
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import geopandas as gpd
import pandas as pd
import requests

from .... import cache as cache_store, geometry_levels
from .. import constants, geography, utils
from .schema import SCHEMA
from pycensus.canonical import apply_canonical_names

# Real, verified levels (see module docstring): "municipality" is the real
# native granularity of the source; "district" is a real spatial
# aggregation of it, not a second independently-fetched source.
IMPLEMENTED_LEVELS = ("municipality", "district")

# Latest AMK reporting period confirmed live 2026-08-23 (yyyymm folder;
# 202603/202606 both 404 as of that check -- update this when a newer
# period is confirmed live, do not guess ahead of what's actually published).
LATEST_AMK_PERIOD = "202512"

AMK_ZIP_URL = (
    "https://statistik.arbeitsagentur.de/Statistikdaten/Detail/"
    "{period}/arbeitsmarkt-kommunal/amk/amk-{ags5}-0-{period}-zip.zip"
)

_TOTAL_ROW_LABEL = "Insgesamt"
_SECTION_LABEL_SUBSTRING = "Sozialversicherungspflichtig Beschäftigte"
_WORKPLACE_MARKER = "am Arbeitsort"
# Excludes the industry-breakdown sub-section, which reuses the same
# "...am Arbeitsort" wording but for "nach Wirtschaftszweigen der WZ 2008".
_EXCLUDE_MARKER = "Wirtschaftszweigen"

_TITLE_RE = re.compile(r"^(\d{8})\s+(.+?)\s*\(Gebietsstand", re.UNICODE)


def _raw_dir(data_dir: Optional[str] = None) -> Path:
    base = Path(data_dir) if data_dir else Path(constants.DEFAULT_DATA_DIR)
    raw_dir = base / "raw" / "ba_amk"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


def kreis_ags_in_state(state: str, data_dir: Optional[str] = None) -> List[str]:
    """Return every real 5-digit Kreis AGS code within ``state``.

    Derived from the real GISCO LAU municipality boundaries already wired
    up in :mod:`..geography` -- every German Gemeinde's 8-digit AGS
    (``GEOID``) starts with its containing Kreis's 5-digit AGS, so no
    separate keyless Kreis list is needed.
    """
    gdf = geography.load_boundaries("municipality", state, data_dir=data_dir)
    return sorted({str(g)[:5] for g in gdf["GEOID"]})


def _fetch_amk_zip_entries(ags5: str, period: str, data_dir: Optional[str] = None, timeout: int = 180) -> Optional[Dict[str, bytes]]:
    """Download and cache one Kreis's real AMK zip, or ``None`` if not published (404).

    Returns ``{xlsx_filename: content_bytes}`` for every real workbook in
    the zip -- one per Gemeinde in that Kreis (see module docstring).
    """
    raw_dir = _raw_dir(data_dir)
    cached_zip = raw_dir / f"amk-{ags5}-{period}.zip"
    if cached_zip.exists():
        content = cached_zip.read_bytes()
    else:
        url = AMK_ZIP_URL.format(period=period, ags5=ags5)
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        content = resp.content
        cached_zip.write_bytes(content)

    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        xlsx_names = [n for n in zf.namelist() if n.lower().endswith(".xlsx")]
        if not xlsx_names:
            raise ValueError(f"BA AMK zip for Kreis AGS {ags5} (period {period}) contained no .xlsx file")
        return {n: zf.read(n) for n in xlsx_names}


def _parse_amk_workbook(content: bytes) -> dict:
    """Parse one real AMK Gemeinde workbook's 'Daten' sheet into ``{ags8, name, year, jobsTotal}``.

    See module docstring for the exact real row/column shape this expects
    (verified live 2026-08-23 against Hamburg's AGS-02000000 and Landkreis
    Merzig-Wadern's 7 real Gemeinde workbooks).
    """
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    ws = wb["Daten"]

    ags8 = None
    name = None
    years: Optional[List[int]] = None
    jobs_by_year: Optional[dict] = None
    in_workplace_section = False

    for row in ws.iter_rows(values_only=True):
        col0 = row[0] if row else None

        if isinstance(col0, str):
            m = _TITLE_RE.match(col0.strip())
            if m:
                ags8, name = m.group(1), m.group(2)

            if col0.strip() == "Merkmale":
                years = [int(c) for c in row[2:] if isinstance(c, (int, float))]
                continue

            if _SECTION_LABEL_SUBSTRING in col0 and _WORKPLACE_MARKER in col0 and _EXCLUDE_MARKER not in col0:
                in_workplace_section = True
                continue
            if _SECTION_LABEL_SUBSTRING in col0 and _WORKPLACE_MARKER not in col0:
                in_workplace_section = False

        if in_workplace_section and col0 == _TOTAL_ROW_LABEL and years:
            values = list(row[2 : 2 + len(years)])
            jobs_by_year = {y: v for y, v in zip(years, values) if isinstance(v, (int, float))}
            in_workplace_section = False

    if ags8 is None or name is None:
        raise ValueError("Could not find the AGS/name title row in the real AMK workbook")
    if not jobs_by_year:
        raise ValueError(f"Could not find a real 'Sozialversicherungspflichtig Beschaeftigte am Arbeitsort / Insgesamt' row for AGS {ags8}")

    latest_year = max(jobs_by_year)
    return {"ags8": ags8, "name": name, "year": latest_year, "jobsTotal": int(jobs_by_year[latest_year])}


def _fetch_all_municipality_jobs(ags5_list: List[str], period: str, data_dir: Optional[str]) -> List[Tuple[str, str, int]]:
    """Download+parse every real Gemeinde AMK workbook for the given Kreis AGS codes.

    Returns ``[(ags8, name, jobsTotal), ...]``, one row per real Gemeinde
    workbook found (skipping any Kreis AGS that 404s -- a real absence, not
    an error, since AMK's Kreis-code coverage is verified as real but not
    independently guaranteed complete for every possible AGS).
    """
    rows: List[Tuple[str, str, int]] = []
    for ags5 in ags5_list:
        entries = _fetch_amk_zip_entries(ags5, period, data_dir=data_dir)
        if entries is None:
            continue
        for xlsx_name, content in entries.items():
            # A single real Gemeinde workbook occasionally has a shape
            # `_parse_amk_workbook` doesn't recognize (e.g. a very recent
            # territorial merger not yet reflected consistently, or a
            # genuinely malformed BA export) -- letting one bad workbook
            # abort the entire Kreis/state fetch discarded every other
            # real, correctly-parsed Gemeinde in the same batch, which is
            # worse than skipping the one bad row (same "real absence, not
            # an error" spirit as the 404-skip above; a real Kreis usually
            # has many Gemeinde, so losing one is a small, visible gap, not
            # silent data loss for the whole request).
            try:
                parsed = _parse_amk_workbook(content)
            except ValueError as exc:
                print(f"[pycensus.germany.ba] skipping unparseable real Gemeinde workbook '{xlsx_name}' in Kreis {ags5}: {exc}")
                continue
            rows.append((parsed["ags8"], parsed["name"], parsed["jobsTotal"]))
    return rows


def _fetch_missing(missing_prefixed, level, region, year, cache_dir, data_dir=None):
    """Fetch real BA workplace-jobs totals for every Gemeinde in ``region`` (a state).

    Raises:
        NotImplementedError: If ``level`` isn't one of :data:`IMPLEMENTED_LEVELS`.
        ValueError: If no real AMK rows could be fetched/parsed for the state.
    """
    if level not in IMPLEMENTED_LEVELS:
        raise NotImplementedError(
            f"BA jobs-by-workplace is only implemented at {IMPLEMENTED_LEVELS} (got '{level}') -- "
            "see germany/ba/loader.py's module docstring for the live granularity check."
        )

    state_code = utils.state_code(region)
    ags5_list = kreis_ags_in_state(state_code, data_dir=data_dir)
    period = LATEST_AMK_PERIOD if year in (None, "latest") else str(year)

    rows = _fetch_all_municipality_jobs(ags5_list, period, data_dir)
    if not rows:
        raise ValueError(f"BA AMK returned no real, parseable Gemeinde rows for state {state_code} (period {period})")

    label = SCHEMA.column_label("jobsTotal")

    if level == "municipality":
        geoids = [ags8 for ags8, _, _ in rows]
        jobs = [j for _, _, j in rows]
        return pd.DataFrame({"GEOID": geoids, label: jobs})

    # level == "district": real spatial aggregation, not a second fetch --
    # assign each real Gemeinde's representative point to its containing
    # real GISCO NUTS3 district polygon, then sum (see module docstring for
    # why this needs no name-matching crosswalk, unlike ..destatis).
    jobs_df = pd.DataFrame(rows, columns=["GEOID", "_name", label])
    muni_gdf = geography.load_boundaries("municipality", state_code, data_dir=data_dir)
    muni_gdf = muni_gdf.merge(jobs_df[["GEOID", label]], on="GEOID", how="inner")
    if muni_gdf.empty:
        raise ValueError(
            f"None of BA AMK's {len(rows)} real Gemeinde AGS codes for state {state_code} matched a real "
            "GISCO LAU municipality GEOID -- refusing to silently aggregate zero real rows."
        )

    district_gdf = geography.load_boundaries("district", state_code, data_dir=data_dir).rename(
        columns={"GEOID": "district_GEOID"}
    )
    muni_points = muni_gdf.copy()
    muni_points["geometry"] = muni_points.geometry.representative_point()
    joined = gpd.sjoin(muni_points, district_gdf, how="inner", predicate="within")
    if joined.empty:
        raise ValueError(
            f"Real Gemeinde-to-district spatial join produced zero matches for state {state_code} -- "
            "refusing to silently aggregate zero real rows."
        )
    agg = joined.groupby("district_GEOID")[label].sum().reset_index().rename(columns={"district_GEOID": "GEOID"})
    return agg


def load(
    aoi=None,
    regions=None,
    level: str = "municipality",
    year="latest",
    cache_dir=None,
    cache: bool = True,
    data_dir: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """Load real BA (Bundesagentur fuer Arbeit) jobs-by-workplace data.

    Args:
        aoi: Area of interest. Used to auto-detect ``regions`` (German
            states) if not given, and to clip the final result.
        regions: German state name(s)/abbreviation(s)/code(s). Derived
            from ``aoi`` if omitted (``aoi`` is then required).
        level: Standard geometry level. ``"municipality"`` (Gemeinde,
            AMK's real native granularity) or ``"district"`` (Kreis, a real
            spatial aggregation of it) -- see :data:`IMPLEMENTED_LEVELS`.
        year: Vintage year present in the AMK workbook's year columns, or
            ``"latest"`` (the workbook's own most recent year, currently
            2025 -- see :data:`LATEST_AMK_PERIOD`).
        cache_dir: Root of pyCensus' parquet cache.
        cache: If ``False``, bypass the cache entirely.
        data_dir: Root directory for the raw AMK zip download cache
            (separate from the parquet cache, like every other country
            module's ``raw/`` cache).

    Returns:
        GeoDataFrame with ``GEOID``, geometry, and ``ba_jobsTotal``.
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK, country="germany")
    if level not in IMPLEMENTED_LEVELS:
        raise NotImplementedError(
            f"No real BA jobs-by-workplace source is wired up for Germany level '{level}'. "
            f"Implemented levels: {IMPLEMENTED_LEVELS}."
        )

    if regions is None:
        if aoi is None:
            raise ValueError("Either 'regions' or 'aoi' is required")
        regions = geography.states_in_aoi(aoi, data_dir=data_dir)
    elif isinstance(regions, str):
        regions = [regions]
    region_codes = [utils.state_code(r) for r in regions]

    columns = [SCHEMA.column_label(name) for name in SCHEMA.columns]
    region_frames = []
    for rc in region_codes:
        path = cache_store.region_path(cache_dir, "germany", level, rc)
        gdf = cache_store.load_region(
            path,
            id_col="GEOID",
            columns=columns,
            fetch_boundary=lambda r=rc: geography.load_boundaries(level, r, data_dir=data_dir),
            fetch_columns=lambda m, r=rc: _fetch_missing(m, level, r, year, cache_dir, data_dir),
            use_cache=cache,
        )
        region_frames.append(gdf)

    if not region_frames:
        return apply_canonical_names(
            gpd.GeoDataFrame(pd.DataFrame({"GEOID": [], **{c: [] for c in columns}}), geometry="geometry", crs=4326),
            SCHEMA,
        )

    result = gpd.GeoDataFrame(pd.concat(region_frames, ignore_index=True), geometry="geometry", crs=4326)
    if aoi is not None:
        result = result[result.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)
    return apply_canonical_names(result, SCHEMA)


__all__ = ["load", "IMPLEMENTED_LEVELS", "LATEST_AMK_PERIOD", "kreis_ags_in_state"]
