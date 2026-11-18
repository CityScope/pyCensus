"""INE "Atlas de Distribución de Renta de los Hogares" (ADRH): income and demographic indicators per census section (Spain)."""
from pycensus.census.countries.spain.adrh.loader import load_attributes

__all__ = ["load_attributes"]
