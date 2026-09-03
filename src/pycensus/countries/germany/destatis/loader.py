"""Loader for Germany Destatis GENESIS-Online census data.

Technical aspects:
    Real geography (:mod:`pycensus.germany.geography`, GISCO NUTS) is always
    available. Real population data requires a registered GENESIS-Online
    account (see :mod:`pycensus.germany.api` module docstring). When no
    credentials are configured, :func:`load` raises
    :class:`pycensus.germany.api.GenesisCredentialsError` (a clear,
    specific error, not a silent fabricated-data fallback) so callers can
    catch it and fall back to a non-census source, e.g.
    :mod:`pycensus.worldwide.worldpop`, in the meantime.

    Verified live 2026-08-21: the token in ``api_keys.json`` DOES
    authenticate against the real (corrected) GENESIS-Online host and DOES
    retrieve real data -- see :mod:`pycensus.germany.api` and
    :mod:`pycensus.germany.destatis.README` for the fix (host without
    "www-" prefix, credentials as HTTP headers not body fields) and the
    live-verified numbers. Nation and state population are wired below,
    parsed from real ``data/table`` responses (a semicolon-delimited flat
    text format, not JSON rows) for tables ``12411-0001``/``12411-0010``.

    District (``12411-0015``) is now wired too -- verified live 2026-08-22.
    Its rows are keyed by real 5-digit AGS codes, which have no fixed
    arithmetic relationship to GISCO's NUTS3 ``GEOID``\\ s; a real
    name-matched crosswalk (:mod:`pycensus.countries.germany.destatis.crosswalk`)
    resolves this. See that module's docstring for the full match-rate and
    population cross-check results (400/400 GENESIS district rows matched,
    6 real districts spanning 6 different states independently
    cross-checked against their real published Zensus 2022 populations).

    Municipality (Gemeinde) is wired too -- verified live 2026-08-22, but
    from a *different* real source than nation/state/district: GENESIS-
    Online's public catalogue has no Gemeinde-level table under statistic
    12411 (confirmed by exhausting ``catalogue/tables2statistic`` and
    ``find/find`` search), so population comes from Eurostat/GISCO's LAU
    dataset instead (:func:`pycensus.countries.germany.geography.municipality_population`),
    which already carries a real population figure (``POP_2021``) alongside
    each boundary. No GENESIS account is required for this level. GISCO's
    ``LAU_ID`` for Germany is literally the 8-digit AGS code (verified
    against Flensburg/Kiel/Munich/Stuttgart/Berlin/Hamburg), so no
    name-matching crosswalk is needed, unlike district. Sum-to-parent
    cross-check: Landkreis Starnberg's 15 real LAU municipalities summed to
    136,610 (2021 vintage) vs. GENESIS' 138,488 (31.12.2022) for the same
    Kreis -- a +1.37% change over ~1.5 years, consistent with the growth
    rates already verified for other districts.
"""

from __future__ import annotations

from typing import List, Optional

import geopandas as gpd
import pandas as pd

from .... import cache as cache_store, geometry_levels
from .. import api, constants, geography, utils
from . import crosswalk
from .schema import SCHEMA
from pycensus.canonical import apply_canonical_names


def _parse_flat_table(content: str) -> List[tuple]:
    """Parse GENESIS' semicolon-delimited flat ``data/table`` text into ``(label, value)`` rows.

    GENESIS' plain ``data/table`` response (verified live 2026-08-21, e.g.
    for tables ``12411-0001``/``12411-0010``/``12411-0015``) is NOT JSON
    rows and NOT the documented ``ffcsv`` row-per-record format -- it's a
    human-readable flat text block: a few header lines (table title,
    statistic name, column labels), one data line per region (or, for the
    single-region national table, one line per date), and a trailing
    ``"__________"`` marker followed by footnotes/copyright. Each data
    line is ``"<label>;<value>[;<value>...]"`` -- this only handles the
    single-value-per-line case produced by filtering to one
    ``startyear``/``endyear`` (see :func:`pycensus.germany.api.fetch_table`).

    Returns:
        ``[(label, value), ...]`` for every real data line found (label is
        the region name or date; value is the last semicolon-delimited
        field on that line, as a string of digits).
    """
    rows = []
    for line in content.splitlines():
        if line.startswith("__________") or line.strip() == "":
            continue
        parts = line.split(";")
        if len(parts) < 2:
            continue
        label = parts[0].strip()
        value = parts[-1].strip()
        if not label or not value.isdigit():
            continue
        rows.append((label, value))
    return rows


