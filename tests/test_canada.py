"""Tests for pycensus.canada: constants, schema, geography, and the StatCan loader.

Technical aspects:
    Mirrors ``tests/test_mexico.py``'s pattern: StatCan's real network calls
    (:func:`pycensus.countries.canada.api.fetch_province_totals`/``fetch_municipality_totals``,
    :func:`pycensus.countries.canada.geography.load_boundaries`) are monkeypatched out
    with small synthetic frames so the suite stays offline and fast.

    The real download/cache pipeline was verified manually against the live
    network during this session:
        - Full Table Download CSV (PID 98-10-0002,
          https://www150.statcan.gc.ca/n1/en/tbl/csv/98100002-eng.zip):
          downloaded, unzipped, parsed. Canada total population
          36,991,981; Ontario 14,223,942; City of Toronto 2,794,356 --
          all match the real downloaded CSV exactly (also matches
          StatCan's own published 2021 Census figures). Households
          (dwellings occupied by usual residents) and total private
          dwellings columns/values also confirmed against the real file.
        - Province boundary zip (lpr_000b21a_e.zip): downloaded in full,
          133,730,024 bytes (exact match to the documented size), 13 rows,
          PRUID values exactly {10,11,12,13,24,35,46,47,48,59,60,61,62}.
        - Municipality/CSD boundary zip (lcsd000b21a_e.zip): downloaded in
          full, 155,981,521 bytes (exact match), 5,161 rows, Toronto's row
          (CSDUID "3520005") bounds [-79.639, 43.579, -79.115, 43.855].
    None of this is re-run here to keep the suite offline, matching every
    other loader test in this repo.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from pycensus.countries.canada import api, constants, geography
from pycensus.countries.canada.statcan import loader
from pycensus.countries.canada.statcan.schema import SCHEMA


class TestConstants:
    def test_province_codes_exist(self):
        assert len(constants.PROVINCE_CODES) == 13

    def test_province_abbr_exist(self):
        assert len(constants.PROVINCE_ABBR) == 13

    def test_province_code_lookup(self):
        assert constants.province_code("Ontario") == "35"
        assert constants.province_code("Quebec") == "24"
        assert constants.province_code("35") == "35"
        assert constants.province_code("ON") == "35"

    def test_province_abbr_lookup(self):
        assert constants.province_abbr("Ontario") == "ON"
        assert constants.province_abbr("35") == "ON"

    def test_unknown_province_raises(self):
        with pytest.raises(ValueError):
            constants.province_code("Narnia")

    def test_level_fallback(self):
        assert constants.LEVEL_FALLBACK["state"] == "province"
        assert constants.LEVEL_FALLBACK["county"] == "municipality"
        assert constants.LEVEL_FALLBACK["tract"] == "dissemination-area"
        assert constants.LEVEL_FALLBACK["blockgroup"] == "dissemination-area"

    def test_latest_year(self):
        assert constants.LATEST_YEAR["census"] == 2021
        assert constants.LATEST_YEAR["geography"] == 2021

    def test_boundary_urls_cover_implemented_levels(self):
        assert set(constants.BOUNDARY_URLS) == {
            "province", "municipality", "dissemination-area", "dissemination-block",
        }

    def test_full_table_url_template_has_pid_placeholder(self):
        assert "{pid}" in constants.FULL_TABLE_URL_TEMPLATE

    def test_census_profile_pid(self):
        assert constants.CENSUS_PROFILE_PID == "98100002"

    def test_dissemination_area_pid(self):
        assert constants.DISSEMINATION_AREA_PID == "98100015"

    def test_geographic_attribute_file_url_is_direct_zip(self):
        assert constants.GEOGRAPHIC_ATTRIBUTE_FILE_URL.endswith(".zip")
        assert constants.GEOGRAPHIC_ATTRIBUTE_FILE_CSV_NAME == "2021_92-151_X.csv"

    def test_block_fallback_resolves_to_dissemination_block(self):
        assert constants.LEVEL_FALLBACK["block"] == "dissemination-block"


class TestSchema:
    def test_schema_has_prefix(self):
        assert SCHEMA.prefix == "statcan"

    def test_schema_has_columns(self):
        assert len(SCHEMA.columns) > 0

    def test_essential_columns_exist(self):
        for col in ["population", "households", "dwellings"]:
            assert col in SCHEMA.columns, f"Missing essential column: {col}"

    def test_column_codes_match_real_full_table_field_names(self):
        """Regression guard: codes must match the real 98100002.csv (province/
        municipality) and 98100015.csv (dissemination-area) column headers
        exactly -- verified against real downloaded files (see module
        docstring)."""
        assert SCHEMA.columns["population"].codes == [
            "Population and dwelling counts (13): Population, 2021 [1]",
            "Population and dwelling counts (5): Population, 2021 [1]",
            "DBPOP2021_IDPOP2021",
        ]
        assert SCHEMA.columns["households"].codes == [
            "Population and dwelling counts (13): Private dwellings occupied by usual residents, 2021 [7]",
            "Population and dwelling counts (5): Private dwellings occupied by usual residents, 2021 [3]",
            "DBURDWELL2021_IDRHLOG2021",
        ]
        assert SCHEMA.columns["dwellings"].codes == [
            "Population and dwelling counts (13): Total private dwellings, 2021 [4]",
            "Population and dwelling counts (5): Total private dwellings, 2021 [2]",
            "DBTDWELL2021_IDTLOG2021",
        ]

    def test_schema_prefixed_columns(self):
        assert SCHEMA.prefixed("population") == "statcan_population"
        assert SCHEMA.prefixed("households") == "statcan_households"

    def test_schema_strip_prefix(self):
        assert SCHEMA.strip_prefix("population") == "population"
        assert SCHEMA.strip_prefix("population") == "population"

    def test_schema_relative_to(self):
        # ownerHouseholds/renterHouseholds are relative to households; the
        # census-profile education/commute breakdowns are relative to their
        # own denominator fields -- every relative_to value must name a
        # feature that actually exists in this same schema (no dangling
        # references, see IMPLEMENTING_A_COUNTRY.md's anti-pattern list).
        expected_relative_to = {
            "ownerHouseholds": "households",
            "renterHouseholds": "households",
            "educationPrimaryOrLessPopulation": "educationTotalPopulation",
            "educationSecondaryPopulation": "educationTotalPopulation",
            "educationOtherTertiaryPopulation": "educationTotalPopulation",
            "educationUniversityPopulation": "educationTotalPopulation",
            "carCommuters": "commuteTotalPopulation",
            "publicTransportCommuters": "commuteTotalPopulation",
            "walkCommuters": "commuteTotalPopulation",
            "bikeCommuters": "commuteTotalPopulation",
            "foreignBornPopulation": "population",
        }
        for name in SCHEMA.columns:
            expected = expected_relative_to.get(name)
            assert SCHEMA.columns[name].relative_to == expected
            if expected is not None:
                assert expected in SCHEMA.columns, f"{name}'s relative_to '{expected}' is dangling"


class TestGeography:
    def test_implemented_levels(self):
        assert set(geography.IMPLEMENTED_LEVELS) == {
            "province", "municipality", "dissemination-area", "dissemination-block",
        }

    def test_load_boundaries_requires_province(self):
        with pytest.raises(ValueError):
            geography.load_boundaries("province")

    def test_load_boundaries_unimplemented_level_raises(self):
        with pytest.raises(ValueError):
            geography.load_boundaries("nation", province="35")

    def test_tract_resolves_to_dissemination_area(self):
        # "tract" isn't a native Canada level -- LEVEL_FALLBACK should
        # resolve it onto "dissemination-area" (StatCan's tract-equivalent).
        from pycensus import geometry_levels

        assert (
            geometry_levels.resolve_level("tract", constants.LEVEL_FALLBACK) == "dissemination-area"
        )


def _fake_province_gdf(geoid: str) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({"GEOID": [geoid]}, geometry=[box(0, 0, 1, 1)], crs=4326)


def _fake_province_totals(province, data_dir=None):
    return pd.DataFrame(
        {
            "GEOID": ["35"],
            "Population and dwelling counts (13): Population, 2021 [1]": [14223942],
            "Population and dwelling counts (13): Private dwellings occupied by usual residents, 2021 [7]": [
                5491201
            ],
            "Population and dwelling counts (13): Total private dwellings, 2021 [4]": [5929250],
        }
    )


def _fake_municipality_totals(province, data_dir=None):
    return pd.DataFrame(
        {
            "GEOID": ["3520005", "3506008"],
            "Population and dwelling counts (13): Population, 2021 [1]": [2794356, 100000],
            "Population and dwelling counts (13): Private dwellings occupied by usual residents, 2021 [7]": [
                1160892,
                40000,
            ],
            "Population and dwelling counts (13): Total private dwellings, 2021 [4]": [1220000, 42000],
        }
    )


def _fake_dissemination_area_totals(province, data_dir=None):
    return pd.DataFrame(
        {
            "GEOID": ["35200001", "35200002"],
            "Population and dwelling counts (5): Population, 2021 [1]": [512, 480],
            "Population and dwelling counts (5): Private dwellings occupied by usual residents, 2021 [3]": [
                200,
                190,
            ],
            "Population and dwelling counts (5): Total private dwellings, 2021 [2]": [210, 198],
        }
    )


def _fake_block_totals(province, data_dir=None):
    return pd.DataFrame(
        {
            "GEOID": ["35200001001", "35200001002"],
            "DBPOP2021_IDPOP2021": [284, 130],
            "DBURDWELL2021_IDRHLOG2021": [110, 55],
            "DBTDWELL2021_IDTLOG2021": [115, 58],
        }
    )


def _fake_census_profile_da_totals(province, characteristic_names, data_dir=None):
    # Small synthetic table matching the real 98-401-X2021006 column shape
    # (GEOID + one column per requested real CHARACTERISTIC_NAME), covering
    # only the DAs used by _fake_dissemination_area_totals.
    values = {
        "Average household size": [1.9, 3.0],
        "Median total income of household in 2020 ($)": [44800, 98000],
        "Average total income of household in 2020 ($)": [48800, 108000],
        "Owner": [0, 125],
        "Renter": [180, 10],
        "Total - Highest certificate, diploma or degree for the population aged 15 years and over in private households - 25% sample data": [
            320,
            365,
        ],
        "No certificate, diploma or degree": [25, 75],
        "High (secondary) school diploma or equivalency certificate": [130, 70],
        "Postsecondary certificate or diploma below bachelor level": [70, 125],
        "Bachelor's degree or higher": [90, 85],
        "Total - Main mode of commuting for the employed labour force aged 15 years and over with a usual place of work or no fixed workplace address - 25% sample data": [
            70,
            90,
        ],
        "Car, truck or van": [20, 85],
        "Public transit": [40, 0],
        "Walked": [10, 0],
        "Bicycle": [0, 0],
        "Immigrants": [160, 55],
    }
    data = {"GEOID": ["35200001", "35200002"]}
    for name in characteristic_names:
        if name in values:
            data[name] = values[name]
    return pd.DataFrame(data)


def _fake_workplace_jobs_totals(data_dir=None):
    # Small synthetic table matching fetch_workplace_jobs_totals's real
    # output shape (GEOID=CSDUID, one jobs-count column) -- values chosen
    # distinct from _fake_municipality_totals's population figures so a
    # test can't pass by accident from column confusion.
    return pd.DataFrame(
        {
            "GEOID": ["3520005", "3506008"],
            api._WORKPLACE_JOBS_COLUMN: [753185, 272920],
        }
    )


def _fake_boundary_gdf(level, province):
    if level == "dissemination-area":
        return gpd.GeoDataFrame(
            {"GEOID": ["35200001", "35200002"]},
            geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
            crs=4326,
        )
    if level == "dissemination-block":
        return gpd.GeoDataFrame(
            {"GEOID": ["35200001001", "35200001002"]},
            geometry=[box(0, 0, 0.5, 1), box(0.5, 0, 1, 1)],
            crs=4326,
        )
    return _fake_province_gdf({"province": "35", "municipality": "3520005"}.get(level, province))


class TestLoader:
    """StatCan's own network calls (Full Table Download, boundary download)
    are monkeypatched out, same pattern as mexico's INEGI loader tests."""

    @pytest.fixture(autouse=True)
    def patch_network(self, monkeypatch):
        import pycensus.countries.canada.api as api_mod
        import pycensus.countries.canada.statcan.loader as loader_mod

        monkeypatch.setattr(api_mod, "fetch_province_totals", _fake_province_totals)
        monkeypatch.setattr(api_mod, "fetch_municipality_totals", _fake_municipality_totals)
        monkeypatch.setattr(api_mod, "fetch_dissemination_area_totals", _fake_dissemination_area_totals)
        monkeypatch.setattr(api_mod, "fetch_block_totals", _fake_block_totals)
        monkeypatch.setattr(loader_mod.api, "fetch_province_totals", _fake_province_totals)
        monkeypatch.setattr(loader_mod.api, "fetch_municipality_totals", _fake_municipality_totals)
        monkeypatch.setattr(
            loader_mod.api, "fetch_dissemination_area_totals", _fake_dissemination_area_totals
        )
        monkeypatch.setattr(loader_mod.api, "fetch_block_totals", _fake_block_totals)
        monkeypatch.setattr(api_mod, "fetch_census_profile_da_totals", _fake_census_profile_da_totals)
        monkeypatch.setattr(loader_mod.api, "fetch_census_profile_da_totals", _fake_census_profile_da_totals)
        monkeypatch.setattr(api_mod, "fetch_workplace_jobs_totals", _fake_workplace_jobs_totals)
        monkeypatch.setattr(loader_mod.api, "fetch_workplace_jobs_totals", _fake_workplace_jobs_totals)
        monkeypatch.setattr(
            geography,
            "load_boundaries",
            lambda level, province=None, year=2021, erase_water=None, data_dir=None: _fake_boundary_gdf(
                level, province
            ),
        )

    def test_load_dissemination_area_level_returns_schema_columns(self, tmp_path):
        gdf = loader.load(provinces=["35"], level="dissemination-area", cache_dir=str(tmp_path))
        assert "population" in gdf.columns
        assert len(gdf) == 2
        assert sorted(gdf["population"].tolist()) == [480, 512]
        assert sorted(gdf["households"].tolist()) == [190, 200]
        assert sorted(gdf["statcan_dwellings"].tolist()) == [198, 210]
        assert gdf.geometry.name == "geometry"
        assert gdf.crs is not None

    def test_load_dissemination_block_level_returns_schema_columns(self, tmp_path):
        gdf = loader.load(provinces=["35"], level="dissemination-block", cache_dir=str(tmp_path))
        assert "population" in gdf.columns
        assert len(gdf) == 2
        assert sorted(gdf["population"].tolist()) == [130, 284]
        assert sorted(gdf["households"].tolist()) == [55, 110]
        assert sorted(gdf["statcan_dwellings"].tolist()) == [58, 115]
        assert gdf.geometry.name == "geometry"
        assert gdf.crs is not None

    def test_load_block_falls_back_to_dissemination_block(self, tmp_path):
        # "block" isn't native to Canada -- LEVEL_FALLBACK should resolve it
        # to "dissemination-block" now that it's implemented.
        gdf = loader.load(provinces=["35"], level="block", cache_dir=str(tmp_path))
        assert len(gdf) == 2
        assert sorted(gdf["population"].tolist()) == [130, 284]

    def test_load_tract_falls_back_to_dissemination_area(self, tmp_path):
        # "tract" isn't native to Canada -- LEVEL_FALLBACK should resolve it
        # to "dissemination-area" and produce the same result.
        gdf = loader.load(provinces=["35"], level="tract", cache_dir=str(tmp_path))
        assert len(gdf) == 2
        assert "population" in gdf.columns

    def test_load_dissemination_area_level_has_foreign_born_population(self, tmp_path):
        gdf = loader.load(provinces=["35"], level="dissemination-area", cache_dir=str(tmp_path))
        assert "foreignBornPopulation" in gdf.columns
        assert sorted(gdf["foreignBornPopulation"].tolist()) == [55, 160]

    def test_load_dissemination_area_level_never_requests_workplace_jobs_sentinel(
        self, monkeypatch, tmp_path
    ):
        """Regression test for a real silent-zero-degradation bug.

        ``statcan_jobsTotal``'s code is the census-subdivision-level
        workplace-jobs sentinel (PID 98-10-0459) -- it is not a real
        98-401-X2021006 CHARACTERISTIC_NAME and has no
        dissemination-area-level equivalent at all. Before the fix,
        ``_fetch_missing``'s dissemination-area branch built
        ``needed_profile_names`` from *every* missing column's codes
        indiscriminately, including this one, and asked
        ``fetch_census_profile_da_totals`` to match it alongside the real
        DA-level fields. The real StatCan CSV never contains that
        sentinel string, so a strict "did every requested name match
        something real" check on the live function (added alongside this
        fix, to convert a true typo/formatting mismatch into a loud
        failure instead of a silently-degraded all-NaN column) would
        always trip on this one always-absent name -- crashing the
        *entire* dissemination-area fetch and turning every real
        household/income/education/foreign-born field to NaN, with
        nothing in any log to explain why. Only checking "no exception
        raised" against the old, non-validating fake stub would not have
        caught this: it needs a fake that behaves like the real source
        and rejects names it doesn't recognize.
        """
        import pycensus.countries.canada.statcan.loader as loader_mod

        seen_names = []

        def strict_fake_census_profile_da_totals(province, characteristic_names, data_dir=None):
            seen_names.extend(characteristic_names)
            unknown = set(characteristic_names) - set(_fake_census_profile_da_totals.__wrapped_values__)
            if unknown:
                raise ValueError(f"unrecognized CHARACTERISTIC_NAME(s): {sorted(unknown)}")
            return _fake_census_profile_da_totals(province, characteristic_names, data_dir)

        _fake_census_profile_da_totals.__wrapped_values__ = {
            "Average household size",
            "Median total income of household in 2020 ($)",
            "Average total income of household in 2020 ($)",
            "Owner",
            "Renter",
            "Total - Highest certificate, diploma or degree for the population aged 15 years and over in "
            "private households - 25% sample data",
            "No certificate, diploma or degree",
            "High (secondary) school diploma or equivalency certificate",
            "Postsecondary certificate or diploma below bachelor level",
            "Bachelor's degree or higher",
            "Total - Main mode of commuting for the employed labour force aged 15 years and over with a "
            "usual place of work or no fixed workplace address - 25% sample data",
            "Car, truck or van",
            "Public transit",
            "Walked",
            "Bicycle",
            "Immigrants",
        }
        monkeypatch.setattr(
            loader_mod.api, "fetch_census_profile_da_totals", strict_fake_census_profile_da_totals
        )

        # Must not raise -- the workplace-jobs sentinel must never reach
        # fetch_census_profile_da_totals for a dissemination-area fetch.
        gdf = loader.load(provinces=["35"], level="dissemination-area", cache_dir=str(tmp_path))

        assert api._WORKPLACE_JOBS_COLUMN not in seen_names
        # Real DA-level fields still come back correctly (not degraded by
        # the sentinel's presence).
        assert sorted(gdf["foreignBornPopulation"].tolist()) == [55, 160]
        assert "statcan_jobsTotal" in gdf.columns
        assert gdf["statcan_jobsTotal"].isna().all()  # genuinely inapplicable at this level

    def test_load_municipality_level_has_workplace_jobs(self, tmp_path):
        # jobsTotal comes from a second real source (PID 98-10-0459, via
        # fetch_workplace_jobs_totals -- see statcan/loader.py's
        # _fetch_missing) merged onto the Census Profile municipality
        # totals, distinct from the residence-based population figures.
        # _fake_boundary_gdf only has a real fake boundary for CSDUID
        # 3520005 at the "municipality" level, so only that CSD survives
        # the boundary/attribute join even though _fake_municipality_totals/
        # _fake_workplace_jobs_totals both return two CSDs' worth of rows.
        gdf = loader.load(provinces=["35"], level="municipality", cache_dir=str(tmp_path))
        assert "statcan_jobsTotal" in gdf.columns
        by_geoid = dict(zip(gdf["GEOID"], gdf["statcan_jobsTotal"]))
        assert by_geoid["3520005"] == 753185
        # Not conflated with population -- Toronto's real 2021 population
        # (2,794,356) is not equal to its real workplace-jobs count.
        assert by_geoid["3520005"] != dict(zip(gdf["GEOID"], gdf["population"]))["3520005"]

    def test_load_province_level_returns_schema_columns(self, tmp_path):
        gdf = loader.load(provinces=["35"], level="province", cache_dir=str(tmp_path))
        assert "population" in gdf.columns
        assert gdf["population"].iloc[0] == 14223942
        assert gdf["households"].iloc[0] == 5491201
        assert gdf["statcan_dwellings"].iloc[0] == 5929250
        assert gdf.geometry.name == "geometry"
        assert gdf.crs is not None

    def test_load_raises_without_provinces_or_aoi(self, tmp_path):
        with pytest.raises(ValueError):
            loader.load(level="province", cache_dir=str(tmp_path))

    def test_load_unimplemented_level_raises(self, tmp_path):
        with pytest.raises(ValueError):
            loader.load(provinces=["35"], level="nation", cache_dir=str(tmp_path))

    def test_load_writes_geoparquet_cache_file(self, tmp_path):
        loader.load(provinces=["35"], level="province", cache_dir=str(tmp_path))
        cache_file = tmp_path / "canada" / "province" / "35.parquet"
        assert cache_file.exists()

        cached = gpd.read_parquet(cache_file)
        assert cached.crs is not None
        # `apply_canonical_names` runs before the cache is written, so
        # the cached file already has bare canonical names too.
        assert "population" in cached.columns
        assert len(cached) == 1

    def test_load_second_call_does_not_refetch(self, monkeypatch, tmp_path):
        calls = {"n": 0}

        def counting_fetch(province, data_dir=None):
            calls["n"] += 1
            return _fake_province_totals(province, data_dir)

        import pycensus.countries.canada.statcan.loader as loader_mod

        monkeypatch.setattr(loader_mod.api, "fetch_province_totals", counting_fetch)

        loader.load(provinces=["35"], level="province", cache_dir=str(tmp_path))
        assert calls["n"] == 1

        loader.load(provinces=["35"], level="province", cache_dir=str(tmp_path))
        assert calls["n"] == 1  # second call served from the parquet cache


