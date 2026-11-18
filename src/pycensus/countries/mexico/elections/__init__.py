# -*- coding: utf-8 -*-
"""Mexico election results (federal 2024 President, casilla level) for the Guadalajara metro, resampled to H3 res 8 and AGEB / manzana."""

from .loader import ELECTIONS, load, load_all

__all__ = ["ELECTIONS", "load", "load_all"]
