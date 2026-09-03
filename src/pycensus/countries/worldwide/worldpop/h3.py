"""WorldPop-raster-specific application of geohierarchy's area-weighted raster->H3 resampler.

This module is the "apply generic method to WorldPop specifically" half of
the area-weighted raster resampling work (the generic, WorldPop-agnostic
primitive lives in :mod:`geohierarchy.raster_resample`, this module just
adds WorldPop's own known quirks on top -- nodata handling, degree-vs-metric
CRS, and clipping-to-AOI):

- WorldPop rasters are shipped in EPSG:4326 (degrees), so pixel area (and
  therefore area-weighting) is not metric there -- see
  :func:`worldpop_raster_to_h3`'s docstring for how this is handled (the
  H3 grid this resamples onto is itself built/consumed in EPSG:4326, same
  as :func:`geohierarchy.utils.h3_cells`, and the underlying
  :func:`geohierarchy.raster_resample.raster_to_polygons` primitive is
  reprojection-agnostic: it just needs *a* shared CRS between the raster
  and the target polygons for its area-ratio math to be self-consistent,
  which holds even in degrees since both sides -- pixel bbox area and H3
  cell polygon area -- are measured in the exact same units and get
  divided against each other, canceling out the degrees-vs-m^2 distortion
  for the *split fraction* even though absolute densities in degrees are
  not physically meaningful on their own).
- WorldPop's real nodata sentinel (commonly -99999, but read from the file
  itself rather than assumed) marks unsettled/off-country land and must be
  excluded, not treated as a real 0.

This replaces the previous naive centroid-based approach for WorldPop
specifically (nearest-H3-cell-to-pixel-center, with no area splitting --
see ``pycensus.raster_to_h3``'s ``resample_grid_to_h3``, and
``UrbanAccessAnalyzer.h3_ops.from_raster_centroid``, both of which remain
in place as the general-purpose/other-source-shaped resamplers but are no
longer the right tool for WorldPop given this exact, mass-conserving
alternative now exists).
"""

from __future__ import annotations

from typing import Optional

import polars as pl

from geohierarchy.raster_resample import raster_to_h3_tiled


def worldpop_raster_to_h3(
    tif_path: str,
    resolution: int,
    value_col: str = "population",
    h3_col: str = "h3_cell",
    tile_resolution: int = 5,
    max_workers: Optional[int] = None,
) -> pl.DataFrame:
    """Area-weighted, mass-conserving resample of a WorldPop GeoTIFF onto an H3 grid.

    Delegates to :func:`geohierarchy.raster_resample.raster_to_h3_tiled`
    (not the older single-shot :func:`~geohierarchy.raster_resample.raster_to_h3`)
    so the source GeoTIFF is never read into memory in one piece -- each
    H3-resolution-5 tile's worker opens `tif_path` itself and reads only
    its own small windowed slice. This is what avoids the OOM kills seen
    live on Boston/Beersheba (2026-08-30, killed past a 20GB cgroup cap
    during this exact join) without needing a larger memory budget: peak
    memory is bounded by one tile, not by the whole city's raster + H3
    grid + spatial index all at once.

    Args:
        tif_path: Path to a (optionally AOI-clipped, e.g. via
            :func:`pycensus.countries.worldwide.worldpop.loader._clip_to_aoi`)
            single-band WorldPop GeoTIFF.
        resolution: Target H3 resolution.
        value_col: Name to give the output value column (e.g.
            ``"population"``, ``"malePopulation"``, whatever
            :func:`~pycensus.countries.worldwide.worldpop.loader.download_worldpop_layer`
            feature this raster represents).
        h3_col: Name to give the output H3 cell-id column.
        tile_resolution: Coarser H3 resolution partitioning the work into
            independent, memory-bounded chunks (default 5 -- see
            `raster_to_h3_tiled`'s docstring for why this resolution
            specifically gives an exact, non-overlapping partition).
        max_workers: Worker process count (default: one process per CPU
            core). Pass 1 for a small AOI where process-pool overhead
            would dominate.

    Returns:
        Polars DataFrame with ``h3_col`` and ``value_col`` -- one row per
        H3 cell touched by at least one valid (non-nodata) pixel. Every
        such cell is present (no silent drops), and
        ``sum(value_col)`` exactly equals the sum of the raster's valid
        pixel values within the H3 grid's covered extent (see
        :func:`geohierarchy.raster_resample.raster_to_polygons` for the
        conservation guarantee this is built on).
    """
    return raster_to_h3_tiled(
        tif_path,
        resolution=resolution,
        value_col=value_col,
        h3_col=h3_col,
        tile_resolution=tile_resolution,
        max_workers=max_workers,
    )


__all__ = ["worldpop_raster_to_h3"]
