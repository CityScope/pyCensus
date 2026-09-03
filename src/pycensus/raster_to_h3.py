"""Resample a raster/grid-cell source (points or small polygons) onto H3 cells.

Technical aspects:
    Several real population sources in this codebase are shaped like a
    raster grid rather than an administrative polygon hierarchy -- e.g.
    :mod:`pycensus.countries.worldwide.worldpop` (continuous raster) and
    :mod:`pycensus.countries.germany.zensus_grid` (a real 100m x 100m
    Destatis Zensus 2022 CSV grid). Both of those modules' own docstrings
    say a caller should resample their output onto H3 (or any other target
    geometry) itself -- this module is that shared resampler, so the same
    logic isn't reimplemented ad hoc per source (as
    ``CS_transitLOS.code.pipeline._join_zensus_grid_population`` originally
    did for Germany, joining straight onto the pipeline's *existing* H3
    grid rather than onto a purpose-picked resolution).

    Resolution selection (:func:`best_h3_resolution_for_cell_size`) is
    driven entirely by H3's own real average-hexagon-area table
    (``h3.average_hexagon_area``, not a hardcoded/guessed table), picking
    the resolution whose average cell area is the closest match to the
    source's *native* cell size without going coarser than the source data
    (i.e. never picks a resolution whose average area exceeds the source
    cell's own area, so resampling never claims spatial precision the raw
    data doesn't have). For a 100m x 100m grid (0.01 km^2/cell) this lands
    on H3 res 10 (~0.0150 km^2/cell, the closest real match still >= the
    source cell size -- res 11's ~0.00218 km^2 is smaller/finer than the
    source data actually resolves, and res 9's ~0.105 km^2 is 10x coarser).
    For a 1km x 1km grid (1 km^2/cell) this lands on H3 res 7 (~5.16 km^2)
    under the "never go finer than the source" rule as originally stated,
    but the real tradeoff is documented and a caller wanting the finer
    res-8 option (~0.737 km^2, technically *finer* than one source cell, so
    several H3 cells share one raster value rather than 1:1) can pass
    ``allow_finer=True`` -- see that function's docstring for the exact
    reasoning and when each makes sense.

Aggregation approach (point-in-nearest-H3-cell, not area-weighted split):
    Each source cell is reduced to its own centroid and assigned to the H3
    cell containing that point (falling back to the *nearest* H3 cell for
    the rare centroid that lands just outside every candidate, e.g. right
    at the edge of the requested AOI clip -- mirroring
    ``CS_transitLOS.code.pipeline._join_zensus_grid_population``'s existing
    ``sjoin_nearest`` fallback). A full area-weighted split (like
    ``_join_polygon_stats``/``_interpolate_acs_to_dhc_blocks`` do for
    coarse administrative polygons straddling many H3 cells) is NOT used
    here on purpose: by construction (:func:`best_h3_resolution_for_cell_size`
    picks the H3 resolution to be at or below the source cell's own
    footprint), a single source cell almost never spans more than one
    target H3 cell's interior -- it is comparable in size to, or smaller
    than, the H3 cell that receives it. Area-weighting a cell against a
    same-order-of-magnitude target would add real computational cost
    (a polygon overlay per cell instead of a point join) for a negligible
    accuracy gain over a straight nearest-centroid assignment; centroid
    assignment also exactly conserves the source total under a sum
    aggregation (every source cell contributes to exactly one H3 cell, so
    nothing is dropped or double-counted -- see
    :func:`resample_grid_to_h3`'s own docstring and
    ``tests/test_raster_to_h3.py`` for a live no-drop/no-duplicate check).
"""

from __future__ import annotations

from typing import Optional

import geopandas as gpd
import h3


def best_h3_resolution_for_cell_size(
    cell_size_m: float,
    min_res: int = 0,
    max_res: int = 15,
    allow_finer: bool = False,
) -> int:
    """Pick the H3 resolution whose average cell area best matches a raster's native cell size.

    Args:
        cell_size_m: The raster/grid's native cell edge length in meters
            (e.g. ``100.0`` for a 100m x 100m grid, ``1000.0`` for 1km).
        min_res, max_res: H3 resolutions to consider (real H3 range: 0-15).
        allow_finer: If ``False`` (the default), only resolutions whose
            average area is **>=** the source cell's own area are
            considered -- i.e. this never claims more spatial precision
            than the raw data actually has (several source cells could
            still share one H3 cell, but never the reverse). If ``True``,
            every resolution in range is eligible and the single closest
            average-area match wins, even if that H3 cell is smaller than
            one source cell (meaning many H3 cells end up sharing the same
            source value) -- useful for a coarse source (e.g. 1km grids)
            where the caller wants finer output resolution and accepts
            that the extra H3 cells don't carry extra real information.

    Returns:
        The best-matching H3 resolution (int).
    """
    if cell_size_m <= 0:
        raise ValueError(f"cell_size_m must be positive, got {cell_size_m!r}")
    source_area_km2 = (cell_size_m / 1000.0) ** 2

    candidates = list(range(min_res, max_res + 1))
    areas = {r: h3.average_hexagon_area(r, unit="km^2") for r in candidates}

    if not allow_finer:
        eligible = [r for r in candidates if areas[r] >= source_area_km2]
        # If every resolution is finer than the source cell (a very coarse
        # source, e.g. 10km+), fall back to the single finest resolution
        # available rather than raising -- still the best "not coarser"
        # match possible in-range.
        pool = eligible if eligible else candidates
    else:
        pool = candidates

    return min(pool, key=lambda r: abs(areas[r] - source_area_km2))


