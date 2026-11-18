# -*- coding: utf-8 -*-
"""US precinct-level election results (Boston, San Francisco) resampled to H3 res 8 and census tracts/block groups."""

from .loader import ELECTIONS, load, load_all

__all__ = ["ELECTIONS", "load", "load_all"]
