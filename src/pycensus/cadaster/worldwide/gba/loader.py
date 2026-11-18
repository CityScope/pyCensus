"""GlobalBuildingAtlas buildings (pycensus.countries.worldwide.gba) mapped onto the unified cadaster schema."""
from __future__ import annotations

import geopandas as gpd

from ... import standardize


def load(aoi: gpd.GeoDataFrame, cache_dir=None) -> gpd.GeoDataFrame:
    """Global Building Atlas buildings (heights filled) inside ``aoi``, in the unified schema.

    Args:
        aoi: Area of interest (GeoDataFrame).
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        The buildings.
    """
    from ....countries.worldwide import gba

    b = gba.fill_heights(gba.load_buildings(aoi, cache_dir=cache_dir))
    b = b.rename(columns={"height": "height_m"})
    b["building_id"] = b["source"].astype(str) + ":" + b["id"].astype(str)
    b["built_area_m2"] = None    # standardize: footprint x max(height / 3, 1)
    return standardize(b.drop(columns=["source"]), "gba", "*")
