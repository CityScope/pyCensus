"""VerBindungen project static working population (commuters), 1km x 1km grid, for Germany."""

from pycensus.census.countries.germany.verbindungen.loader import download_grid, load

__all__ = ["download_grid", "load"]
