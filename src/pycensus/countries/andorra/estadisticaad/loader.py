"""Loader for Andorra's Departament d'Estadistica population-by-locality table.

Technical aspects:
    Real data, verified live 2026-08-20 -- see :mod:`pycensus.andorra.api`
    module docstring for the exact URLs and how they were found (the
    estadistica.ad dataset-browser portal is Esri ArcGIS Hub, and its
    search API lists this as a real, public, keyless FeatureServer item
    titled "Poblacio 2010-2025").

    The source table is per-locality ("poble"), not per-parish: each of the
    44 real localities carries a ``parroquia`` attribute naming its parish,
    and one ``pob_<year>`` integer column per published year. This loader
    fetches the whole table once (44 rows, one request) and sums
    ``pob_<year>`` grouped by parish to build parish-level population --
    the same locality-sum-to-region pattern as
    :mod:`pycensus.mexico.inegi.loader`'s municipality aggregation.

    One real data quirk, verified live rather than guessed: this source
    spells one parish's name without the "i" (``"Sant Julà de Lòria"``
    instead of the correct ``"Sant Julià de Lòria"``) -- handled by
    :data:`pycensus.andorra.constants.PARISH_NAME_ALIASES` rather than
    silently dropping that parish's population.

    Cross-check performed 2026-08-20: nationwide ``pob_2023`` (summed
    across all 44 localities) is exactly 85,101 -- matching Diari
    d'Andorra's reporting of the Departament d'Estadistica's own published
    31-Dec-2023 population figure.

    Extended 2026-08-23 with two more real, keyless, live-verified
    parish-level sources: building-footprint counts (``buildingCount``,
    single vintage year 2019, from the "Edificis 2019" FeatureServer) and
    active-business counts (``activeBusinessCount``, a live current-state
    snapshot, from the "REE_Ubicacio" business register FeatureServer).
    Neither carries a real historical year axis, so both are fetched fresh
    regardless of the requested ``year`` -- see
    :mod:`pycensus.andorra.api` module docstring for the exact URLs and
    verification numbers.

Source:
    https://sig.govern.ad/server/rest/services/Hosted/Poblaci%C3%B3_2010_2021/FeatureServer/0
    https://sig.govern.ad/server/rest/services/Hosted/Edificis_2019/FeatureServer/0
    https://sig.govern.ad/server/rest/services/Estadistica/REE_Ubicaci%C3%B3/FeatureServer/1
"""

from __future__ import annotations

from typing import List, Optional, Union

import geopandas as gpd
import pandas as pd

from .... import cache as cache_store
from .... import geometry_levels
from .. import api, constants, geography
from .schema import SCHEMA
from pycensus.canonical import apply_canonical_names

_VALID_YEARS = (2003, *range(2010, 2026))


def _fetch_all_localities() -> pd.DataFrame:
    """Fetch (real, live, no caching needed -- 44 rows) the full locality/year population table."""
    return api.fetch_population_by_locality()


def _aggregate_to_parish(locality_df: pd.DataFrame) -> pd.DataFrame:
    """Sum per-locality population columns up to parish level, resolving the known name typo."""
    df = locality_df.copy()
    df["_parish_code"] = df["parroquia"].apply(constants.parish_code)
    value_cols = [c for c in df.columns if c.startswith("pob_")]
    grouped = df.groupby("_parish_code", as_index=False)[value_cols].sum()
    return grouped.rename(columns={"_parish_code": "GEOID"})


def _fetch_population(missing_prefixed: List[str], level: str, region: Optional[str], year: int) -> pd.DataFrame:
    """Fetch and select just the population logical column for one year."""
    if year not in _VALID_YEARS:
        raise ValueError(
            f"Andorra population data is only published for years {_VALID_YEARS}; got {year}."
        )
    raw_col = f"pob_{year}"

    raw = _fetch_all_localities()
    parish_totals = _aggregate_to_parish(raw)

    if level == "parish":
        out = parish_totals[["GEOID", raw_col]].copy()
        if region:
            code = constants.parish_code(region)
            out = out[out["GEOID"] == code]
    elif level == "nation":
        total = parish_totals[raw_col].sum()
        out = pd.DataFrame([{"GEOID": "AD", raw_col: total}])
    else:
        raise ValueError(f"Unsupported level for Andorra population aggregation: '{level}'")

    result = pd.DataFrame({"GEOID": out["GEOID"]})
    for prefixed_name in missing_prefixed:
        col_name = SCHEMA.strip_prefix(prefixed_name)
        col_def = SCHEMA.columns[col_name]
        if raw_col in col_def.codes:
            result[prefixed_name] = pd.to_numeric(out[raw_col], errors="coerce")
        else:
            # Requested logical column has no data for this year (shouldn't
            # happen for "population", the only field defined so far) --
            # leave it unfetched rather than fabricate a zero.
            result[prefixed_name] = pd.Series(dtype="float64", index=out.index)
    return result


