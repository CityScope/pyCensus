# -*- coding: utf-8 -*-
"""Official (state election authority) precinct results -- the ONLY source of precinct-level votes in the US study.

``REGISTRY`` maps a state FIPS to a module whose ``load(cache_dir)`` returns precinct polygons (EPSG:4326) with ``county_fips``,
``votes_dem``, ``votes_rep``, ``votes_total`` and which defines ``ATTRIBUTION``. A state without an entry has NO precinct election data:
``load_state_precincts`` returns ``(None, "")`` -- compilations by newspapers or research groups (NYT, VEST, MEDSL) are not used.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

import geopandas as gpd

from pycensus.census.countries.usa.elections_precinct.official import ca, de, hi, nc

logger = logging.getLogger(__name__)

REGISTRY = {"06": ca, "10": de, "15": hi, "37": nc}


def load_state_precincts(state_fips: str, cache_dir: Optional[str] = None) -> Tuple[Optional[gpd.GeoDataFrame], str]:
    """(precincts, attribution) from the state's official loader; (None, "") when the state has none or the loader fails.

    Args:
        state_fips: 2-digit state FIPS.
        cache_dir: Cache folder; ``None`` = the pycensus cache.
    """
    mod = REGISTRY.get(str(state_fips).zfill(2))
    if mod is None:   # no official loader: the cross-validated unofficial source (MEDSL results + NYT polygons), only if it passes its own acceptance test
        try:
            from pycensus.census.countries.usa.elections_precinct.unofficial import nyt_medsl
            from pycensus.census.countries.usa.elections_precinct.nyt2024 import STATE_ABBR
            from pycensus.census.countries.usa.elections_precinct.unofficial import fec
            gdf = nyt_medsl.load(state_fips, cache_dir)
            if gdf is not None and len(gdf):
                gdf = fec.calibrate(gdf, STATE_ABBR[str(state_fips).zfill(2)])   # ValueError when MEDSL itself is >2% off the official total
            return (gdf, nyt_medsl.ATTRIBUTION) if gdf is not None and len(gdf) else (None, "")
        except Exception as exc:  # noqa: BLE001
            logger.warning("exact-count NYT+MEDSL join not used for %s: %s", state_fips, exc)
            if str(state_fips).zfill(2) == "02":   # Alaska: MEDSL election-day precincts + district-level ballots on Census voting districts
                try:
                    from pycensus.census.countries.usa.elections_precinct.unofficial import fec, medsl_alaska
                    gdf = fec.calibrate(medsl_alaska.load("02", cache_dir), "ak", max_dev=0.10)
                    return gdf, medsl_alaska.ATTRIBUTION
                except Exception as exc_ak:  # noqa: BLE001
                    logger.warning("Alaska MEDSL route failed: %s", exc_ak)
            try:   # official state precinct polygons + MEDSL votes (Oklahoma)
                from pycensus.census.countries.usa.elections_precinct.unofficial import medsl_boundaries
                gdf = medsl_boundaries.load(state_fips, cache_dir)
                return (gdf, medsl_boundaries.ATTRIBUTION[state_fips]) if gdf is not None and len(gdf) else (None, "")
            except Exception as exc1:  # noqa: BLE001
                logger.warning("official boundaries + MEDSL not used for %s: %s", state_fips, exc1)
            try:   # second unofficial route: NYT polygons with their own votes, if their county totals reproduce MEDSL's
                from pycensus.census.countries.usa.elections_precinct.unofficial import nyt_direct
                gdf = nyt_direct.load(state_fips, cache_dir)
                if gdf is None or not len(gdf):
                    return None, ""
                attribution = nyt_direct.ATTRIBUTION
                if "estimated" in gdf.columns:   # SD / VT: the uncovered precincts hold allocated, not counted, votes
                    from pycensus.census.countries.usa.elections_precinct.unofficial import vest_residual
                    attribution += " " + vest_residual.ATTRIBUTION_SUFFIX
                    gdf = gdf.drop(columns="estimated")
                from pycensus.census.countries.usa.elections_precinct.nyt2024 import STATE_ABBR
                from pycensus.census.countries.usa.elections_precinct.unofficial import fec
                gdf = fec.calibrate(gdf, STATE_ABBR[str(state_fips).zfill(2)])
                return gdf, attribution
            except Exception as exc2:  # noqa: BLE001
                logger.warning("unofficial source not used for %s: %s", state_fips, exc2)
                return None, ""
    try:
        gdf = mod.load(cache_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("official loader failed for %s: %s", state_fips, exc)
        return None, ""
    return (gdf, mod.ATTRIBUTION) if gdf is not None and len(gdf) else (None, "")