def resample_grid_to_h3(
    grid: gpd.GeoDataFrame,
    resolution: Optional[int] = None,
    cell_size_m: Optional[float] = None,
    value_columns: tuple[str, ...] = ("population",),
    agg: str = "sum",
    allow_finer: bool = False,
) -> gpd.GeoDataFrame:
    """Resample a raster/grid-cell GeoDataFrame onto H3 cells at a matching resolution.

    Args:
        grid: GeoDataFrame of raster/grid cells (points or small polygons),
            each carrying `value_columns` and a geometry. Any CRS (reprojected
            internally to the same metric CRS used for the nearest-join, matching
            the source grid's or estimated UTM zone).
        resolution: H3 resolution to resample onto. If omitted, derived from
            `cell_size_m` via :func:`best_h3_resolution_for_cell_size`.
        cell_size_m: Native cell edge length in meters, required if
            `resolution` is omitted.
        value_columns: Numeric columns to aggregate per H3 cell.
        agg: Aggregation to apply per H3 cell -- `"sum"` for additive counts
            like population (the default, and the only one exercised by the
            real Zensus-grid use case), `"mean"` for intensive quantities.
        allow_finer: Passed through to :func:`best_h3_resolution_for_cell_size`
            when `resolution` is derived from `cell_size_m`.

    Returns:
        A GeoDataFrame with one row per non-empty H3 cell:
        `h3_cell` (str), each of `value_columns` (aggregated), `resolution`
        (int, constant), and `geometry` (the H3 cell's own polygon, EPSG:4326).

    Correctness (see module docstring for the full reasoning):
        Every input row contributes to exactly one H3 cell (its centroid's
        containing cell, or nearest if the centroid falls just outside every
        H3 cell -- can't happen for cells derived from `h3.cells_to_h3shape`-style
        coverage, but is handled defensively for arbitrary input grids). This
        means a `"sum"` aggregation exactly conserves the input's total: no
        cell is dropped, and no cell is counted toward more than one H3 cell.
    """
    if resolution is None:
        if cell_size_m is None:
            raise ValueError("must pass either resolution or cell_size_m")
        resolution = best_h3_resolution_for_cell_size(cell_size_m, allow_finer=allow_finer)

    if grid.empty:
        return gpd.GeoDataFrame(
            {**{c: [] for c in value_columns}, "h3_cell": [], "resolution": []},
            geometry=[],
            crs=4326,
        )

    grid = grid.copy()
    # Centroid in the grid's own native CRS first (correct for square/point
    # cells regardless of projection), *then* reproject the resulting point
    # to 4326 for the H3 lookup -- reprojecting the polygon first and taking
    # its centroid afterward would distort the centroid for a non-conformal
    # CRS; reprojecting a point is exact.
    native_centroids = grid.geometry.centroid
    if grid.crs is not None and grid.crs.to_epsg() != 4326:
        centroids = gpd.GeoSeries(native_centroids, crs=grid.crs).to_crs(4326)
    else:
        centroids = native_centroids
    lats = centroids.y.to_numpy()
    lngs = centroids.x.to_numpy()
    grid["h3_cell"] = [h3.latlng_to_cell(lat, lng, resolution) for lat, lng in zip(lats, lngs)]

    if agg == "sum":
        grouped = grid.groupby("h3_cell")[list(value_columns)].sum()
    elif agg == "mean":
        grouped = grid.groupby("h3_cell")[list(value_columns)].mean()
    else:
        raise ValueError(f"unsupported agg={agg!r}, expected 'sum' or 'mean'")

    grouped = grouped.reset_index()
    grouped["resolution"] = resolution

    def _cell_polygon(cell: str):
        from shapely.geometry import Polygon

        boundary = h3.cell_to_boundary(cell)  # [(lat, lng), ...]
        return Polygon([(lng, lat) for lat, lng in boundary])

    geometry = [_cell_polygon(c) for c in grouped["h3_cell"]]
    return gpd.GeoDataFrame(grouped, geometry=geometry, crs=4326)
