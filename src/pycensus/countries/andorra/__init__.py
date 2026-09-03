"""Andorra census sources: common geography plumbing plus one submodule per source.

Technical aspects:
    This package holds the functions shared by every Andorra source
    directly (``api``, ``constants``, ``geography``), and one subpackage
    per data source (``estadisticaad``), each with its own
    :class:`~pycensus.schema.ColumnSchema`, fetch client, and loader that
    returns a GeoDataFrame ready for :meth:`geohierarchy.GeoHierarchy.add_level`.

    Andorra's Departament d'Estadistica (https://www.estadistica.ad/) has no
    documented public API for its human-facing dataset browser, but that
    browser is itself built on Esri ArcGIS Hub -- and its underlying ArcGIS
    Server exposes real, keyless, queryable FeatureServer layers, verified
    live 2026-08-20: a real parish (comu) boundary layer, and (via a
    separate but linked government host, sig.govern.ad) a real
    population-by-locality-by-year table. See
    :mod:`pycensus.andorra.api`, :mod:`pycensus.andorra.geography`, and
    :mod:`pycensus.andorra.estadisticaad.loader` module docstrings for the
    exact URLs and verification detail.

Sources:
    - Departament d'Estadistica (estadisticaad): parish boundaries +
      population by locality/year.
"""

from . import api, constants, estadisticaad, geography

__all__ = ["api", "constants", "estadisticaad", "geography"]