def _aggregate_group_count_to_parish(
    raw: pd.DataFrame, group_field: str, resolve_code
) -> pd.DataFrame:
    """Resolve a group-count DataFrame's group field to real parish codes and sum by parish."""
    df = raw.copy()
    df["GEOID"] = df[group_field].apply(resolve_code)
    return df.groupby("GEOID", as_index=False)["count"].sum()


def _fetch_by_parish_snapshot(
    missing_prefixed: List[str],
    level: str,
    region: Optional[str],
    fetch_fn,
    group_field: str,
    resolve_code,
    schema_code: str,
) -> pd.DataFrame:
    """Shared fetch path for the single-snapshot (no year axis) buildings/businesses features."""
    raw = fetch_fn()
    parish_totals = _aggregate_group_count_to_parish(raw, group_field, resolve_code)

    if level == "parish":
        out = parish_totals[["GEOID", "count"]].copy()
        if region:
            code = constants.parish_code(region)
            out = out[out["GEOID"] == code]
    elif level == "nation":
        total = parish_totals["count"].sum()
        out = pd.DataFrame([{"GEOID": "AD", "count": total}])
    else:
        raise ValueError(f"Unsupported level for Andorra snapshot aggregation: '{level}'")

    result = pd.DataFrame({"GEOID": out["GEOID"]})
    for prefixed_name in missing_prefixed:
        col_name = SCHEMA.strip_prefix(prefixed_name)
        col_def = SCHEMA.columns[col_name]
        if schema_code in col_def.codes:
            result[prefixed_name] = pd.to_numeric(out["count"], errors="coerce")
        else:
            result[prefixed_name] = pd.Series(dtype="float64", index=out.index)
    return result


def _fetch_buildings(missing_prefixed: List[str], level: str, region: Optional[str]) -> pd.DataFrame:
    """Fetch the single-vintage (2019) building-footprint count by parish."""
    return _fetch_by_parish_snapshot(
        missing_prefixed,
        level,
        region,
        fetch_fn=api.fetch_building_counts_by_parish,
        group_field="parròquia",
        resolve_code=constants.parish_code,
        schema_code="edif_2019",
    )


def _fetch_foreign_population(
    missing_prefixed: List[str], level: str, region: Optional[str]
) -> pd.DataFrame:
    """Fetch the real foreign-nationality ('Estrangera') population snapshot by parish.

    Unlike buildings/businesses, this source (see
    :func:`pycensus.andorra.api.fetch_population_by_nationality_and_parish`)
    already returns one row per parish plus a national total, so no
    locality/group-count aggregation step is needed here.
    """
    raw = api.fetch_population_by_nationality_and_parish()

    if level == "parish":
        out = raw[["GEOID", "foreign_nationality"]].copy()
        if region:
            code = constants.parish_code(region)
            out = out[out["GEOID"] == code]
    elif level == "nation":
        out = raw[raw["GEOID"] == "AD"][["GEOID", "foreign_nationality"]].copy()
    else:
        raise ValueError(f"Unsupported level for Andorra foreign-population aggregation: '{level}'")

    result = pd.DataFrame({"GEOID": out["GEOID"]})
    for prefixed_name in missing_prefixed:
        col_name = SCHEMA.strip_prefix(prefixed_name)
        col_def = SCHEMA.columns[col_name]
        if "estrangera" in col_def.codes:
            result[prefixed_name] = pd.to_numeric(out["foreign_nationality"], errors="coerce")
        else:
            result[prefixed_name] = pd.Series(dtype="float64", index=out.index)
    return result


def _fetch_businesses(missing_prefixed: List[str], level: str, region: Optional[str]) -> pd.DataFrame:
    """Fetch the live current-snapshot active-business count by parish."""
    return _fetch_by_parish_snapshot(
        missing_prefixed,
        level,
        region,
        fetch_fn=api.fetch_active_business_counts_by_parish,
        group_field="PARROQUIA",
        resolve_code=lambda n: f"AD-{int(n):02d}",
        schema_code="empreses_actives",
    )