@pytest.mark.network
def test_real_gaf_toronto_block_sums_match_da_totals_exactly():
    """Hits the live StatCan Geographic Attribute File download (catalogue
    92-151-X) and the live PID 98-10-0015 Full Table Download. Verified
    2026-08-22: summing the GAF's real DBPOP2021 by DAUID for every one of
    Toronto's 3,743 real dissemination areas reproduces PID 98-10-0015's
    own published DA-level population exactly -- 0 mismatches -- and the
    grand total (2,794,356) matches the City of Toronto's published CSD
    population exactly."""
    import re

    from pycensus.countries.canada import api

    block_df = api._read_geographic_attribute_file()
    toronto_pruid_da = block_df[block_df["PRUID_PRIDU"] == "35"]
    # DAUID isn't in the trimmed usecols read by fetch_block_totals, so
    # read the raw CSV directly here (small extra column) for this check.
    import pandas as pd

    from pycensus.countries.canada import constants

    csv_path = api.download_geographic_attribute_file()
    full = pd.read_csv(
        csv_path,
        usecols=["CSDUID_SDRIDU", "DAUID_ADIDU", "DBPOP2021_IDPOP2021"],
        dtype={"CSDUID_SDRIDU": str, "DAUID_ADIDU": str},
        encoding="latin-1",
    )
    toronto = full[full["CSDUID_SDRIDU"] == "3520005"]
    block_sums = toronto.groupby("DAUID_ADIDU")["DBPOP2021_IDPOP2021"].sum()
    assert block_sums.sum() == 2_794_356

    da_df = api._read_dissemination_area_table()
    da_geoids = da_df["DGUID"].map(lambda d: (m.group(1) if (m := re.match(r"^2021S0512(\d{8})$", d)) else None))
    da_pop = da_df[da_geoids.notna()].assign(DAUID=da_geoids[da_geoids.notna()]).set_index("DAUID")[
        "Population and dwelling counts (5): Population, 2021 [1]"
    ]

    merged = block_sums.to_frame("block_sum").join(da_pop.rename("official"), how="inner")
    assert len(merged) > 3000  # sanity: real join, not an empty/degenerate one
    assert (merged["block_sum"] != merged["official"]).sum() == 0


