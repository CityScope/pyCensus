"""Eurostat GISCO LAU (municipalities) with population, EU-wide (resolution class ``low``)."""

from pycensus.census.countries.eu.lau import loader, schema
from pycensus.census.countries.eu.lau.loader import load, vintage_by_country

__all__ = ["loader", "schema", "load", "vintage_by_country"]
