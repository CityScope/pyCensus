"""Loader for CBS Census 2022 locality-level data, returning a common-schema GeoDataFrame.

Technical aspects:
    Mirrors :mod:`pycensus.mexico.inegi.loader`'s shape: reads as much as
    possible from pyCensus' parquet cache (:mod:`pycensus.cache`), fetching
    only the logical columns actually missing, per region (here: per CBS
    locality). Attribute data comes from a real, live, unauthenticated
    ArcGIS FeatureServer query (:data:`pycensus.israel.constants.CENSUS_SETL_2022_URL`,
    verified 2026-08-19), boundary data from
    :func:`pycensus.israel.geography.load_boundaries`.

    Both ``locality`` and ``statistical_area`` have a real, verified
    attribute source wired up (see :mod:`pycensus.israel.cbs.schema`'s
    field list -- all fields verified against a live query, e.g.
    SETL_CODE=9000 (Be'er Sheva) -> pop_approx=217580.0 at locality level;
    summing ``pop_approx`` over the 83 statistical areas with
    SEMEL_YISHUV=9000 gives 217,600, matching to rounding). See
    :data:`pycensus.israel.constants.CENSUS_STAT_2022_URL`'s docstring for
    how the statistical-area source was found and verified.
    ``district``/``nation`` requests raise (no CBS attribute table at that
    native granularity is wired up here; aggregate up from ``locality``/
    ``statistical_area`` via :mod:`geohierarchy` instead, which is how
    every other pyCensus source handles resampling across levels).

    Investigated 2026-08-22 and confirmed **not** to exist: any real,
    live-queryable geography finer than ``statistical_area`` with actual
    population/demographic data. Both CBS's own ArcGIS org
    (JcXY3lLZni6BK4El) and the general municipal-GIS org
    (b6zSqPB0TQc3mBgU) that hosts the ``מפקד_2022``/socioeconomic-index
    layers were enumerated (``FeatureServer`` service lists at each org's
    REST root); the only finer-than-statistical_area polygon layer found
    (``שכונות`` / neighborhoods, on b6zSqPB0TQc3mBgU) carries only
    ``shchuna``/``yishuv``/``nyb_name`` codes and names -- no population,
    household, or demographic attribute of any kind. ``statistical_area``
    is therefore this module's real ceiling for finer-than-locality
    geography with actual census data, not an arbitrary stopping point.
    (A ``מדד_חברתי_כלכלי_2021`` -- socioeconomic index -- layer does exist on
    b6zSqPB0TQc3mBgU, but is keyed to 2011-vintage statistical-area codes
    (``STAT11``/``YISHUV_STAT11``), not the 2022 vintage used everywhere
    else in this module, and no verified crosswalk between the two
    vintages was found, so it isn't wired in.)

    2026-08-22: added 11 new fields (age-by-sex medians, labour-force
    participation, work hours, self-employed wage, top-wage-decile share,
    household composition by age of resident, children-born, household
    parking) after confirming they're real columns on both the locality
    (``census_2022_setl_all_2021``) and statistical-area (``מפקד_2022``)
    ArcGIS layers -- verified live for Be'er Sheva (SETL_CODE=9000) and one
    of its statistical areas (YISHUV_STAT_2022=90000111); see
    ``tests/test_israel.py``'s ``test_real_cbs_new_fields_for_beersheba_locality``/
    ``test_real_cbs_new_fields_present_at_statistical_area_level``.

Source:
    CBS Census 2022 (via CBS's own hosted ArcGIS layers):
    https://services8.arcgis.com/JcXY3lLZni6BK4El/arcgis/rest/services/
    https://services.arcgis.com/b6zSqPB0TQc3mBgU/arcgis/rest/services/
"""

from __future__ import annotations

from typing import List, Optional, Union

import geopandas as gpd
import numpy as np
import pandas as pd

from .... import cache as cache_store
from .... import geometry_levels
from .. import arcgis, constants, geography, utils
from .schema import SCHEMA
from pycensus.canonical import apply_canonical_names

IMPLEMENTED_LEVELS = ("locality", "statistical_area")

# Per-level attribute source: the ArcGIS layer URL, the field used to
# select region(s) from it (``where_field``), and the field holding this
# level's GEOID (``id_field``). For ``locality``, ``region`` (a SETL_CODE)
# selects exactly one feature. For ``statistical_area``, ``region`` is
# still a *locality* code (matching geography.load_boundaries's own
# ``statistical_area`` region semantics -- it filters by SEMEL_YISHUV, the
# locality code, and returns every statistical area within it), so one
# query can return many features, one per YISHUV_STAT_2022 within that
# locality.
_ATTRIBUTE_SOURCE = {
    "locality": (constants.CENSUS_SETL_2022_URL, "SETL_CODE", "SETL_CODE"),
    "statistical_area": (constants.CENSUS_STAT_2022_URL, "SEMEL_YISHUV", "YISHUV_STAT_2022"),
}


