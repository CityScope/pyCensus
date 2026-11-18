"""Spain election results (Congreso 2023, Municipales 2023, Parlamento Vasco 2024) by census section and H3."""
from .loader import load_congreso_2023, load_election, load_municipal_2023, load_parlamento_vasco_2024

__all__ = ["load_election", "load_congreso_2023", "load_municipal_2023", "load_parlamento_vasco_2024"]