# Logical (unprefixed) column name -> which fetcher owns it. Both new
# features are single-snapshot (no real year axis), unlike "population".
_SNAPSHOT_FETCHERS = {
    "buildingCount": _fetch_buildings,
    "activeBusinessCount": _fetch_businesses,
    "foreignBornPopulation": _fetch_foreign_population,
}


def _fetch_missing(missing_prefixed: List[str], level: str, region: Optional[str], year: int) -> pd.DataFrame:
    """Dispatch each requested logical column to its real fetcher, then align on GEOID."""
    by_fetcher: dict = {}
    population_cols: List[str] = []
    for prefixed_name in missing_prefixed:
        col_name = SCHEMA.strip_prefix(prefixed_name)
        if col_name in _SNAPSHOT_FETCHERS:
            by_fetcher.setdefault(col_name, []).append(prefixed_name)
        else:
            population_cols.append(prefixed_name)

    frames = []
    if population_cols:
        frames.append(_fetch_population(population_cols, level, region, year))
    for col_name, cols in by_fetcher.items():
        frames.append(_SNAPSHOT_FETCHERS[col_name](cols, level, region))

    if not frames:
        return pd.DataFrame({"GEOID": []})
    result = frames[0]
    for frame in frames[1:]:
        result = result.merge(frame, on="GEOID", how="outer")
    return result


def load(
    aoi: Optional[gpd.GeoDataFrame] = None,
    regions: Optional[Union[str, List[str]]] = None,
    level: str = "parish",
    year: Union[int, str] = "latest",
    api_key: Optional[str] = None,
    cache_dir: Optional[str] = None,
    cache: bool = True,
    data_dir: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """Load Andorra's real population-by-parish data as a common-schema GeoDataFrame.

    Args:
        aoi: Area of interest. Used to auto-detect ``regions`` if not given,
            and to clip the final result.
        regions: Region code(s) -- a parish name or ISO 3166-2:AD code
            (``"AD-01"``..``"AD-07"``), or ``"AD"``/``None`` for the whole
            country at ``level="nation"``. Derived from ``aoi`` if omitted
            (``aoi`` is then required).
        level: Standard geometry level name. Only ``"nation"``/``"parish"``
            are implemented (see :mod:`pycensus.andorra.geography`); other
            standard levels fall back to ``"parish"`` via
            :data:`pycensus.andorra.constants.LEVEL_FALLBACK`.
        year: Vintage year, or ``"latest"`` (resolves to 2025, the newest
            year this source publishes -- see
            :data:`pycensus.andorra.constants.LATEST_YEAR`).
        api_key: Not used -- this source requires no API key.
        cache_dir: Root of pyCensus' parquet cache. Defaults to
            :func:`pycensus.cache.default_cache_dir`.
        cache: If ``False``, bypass the parquet cache entirely.
        data_dir: Accepted for interface parity; this loader has no raw
            on-disk cache of its own (the source is one small live request).

    Returns:
        GeoDataFrame with ``GEOID``, geometry, and one
        ``estadisticaad_``-prefixed column per logical column in
        :data:`pycensus.andorra.estadisticaad.schema.SCHEMA`.

    Raises:
        ValueError: If neither ``regions`` nor ``aoi`` is given, or if
            ``year`` is not one of the years this source publishes.
        NotImplementedError: If ``level`` resolves to a level without a
            real boundary source.
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK, country="andorra")
    resolved_year = constants.LATEST_YEAR["census"] if year == "latest" else int(year)

    if level == "nation":
        # Nation-level population is the whole-country sum regardless of
        # which regions/aoi were passed, so it doesn't need either.
        region_codes = ["AD"]
    elif regions is None:
        if aoi is None:
            raise ValueError("Either 'regions' or 'aoi' is required")
        regions = geography.states_in_aoi(aoi)
        region_codes = [constants.parish_code(r) if r != "AD" else "AD" for r in regions]
    else:
        if isinstance(regions, str):
            regions = [regions]
        region_codes = [constants.parish_code(r) if r != "AD" else "AD" for r in regions]

    columns = [SCHEMA.prefixed(name) for name in SCHEMA.columns]

    region_frames = []
    for region_code in region_codes:
        path = cache_store.region_path(cache_dir, "andorra", level, f"{region_code}_{resolved_year}")

        def fetch_boundary(region=region_code):
            return geography.load_boundaries(level, None if region == "AD" else region)

        def fetch_columns(missing, region=region_code):
            return _fetch_missing(missing, level, None if region == "AD" else region, resolved_year)

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
