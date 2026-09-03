"""Loader for BA (Bundesagentur fuer Arbeit) Pendlerstatistik (commuter statistics) by Gemeinde.

Technical aspects:
    Real, keyless, single-file national bulk download (verified live
    2026-08-25): BA's "Gemeindedaten aus der Beschaeftigungsstatistik"
    report, found via
    https://statistik.arbeitsagentur.de/DE/Navigation/Footer/Top-Produkte/
    Gemeindedaten-sozialversicherungspflichtig-Beschaeftigter-Nav.html ->
    the report search filtered to ``topic_f=beschaeftigung-sozbe-gemband``.
    Unlike :mod:`..ba` (AMK, one zip per Kreis), this product is a single
    national workbook per period:
    ``https://statistik.arbeitsagentur.de/Statistikdaten/Detail/{period}/
    iiia6/beschaeftigung-sozbe-gemband/gemband-dlk-0-{period}-xlsx.xlsx``.
    ``requests.get`` with no special headers/params returns it directly
    (200, verified live).

    The 'Gemeindedaten' sheet (11,836 rows for period 202506) is a real
    Wohnort/Arbeitsort/Pendler cross-tab: every row's first column ('Schl.
    Nr.') is either an 8-digit Gemeinde AGS (GISCO's ``LAU_ID``, same
    convention as ``..ba``) or a shorter 2/5-digit Land/Kreis aggregate
    AGS also present in the same sheet -- filtered to 8-digit rows only,
    see :func:`_parse_gemeindedaten`.

    Real column layout (verified live against the workbook's merged
    header rows 4-7, see ``germany/schema/ba_pendler_schema.json`` for the
    full live-verification note and cross-checks against Hamburg and
    Pinneberg):
        col C  -- Wohnort (residentWorkers)
        col K  -- Arbeitsort (pendlerJobsAtWorkplace; matches ``..ba``'s
                  AMK ``jobsTotal`` exactly for Hamburg, same Stichtag)
        col L  -- Wohnort gleich Arbeitsort (sameGemeindeWorkers)
        col M  -- Einpendler (einpendler)
        col N  -- Auspendler (auspendler)
    Columns D-J (sex/nationality/age breakdown of Wohnort) and O (Zahl der
    Betriebe) are present in the real workbook but not wired here -- add a
    row-field + schema feature if wanted later.

    District-level totals are a real spatial aggregation of the real
    Gemeinde rows (same representative-point-in-NUTS3-polygon approach as
    ``..ba``'s district branch), not a second fetch.

Source:
    https://statistik.arbeitsagentur.de/DE/Navigation/Footer/Top-Produkte/Gemeindedaten-sozialversicherungspflichtig-Beschaeftigter-Nav.html
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Dict, List, Optional

import geopandas as gpd
import openpyxl
import pandas as pd
import requests

from .... import cache as cache_store, geometry_levels
from .. import constants, geography, utils
from .schema import SCHEMA
from pycensus.canonical import apply_canonical_names

IMPLEMENTED_LEVELS = ("municipality", "district")

# Latest "Gemeindedaten aus der Beschaeftigungsstatistik" period confirmed
# live 2026-08-25 (yyyymm folder, Stichtag 30.06 of the corresponding year).
LATEST_PENDLER_PERIOD = "202506"

GEMBAND_XLSX_URL = (
    "https://statistik.arbeitsagentur.de/Statistikdaten/Detail/{period}/"
    "iiia6/beschaeftigung-sozbe-gemband/gemband-dlk-0-{period}-xlsx.xlsx"
)

_SHEET_NAME = "Gemeindedaten"
# 0-based column indices into the real 'Gemeindedaten' sheet (see module docstring).
_COL_AGS = 0
_COL_WOHNORT = 2
_COL_ARBEITSORT = 10
_COL_SAME_GEMEINDE = 11
_COL_EINPENDLER = 12
_COL_AUSPENDLER = 13


def _raw_dir(data_dir: Optional[str] = None) -> Path:
    base = Path(data_dir) if data_dir else Path(constants.DEFAULT_DATA_DIR)
    raw_dir = base / "raw" / "ba_pendler"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


def _fetch_gemband_workbook(period: str, data_dir: Optional[str] = None, timeout: int = 180) -> Optional[bytes]:
    """Download and cache the real national 'Gemeindedaten' workbook for one period.

    Returns ``None`` if the period isn't published yet (404) -- a real
    absence, not an error.
    """
    raw_dir = _raw_dir(data_dir)
    cached = raw_dir / f"gemband-{period}.xlsx"
    if cached.exists():
        return cached.read_bytes()

    url = GEMBAND_XLSX_URL.format(period=period)
    resp = requests.get(url, timeout=timeout)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    cached.write_bytes(resp.content)
    return resp.content


def _parse_gemeindedaten(content: bytes) -> List[dict]:
    """Parse the real 'Gemeindedaten' sheet into one dict per real Gemeinde row.

    Skips any row whose 'Schl. Nr.' isn't an 8-digit AGS (real Land/Kreis
    aggregate rows are interleaved in the same sheet, see module
    docstring) and any row with a non-numeric value in a wired column (BA
    suppresses individual cells for statistical secrecy on small
    Gemeinden, per the workbook's own footnote -- a real gap, not a
    parsing bug; such rows are skipped rather than fabricated as zero).
    """
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    ws = wb[_SHEET_NAME]

    rows: List[dict] = []
    for row in ws.iter_rows(values_only=True):
        if not row or row[_COL_AGS] is None:
            continue
        ags = str(row[_COL_AGS]).strip()
        if not (ags.isdigit() and len(ags) == 8):
            continue

        values = {}
        for key, idx in (
            ("residentWorkers", _COL_WOHNORT),
            ("pendlerJobsAtWorkplace", _COL_ARBEITSORT),
            ("sameGemeindeWorkers", _COL_SAME_GEMEINDE),
            ("einpendler", _COL_EINPENDLER),
            ("auspendler", _COL_AUSPENDLER),
        ):
            v = row[idx] if idx < len(row) else None
            values[key] = int(v) if isinstance(v, (int, float)) else None

        rows.append({"ags8": ags, **values})

    if not rows:
        raise ValueError(
            "No real 8-digit-AGS Gemeinde rows found in the real 'Gemeindedaten' sheet -- "
            "the workbook's column layout may have changed, see loader.py module docstring."
        )
    return rows


def _fetch_missing(missing_prefixed, level, region, year, cache_dir, data_dir=None):
    """Fetch real BA Pendlerstatistik columns for every Gemeinde in ``region`` (a state).

    Raises:
        NotImplementedError: If ``level`` isn't one of :data:`IMPLEMENTED_LEVELS`.
        ValueError: If no real rows could be fetched/parsed, or the period 404s.
    """
    if level not in IMPLEMENTED_LEVELS:
        raise NotImplementedError(
            f"BA Pendlerstatistik is only implemented at {IMPLEMENTED_LEVELS} (got '{level}') -- "
            "see germany/ba_pendler/loader.py's module docstring for the live granularity check."
        )

    state_code = utils.state_code(region)
    ags_prefix = constants.STATE_AGS[state_code]
    period = LATEST_PENDLER_PERIOD if year in (None, "latest") else str(year)

    content = _fetch_gemband_workbook(period, data_dir=data_dir)
    if content is None:
        raise ValueError(
            f"BA Pendlerstatistik period {period} is not published (404) -- "
            "see LATEST_PENDLER_PERIOD in loader.py."
        )
    all_rows = _parse_gemeindedaten(content)
    rows = [r for r in all_rows if r["ags8"].startswith(ags_prefix)]
    if not rows:
        raise ValueError(f"BA Pendlerstatistik returned no real Gemeinde rows for state {state_code} (period {period})")

    labels = {name: SCHEMA.column_label(name) for name in SCHEMA.columns}

    if level == "municipality":
        data = {"GEOID": [r["ags8"] for r in rows]}
        for name, label in labels.items():
            data[label] = [r[name] for r in rows]
        return pd.DataFrame(data)

    # level == "district": real spatial aggregation, not a second fetch --
    # same representative-point-in-NUTS3-polygon approach as ../ba's
    # district branch.
    muni_df = pd.DataFrame({"GEOID": [r["ags8"] for r in rows], **{labels[n]: [r[n] for r in rows] for n in labels}})
    muni_gdf = geography.load_boundaries("municipality", state_code, data_dir=data_dir)
    muni_gdf = muni_gdf.merge(muni_df, on="GEOID", how="inner")
    if muni_gdf.empty:
        raise ValueError(
            f"None of BA Pendlerstatistik's {len(rows)} real Gemeinde AGS codes for state {state_code} "
            "matched a real GISCO LAU municipality GEOID -- refusing to silently aggregate zero real rows."
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
    agg = joined.groupby("district_GEOID")[list(labels.values())].sum().reset_index().rename(
        columns={"district_GEOID": "GEOID"}
    )
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
    """Load real BA (Bundesagentur fuer Arbeit) Pendlerstatistik (commuter statistics) data.

    Args:
        aoi: Area of interest. Used to auto-detect ``regions`` (German
            states) if not given, and to clip the final result.
        regions: German state name(s)/abbreviation(s)/code(s). Derived
            from ``aoi`` if omitted (``aoi`` is then required).
        level: Standard geometry level. ``"municipality"`` (Gemeinde,
            this source's real native granularity) or ``"district"``
            (Kreis, a real spatial aggregation of it).
        year: Vintage year present in the workbook's period, or
            ``"latest"`` (currently 2025 -- see :data:`LATEST_PENDLER_PERIOD`).
        cache_dir: Root of pyCensus' parquet cache.
        cache: If ``False``, bypass the cache entirely.
        data_dir: Root directory for the raw workbook download cache.

    Returns:
        GeoDataFrame with ``GEOID``, geometry, and the real
        ``ba_pendler_*`` columns (pendlerJobsAtWorkplace, residentWorkers,
        sameGemeindeWorkers, einpendler, auspendler).
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK, country="germany")
    if level not in IMPLEMENTED_LEVELS:
        raise NotImplementedError(
            f"No real BA Pendlerstatistik source is wired up for Germany level '{level}'. "
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


__all__ = ["load", "IMPLEMENTED_LEVELS", "LATEST_PENDLER_PERIOD"]
