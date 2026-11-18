"""Hamburg election results by Wahlbezirk (polling district) and H3 (Bundestag 2025, Buergerschaft 2025, Bezirksversammlungen 2024)."""
from pycensus.census.countries.germany.elections.loader import load_buergerschaft_2025, load_bundestag_2025, load_bezirksversammlung_2024, load_election

__all__ = ["load_election", "load_bundestag_2025", "load_buergerschaft_2025", "load_bezirksversammlung_2024"]