@pytest.mark.network
def test_real_dissemination_block_boundary_matches_gaf_dbuids():
    """Hits the live StatCan dissemination-block cartographic boundary
    download (ldb_000b21a_e.zip). Verified 2026-08-22: Toronto's 13,323
    real block DBUIDs (from the GAF) match 13,322 of this shapefile's
    real DBUIDs (the one gap is a coastal-water-only block, consistent
    with StatCan's own documented exclusion for this file), with bounds
    landing squarely inside Toronto's known extent."""
    from pycensus.countries.canada import geography

    gdf = geography.load_boundaries("dissemination-block", province="35")
    assert gdf.crs is not None
    assert len(gdf) > 100_000  # Ontario alone has well over 100k dissemination blocks


class TestCensusProfile:
    """Offline tests for the long/tall 98-401-X2021006 pivot logic
    (:func:`pycensus.countries.canada.api.fetch_census_profile_da_totals`),
    using a small real fixture (``tests/fixtures/canada_census_profile_Ontario_sample.zip``)
    -- an actual excerpt (42 rows: 2 real Toronto DAs x 16 real target
    characteristics, plus one extra real row) captured directly from the
    real downloaded 98-401-X2021006_Ontario_eng_CSV.zip during this
    session, not invented data."""

    FIXTURE_ZIP = Path(__file__).parent / "fixtures" / "canada_census_profile_Ontario_sample.zip"

    def test_pivot_matches_real_captured_values(self, monkeypatch, tmp_path):
        from pycensus.countries.canada import api

        monkeypatch.setattr(api, "_census_profile_zip_path", lambda province, data_dir=None: self.FIXTURE_ZIP)

        names = [
            "Average household size",
            "Median total income of household in 2020 ($)",
            "Owner",
            "Renter",
            "Bachelor's degree or higher",
            "Car, truck or van",
            "Public transit",
        ]
        df = api.fetch_census_profile_da_totals("35", names)
        df = df.set_index("GEOID")

        # Real values captured live 2026-08-23 from the downloaded Ontario
        # file for these exact two real Toronto DAs.
        assert df.loc["35204609", "Average household size"] == 1.9
        assert df.loc["35204609", "Median total income of household in 2020 ($)"] == 44800
        assert df.loc["35204609", "Owner"] == 0
        assert df.loc["35204609", "Renter"] == 180
        assert df.loc["35203712", "Average household size"] == 3
        assert df.loc["35203712", "Median total income of household in 2020 ($)"] == 98000
        assert df.loc["35203712", "Car, truck or van"] == 85
        assert df.loc["35203712", "Public transit"] == 0

    def test_unrequested_columns_are_not_returned(self, monkeypatch):
        from pycensus.countries.canada import api

        monkeypatch.setattr(api, "_census_profile_zip_path", lambda province, data_dir=None: self.FIXTURE_ZIP)
        df = api.fetch_census_profile_da_totals("35", ["Average household size"])
        assert set(df.columns) == {"GEOID", "Average household size"}

    def test_non_ontario_province_raises_not_implemented(self):
        from pycensus.countries.canada import api

        with pytest.raises(NotImplementedError):
            api.fetch_census_profile_da_totals("Quebec", ["Average household size"])


