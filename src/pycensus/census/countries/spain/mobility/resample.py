# -*- coding: utf-8 -*-
"""Zone -> census-section resampling for mobility survey results (modal split, trips, distance).

A mobility survey is published on its OWN zoning (traffic zones, districts, municipalities, comarcas ...). ``zones_to_sections`` moves the
zone values onto census sections: every section takes the population-weighted mean of the zones it overlaps, where each overlap piece
carries the section's population in proportion to its area (population spread evenly over the section). Intensive columns (shares, trips
per person, km per person) are averaged this way; extensive columns (trip counts, km) are split among sections by the same weights.
"""

from __future__ import annotations

from typing import Iterable, Optional

import geopandas as gpd
import numpy as np
import pandas as pd

AREA_CRS = 3035   # ETRS89-LAEA Europe: equal-area, fine for ratios anywhere in Spain


def zones_to_sections(
    zones: gpd.GeoDataFrame,
    sections: gpd.GeoDataFrame,
    intensive: Iterable[str] = (),
    extensive: Iterable[str] = (),
    zone_id: str = "zone_id",
    section_id: str = "CUSEC",
    pop_col: str = "population",
) -> pd.DataFrame:
    """Values per section (index ``section_id``) from zone values. Sections no zone reaches get NaN.

    Args:
        zones: Zones with values.
        sections: Census sections with population.
        intensive: Rate columns (population-weighted).
        extensive: Count columns (split by population).
        zone_id: Zone id column.
        section_id: Section id column.
        pop_col: Section population column.
    """
    intensive, extensive = list(intensive), list(extensive)
    z = zones[[zone_id, *intensive, *extensive, "geometry"]].to_crs(AREA_CRS).copy()
    s = sections[[section_id, pop_col, "geometry"]].to_crs(AREA_CRS).copy()
    z["geometry"] = z.geometry.make_valid().buffer(0)
    s["geometry"] = s.geometry.make_valid().buffer(0)
    s["_pop"] = pd.to_numeric(s[pop_col], errors="coerce").fillna(0.0)
    s["_area"] = s.geometry.area.replace(0, np.nan)
    pieces = gpd.overlay(s[[section_id, "_pop", "_area", "geometry"]], z, how="intersection", keep_geom_type=False)
    if pieces.empty:
        return pd.DataFrame(index=pd.Index(sections[section_id], name=section_id))
    frac_of_section = (pieces.geometry.area / pieces["_area"]).fillna(0.0)
    pieces["_w"] = pieces["_pop"] * frac_of_section
    # a section with no population falls back to area weights so it still gets a value
    zero = pieces.groupby(section_id)["_w"].transform("sum") <= 0
    pieces.loc[zero, "_w"] = frac_of_section[zero]
    out = {}
    wsum = pieces.groupby(section_id)["_w"].transform("sum").replace(0, np.nan)
    for c in intensive:
        out[c] = (pieces[c] * pieces["_w"] / wsum).groupby(pieces[section_id]).sum(min_count=1)
    if extensive:
        zone_w = pieces.groupby(zone_id)["_w"].transform("sum").replace(0, np.nan)
        for c in extensive:   # a zone's total is shared among its sections in proportion to their weight inside it
            out[c] = (pieces[c] * pieces["_w"] / zone_w).groupby(pieces[section_id]).sum(min_count=1)
    return pd.DataFrame(out).reindex(pd.Index(sections[section_id], name=section_id))
