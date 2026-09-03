"""Loader for Chile's Casen SAE comunal poverty estimates, returning a common-schema GeoDataFrame.

Technical aspects:
    Mirrors :mod:`pycensus.countries.chile.ine.loader`'s shape (parquet
    cache via :mod:`pycensus.cache`, geometry from
    :mod:`pycensus.countries.chile.geography`), but the underlying source
    is a real bulk .xlsx download (see :mod:`pycensus.countries.chile.casen.api`)
    rather than a per-region API query -- so ``_fetch_missing`` fetches the
    (cached) national table once and filters to just the comunas in the
    requested region, instead of making a per-region network call.

    Only ``"comuna"`` is implemented -- Casen SAE only publishes comuna-
    level estimates (region-level poverty is already directly estimable
    from the Casen survey itself without SAE, and isn't republished in
    this bulk file).
"""

from __future__ import annotations

from typing import List, Optional, Union

import geopandas as gpd
import pandas as pd

from .... import cache as cache_store
from .... import geometry_levels
from pycensus.canonical import apply_canonical_names

from .. import constants, geography, utils
from . import api
from .schema import SCHEMA


def _fetch_missing(
    missing_prefixed: List[str],
    level: str,
    region: str,
    data_dir: Optional[str],
) -> pd.DataFrame:
    """Fetch (via the cached national xlsx tables) just the logical columns in ``missing_prefixed``, filtered to ``region``."""
    if level != "comuna":
        raise ValueError(
            f"Casen SAE comunal poverty data is only published at comuna level -- got level={level!r}."
        )

    missing_defs = [SCHEMA.columns[SCHEMA.strip_prefix(c)] for c in missing_prefixed]

    region_2digit = utils.region_code(region)

    tables = []
    for col in missing_defs:
        table = api.fetch_table(col.name, data_dir)
        tables.append(table[[col.name]])

    if not tables:
        return pd.DataFrame({"GEOID": []})

    merged = tables[0]
    for t in tables[1:]:
        merged = merged.join(t, how="outer")

    merged = merged[merged.index.str.startswith(region_2digit)]

    result = merged.reset_index().rename(columns={c: SCHEMA.column_label(c) for c in merged.columns})
    return result


def load(
    aoi: Optional[gpd.GeoDataFrame] = None,
    regions: Optional[Union[str, List[str]]] = None,
    level: str = "comuna",
    year: Union[int, str] = "latest",
    cache_dir: Optional[str] = None,
    cache: bool = True,
    data_dir: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """Load Chile Casen SAE comunal poverty data as a common-schema GeoDataFrame.

    Args:
        aoi: Area of interest. Used to auto-detect ``regions`` if not
            given (via :func:`pycensus.countries.chile.geography.regions_in_aoi`),
            and to clip the final result.
        regions: Region name(s)/code(s) to load. Derived from ``aoi`` if
            omitted (``aoi`` is then required).
        level: Must resolve to ``"comuna"`` -- the only level this source
            publishes.
        year: Vintage year, or ``"latest"``. Only 2022 (Casen 2022) is
            available.
        cache_dir: Root of pyCensus' parquet cache. Defaults to
            :func:`pycensus.cache.default_cache_dir`.
        cache: If ``False``, bypass the parquet cache entirely.
        data_dir: Base directory for the raw .xlsx cache. Defaults to
            :data:`pycensus.countries.chile.constants.DEFAULT_DATA_DIR`.

    Returns:
        GeoDataFrame with ``GEOID``, geometry, and one ``casen_cl``-
        prefixed column per logical column in
        :data:`pycensus.countries.chile.casen.schema.SCHEMA`.

    Raises:
        ValueError: If neither ``regions`` nor ``aoi`` is given.
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK, country="chile")
    if level != "comuna":
        raise NotImplementedError(
            f"Casen SAE comunal poverty data is only published at comuna level -- got level={level!r}."
        )
    year = 2022 if year == "latest" else int(year)

    if regions is None:
        if aoi is None:
            raise ValueError("Either 'regions' or 'aoi' is required")
        regions = geography.regions_in_aoi(aoi)
    elif isinstance(regions, str):
        regions = [regions]

    region_codes = [utils.region_code(r) for r in regions]
    columns = [SCHEMA.column_label(name) for name in SCHEMA.columns]

    region_frames = []
    for region_code in region_codes:
        path = cache_store.region_path(cache_dir, "chile_casen", level, region_code)

        gdf = cache_store.load_region(
            path,
            id_col="GEOID",
            columns=columns,
            fetch_boundary=lambda region=region_code: geography.load_boundaries(
                level, region, constants.LATEST_YEAR.get("geography"), data_dir=data_dir
            ),
            fetch_columns=lambda missing, region=region_code: _fetch_missing(
                missing, level, region, data_dir
            ),
            use_cache=cache,
        )
        region_frames.append(gdf)

    if not region_frames:
        return apply_canonical_names(
            gpd.GeoDataFrame(
                pd.DataFrame({"GEOID": [], **{c: [] for c in columns}}),
                geometry=gpd.GeoSeries([], crs=4326),
                crs=4326,
            ),
            SCHEMA,
        )

    result = gpd.GeoDataFrame(pd.concat(region_frames, ignore_index=True), geometry="geometry", crs=4326)

    if aoi is not None:
        result = result[result.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)

    return apply_canonical_names(result, SCHEMA)


__all__ = ["load"]
