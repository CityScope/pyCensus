"""Loader for INEGI Census (Censo de Poblacion y Vivienda) 2020, returning a common-schema GeoDataFrame.

Technical aspects:
    Mirrors :mod:`pycensus.usa.acs5.loader`'s shape: reads as much as
    possible from pyCensus' parquet cache (:mod:`pycensus.cache`),
    fetching only the logical columns actually missing, and merges the
    result back into the shared per-level/region cache file. The
    difference from every ``usa.*`` source is that INEGI has no queryable
    API -- :mod:`pycensus.mexico.api` downloads and caches INEGI's bulk
    per-state ITER CSV on disk (independent of, and upstream of,
    :mod:`pycensus.cache`'s parquet cache) the first time any column is
    requested for a state, then every subsequent column/level request for
    that state is served from the already-downloaded file.

    ``state``, ``municipality``, ``ageb`` (urban only), and ``block``
    (urban only) levels are implemented. ``ageb``/``block``-level
    attribute columns come from a different INEGI bulk file, RESAGEBURB
    (:func:`pycensus.mexico.api.fetch_ageb_totals`/
    :func:`pycensus.mexico.api.fetch_block_totals`), not ITER (see
    :mod:`pycensus.mexico.geography` for the live end-to-end verification
    of the block boundary/attribute pairing).

Source:
    INEGI Census 2020: https://www.inegi.org.mx/programas/ccpv/2020/
"""

from __future__ import annotations

from typing import List, Optional, Union

import geopandas as gpd
import pandas as pd

from .... import cache as cache_store
from .... import geometry_levels
from .. import api, constants, geography, utils
from .schema import SCHEMA
from ....canonical import apply_canonical_names

_FETCH_TOTALS_NAMES = {
    "state": "fetch_state_totals",
    "municipality": "fetch_municipality_totals",
    "ageb": "fetch_ageb_totals",
    "block": "fetch_block_totals",
}


def _fetch_missing(
    missing_prefixed: List[str],
    level: str,
    state: str,
    data_dir: Optional[str],
) -> pd.DataFrame:
    """Fetch and compute just the logical columns in ``missing_prefixed`` from ITER/RESAGEBURB.

    Most columns are a straight raw-code lookup. A few (e.g.
    ``religiousPopulation``) have no codes of their own and are instead
    derived as ``computed_from[0] - computed_from[1]`` from two other
    logical columns (:attr:`pycensus.schema.ColumnDef.computed_from`) --
    mirrors :func:`pycensus.usa.dhc.loader._fetch_missing`'s pattern; those
    base columns are fetched too even if not directly requested.
    """
    fetch_name = _FETCH_TOTALS_NAMES.get(level)
    if fetch_name is None:
        raise ValueError(
            f"INEGI attribute data for level '{level}' is not implemented -- only "
            f"{sorted(_FETCH_TOTALS_NAMES)} are wired up (see pycensus.mexico.api module docstring)."
        )
    # Looked up dynamically (not bound at import time) so tests can
    # monkeypatch pycensus.mexico.api.fetch_state_totals/etc.
    fetch_totals = getattr(api, fetch_name)

    raw = fetch_totals(state, data_dir)
    missing_defs = [SCHEMA.columns[SCHEMA.strip_prefix(c)] for c in missing_prefixed]

    direct_defs = [col for col in missing_defs if not col.computed_from]
    computed_defs = [col for col in missing_defs if col.computed_from]

    # Computed columns need their base columns' raw codes too, even if not
    # directly requested by the caller.
    base_names = {name for col in computed_defs for name in col.computed_from}
    base_defs = [SCHEMA.columns[name] for name in base_names]
    all_direct_defs = list({col.name: col for col in [*direct_defs, *base_defs]}.values())

    result = pd.DataFrame({"GEOID": raw["GEOID"]})
    for col in all_direct_defs:
        prefixed = SCHEMA.column_label(col.name)
        raw_col = next((c for c in col.codes if c in raw.columns), None)
        if raw_col is None:
            result[prefixed] = pd.Series(dtype="float64", index=raw.index)
        else:
            result[prefixed] = pd.to_numeric(raw[raw_col], errors="coerce")

    for col in computed_defs:
        left = SCHEMA.column_label(col.computed_from[0])
        right = SCHEMA.column_label(col.computed_from[1])
        result[SCHEMA.column_label(col.name)] = result[left] - result[right]

    keep = ["GEOID", *[SCHEMA.column_label(c.name) for c in direct_defs], *[SCHEMA.column_label(c.name) for c in computed_defs]]
    return result[keep]