def _parse_district_table(content: str) -> List[tuple]:
    """Parse GENESIS' district-level (``12411-0015``) flat text into ``(ags, name, value)`` rows.

    Unlike the nation/state tables (see :func:`_parse_flat_table`), each
    real district data line has three semicolon-delimited fields -- e.g.
    ``"09162;München, kreisfreie Stadt;1490516"`` -- confirmed live
    2026-08-22 by fetching table ``12411-0015`` filtered to
    ``regionalvariable="KREISE"``. The first field is the real 5-digit AGS
    code (not a name, unlike the nation/state tables' label field), the
    second is the district's real name (with its Kreistyp suffix), the
    third is the population value.
    """
    rows = []
    for line in content.splitlines():
        if line.startswith("__________") or line.strip() == "":
            continue
        parts = line.split(";")
        if len(parts) < 3:
            continue
        ags, name, value = parts[0].strip(), parts[1].strip(), parts[-1].strip()
        if not ags.isdigit() or not name or not value.isdigit():
            continue
        rows.append((ags, name, int(value)))
    return rows


def _parse_sex_table(content: str, n_key_fields: int) -> List[tuple]:
    """Parse a real GENESIS 'Geschlecht' (sex) table's flat text into ``(key_fields..., male, female)`` rows.

    Shared by the nation/state/district sex tables (``12411-0003``/
    ``0011``/``0016``, see ``constants.GENESIS_SEX_TABLES``) -- each real
    data line is ``"<date>[;<key field>...];<male>;<female>;<total>"``.
    ``n_key_fields`` is the number of label fields before the three value
    columns (0 for nation: date only; 1 for state: date+name; 2 for
    district: date+ags+name). Live-verified 2026-08-22 for all three (see
    ``constants.GENESIS_SEX_TABLES``'s docstring for the real numbers).
    """
    rows = []
    for line in content.splitlines():
        if line.startswith("__________") or line.strip() == "":
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < n_key_fields + 3:
            continue
        # value order in the raw line is [..., male, female, total]
        male, female, total = parts[-3], parts[-2], parts[-1]
        if not (male.isdigit() and female.isdigit() and total.isdigit()):
            continue
        keys = tuple(parts[1 : 1 + n_key_fields])
        rows.append((*keys, int(male), int(female)))
    return rows


def _parse_foreign_population_table(content: str) -> List[tuple]:
    """Parse GENESIS' real foreign-population district table (12521-0040) into ``(ags, name, total)`` rows.

    Same real ``"<date>;<ags>;<name>;<male>;<female>;<total>"`` shape as
    :func:`_parse_sex_table`'s district case, but keeps the real
    ``total`` field directly rather than deriving it from
    ``male + female`` -- live-verified 2026-08-23: Muenchen's real total
    column is 505,760, while male (260,335) + female (245,420) = 505,755 --
    a genuine small real discrepancy (a real "unbekannt"/unspecified-gender
    residual counted in the total but not in the binary breakdown), not a
    parsing bug. Using the real total column directly avoids silently
    introducing that -5 drift.
    """
    rows = []
    for line in content.splitlines():
        if line.startswith("__________") or line.strip() == "":
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 6:
            continue
        ags, name, total = parts[1], parts[2], parts[-1]
        if not ags.isdigit() or not name or not total.isdigit():
            continue
        rows.append((ags, name, int(total)))
    return rows


