"""Resolve which vintage year(s) to fetch for a census source/level request.

Technical aspects:
    Per the schema redesign spec: "When doing a request on the census if no
    year specified then take the latest year for every source (latest year
    which provides the finest requested level). If a year is specified where
    the source is not available interpolate between two available years.
    year can be specified for the complete request or as a source:year
    dict."

    This module is pure logic -- it knows nothing about HTTP fetching. A
    loader (e.g. :mod:`pycensus.usa.acs5.loader`) calls
    :func:`resolve_year` (single source) or :func:`resolve_years_for_request`
    (multiple sources, from a plain year or a ``{source: year}`` dict), gets
    back a :class:`YearResolution` describing either one concrete year to
    fetch, or two bracketing years to fetch-and-blend via
    :func:`interpolate_frames`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Union

import polars as pl

YearRequest = Union[None, int, Dict[str, int]]


@dataclass(frozen=True)
class YearResolution:
    """How to satisfy one source's year request.

    Attributes:
        mode: ``"exact"`` if an available year matches directly (or was
            snapped to the nearest bound when the request fell outside the
            available range), ``"interpolate"`` if it must be linearly
            blended from two bracketing years.
        year: The concrete year to fetch when ``mode == "exact"``.
        year_low: Lower bracketing year when ``mode == "interpolate"``.
        year_high: Upper bracketing year when ``mode == "interpolate"``.
        target_year: The originally requested (or resolved-latest) year --
            equal to ``year`` when ``mode == "exact"``.
    """

    mode: str
    target_year: int
    year: Optional[int] = None
    year_low: Optional[int] = None
    year_high: Optional[int] = None


def _years_supporting_level(
    available_years: Sequence[int],
    level: Optional[str],
    min_year_by_level: Optional[Dict[str, int]],
) -> List[int]:
    """Filter ``available_years`` down to those that actually cover ``level``.

    A source's finest available geography can vary by year (e.g. Census
    ACS5 block-group tables were suppressed in early vintages), so picking
    "the latest year" without checking level support could silently return
    a year that has no data at the requested resolution.
    """
    years = sorted(set(available_years))
    if level is None or not min_year_by_level or level not in min_year_by_level:
        return years
    min_year = min_year_by_level[level]
    if min_year is None:
        # Level never supported by this source at any vintage.
        return []
    return [y for y in years if y >= min_year]


def resolve_year(
    requested_year: Optional[int],
    available_years: Sequence[int],
    level: Optional[str] = None,
    min_year_by_level: Optional[Dict[str, int]] = None,
) -> YearResolution:
    """Resolve a single source's year request to a concrete fetch plan.

    Args:
        requested_year: The year asked for, or ``None`` to mean "latest".
        available_years: All vintage years this source publishes at all
            (regardless of level).
        level: Geometry level being requested, used to further restrict
            ``available_years`` via ``min_year_by_level``.
        min_year_by_level: Per-level earliest year with data at that level,
            e.g. ``{"tract": 2009, "blockgroup": 2013, "block": None}``. A
            ``None`` value means the level is never available.

    Returns:
        A :class:`YearResolution` describing an exact year to fetch, or two
        bracketing years to interpolate between.

    Raises:
        ValueError: If no year supports the requested level at all.
    """
    years = _years_supporting_level(available_years, level, min_year_by_level)
    if not years:
        raise ValueError(
            f"No available year supports level={level!r} for this source "
            f"(available_years={sorted(set(available_years))}, "
            f"min_year_by_level={min_year_by_level})"
        )

    if requested_year is None:
        latest = max(years)
        return YearResolution(mode="exact", target_year=latest, year=latest)

    if requested_year in years:
        return YearResolution(mode="exact", target_year=requested_year, year=requested_year)

    lower = [y for y in years if y < requested_year]
    upper = [y for y in years if y > requested_year]

    if lower and upper:
        return YearResolution(
            mode="interpolate",
            target_year=requested_year,
            year_low=max(lower),
            year_high=min(upper),
        )

    # Requested year is outside the available range on one side -- nothing
    # to interpolate between, so snap to the nearest available year.
    nearest = min(years, key=lambda y: abs(y - requested_year))
    return YearResolution(mode="exact", target_year=requested_year, year=nearest)


def resolve_years_for_request(
    sources: Sequence[str],
    year: YearRequest,
    available_years_by_source: Dict[str, Sequence[int]],
    level: Optional[str] = None,
    min_year_by_level_by_source: Optional[Dict[str, Dict[str, int]]] = None,
) -> Dict[str, YearResolution]:
    """Resolve year requests for every source in one request.

    Args:
        sources: Source names being queried (e.g. ``["acs5", "dhc"]``).
        year: ``None`` (latest for every source), a single int (applied to
            every source), or a ``{source: year}`` dict (per-source,
            sources not present default to latest).
        available_years_by_source: Per-source available vintage years.
        level: Geometry level being requested.
        min_year_by_level_by_source: Per-source ``min_year_by_level`` dict,
            see :func:`resolve_year`.

    Returns:
        ``{source: YearResolution}`` for every source in ``sources``.
    """
    if isinstance(year, dict):
        per_source_year = {s: year.get(s) for s in sources}
    else:
        per_source_year = {s: year for s in sources}

    result = {}
    for source in sources:
        min_year_by_level = (
            min_year_by_level_by_source.get(source) if min_year_by_level_by_source else None
        )
        result[source] = resolve_year(
            per_source_year[source],
            available_years_by_source[source],
            level=level,
            min_year_by_level=min_year_by_level,
        )
    return result


def interpolate_frames(
    df_low: pl.DataFrame,
    year_low: int,
    df_high: pl.DataFrame,
    year_high: int,
    target_year: int,
    id_col: str,
    value_cols: Sequence[str],
) -> pl.DataFrame:
    """Linearly interpolate value columns between two years, per geography.

    Applied *after* both years have been fetched independently (each row
    already summed/joined into its final logical columns). For each
    geography id present in both frames, every value column is blended as
    ``low + (high - low) * t`` where
    ``t = (target_year - year_low) / (year_high - year_low)``. A geography
    present in only one frame (e.g. a tract that didn't exist yet, or was
    split/merged between vintages) is dropped -- there's nothing sound to
    interpolate it from.

    Args:
        df_low: Data fetched at ``year_low``.
        year_low: The earlier bracketing year.
        df_high: Data fetched at ``year_high``.
        year_high: The later bracketing year.
        target_year: The year actually requested (``year_low < target_year
            < year_high``).
        id_col: Geography id column present in both frames, joined on.
        value_cols: Numeric columns to interpolate. Columns not listed here
            (other than ``id_col``) are dropped from the result.

    Returns:
        One row per geography id present in both inputs, with each of
        ``value_cols`` linearly interpolated to ``target_year``.

    Raises:
        ValueError: If ``year_low``, ``target_year``, ``year_high`` aren't
            strictly increasing.
    """
    if not (year_low < target_year < year_high):
        raise ValueError(
            f"target_year ({target_year}) must lie strictly between "
            f"year_low ({year_low}) and year_high ({year_high})"
        )

    t = (target_year - year_low) / (year_high - year_low)

    low = df_low.select([id_col, *value_cols])
    high = df_high.select([id_col, *value_cols]).rename(
        {c: f"{c}__high" for c in value_cols}
    )
    joined = low.join(high, on=id_col, how="inner")

    exprs = [
        (
            pl.col(c).cast(pl.Float64, strict=False)
            + (pl.col(f"{c}__high").cast(pl.Float64, strict=False) - pl.col(c).cast(pl.Float64, strict=False))
            * t
        ).alias(c)
        for c in value_cols
    ]
    return joined.select([id_col, *exprs])
