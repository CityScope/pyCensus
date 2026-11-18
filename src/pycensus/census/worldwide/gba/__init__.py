"""GlobalBuildingAtlas (GBA) global source: building footprints with heights, building metrics, and a population estimate from built floor area.

    from pycensus.census.worldwide import gba
    b = gba.fill_heights(gba.load_buildings(aoi, cache_dir))       # footprints + heights (+ built_m2)
    cells = gba.h3_metrics(b, 11)                                  # buildingHeightMax/Median, buildingFootprintArea, builtFloorArea, ...
    built, prof = gba.built_area_raster(b, worldpop_tif)           # built m2 on WorldPop's grid
    est, info = gba.built_surface_population(built, worldpop, prof, census=polys)
"""
from pycensus.census.worldwide.gba.loader import download_tiles, load_buildings, read_heights, tile_index, tile_name, tiles_for_bbox
from pycensus.census.worldwide.gba.metrics import METRIC_COLUMNS, built_area_raster, fill_heights, h3_metrics, polygon_metrics, zone_metrics
from pycensus.census.worldwide.gba.population import built_surface_population

__all__ = ["download_tiles", "load_buildings", "read_heights", "tile_index", "tile_name", "tiles_for_bbox", "METRIC_COLUMNS",
           "built_area_raster", "fill_heights", "h3_metrics", "polygon_metrics", "zone_metrics", "built_surface_population"]