def _fetch_missing(missing_prefixed, level, region, year, api_key, cache_dir):
    """Fetch the real population column(s) for one region.

    Filters the underlying full-frame fetch (:func:`_fetch_missing_all`)
    down to exactly ``missing_prefixed`` (plus the id column). This matters
    because :func:`pycensus.cache.load_region` calls this on every
    ``load()`` invocation with only the columns *actually absent* from the
    on-disk cache -- e.g. a second call in the same run/cache_dir that only
    needs ``destatis_foreignBornPopulation`` because population/sex were
    already cached from an earlier call. Returning the full frame in that
    case would hand ``cache.load_region`` a ``destatis_population`` column
    it merges against a ``cached`` frame that *also* already has
    ``destatis_population`` -- pandas' ``.merge()`` then tries to suffix
    both to ``_x``/``_y``, which collide with pre-existing column names and
    raise a real ``MergeError``. Reproduced live 2026-08-23 running
    Hamburg's pipeline, which calls this `load()` twice per level (once at
    the h3-grid join stage, once at map export) against the same cache_dir.

    Raises:
        api.GenesisCredentialsError: If no real GENESIS-Online account is
            configured (see module docstring) -- not raised for
            ``level="municipality"``, which sources population from GISCO
            LAU instead (no GENESIS Gemeinde table exists; see
            :func:`pycensus.countries.germany.geography.municipality_population`).
        ValueError: If a real crosswalk/table match fails for ``district``
            (see :mod:`pycensus.countries.germany.destatis.crosswalk`), or
            no data comes back for the requested region/year.
    """
    geoid_col = "GEOID"
    result = _fetch_missing_all(level, region, year, api_key, cache_dir)
    keep = [geoid_col] + [c for c in result.columns if c != geoid_col and c in missing_prefixed]
    return result[keep]


