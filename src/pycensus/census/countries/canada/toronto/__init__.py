"""City of Toronto Neighbourhood Profiles (2021 Census of Population) as a pycensus source: 158 neighbourhoods, ~330 characteristics."""
from pycensus.census.countries.canada.toronto.loader import load

__all__ = ["load"]
