"""Eurostat Census 2021 population grid, 1 km x 1 km, EU-27 + CH, LI, NO (resolution class ``high``)."""

from pycensus.census.countries.eu.census_grid import loader, schema
from pycensus.census.countries.eu.census_grid.loader import load, unallocated

__all__ = ["loader", "schema", "load", "unallocated"]
