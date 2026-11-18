# -*- coding: utf-8 -*-
"""Toronto election results (federal 2025, Ontario 2025, municipal 2022) at poll level, resampled to H3 res 8 and 2021 dissemination areas."""

from .loader import ELECTIONS, load, load_all

__all__ = ["ELECTIONS", "load", "load_all"]
