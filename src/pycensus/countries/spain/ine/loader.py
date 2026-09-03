"""Loader for Spain's INE Padron municipal, returning a common-schema GeoDataFrame.

Technical aspects:
    Mirrors :mod:`pycensus.mexico.inegi.loader`'s shape: reads as much as
    possible from pyCensus' parquet cache (:mod:`pycensus.cache`), fetching
    only the logical columns actually missing. Unlike Mexico's per-state
    ITER file, INE's Tempus API (:mod:`pycensus.spain.api`) returns every
    Spanish municipality in a single request, so the raw response is
    downloaded once (cached on disk, independent of the parquet cache) and
    then sliced per requested region/level.

    Only ``population``/``malePopulation``/``femalePopulation`` are
    implemented -- see :mod:`pycensus.spain.ine.schema` module docstring
    for why fields present in earlier (fabricated) versions of this module
    (age brackets, employment, income, housing) were removed rather than
    kept with invented INE codes: they were never verified against a real
    downloaded INE file. Real values for those exist in INE's Census 2021
    (Censo de Poblacion y Viviendas) microdata/tables, which is a separate,
    unverified follow-up (see this module's ``download_census_data``
    docstring).

Source:
    INE Padron municipal (table 29005): https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/29005
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union

import geopandas as gpd
import pandas as pd

from .... import cache as cache_store
from .... import geometry_levels
from .. import api, constants, geography, utils
from .schema import SCHEMA
from pycensus.canonical import apply_canonical_names

_RAW_FILENAME = "padron_municipios.json"


def _raw_cache_path(data_dir: Optional[str]) -> Path:
    base = Path(data_dir) if data_dir else Path(constants.DEFAULT_DATA_DIR)
    raw_dir = base / "raw" / "ine_padron"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir / _RAW_FILENAME


def _fetch_all_municipios(data_dir: Optional[str]) -> pd.DataFrame:
    """Fetch (or read cached) the full nationwide municipality population table."""
    return api.fetch_padron_municipios(raw_cache_path=_raw_cache_path(data_dir))


def _secciones_raw_cache_path(province_code: str, data_dir: Optional[str]) -> Path:
    base = Path(data_dir) if data_dir else Path(constants.DEFAULT_DATA_DIR)
    raw_dir = base / "raw" / "ine_padron_secciones"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir / f"padron_secciones_{province_code}.csv"


def _fetch_secciones_for_region(region: str, data_dir: Optional[str]) -> pd.DataFrame:
    """Fetch (or read cached) section-level population for every province in ``region``.

    ``region`` is an autonomous-community or province code (see
    :func:`pycensus.spain.geography._province_codes_in_region`). Unlike
    the municipality Padron (one nationwide request), INE's section-level
    Padron is published per-province, so this fetches/caches one file per
    province and concatenates.
    """
    province_codes = geography._province_codes_in_region(region)
    frames = [
        api.fetch_padron_secciones(p, raw_cache_path=_secciones_raw_cache_path(p, data_dir))
        for p in province_codes
    ]
    return pd.concat(frames, ignore_index=True)


def _aggregate_to_level(
    municipio_df: pd.DataFrame, level: str, region: Optional[str], data_dir: Optional[str] = None
) -> pd.DataFrame:
    """Aggregate municipality-level population rows up to province/AC/nation.

    Population fields are additive counts (``resampling_up: "sum"`` in
    ``schema.json``), so summing the raw municipality rows by the
    requested level's GEOID prefix/mapping reproduces the correct total.
    """
    df = municipio_df.copy()
    value_cols = ["TOTAL_POB", "POB_HOMBRES", "POB_MUJERES"]

    if level == "municipality":
        out = df[["GEOID", *value_cols]].copy()
        if region:
            codes = geography._municipality_codes_in_region(
                region, geography._load_spain_municipalities(data_dir)
            )
            out = out[out["GEOID"].isin(codes)]
        return out

    if level == "province":
        df["_key"] = df["GEOID"].str[:2]
        if region:
            df = df[df["_key"] == utils.province_code(region)]
        grouped = df.groupby("_key", as_index=False)[value_cols].sum()
        return grouped.rename(columns={"_key": "GEOID"})

    if level == "autonomous_community":
        prov_to_ac = {
            p: ac for ac, provs in constants.AUTONOMOUS_COMMUNITY_PROVINCES.items() for p in provs
        }
        df["_prov"] = df["GEOID"].str[:2]
        df["_key"] = df["_prov"].map(prov_to_ac)
        df = df.dropna(subset=["_key"])
        if region:
            df = df[df["_key"] == utils.autonomous_community_code(region)]
        grouped = df.groupby("_key", as_index=False)[value_cols].sum()
        return grouped.rename(columns={"_key": "GEOID"})

    if level == "nation":
        totals = df[value_cols].sum()
        return pd.DataFrame([{"GEOID": "ES", **totals.to_dict()}])

    raise ValueError(f"Unsupported level for INE Padron aggregation: '{level}'")


def _fetch_missing(missing_prefixed: List[str], level: str, region: str, data_dir: Optional[str]) -> pd.DataFrame:
    """Fetch and select just the logical columns in ``missing_prefixed``."""
    if level == "section":
        aggregated = _fetch_secciones_for_region(region, data_dir)
    else:
        raw = _fetch_all_municipios(data_dir)
        aggregated = _aggregate_to_level(raw, level, region, data_dir)

    result = pd.DataFrame({"GEOID": aggregated["GEOID"]})
    for prefixed_name in missing_prefixed:
        col_name = SCHEMA.strip_prefix(prefixed_name)
        col_def = SCHEMA.columns[col_name]
        raw_col = next((c for c in col_def.codes if c in aggregated.columns), None)
        if raw_col is None:
            result[prefixed_name] = pd.Series(dtype="float64", index=aggregated.index)
        else:
            result[prefixed_name] = pd.to_numeric(aggregated[raw_col], errors="coerce")
    return result


def load(
    aoi: Optional[gpd.GeoDataFrame] = None,
    regions: Optional[Union[str, List[str]]] = None,
    level: str = "municipality",
    year: Union[int, str] = "latest",
    api_key: Optional[str] = None,
    cache_dir: Optional[str] = None,
    cache: bool = True,
    data_dir: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """Load INE's Padron municipal population data as a common-schema GeoDataFrame.

    Args:
        aoi: Area of interest. Used to auto-detect ``regions`` if not given,
            and to clip the final result.
        regions: Region code(s) -- autonomous community code, province code,
            or 5-digit municipality code, matching ``level``. Derived from
            ``aoi`` if omitted (``aoi`` is then required).
        level: Standard geometry level name. Spain supports ``nation``,
            ``autonomous_community``, ``province``, ``municipality``,
            ``section`` directly; other standard levels fall back via
            :data:`pycensus.spain.constants.LEVEL_FALLBACK` (``tract``/
            ``blockgroup`` -> ``section``). ``district``/``block`` are not
            implemented (see :mod:`pycensus.spain.geography`). ``section``
            population comes from a different, per-province INE source
            (2022 vintage) than municipality+ (2025 vintage) -- see
            :mod:`pycensus.spain.api` module docstring.
        year: Vintage year, or ``"latest"``. INE's Padron API always
            returns its single latest published year (2025 as of this
            module's implementation) -- ``year`` is accepted for interface
            parity but not otherwise used to select a vintage.
        api_key: Not used -- INE's Padron Tempus API requires no API key.
        cache_dir: Root of pyCensus' parquet cache. Defaults to
            :func:`pycensus.cache.default_cache_dir`.
        cache: If ``False``, bypass the parquet cache entirely.
        data_dir: Root directory for raw INE/GISCO downloads (separate from
            ``cache_dir``). Defaults to
            :data:`pycensus.spain.constants.DEFAULT_DATA_DIR`.

    Returns:
        GeoDataFrame with ``GEOID``, geometry, and one ``ine_``-prefixed
        column per logical column in :data:`pycensus.spain.ine.schema.SCHEMA`.

    Raises:
        ValueError: If neither ``regions`` nor ``aoi`` is given.
        NotImplementedError: If ``level`` resolves to a level without a
            real boundary source (see :mod:`pycensus.spain.geography`).
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK)

    if regions is None:
        if aoi is None:
            raise ValueError("Either 'regions' or 'aoi' is required")
        regions = geography.states_in_aoi(aoi, data_dir=data_dir)
    elif isinstance(regions, str):
        regions = [regions]

    region_codes = []
    for r in regions:
        if isinstance(r, str) and len(r) == 5 and r.isdigit():
            region_codes.append(r)
            continue
        try:
            region_codes.append(utils.autonomous_community_code(r))
            continue
        except ValueError:
            pass
        try:
            region_codes.append(utils.province_code(r))
            continue
        except ValueError:
            pass
        if isinstance(r, str) and len(r) == 2 and r.isdigit():
            region_codes.append(r)
        else:
            raise ValueError(f"Cannot resolve region: '{r}'")

    columns = [SCHEMA.prefixed(name) for name in SCHEMA.columns]

    region_frames = []
    for region_code in region_codes:
        path = cache_store.region_path(cache_dir, "spain", level, region_code)

        def fetch_boundary(region=region_code):
            return geography.load_boundaries(level, region, data_dir=data_dir)

        def fetch_columns(missing, region=region_code):
            return _fetch_missing(missing, level, region, data_dir)

        gdf = cache_store.load_region(
            path,
            id_col="GEOID",
            columns=columns,
            fetch_boundary=fetch_boundary,
            fetch_columns=fetch_columns,
            use_cache=cache,
        )
        region_frames.append(gdf)

    if not region_frames:
        return apply_canonical_names(
            gpd.GeoDataFrame(
                pd.DataFrame({"GEOID": [], **{c: [] for c in columns}}),
                geometry="geometry",
                crs=4326,
            ),
            SCHEMA,
        )

    result = gpd.GeoDataFrame(pd.concat(region_frames, ignore_index=True), geometry="geometry", crs=4326)

    if aoi is not None:
        result = result[result.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)

    return apply_canonical_names(result, SCHEMA)


def download_census_data(
    level: str = "municipality",
    regions: Optional[Union[str, List[str]]] = None,
    data_dir: Optional[str] = None,
    overwrite: bool = False,
) -> str:
    """Force a fresh download of INE's Padron municipal table to the raw cache.

    Args:
        level: Accepted for interface parity; the Padron API returns every
            municipality in one request regardless of level.
        regions: Accepted for interface parity; not used to filter the
            download (the raw file always holds every municipality).
        data_dir: Root directory for raw downloads.
        overwrite: If ``True``, delete the cached raw JSON file first so it
            is re-downloaded from INE.

    Returns:
        Path to the raw cache file that was downloaded/refreshed.

    Note:
        Only the Padron (population by sex) is implemented here. INE's
        Census 2021 (Censo de Poblacion y Viviendas) publishes households,
        housing, education, and employment data at municipality level too,
        via the same Tempus API under a different operation/table id, but
        that was not identified and verified against a real downloaded
        file in this rebuild -- see the module docstring.
    """
    raw_path = _raw_cache_path(data_dir)
    if overwrite and raw_path.exists():
        raw_path.unlink()
    api.fetch_padron_municipios(raw_cache_path=raw_path)
    return str(raw_path)


__all__ = ["load", "download_census_data"]
