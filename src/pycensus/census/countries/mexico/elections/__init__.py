# -*- coding: utf-8 -*-
"""Mexico election results (federal 2024 President, casilla level) for the Guadalajara metro, resampled to H3 res 8 and AGEB / manzana."""

from pycensus.census.countries.mexico.elections.loader import ELECTIONS, load, load_all

__all__ = ["ELECTIONS", "load", "load_all"]
