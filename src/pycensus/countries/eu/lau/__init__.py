"""Eurostat GISCO LAU (municipalities) with population, EU-wide (resolution class ``low``)."""

from . import loader, schema
from .loader import load, vintage_by_country

__all__ = ["loader", "schema", "load", "vintage_by_country"]
