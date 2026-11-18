"""U.S. Religion Census 2020 (ASARB): congregations and adherents per county, in total and by tradition."""
from pycensus.census.countries.usa.religion.loader import load_county_religion

__all__ = ["load_county_religion"]
