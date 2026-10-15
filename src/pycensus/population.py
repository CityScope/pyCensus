"""One call to get population for any area: WorldPop (worldwide) or the national census.

    from pycensus import get_population

    people = get_population(aoi_gdf, source="worldpop")  # anywhere in the world
    people = get_population(aoi_gdf, source="census")    # the country's own census, if implemented

Both return a GeoDataFrame with a ``population`` column (count per feature), ready for
``GeoHierarchy.add_vector_data(people, ..., columns=["population"], agg=Sum(), geoweight_by="area")``.
"""

from __future__ import annotations

import os
from typing import Optional

import geopandas as gpd
import numpy as np

SOURCES = ("worldpop", "census")


def _census_spain(aoi: gpd.GeoDataFrame, year, folder) -> gpd.GeoDataFrame:
    from .countries.spain.ine import loader

    return loader.load(aoi=aoi, level="section", data_dir=folder)[["population", "geometry"]]


# ISO 3166-1 alpha-2 country code -> function(aoi, year, folder) returning a GeoDataFrame with
# ``population`` at the country's finest census level. Add a country here to enable it.
CENSUS_LOADERS = {
    "ES": _census_spain,  # INE census sections (secciones censales)
}


def census_countries() -> list[str]:
    """Country codes for which ``source="census"`` is implemented."""
    return sorted(CENSUS_LOADERS)


def _worldpop(aoi: gpd.GeoDataFrame, year: int, folder: Optional[str], kids_only: bool) -> gpd.GeoDataFrame:
    import rasterio
    import zipfile
    from rasterio.windows import from_bounds

    from .worldwide import worldpop

    kwargs = {"dataset": "age_structures", "subset": "U18"} if kids_only else {}
    path = worldpop.download_worldpop_population(aoi, year, folder=folder, resolution="100m", **kwargs)
    if path.endswith(".zip"):  # age-structure files come zipped
        out = os.path.splitext(path)[0]
        with zipfile.ZipFile(path) as z:
            z.extractall(out)
        path = next(os.path.join(out, f) for f in os.listdir(out) if f.lower().endswith(".tif") and "_T_" in f)

    # Files cover a whole country: read only the area, and drop "no data" pixels.
    with rasterio.open(path) as src:
        win = from_bounds(*aoi.to_crs(src.crs).total_bounds, transform=src.transform).round_offsets().round_lengths()
        values = src.read(1, window=win).astype("float64")
        transform = src.window_transform(win)
        crs = src.crs
        if src.nodata is not None:
            values[values == src.nodata] = np.nan
    rows, cols = np.nonzero(~np.isnan(values) & (values > 0))
    xs, ys = rasterio.transform.xy(transform, rows, cols)  # pixel centers
    return gpd.GeoDataFrame({"population": values[rows, cols]}, geometry=gpd.points_from_xy(xs, ys), crs=crs)


def get_population(
    aoi: gpd.GeoDataFrame,
    source: str = "worldpop",
    year: int = 2025,
    folder: Optional[str] = "population_data",
    kids_only: bool = False,
) -> gpd.GeoDataFrame:
    """Population of an area from WorldPop or from the national census.

    Args:
        aoi: Area of interest (any CRS).
        source: ``"worldpop"`` (100 m grid, anywhere in the world) or ``"census"``
            (official census polygons of the AOI's country; raises if that country
            is not implemented, see :func:`census_countries`).
        year: Year of the data. WorldPop only; the census uses its latest release.
        folder: Where raw downloads are kept.
        kids_only: Only people under 18. WorldPop only.

    Returns:
        GeoDataFrame with a ``population`` column: one point per WorldPop pixel, or one
        polygon per census unit.

    Raises:
        ValueError: Unknown ``source``.
        NotImplementedError: ``source="census"`` for a country without an implemented census,
            or ``kids_only`` with the census.
    """
    if source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}, got {source!r}")
    aoi = aoi.to_crs(4326)

    if source == "worldpop":
        return _worldpop(aoi, year, folder, kids_only)

    if kids_only:
        raise NotImplementedError("kids_only is only available with source='worldpop'.")
    from .worldwide.worldpop import get_country_region

    centroid = aoi.union_all().centroid
    country = get_country_region(centroid.y, centroid.x, get_region=False)
    if country not in CENSUS_LOADERS:
        raise NotImplementedError(
            f"No census implemented for country {country!r} (implemented: {census_countries()}). "
            "Use source='worldpop' instead."
        )
    return CENSUS_LOADERS[country](aoi, year, folder)
