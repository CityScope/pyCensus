"""Andorra election results by parish (Consell General 2023, Comunals 2023) and H3."""
from pycensus.census.countries.andorra.elections.loader import load_comunals_2023, load_consell_general_2023, load_election

__all__ = ["load_election", "load_consell_general_2023", "load_comunals_2023"]