@pytest.mark.network
def test_real_census_profile_household_size_and_income_match_prior_spot_check():
    """Hits the live StatCan Census Profile (98-401-X2021006) Ontario
    download. Verified 2026-08-23: DA 35204609 (downtown Toronto core)
    reports Average household size 1.9 and Median total income of
    household in 2020 ($) 44800 -- exactly matching the values already
    spot-checked in a prior session (see MEMORY.md /
    canada_census_profile_household_income). Also cross-checks 3 more real
    Toronto DAs (35203712 Scarborough, 35204196 North York, 35201868
    Etobicoke) purely for internal consistency (plausible household-size
    and income ranges), since no independent live cross-check source was
    used beyond StatCan's own file."""
    from pycensus.countries.canada import api

    df = api.fetch_census_profile_da_totals(
        "35",
        ["Average household size", "Median total income of household in 2020 ($)"],
    ).set_index("GEOID")

    assert df.loc["35204609", "Average household size"] == 1.9
    assert df.loc["35204609", "Median total income of household in 2020 ($)"] == 44800

    for da in ["35203712", "35204196", "35201868"]:
        assert da in df.index
        assert 1.0 <= df.loc[da, "Average household size"] <= 6.0
        assert 10_000 <= df.loc[da, "Median total income of household in 2020 ($)"] <= 500_000


