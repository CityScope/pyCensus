"""Zensus 2022 100m x 100m population grid for Germany (Eurostat INSPIRE grid)."""

from pycensus.census.countries.germany.zensus_grid.loader import download_grid, load

__all__ = ["download_grid", "load"]
