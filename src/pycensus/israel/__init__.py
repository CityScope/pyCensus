"""Israel census sources: common geography plumbing plus one submodule per source.

Technical aspects:
    This package holds the functions shared by every Israel source directly
    (``api``, ``constants``, ``geography``, ``utils``), and one subpackage per
    data source (``census2022``), each with its own :class:`~pycensus.schema.ColumnSchema`,
    fetch client, and loader that returns a GeoDataFrame ready for
    :meth:`geohierarchy.GeoHierarchy.add_level`.

Sources:
    - Census 2022 (Census of Population and Housing): 
      https://www.cbs.gov.il/en/subjects/pages/census-of-population-and-housing.aspx
"""

from . import api, census2022, constants, geography, utils

__all__ = ["api", "census2022", "constants", "geography", "utils"]
