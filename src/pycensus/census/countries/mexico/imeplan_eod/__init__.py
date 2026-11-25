"""IMEPLAN Encuesta Origen-Destino 2023 (Guadalajara): main means of transport to work per AGEB of residence (see :mod:`.loader`)."""
from pycensus.accessors import register_source_accessor
from pycensus.census.countries.mexico.imeplan_eod.loader import LEVELS, SCHEMA, load, table

register_source_accessor(SCHEMA)

__all__ = ["load", "table", "SCHEMA", "LEVELS"]
