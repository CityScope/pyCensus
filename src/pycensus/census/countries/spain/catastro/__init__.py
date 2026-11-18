"""Catastro (state INSPIRE Buildings + the foral cadastres of Gipuzkoa, Araba and Navarra) aggregated to census sections."""
from pycensus.census.countries.spain.catastro.loader import FEATURES, load_attributes, source_of_province

__all__ = ["FEATURES", "load_attributes", "source_of_province"]