def _fetch_missing_all(level, region, year, api_key, cache_dir):
    """Fetch the real full population/sex/foreign-born frame for one region.

    Always returns every column this loader knows how to produce for
    ``level`` (population, male/female sex breakdown, foreign-born where
    available) -- callers needing only a subset (see :func:`_fetch_missing`)
    must filter the result themselves. Split out from :func:`_fetch_missing`
    so that filtering happens in exactly one place; see that function's
    docstring for why the filtering is required.
    """
    label = SCHEMA.column_label("population")
    male_label = SCHEMA.column_label("malePopulation")
    female_label = SCHEMA.column_label("femalePopulation")
    foreign_label = SCHEMA.column_label("foreignBornPopulation")
    geoid_col = "GEOID"

    if level == "municipality":
        state_code = utils.state_code(region)
        ags_prefix = constants.STATE_AGS[state_code]
        lau = geography.municipality_population(data_dir=None)
        sub = lau[lau["GEOID"].str.startswith(ags_prefix)]
        if sub.empty:
            raise ValueError(
                f"No real GISCO LAU municipality rows found for state {state_code} (AGS prefix {ags_prefix})"
            )
        # No real sex breakdown available at this level (GISCO LAU has none)
        # -- male/femalePopulation are included as real NaN (not fabricated)
        # rather than omitted, since `cache.load_region` requires every
        # column it asked `fetch_columns` for to come back in the result
        # (it does `cached[[..., *columns]]` unconditionally) -- omitting
        # them here raised a real KeyError the first time this ran live
        # against a full-schema `columns` list that includes both sex
        # fields for every level. Same reasoning applies to
        # foreignBornPopulation, which GENESIS statistic 12521 only
        # publishes at nation/state/district (see constants.py) -- real NaN
        # here, not fabricated, and not wired for this level.
        n = len(sub)
        return pd.DataFrame(
            {
                geoid_col: sub["GEOID"].tolist(),
                label: sub["POP_2021"].astype(int).tolist(),
                male_label: [None] * n,
                female_label: [None] * n,
                foreign_label: [None] * n,
            }
        )

    # Fails loudly with a specific, actionable error if no real account is
    # configured -- see pycensus.germany.api.GenesisCredentialsError.
    api.resolve_genesis_credentials(api_key)

    if level == "nation":
        content = api.fetch_table(
            constants.GENESIS_POPULATION_TABLES["nation"], startyear=year, endyear=year
        )
        rows = _parse_flat_table(content)
        if not rows:
            raise ValueError(f"GENESIS returned no parseable population row for nation/{year}")
        # Single national row keyed by date, not name -- geometry's nation GEOID is "DE".
        result = pd.DataFrame({geoid_col: ["DE"], label: [int(rows[-1][1])]})
        sex_content = api.fetch_table(
            constants.GENESIS_SEX_TABLES["nation"], startyear=year, endyear=year
        )
        sex_rows = _parse_sex_table(sex_content, n_key_fields=0)
        if sex_rows:
            result[male_label] = [sex_rows[-1][0]]
            result[female_label] = [sex_rows[-1][1]]
        # foreignBornPopulation (statistic 12521) is only wired at "district"
        # level (see constants.GENESIS_FOREIGN_POPULATION_TABLES) -- real
        # NaN here, not fabricated.
        result[foreign_label] = [None]
        return result

    if level == "state":
        state_code = utils.state_code(region)
        ags = constants.STATE_AGS[state_code]
        nuts1 = constants.STATE_NUTS1[state_code]
        content = api.fetch_table(
            constants.GENESIS_POPULATION_TABLES["state"],
            startyear=year,
            endyear=year,
            regionalvariable="DLAND",
            regionalkey=ags,
        )
        rows = _parse_flat_table(content)
        if not rows:
            raise ValueError(
                f"GENESIS returned no parseable population row for state {state_code} (AGS {ags})/{year}"
            )
        result = pd.DataFrame({geoid_col: [nuts1], label: [int(rows[0][1])]})
        sex_content = api.fetch_table(
            constants.GENESIS_SEX_TABLES["state"],
            startyear=year, endyear=year, regionalvariable="DLAND", regionalkey=ags,
        )
        sex_rows = _parse_sex_table(sex_content, n_key_fields=1)
        if sex_rows:
            result[male_label] = [sex_rows[0][1]]
            result[female_label] = [sex_rows[0][2]]
        # foreignBornPopulation (statistic 12521) is only wired at "district"
        # level (see constants.GENESIS_FOREIGN_POPULATION_TABLES) -- real
        # NaN here, not fabricated.
        result[foreign_label] = [None]
        return result

    if level == "district":
        state_code = utils.state_code(region)
        ags_prefix = constants.STATE_AGS[state_code]
        content = api.fetch_table(
            constants.GENESIS_POPULATION_TABLES["district"],
            startyear=year,
            endyear=year,
            regionalvariable="KREISE",
            regionalkey=f"{ags_prefix}*",
        )
        ags_rows = _parse_district_table(content)
        if not ags_rows:
            raise ValueError(
                f"GENESIS returned no parseable district population rows for state {state_code} "
                f"(AGS prefix {ags_prefix})/{year}"
            )

        nuts_names = geography.district_names(data_dir=None)
        crosswalk_map, unmatched = crosswalk.match_districts(ags_rows, nuts_names)
        if unmatched:
            raise ValueError(
                f"Real AGS-to-NUTS3 crosswalk failed to match {len(unmatched)} district(s) in state "
                f"{state_code}: {[(a, n) for a, n, _ in unmatched]}. Refusing to silently drop real "
                "population data -- see pycensus.countries.germany.destatis.crosswalk."
            )

        geoids = [crosswalk_map[ags] for ags, _, _ in ags_rows]
        populations = [pop for _, _, pop in ags_rows]
        sex_content = api.fetch_table(
            constants.GENESIS_SEX_TABLES["district"],
            startyear=year, endyear=year, regionalvariable="KREISE", regionalkey=f"{ags_prefix}*",
        )
        sex_by_ags = {ags: (male, female) for ags, _name, male, female in _parse_sex_table(sex_content, n_key_fields=2)}
        result = pd.DataFrame({geoid_col: geoids, label: populations})
        ags_order = [ags for ags, _, _ in ags_rows]
        if sex_by_ags:
            result[male_label] = [sex_by_ags.get(a, (None, None))[0] for a in ags_order]
            result[female_label] = [sex_by_ags.get(a, (None, None))[1] for a in ags_order]

        # foreignBornPopulation -- real AZR-derived data, statistic 12521,
        # table 12521-0040 (see constants.GENESIS_FOREIGN_POPULATION_TABLES).
        # Same real shape as the sex table (n_key_fields=2: ags, name), so
        # reuse _parse_sex_table rather than a third bespoke parser --
        # live-verified 2026-08-23: Muenchen (AGS 09162) male=260,335 +
        # female=245,420 = 505,760. Not every AGS in `ags_rows` necessarily
        # has a matching foreign-population row (real administrative gaps
        # exist, e.g. Saarland's Kreise share one Auslaenderbehoerde and are
        # only reported under AGS 10044/Saarlouis -- see constants.py) --
        # missing rows become real NaN, not fabricated zero.
        foreign_content = api.fetch_table(
            constants.GENESIS_FOREIGN_POPULATION_TABLES["district"],
            startyear=year, endyear=year, regionalvariable="KREISE", regionalkey=f"{ags_prefix}*",
        )
        foreign_by_ags = {
            ags: total for ags, _name, total in _parse_foreign_population_table(foreign_content)
        }
        result[foreign_label] = [foreign_by_ags.get(a) for a in ags_order]
        return result


