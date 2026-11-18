"""Municipality-level INE tables: tourist dwellings (experimental VTE) and migration balance (EMCR)."""
from pycensus.census.countries.spain.ine_tables.loader import load_migration_balance, load_tourist_dwellings

__all__ = ["load_tourist_dwellings", "load_migration_balance"]