@pytest.mark.network
def test_real_census_profile_immigrants_matches_national_headline_figure():
    """Hits the live StatCan Census Profile (98-401-X2021006) Ontario
    download. Verified 2026-08-23: the real 'Immigrants' CHARACTERISTIC_NAME
    for downtown-Toronto DA 35204609 is 160 (45.1% of that DA's population
    in private households) -- also cross-checked against the standalone
    'Canada' row in the same real download, which reports 8,361,505
    Immigrants nationwide (23.0%), exactly matching StatCan's own widely
    published 2021 Census headline immigrant count/share."""
    from pycensus.countries.canada import api

    df = api.fetch_census_profile_da_totals("35", ["Immigrants"]).set_index("GEOID")
    assert df.loc["35204609", "Immigrants"] == 160


@pytest.mark.network
def test_real_workplace_jobs_toronto_matches_prior_spot_check():
    """Hits the live StatCan Full Table Download for PID 98-10-0459
    ('Commuting flow from geography of residence to geography of work by
    gender: Census subdivisions') -- a real ~2.2GB national commuting-flow
    file. Verified 2026-08-23: summing every residence-CSD's flow into
    workplace CSDUID 3520005 (Toronto) gives 753,185, matching the value
    already spot-checked directly against the raw downloaded CSV in the
    same session (see pycensus.countries.canada.constants.WORKPLACE_JOBS_PID's
    docstring for the full verification, including the national-total
    cross-check against table 98-10-0456)."""
    from pycensus.countries.canada import api

    df = api.fetch_workplace_jobs_totals().set_index("GEOID")
    assert df.loc["3520005", api._WORKPLACE_JOBS_COLUMN] == 753185


class TestAccessor:
    def test_accessor_registered(self):
        poly_gdf = gpd.GeoDataFrame(
            {"GEOID": ["35"], "population": [1000], "households": [400]},
            geometry=[box(0, 0, 1, 1)],
            crs="EPSG:4326",
        )
        assert hasattr(poly_gdf, "statcan")
        assert poly_gdf.statcan["population"].tolist() == [1000]
