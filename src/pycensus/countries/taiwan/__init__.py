"""Taiwan census sources: common geography plumbing plus one submodule per source.

Technical aspects:
    This package holds the functions shared by every Taiwan source directly
    (``api``, ``constants``, ``geography``, ``utils``), and one subpackage
    per data source (``moi``), each with its own
    :class:`~pycensus.schema.ColumnSchema`, fetch client, and loader that
    returns a GeoDataFrame ready for :meth:`geohierarchy.GeoHierarchy.add_level`.

    Boundary geometry is not implemented for any level yet -- see
    :mod:`pycensus.taiwan.geography` module docstring for what was tried
    and why it's blocked. Population data (:mod:`pycensus.taiwan.moi`) is
    real and verified independently of geometry.

Sources:
    - MOI RIS (內政部戶政司, Department of Household Registration):
      https://www.ris.gov.tw/
"""

from . import api, constants, geography, utils
from . import moi

__all__ = ["api", "constants", "geography", "utils", "moi"]
