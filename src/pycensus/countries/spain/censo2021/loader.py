"""Loader for Spain's Censo 2021 (SDC21) source, returning a common-schema GeoDataFrame.

Technical aspects:
    Mirrors :mod:`pycensus.countries.spain.ine.loader`'s shape (parquet
    cache via :mod:`pycensus.cache`, fetch-only-missing-columns), but reads
    from the SDC21 dissemination API
    (:mod:`pycensus.countries.spain.censo2021.api`) instead of the Padron
    Tempus3/PC-Axis sources. SDC21's API returns real *census-section*
    level breakdowns nationwide in a single request per category variable
    (see ``api.py`` module docstring for the live verification numbers);
    this loader aggregates those section rows up to municipality/
    province/autonomous_community/nation the same way
    ``ine.loader._aggregate_to_level`` does for the Padron.

    Only ``households``, ``educationPrimaryOrLessPopulation``,
    ``educationSecondaryPopulation``, ``educationUniversityPopulation``,
    ``laborForce``, ``employedResidents``, ``unemployedResidents``, and
    ``foreignBornPopulation`` are implemented -- see
    ``spain/schema/censo2021_schema.json`` and this module's docstring
    for exactly which real SDC21 table/metric/variable/category each maps
    to. ``educationOtherTertiaryPopulation`` is intentionally not
    implemented: INE's SDC21 ``ID_ESREAL_GR5`` variable only has one
    tertiary-education bucket ("Educacion Superior"), with no real way to
    split university from other tertiary without a different, unverified
    variable (``ID_ESREAL_CNEDA``, a finer detail code not yet mapped).
    Income (``medianHouseholdIncome`` etc.) and commute-mode fields
    (``carCommuters`` etc.) are also not implemented: SDC21 has no income
    variable at all (Spain's household income data comes from a separate,
    municipality-level-only source, the Atlas de Distribucion de Renta de
    los Hogares) and no commute-mode-of-transport variable.

Source:
    INE Censo 2021 SDC21 API: https://www.ine.es/Censo2021/api
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union

import geopandas as gpd
import pandas as pd

from .... import cache as cache_store
from .... import geometry_levels
from .. import constants, geography, utils
from . import api
from .schema import FEATURE_FETCH_SPEC, SCHEMA
from pycensus.canonical import apply_canonical_names

_RAW_FILENAME_TMPL = "censo2021_{variable}_{table}.json"


def _raw_cache_path(table: str, variable: Optional[str], data_dir: Optional[str]) -> Path:
    base = Path(data_dir) if data_dir else Path(constants.DEFAULT_DATA_DIR)
    raw_dir = base / "raw" / "censo2021"
    raw_dir.mkdir(parents=True, exist_ok=True)
    var_part = variable or "none"
    return raw_dir / _RAW_FILENAME_TMPL.format(variable=var_part, table=table)


def _fetch_section_totals(feature_name: str, data_dir: Optional[str]) -> pd.Series:
    """Fetch (or read cached) nationwide section-level values for one logical feature.

    Returns a ``pd.Series`` indexed by 10-digit section ``GEOID`` with the
    feature's value (summed across ``category_value`` when it names more
    than one raw SDC21 category, e.g. ``educationSecondaryPopulation``).
    """
    spec = FEATURE_FETCH_SPEC[feature_name]
    table = spec["table"]
    metric = spec["metric"]
    variable = spec["variable"]
    category_value = spec["category_value"]

    if variable is None:
        # Whole-table total (e.g. households) -- no category breakdown needed.
        breakdown = api.fetch_section_breakdown(
            table, metric, None, raw_cache_path=_raw_cache_path(table, "none", data_dir)
        )
        return breakdown.groupby("GEOID")["value"].sum()

    breakdown = api.fetch_section_breakdown(
        table, metric, variable, raw_cache_path=_raw_cache_path(table, variable, data_dir)
    )
    if isinstance(category_value, list):
        breakdown = breakdown[breakdown["category"].isin(category_value)]
    else:
        breakdown = breakdown[breakdown["category"] == category_value]
    return breakdown.groupby("GEOID")["value"].sum()


def _aggregate_series_to_level(
    section_series: pd.Series, level: str, region: Optional[str], data_dir: Optional[str] = None
) -> pd.DataFrame:
    """Aggregate a section-indexed value Series up to a coarser level's GEOID.

    Mirrors :func:`pycensus.countries.spain.ine.loader._aggregate_to_level`:
    section GEOIDs are 10-digit CUSEC codes (2 province + 3 municipality +
    2 district + 3 section), so every coarser level's GEOID is a real
    prefix/mapping of the section code and summing reproduces the correct
    total (all censo2021 fields implemented here are additive counts).
    """
    df = section_series.rename("value").reset_index()

    if level == "section":
        if region:
            province_codes = geography._province_codes_in_region(region)
            df = df[df["GEOID"].str[:2].isin(province_codes)]
        return df

    if level == "municipality":
        df["_key"] = df["GEOID"].str[:5]
        if region:
            codes = geography._municipality_codes_in_region(
                region, geography._load_spain_municipalities(data_dir)
            )
            df = df[df["_key"].isin(codes)]
        grouped = df.groupby("_key", as_index=False)["value"].sum()
        return grouped.rename(columns={"_key": "GEOID"})

    if level == "province":
        df["_key"] = df["GEOID"].str[:2]
        if region:
            df = df[df["_key"] == utils.province_code(region)]
        grouped = df.groupby("_key", as_index=False)["value"].sum()
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
        grouped = df.groupby("_key", as_index=False)["value"].sum()
        return grouped.rename(columns={"_key": "GEOID"})

    if level == "nation":
        return pd.DataFrame([{"GEOID": "ES", "value": df["value"].sum()}])

    raise ValueError(f"Unsupported level for censo2021 aggregation: '{level}'")


def _fetch_missing(missing_prefixed: List[str], level: str, region: str, data_dir: Optional[str]) -> pd.DataFrame:
    """Fetch and select just the logical columns in ``missing_prefixed``."""
    result: Optional[pd.DataFrame] = None
    for prefixed_name in missing_prefixed:
        feature_name = SCHEMA.strip_prefix(prefixed_name)
        section_series = _fetch_section_totals(feature_name, data_dir)
        aggregated = _aggregate_series_to_level(section_series, level, region, data_dir)
        aggregated = aggregated.rename(columns={"value": prefixed_name})
        if result is None:
            result = aggregated[["GEOID", prefixed_name]]
        else:
            result = result.merge(aggregated[["GEOID", prefixed_name]], on="GEOID", how="outer")
    if result is None:
        return pd.DataFrame({"GEOID": []})
    return result


def load(
    aoi: Optional[gpd.GeoDataFrame] = None,
    regions: Optional[Union[str, List[str]]] = None,
    level: str = "section",
    year: Union[int, str] = "latest",
    api_key: Optional[str] = None,
    cache_dir: Optional[str] = None,
    cache: bool = True,
    data_dir: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """Load INE's Censo 2021 (SDC21) data as a common-schema GeoDataFrame.

    Args:
        aoi: Area of interest. Used to auto-detect ``regions`` if not
            given, and to clip the final result.
        regions: Region code(s) -- autonomous community code, province
            code, or 5-digit municipality code, matching ``level``.
            Derived from ``aoi`` if omitted (``aoi`` is then required).
        level: Standard geometry level name. Uses the same real,
            live-verified boundary levels as ``spain.ine.load``
            (nation/autonomous_community/province/municipality/section),
            since both sources share :mod:`pycensus.countries.spain.geography`.
        year: Vintage year. SDC21's 2021 census is the only vintage
            (accepted for interface parity; not otherwise used).
        api_key: Not used -- SDC21's API requires no API key.
        cache_dir: Root of pyCensus' parquet cache.
        cache: If ``False``, bypass the parquet cache entirely.
        data_dir: Root directory for raw SDC21 downloads.

    Returns:
        GeoDataFrame with ``GEOID``, geometry, and one ``censo2021_``
        (canonicalized where a bare global-schema name applies) column per
        logical column implemented in
        :mod:`pycensus.countries.spain.censo2021.schema`.

    Raises:
        ValueError: If neither ``regions`` nor ``aoi`` is given.
        NotImplementedError: If ``level`` resolves to a level without a
            real boundary source (see :mod:`pycensus.countries.spain.geography`).
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
        path = cache_store.region_path(cache_dir, "spain_censo2021", level, region_code)

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


__all__ = ["load"]
