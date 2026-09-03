"""Loader for INE Chile Censo 2017 (via the Esri Chile DPA FeatureServer), returning a common-schema GeoDataFrame.

Technical aspects:
    Mirrors :mod:`pycensus.mexico.inegi.loader`'s shape: reads as much as
    possible from pyCensus' parquet cache (:mod:`pycensus.cache`),
    fetching only the logical columns actually missing, and merges the
    result back into the shared per-level/region cache file.

    Unlike Mexico's INEGI (a plain CSV per state), Chile's real source
    (:mod:`pycensus.chile.api`) returns geometry *and* attributes together
    in one GeoJSON response per level/region, cached to disk. So
    ``_fetch_missing`` here re-reads the very same cached raw file that
    :mod:`pycensus.chile.geography` already fetched for the boundary --
    no second network call for the same level/region.

    Only ``region``, ``provincia``, ``comuna``, ``distrito`` are
    implemented (see :mod:`pycensus.chile.geography` for why ``nation``/
    ``block`` aren't).

Source:
    https://services.arcgis.com/r7t1P5pnkoOLRdhr/arcgis/rest/services/
    Divisi%C3%B3n_Pol%C3%ADtico_Administrativa_y_Censal/FeatureServer
"""

from __future__ import annotations

from typing import List, Optional, Union

import geopandas as gpd
import pandas as pd

from .... import cache as cache_store
from .... import geometry_levels
from .. import api, constants, geography, utils
from .schema import SCHEMA
from pycensus.canonical import apply_canonical_names


def _fetch_missing(
    missing_prefixed: List[str],
    level: str,
    region: str,
    data_dir: Optional[str],
) -> pd.DataFrame:
    """Fetch (via the cached raw GeoJSON) and select just the logical columns in ``missing_prefixed``."""
    if level not in api.LAYER_IDS:
        raise ValueError(
            f"INE Chile attribute data for level '{level}' is not implemented -- only "
            f"{sorted(api.LAYER_IDS)} are wired up (see pycensus.chile.api module docstring)."
        )

    raw = api.fetch_features(level, region, data_dir)
    code_field = api.CODE_FIELDS[level]

    geoids = []
    rows = []
    for feature in raw["features"]:
        props = feature["properties"]
        geoids.append(api.build_geoid(level, props[code_field]))
        rows.append(props)

    missing_defs = [SCHEMA.columns[SCHEMA.strip_prefix(c)] for c in missing_prefixed]

    result = pd.DataFrame({"GEOID": geoids})
    raw_df = pd.DataFrame(rows)
    for col in missing_defs:
        prefixed = SCHEMA.column_label(col.name)
        raw_col = next((c for c in col.codes if c in raw_df.columns), None)
        if raw_col is None:
            result[prefixed] = pd.Series(dtype="float64", index=result.index)
        else:
            result[prefixed] = pd.to_numeric(raw_df[raw_col], errors="coerce")
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
    """Load INE Chile Censo 2017 data as a common-schema GeoDataFrame.

    Args:
        aoi: Area of interest. Used to auto-detect ``regions`` if not
            given (via :func:`pycensus.chile.geography.regions_in_aoi`),
            and to clip the final result.
        regions: Region name(s)/code(s) to load. Derived from ``aoi`` if
            omitted (``aoi`` is then required).
        level: Standard geometry level name, resolved through
            :data:`pycensus.chile.constants.LEVEL_FALLBACK`. Only
            ``"region"``, ``"provincia"``, ``"comuna"``, ``"distrito"``
            are implemented.
        year: Vintage year, or ``"latest"``. Only 2017 (Censo 2017, the
            only vintage this DPA service publishes) is available.
        cache_dir: Root of pyCensus' parquet cache. Defaults to
            :func:`pycensus.cache.default_cache_dir`.
        cache: If ``False``, bypass the parquet cache entirely.
        data_dir: Base directory for the raw GeoJSON cache. Defaults to
            :data:`pycensus.chile.constants.DEFAULT_DATA_DIR`.

    Returns:
        GeoDataFrame with ``GEOID``, geometry, and one ``ine_``-prefixed
        column per logical column in :data:`pycensus.chile.ine.schema.SCHEMA`.

    Raises:
        ValueError: If neither ``regions`` nor ``aoi`` is given.
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK, country="chile")
    year = constants.LATEST_YEAR.get("census", 2017) if year == "latest" else int(year)

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
        path = cache_store.region_path(cache_dir, "chile", level, region_code)

        gdf = cache_store.load_region(
            path,
            id_col="GEOID",
            columns=columns,
            fetch_boundary=lambda region=region_code: geography.load_boundaries(
                level, region, year, data_dir=data_dir
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