def _fetch_missing(
    missing_prefixed: List[str],
    region: str,
    level: str = "locality",
) -> pd.DataFrame:
    """Fetch and select just the logical columns in ``missing_prefixed`` for one region.

    Returns one row per feature matched -- exactly one for ``locality``,
    possibly several (one per statistical area) for ``statistical_area``.
    """
    missing_defs = [SCHEMA.columns[SCHEMA.strip_prefix(c)] for c in missing_prefixed]

    url, where_field, id_field = _ATTRIBUTE_SOURCE[level]
    # `out_fields="*"` rather than an explicit field list: some logical
    # columns (e.g. "religionCode") list multiple candidate raw field names
    # because the locality layer and statistical-area layer use different
    # real names for the same concept (`Religion_Code` vs
    # `Religion_Stat_Code`) -- requesting a candidate that doesn't exist on
    # the *other* layer makes ArcGIS reject the whole query with "outFields
    # parameter is invalid" rather than just omitting it. `*` sidesteps that
    # per-layer field-name mismatch entirely; `_fetch_missing` already only
    # reads whichever candidate is actually present in `attrs` below.
    features = arcgis.query_features(
        url,
        where=f"{where_field} = {int(region)}",
        out_fields="*",
        return_geometry=False,
    )

    if not features:
        return pd.DataFrame({"GEOID": [], **{c: [] for c in missing_prefixed}})

    rows = []
    for feature in features:
        attrs = feature["attributes"]
        row = {"GEOID": str(attrs[id_field])}
        for col in missing_defs:
            prefixed = SCHEMA.column_label(col.name)
            raw_col = next((c for c in col.codes if c in attrs), None)
            row[prefixed] = attrs.get(raw_col) if raw_col is not None else None
        rows.append(row)

    return pd.DataFrame(rows)


def _localities_for(aoi: Optional[gpd.GeoDataFrame], localities: Optional[Union[str, List[str]]]) -> List[str]:
    if localities is not None:
        if isinstance(localities, str):
            localities = [localities]
        return [utils.locality_code(loc) for loc in localities]

    if aoi is None:
        raise ValueError("Either 'localities' or 'aoi' is required")

    return geography.localities_in_aoi(aoi)


