"""Spatial resolution class of a census dataset: ``low``, ``normal`` or ``high``.

Every source (and geometry level of a source) carries one of three classes, so that callers can refuse data that are too
coarse for a use:

* ``low``: the finest unit is the municipality or something larger (LAU, NUTS, county, province, state, nation).
* ``normal``: municipal units only where municipalities (or counties) are small -- under 10,000 residents -- and
  sub-municipal units wherever they are larger.
* ``high``: ``normal`` and, in addition, every unit of the dataset with more than 5,000 residents covers 1 km2 or less.

Rules of use (user, 2026-11-17):

* regressions never use ``low`` datasets;
* the census tab of the maps uses only ``high`` datasets.

The class is computed from the data, never typed by hand: :func:`classify` takes the dataset's units (population +
geometry) and the municipalities of the same territory, and returns the class together with the units that broke the
rule, so an exception can be inspected rather than hidden.

Example:
    >>> from pycensus.resolution import classify
    >>> result = classify(units, municipalities)      # doctest: +SKIP
    >>> result.resolution, len(result.high_failures)  # doctest: +SKIP
    ('high', 0)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

LOW = "low"
NORMAL = "normal"
HIGH = "high"
ORDER = {LOW: 0, NORMAL: 1, HIGH: 2}

#: Municipalities (or counties) at or above this population must be split into sub-municipal units for ``normal``.
NORMAL_MUNICIPAL_POP = 10_000
#: Units above this population must cover at most :data:`HIGH_MAX_AREA_KM2` for ``high``.
HIGH_UNIT_POP = 5_000
HIGH_MAX_AREA_KM2 = 1.0
#: Equal-area projection used to measure areas everywhere (WGS 84 / NSIDC EASE-Grid 2.0 Global). A Eurostat 1 km cell
#: measures 1.000 km2 in it, as in ETRS89-LAEA; World Mollweide (ESRI:54009) gave 1.001 and is not used.
AREA_CRS = "EPSG:6933"
#: Relative tolerance on the 1 km2 limit, for vertex rounding after reprojection.
AREA_TOL = 0.005


@dataclass
class ResolutionResult:
    """Outcome of :func:`classify`.

    Attributes:
        resolution: ``"low"``, ``"normal"`` or ``"high"``.
        normal_failures: ids of municipalities with at least ``NORMAL_MUNICIPAL_POP`` residents that the dataset does not
            split (one unit covers most of the municipality).
        high_failures: ids of the dataset's units with more than ``HIGH_UNIT_POP`` residents and more than
            ``HIGH_MAX_AREA_KM2`` of area.
    """

    resolution: str
    normal_failures: List[str] = field(default_factory=list)
    high_failures: List[str] = field(default_factory=list)


def at_least(resolution: str, required: str) -> bool:
    """Whether ``resolution`` is at least ``required`` (``high`` >= ``normal`` >= ``low``).

    Args:
        resolution: The dataset's class.
        required: The minimum class a use accepts.

    Returns:
        True if the dataset may be used.
    """
    return ORDER[resolution] >= ORDER[required]


def usable_for(resolution: str, use: str) -> bool:
    """Apply the rules of use: ``"regression"`` needs ``normal`` or better, ``"census_tab"`` needs ``high``.

    Args:
        resolution: The dataset's class.
        use: ``"regression"`` or ``"census_tab"``.

    Returns:
        True if the dataset may be used for ``use``.

    Raises:
        ValueError: for an unknown use.
    """
    need = {"regression": NORMAL, "census_tab": HIGH}
    if use not in need:
        raise ValueError(f"unknown use {use!r}; expected one of {sorted(need)}")
    return at_least(resolution, need[use])


def classify(units, municipalities=None, pop_col: str = "population", id_col: str = "GEOID",
             muni_pop_col: str = "population", muni_id_col: str = "GEOID", is_municipal: Optional[bool] = None,
             cover_share: float = 0.9) -> ResolutionResult:
    """Classify a dataset's units as ``low``, ``normal`` or ``high``.

    Args:
        units: GeoDataFrame of the dataset's finest units, with a population column.
        municipalities: GeoDataFrame of the municipalities of the same territory, with their population. Needed for the
            ``normal`` test unless ``is_municipal`` settles it.
        pop_col: Population column of ``units``.
        id_col: Id column of ``units``.
        muni_pop_col: Population column of ``municipalities``.
        muni_id_col: Id column of ``municipalities``.
        is_municipal: ``True`` when the units are municipalities or larger (the class is then ``low`` without any
            geometric test); ``None`` to decide from the geometry.
        cover_share: a large municipality counts as "not split" when one unit covers at least this share of its area.

    Returns:
        :class:`ResolutionResult`.
    """
    if is_municipal:
        return ResolutionResult(LOW)
    if municipalities is None and is_municipal is None:
        raise ValueError("pass the municipalities of the territory (for the 'normal' test) or is_municipal=True/False")
    u = units.to_crs(AREA_CRS)
    area = u.geometry.area.to_numpy() / 1e6
    pop = np.nan_to_num(u[pop_col].to_numpy(dtype=float))
    high_fail = u.loc[(pop > HIGH_UNIT_POP) & (area > HIGH_MAX_AREA_KM2 * (1 + AREA_TOL)), id_col].astype(str).tolist()
    normal_fail: List[str] = []
    if municipalities is not None:
        import geopandas as gpd

        m = municipalities.to_crs(AREA_CRS)
        big = m[np.nan_to_num(m[muni_pop_col].to_numpy(dtype=float)) >= NORMAL_MUNICIPAL_POP]
        if len(big):
            inter = gpd.overlay(big[[muni_id_col, "geometry"]].rename(columns={muni_id_col: "_m"}),
                                u[[id_col, "geometry"]].rename(columns={id_col: "_u"}), how="intersection", keep_geom_type=True)
            inter["_a"] = inter.geometry.area
            share = inter.groupby("_m")["_a"].max() / big.set_index(muni_id_col).geometry.area.reindex(inter["_m"].unique())
            # a large municipality that one unit covers (or that is itself a unit) is not split: "normal" fails
            normal_fail = share[share >= cover_share].index.astype(str).tolist()
    if normal_fail:
        return ResolutionResult(LOW, normal_fail, high_fail)
    return ResolutionResult(HIGH if not high_fail else NORMAL, normal_fail, high_fail)


__all__ = ["LOW", "NORMAL", "HIGH", "NORMAL_MUNICIPAL_POP", "HIGH_UNIT_POP", "HIGH_MAX_AREA_KM2", "ResolutionResult",
           "at_least", "usable_for", "classify"]