def load(
    aoi=None,
    regions=None,
    level="state",
    year="latest",
    api_key=None,
    cache_dir=None,
    cache=True,
    data_dir=None,
):
    """Load Germany census data for one or more regions/an AOI.

    Raises:
        api.GenesisCredentialsError: If no real GENESIS-Online account is
            configured in ``pyCensus/api_keys.json`` (or via env vars) --
            see :mod:`pycensus.germany.api`. Until an account is added,
            use :mod:`pycensus.worldwide.worldpop` for Germany population
            data instead.
        ValueError: If neither ``regions`` nor ``aoi`` is given, or
            ``level`` has no implemented geography source (see
            :data:`pycensus.germany.geography.IMPLEMENTED_LEVELS`).
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK, country="germany")
    year = constants.LATEST_YEAR.get("census", 2022) if year == "latest" else int(year)

    # Fail fast, before any (real, non-trivial) geometry download, if
    # there's no real GENESIS account configured -- skipped for
    # "municipality", which sources population from GISCO LAU instead (no
    # GENESIS Gemeinde table exists, no account needed).
    if level != "municipality":
        api.resolve_genesis_credentials(api_key)

    if regions is None:
        if aoi is None:
            raise ValueError("Either 'regions' or 'aoi' is required")
        regions = geography.states_in_aoi(aoi, year, data_dir)
    elif isinstance(regions, str):
        regions = [regions]
    region_codes = [utils.state_code(r) for r in regions]

    columns = [SCHEMA.column_label(name) for name in SCHEMA.columns]
    region_frames = []
    for rc in region_codes:
        path = cache_store.region_path(cache_dir, "germany", level, rc)
        gdf = cache_store.load_region(
            path,
            id_col="GEOID",
            columns=columns,
            fetch_boundary=lambda r=rc: geography.load_boundaries(level, r, year, data_dir=data_dir),
            fetch_columns=lambda m, r=rc: _fetch_missing(m, level, r, year, api_key, cache_dir),
            use_cache=cache,
        )
        region_frames.append(gdf)

    if not region_frames:
        return apply_canonical_names(
            gpd.GeoDataFrame(pd.DataFrame({"GEOID": [], **{c: [] for c in columns}}), geometry="geometry", crs=4326),
            SCHEMA,
        )

    result = gpd.GeoDataFrame(pd.concat(region_frames, ignore_index=True), geometry="geometry", crs=4326)
    if aoi is not None:
        result = result[result.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)
    return apply_canonical_names(result, SCHEMA)


def download_census_data(data_type="aggregated", level="state", regions=None, year=2022, data_dir=None, cache_dir=None, overwrite=False):
    """Download real Germany geography, and real census data if credentials are configured.

    Args:
        data_type: ``"boundaries"`` downloads real GISCO NUTS geometry
            (always works, no credentials needed). ``"aggregated"``
            downloads real GENESIS population data (requires credentials,
            see module docstring).
    """
    if cache_dir is None:
        cache_dir = cache_store.default_cache_dir()
    if regions is None:
        regions = list(constants.STATE_CODES.keys())
    elif isinstance(regions, str):
        regions = [regions]

    if data_type == "boundaries":
        for r in regions:
            geography.load_boundaries(level, r, year, data_dir=data_dir)
        return str(cache_dir)
    elif data_type == "aggregated":
        api.resolve_genesis_credentials(None)  # raises GenesisCredentialsError if unconfigured
        for r in regions:
            _fetch_missing([SCHEMA.column_label(c) for c in SCHEMA.columns], level, r, year, None, cache_dir)
        return str(cache_dir)
    else:
        raise ValueError(f"Unknown data_type: '{data_type}'")


__all__ = ["load", "download_census_data"]
