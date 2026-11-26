"""Geology (lithology, faults, soil type): prepared, no source yet; see pycensus.geography.

Add a global source in ``worldwide/<source>/loader.py`` (candidates: OneGeology, the Global Lithological Map, SoilGrids) and national geological
surveys in ``countries/<country>/<source>/``, and give this module ``load(aoi, cache_dir, ...)`` returning a GeoDataFrame of polygons (and fault
lines) with the unit's name, age and rock or soil class.
"""
