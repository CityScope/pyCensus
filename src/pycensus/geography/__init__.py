"""Physical geography layers, besides ``census`` (people) and ``cadaster`` (buildings): what the ground is like.

Layout, one folder per topic, each with ``worldwide/`` (global sources) and ``countries/`` (a national source finer than the global one):

    geography/dem/           elevation models (GeoTIFF of an area): `pycensus.geography.dem.load(aoi, cache_dir)`          implemented
    geography/hydrography/   rivers, lakes, coast and flood-prone land (e.g. HydroRIVERS / HydroLAKES, national river networks)   prepared
    geography/geology/       geological maps: lithology, faults, soil (e.g. OneGeology, national geological surveys)              prepared

A topic is added the way the others are: a folder with ``worldwide/<source>/loader.py`` (``load(aoi, cache_dir, ...)``) and a ``load`` in the
topic's ``__init__`` that picks the source; sources of a country go in ``countries/<country>/<source>/``. The cache of every topic is
``<pycensus cache>/geography/<topic>``. None of these layers is census data: they are inputs of maps (3D terrain) and of analyses (the slope of
streets, flood and tsunami exposure).
"""
from __future__ import annotations

TOPICS = {"dem": "implemented", "hydrography": "prepared", "geology": "prepared"}