def load(
    aoi: Optional[gpd.GeoDataFrame] = None,
    localities: Optional[Union[str, List[str]]] = None,
    regions: Optional[Union[str, List[str]]] = None,
    level: str = "locality",
    year: Union[int, str] = "latest",
    api_key: Optional[str] = None,
    cache_dir: Optional[str] = None,
    cache: bool = True,
    data_dir: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """Load CBS Census 2022 locality-level data as a common-schema GeoDataFrame.

    Args:
        aoi: Area of interest. Used to auto-detect which localities to
            load if ``localities``/``regions`` isn't given, and to clip
            the final result.
        localities: Locality name(s) or CBS/LAMAS code(s) to load (see
            :func:`pycensus.israel.utils.locality_code`). Derived from
            ``aoi`` if omitted (``aoi`` is then required).
        regions: Alias for ``localities``, kept for interface parity with
            other pyCensus sources.
        level: Standard geometry level name. ``"locality"`` and
            ``"statistical_area"`` have real attribute sources wired up
            (see module docstring); anything else raises.
        year: Vintage year, or ``"latest"``. Only 2022 is available.
        api_key: Not used -- every source wired up here is public and
            unauthenticated (verified 2026-08-19).
        cache_dir: Root of pyCensus' parquet cache. Defaults to
            :func:`pycensus.cache.default_cache_dir`.
        cache: If ``False``, bypass the cache entirely -- always fetch
            fresh and don't persist the result.
        data_dir: Not used (kept for interface parity).

    Returns:
        GeoDataFrame with ``GEOID``, geometry, and one ``cbs_``-prefixed
        column per logical column in :data:`pycensus.israel.cbs.schema.SCHEMA`.

    Raises:
        ValueError: If neither ``localities``/``regions`` nor ``aoi`` is
            given, or ``level`` resolves to something outside
            :data:`IMPLEMENTED_LEVELS`.
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK, country="israel")
    if level not in IMPLEMENTED_LEVELS:
        raise ValueError(
            f"CBS attribute data for level '{level}' is not implemented -- only "
            f"{IMPLEMENTED_LEVELS} are wired to a real, verified source. Aggregate up from "
            f"'locality'/'statistical_area' via geohierarchy for district/nation totals. See "
            f"pycensus.israel.cbs.loader module docstring."
        )
    year = constants.LATEST_YEAR.get("census", 2022) if year == "latest" else int(year)

    # Both locality and statistical_area attribute fetches are keyed by
    # *locality* code (see _ATTRIBUTE_SOURCE) -- geography.load_boundaries
    # itself keys a "statistical_area" region by its containing locality's
    # SEMEL_YISHUV, returning every statistical area within it in one call.
    locality_codes = _localities_for(aoi, localities if localities is not None else regions)
    columns = [SCHEMA.column_label(name) for name in SCHEMA.columns]

    region_frames = []
    for region_code in locality_codes:
        path = cache_store.region_path(cache_dir, "israel", level, region_code)

        gdf = cache_store.load_region(
            path,
            id_col="GEOID",
            columns=columns,
            fetch_boundary=lambda region=region_code: geography.load_boundaries(level, region, year),
            fetch_columns=lambda missing, region=region_code: _fetch_missing(missing, region, level),
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

    # foreignBornPopulation has no native CBS ArcGIS field (empty "codes"
    # in cbs_schema.json) -- derived here as
    # round(Foreign_pcnt/100 * pop_approx) since Foreign_pcnt is verified
    # relative_to the same population field wired as "population" (see
    # cbs_schema.json's foreignBornPopulation entry for the live
    # verification). Only computed where both inputs are real (non-NaN).
    if "cbs_foreignBornPopulation" in result.columns:
        rate = pd.to_numeric(result.get("cbs_foreignResidentRate"), errors="coerce")
        pop = pd.to_numeric(result.get("cbs_population"), errors="coerce")
        result["cbs_foreignBornPopulation"] = (rate / 100.0 * pop).round()

    # Religion population columns -- CBS reports religion as a single
    # per-area dominant-religion classification code (1=Jewish, 2=Muslim,
    # 3=Christian, 5=Druze, 6=Other; live-verified 2026-08-25, see
    # "religionCode"'s definition in cbs_schema.json), not a population
    # breakdown. Reconstruct real per-religion population counts the same
    # way foreignBornPopulation is derived above, then drop the raw code
    # column -- a bare 1-6 category is meaningless once resampled/summed,
    # unlike these derived counts.
    if "cbs_religionCode" in result.columns:
        code = pd.to_numeric(result["cbs_religionCode"], errors="coerce")
        pop = pd.to_numeric(result.get("cbs_population"), errors="coerce")
        for col, religion_code in (
            ("cbs_jewishPopulation", 1),
            ("cbs_muslimPopulation", 2),
            ("cbs_christianPopulation", 3),
            ("cbs_druzePopulation", 5),
            ("cbs_otherReligionPopulation", 6),
        ):
            if col in result.columns:
                # 0 where the area's classification is known and different;
                # NaN (not 0) where the classification itself is missing --
                # an unclassified area's religion breakdown is unknown, not
                # zero, so it must not silently zero out downstream sums.
                result[col] = pop.where(code == religion_code, 0.0).where(code.notna(), np.nan)
        result = result.drop(columns=["cbs_religionCode"])

    # Religious-observance ("degree of religiosity") population columns --
    # same shape as the religion columns above, from CBS's per-area
    # secular/traditional/religious/Haredi classification code
    # ("religiosityCode"/`hh_MidatDatiyut`, live-verified 2026-08-25: real
    # variation across Beersheba's statistical areas -- 51 secular / 15
    # traditional / 1 religious / 16 unclassified of 83).
    if "cbs_religiosityCode" in result.columns:
        code = pd.to_numeric(result["cbs_religiosityCode"], errors="coerce")
        pop = pd.to_numeric(result.get("cbs_population"), errors="coerce")
        for col, religiosity_code in (
            ("cbs_secularPopulation", 1),
            ("cbs_traditionalReligiosityPopulation", 2),
            ("cbs_religiousObservantPopulation", 3),
            ("cbs_haredimPopulation", 4),
            ("cbs_otherReligiosityPopulation", 6),
        ):
            if col in result.columns:
                result[col] = pop.where(code == religiosity_code, 0.0).where(code.notna(), np.nan)
        result = result.drop(columns=["cbs_religiosityCode"])

    if aoi is not None:
        result = result[result.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)

    return apply_canonical_names(result, SCHEMA)


__all__ = ["load"]