def load(
    aoi: Optional[gpd.GeoDataFrame] = None,
    states: Optional[Union[str, List[str]]] = None,
    level: str = "municipality",
    year: Union[int, str] = "latest",
    cache_dir: Optional[str] = None,
    cache: bool = True,
    data_dir: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """Load INEGI Census 2020 data as a common-schema GeoDataFrame.

    Args:
        aoi: Area of interest. Used to auto-detect ``states`` if not
            given, and to clip the final result. Every state is checked
            since no national boundary layer is wired up to pre-filter
            (see :func:`pycensus.mexico.geography.states_in_aoi`).
        states: State name(s)/abbreviation(s)/code(s) to load. Derived
            from ``aoi`` if omitted (``aoi`` is then required).
        level: Standard geometry level name. ``"state"``,
            ``"municipality"``, ``"ageb"``, and ``"block"`` are
            implemented; other standard levels (e.g.
            ``"tract"``/``"blockgroup"``) fall back onto one of those via
            :data:`pycensus.mexico.constants.LEVEL_FALLBACK` where
            possible, else raise.
        year: Vintage year, or ``"latest"``. Only 2020 is available.
        cache_dir: Root of pyCensus' parquet cache (geometry + attribute
            columns, merged per level/region). Defaults to
            :func:`pycensus.cache.default_cache_dir`.
        cache: If ``False``, bypass the parquet cache entirely -- always
            fetch fresh and don't persist the result. INEGI's own raw
            ITER/Marco Geoestadistico downloads (:mod:`pycensus.mexico.api`,
            :mod:`pycensus.mexico.geography`) are cached on disk
            independently of this flag, since re-downloading multi-MB
            per-state files on every call would be impractical.
        data_dir: Base directory for INEGI's raw downloaded files (ITER
            CSVs, Marco Geoestadistico zips). Defaults to
            :data:`pycensus.mexico.constants.DEFAULT_DATA_DIR`.

    Returns:
        GeoDataFrame with ``GEOID``, geometry, and one ``inegi_``-prefixed
        column per logical column in :data:`pycensus.mexico.inegi.schema.SCHEMA`.

    Raises:
        ValueError: If neither ``states`` nor ``aoi`` is given, or
            ``level`` has no implemented data source.
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK, country="mexico")
    year = constants.LATEST_YEAR.get("census", 2020) if year == "latest" else int(year)

    if states is None:
        if aoi is None:
            raise ValueError("Either 'states' or 'aoi' is required")
        states = geography.states_in_aoi(aoi, year)
    elif isinstance(states, str):
        states = [states]

    state_codes = [utils.state_code(s) for s in states]
    columns = [SCHEMA.column_label(name) for name in SCHEMA.columns]

    state_frames = []
    for state_code in state_codes:
        path = cache_store.region_path(cache_dir, "mexico", level, state_code)

        gdf = cache_store.load_region(
            path,
            id_col="GEOID",
            columns=columns,
            fetch_boundary=lambda state=state_code: geography.load_boundaries(
                level, state, year, data_dir=data_dir
            ),
            fetch_columns=lambda missing, state=state_code: _fetch_missing(
                missing, level, state, data_dir
            ),
            use_cache=cache,
        )
        state_frames.append(gdf)

    if not state_frames:
        return apply_canonical_names(
            gpd.GeoDataFrame(
            pd.DataFrame({"GEOID": [], **{c: [] for c in columns}}),
            geometry=gpd.GeoSeries([], crs=4326),
            crs=4326,
        ),
            SCHEMA,
        )

    result = gpd.GeoDataFrame(pd.concat(state_frames, ignore_index=True), geometry="geometry", crs=4326)

    if aoi is not None:
        result = result[result.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)

    return apply_canonical_names(result, SCHEMA)


__all__ = ["load"]
