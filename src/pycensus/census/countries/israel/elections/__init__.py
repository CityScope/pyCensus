"""Israel election results (Central Elections Committee data republished on data.gov.il) -> H3 res 8 -> CBS statistical areas."""
from pycensus.census.countries.israel.elections.loader import ElectionResult, load_knesset, load_local_authorities

__all__ = ["ElectionResult", "load_knesset", "load_local_authorities"]
