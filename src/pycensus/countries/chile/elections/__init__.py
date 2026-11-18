# -*- coding: utf-8 -*-
"""Chile election results (2025 presidential runoff, mesa level) for Gran Concepcion, resampled to H3 res 8 and census manzana / zona."""

from .loader import ELECTIONS, load, load_all

__all__ = ["ELECTIONS", "load", "load_all"]
