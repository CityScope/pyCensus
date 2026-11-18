"""EU-wide census sources from Eurostat and its geographic service GISCO (country code ``eu``).

Technical aspects:
    Shared plumbing lives here (``constants``, ``geography`` for NUTS 0-3 and LAU boundaries); each data source is a
    subpackage with its own schema JSON (``schema/<source>_schema.json``), :class:`~pycensus.schema.ColumnSchema` and
    loader returning a GeoDataFrame (EPSG:4326, ``GEOID``):

    * ``census_grid``: Census 2021 population grid, 1 km cells -- population, sex, broad age, employed persons, place
      of birth, residence one year before. Resolution class ``high``.
    * ``lau``: municipalities with population (latest GISCO vintage reported per country). Resolution class ``low``.
    * ``eurostat``: regional indicators at NUTS 2 / 3 (GDP, household income, unemployment, employment, poverty,
      education, cars, density). Resolution class ``low``.

    Every source is keyless. Raw files go to the shared pycensus cache under ``data/eu/raw/<source>``.

Example:
    >>> from pycensus.countries.eu import census_grid
    >>> cells = census_grid.load(aoi=madrid_boundary)        # doctest: +SKIP
"""

from . import census_grid, constants, eurostat, geography, lau

RESOLUTION = {"census_grid": census_grid.loader.RESOLUTION, "lau": lau.loader.RESOLUTION, "eurostat": eurostat.loader.RESOLUTION}

__all__ = ["census_grid", "constants", "eurostat", "geography", "lau", "RESOLUTION"]
