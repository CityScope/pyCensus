# -*- coding: utf-8 -*-
"""US election results (MEDSL) -- see `loader`'s module docstring for exactly
what's implemented and why the rest is a documented gap."""

from pycensus.census.countries.usa.elections.loader import AVAILABLE, load
from pycensus.census.countries.usa.elections.schema import NATIVE_LEVELS, SCHEMA

__all__ = ["AVAILABLE", "load", "SCHEMA", "NATIVE_LEVELS"]
