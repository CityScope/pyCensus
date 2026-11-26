"""Hydrography (rivers, lakes, coastline, flood-prone land): prepared, no source yet; see pycensus.geography.

Add a global source in ``worldwide/<source>/loader.py`` (candidates: HydroRIVERS and HydroLAKES, OpenStreetMap waterways) and a national one in
``countries/<country>/<source>/``, and give this module ``load(aoi, cache_dir, ...)`` returning a GeoDataFrame of lines or polygons with the
name, kind (river, canal, lake, sea) and, where the source has it, the flow or the water depth.
"""
