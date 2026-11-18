"""Eurostat regional statistics (NUTS 2 / NUTS 3) from the keyless dissemination API (resolution class ``low``)."""

from . import api, loader, schema
from .loader import load, load_dataset, tables

__all__ = ["api", "loader", "schema", "load", "load_dataset", "tables"]
