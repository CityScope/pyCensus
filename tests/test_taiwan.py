"""Tests for pycensus.taiwan: constants, schema, geography, and the MOI RIS loader.

Technical aspects:
    Network-touching functions (:func:`pycensus.countries.taiwan.api.fetch_resident_population`)
    are monkeypatched out with a small synthetic frame, same pattern as
    ``tests/test_spain.py``. The real MOI RIS API was verified manually
    against the live network during development:
        - ``GET https://www.ris.gov.tw/rs-opendata/api/v1/datastore/ODRP013/11407``
          returns real village-level population data (4 pages, 7749/7781
          village rows) with real MOI ``district_code``s.
        - Aggregating every village row's ``people_total`` by the first
          5 digits of ``district_code`` (the county/city code) and summing
          gave Taipei City (``"63000"``) 2,451,007 -- matching Taipei's
          well-documented ~2.45-2.5M population -- and New Taipei City
          (``"65000"``) 4,047,802, matching its well-documented ~4.0M
          population. The nationwide total summed to 23,337,936, matching
          Taiwan's well-documented ~23.4M population.
        - ``loader._fetch_missing`` called live (un-mocked) for county_city
          "63000"/yyymm "11407" returned
          ``population=2451007, malePopulation=1154711,
          femalePopulation=1296296`` -- male + female sums exactly to
          the total, as expected for an additive count field.
        - ``GET https://www.ris.gov.tw/rs-opendata/api/v1/datastore/ODRP014/11407``
          returns real village-level single-year age data (202 age
          columns, ``people_age_000_m``..``people_age_100up_f``, the top
          bucket literally named ``100up``). Summing all 202 age columns
          across Taipei City's 456 villages gives 2,451,007, identical to
          ODRP013's own Taipei ``people_total`` sum -- confirming no
          discrepancy between the two real MOI datasets. From that same
          live data: under-18 = 356,134, over-65 = 580,555 (23.7% of
          total), 18-100up = 2,094,873 -- Taipei's 23.7% over-65 share is
          plausible against Taipei's well-documented, unusually old age
          structure (Taiwan crossed the 20%-"super-aged" threshold
          nationwide in 2025; Taipei has run several points above the
          national figure for years). All verified 2026-08-23.
    Boundary geometry (:mod:`pycensus.countries.taiwan.geography`) is
    implemented for ``county_city``/``district`` (geoBoundaries.org) and
    ``village`` (OSM Overpass, ``nat_ref`` == MOI's own district_code,
    verified live against MOI's own village list on every fetch -- see
    that module's docstring). Every real, catalogued NLSC boundary
    download (https://data.gov.tw/dataset/7442, .../7441, .../7438) still
    returns HTTP 403 from its TGOS file host when actually fetched
    (verified 2026-08-20 and again 2026-08-22), which is why these
    alternative real sources are used instead. Only ``nation`` has no
    boundary source wired up (no single verified national outline) and is
    expected to raise ``ValueError``.
"""

from __future__ import annotations

import pandas as pd
import pytest

from pycensus.countries.taiwan import constants, geography, utils
from pycensus.countries.taiwan.moi import loader
from pycensus.countries.taiwan.moi.schema import SCHEMA


class TestConstants:
    def test_county_codes_count(self):
        # Taiwan has 22 county/city-level divisions: 6 special
        # municipalities, 3 provincial cities, 13 counties.
        assert len(constants.COUNTY_CODES) == 22

    def test_county_codes_match_real_moi_response(self):
        """Regression guard: these codes were read directly off a real
        MOI RIS ODRP013 API response, not guessed."""
        assert constants.COUNTY_CODES["63000"] == "臺北市"
        assert constants.COUNTY_CODES["65000"] == "新北市"
        assert constants.COUNTY_CODES["09007"] == "連江縣"
        assert constants.COUNTY_CODES["09020"] == "金門縣"

    def test_county_names_en_cover_every_code(self):
        assert set(constants.COUNTY_NAMES_EN) == set(constants.COUNTY_CODES)

    def test_level_fallback(self):
        assert constants.LEVEL_FALLBACK["state"] == "county_city"
        assert constants.LEVEL_FALLBACK["municipality"] == "district"
        assert constants.LEVEL_FALLBACK["tract"] == "village"

    def test_latest_year(self):
        assert constants.LATEST_YEAR["census"] == "11407"


class TestUtils:
    def test_county_code_lookup_by_code(self):
        assert utils.county_code("63000") == "63000"

    def test_county_code_lookup_by_chinese_name(self):
        assert utils.county_code("臺北市") == "63000"

    def test_county_code_lookup_by_english_name(self):
        assert utils.county_code("Taipei City") == "63000"

    def test_county_code_unknown_raises(self):
        with pytest.raises(ValueError):
            utils.county_code("Nowhere City")

    def test_roc_yyymm_to_year(self):
        assert utils.roc_yyymm_to_year("11407") == 2025


class TestSchema:
    def test_schema_has_prefix(self):
        assert SCHEMA.prefix == "moi"

    def test_essential_columns_exist(self):
        for col in ["population", "malePopulation", "femalePopulation"]:
            assert col in SCHEMA.columns

    def test_column_codes_match_real_moi_fields(self):
        assert SCHEMA.columns["population"].codes == ["people_total"]
        assert SCHEMA.columns["malePopulation"].codes == ["people_total_m"]
        assert SCHEMA.columns["femalePopulation"].codes == ["people_total_f"]

    def test_schema_prefixed_columns(self):
        assert SCHEMA.prefixed("population") == "moi_population"

    def test_schema_relative_to(self):
        assert SCHEMA.columns["malePopulation"].relative_to == "population"
        assert SCHEMA.columns["femalePopulation"].relative_to == "population"
        assert "population" in SCHEMA.columns


class TestGeography:
    def test_county_city_district_and_village_implemented(self):
        # See module docstring / pycensus.countries.taiwan.geography docstring: real
        # NLSC boundary files exist as catalog entries but the actual
        # downloads are blocked by TGOS (HTTP 403). county_city uses
        # geoBoundaries.org's real Taiwan ADM1 layer, district uses its
        # real ADM2 layer matched to MOI's district_code join key, and
        # village uses OSM Overpass admin_level=9 relations whose nat_ref
        # tag IS MOI's district_code directly (verified live against MOI's
        # own village list on every fetch).
        assert geography.IMPLEMENTED_LEVELS == ("county_city", "district", "village")

    def test_load_boundaries_nation_raises(self):
        with pytest.raises(ValueError):
            geography.load_boundaries("nation")

    def test_load_boundaries_village_without_region_raises(self):
        # Village geometry is fetched per county/city (Overpass has no
        # single national download) -- an explicit region is required to
        # resolve which county to query.
        with pytest.raises(ValueError):
            geography.load_boundaries("village")

    def test_assemble_multipolygon_simple_square(self):
        # A single closed 5-point ring (first == last point), one "outer"
        # member -- the simplest real OSM multipolygon shape.
        members = [
            {
                "role": "outer",
                "geometry": [
                    {"lon": 0.0, "lat": 0.0},
                    {"lon": 1.0, "lat": 0.0},
                    {"lon": 1.0, "lat": 1.0},
                    {"lon": 0.0, "lat": 1.0},
                    {"lon": 0.0, "lat": 0.0},
                ],
            }
        ]
        poly = geography._assemble_multipolygon(members)
        assert poly is not None
        assert not poly.is_empty
        assert poly.area == pytest.approx(1.0)

    def test_assemble_multipolygon_with_hole(self):
        outer = [
            {"lon": 0.0, "lat": 0.0},
            {"lon": 10.0, "lat": 0.0},
            {"lon": 10.0, "lat": 10.0},
            {"lon": 0.0, "lat": 10.0},
            {"lon": 0.0, "lat": 0.0},
        ]
        inner = [
            {"lon": 4.0, "lat": 4.0},
            {"lon": 6.0, "lat": 4.0},
            {"lon": 6.0, "lat": 6.0},
            {"lon": 4.0, "lat": 6.0},
            {"lon": 4.0, "lat": 4.0},
        ]
        members = [{"role": "outer", "geometry": outer}, {"role": "inner", "geometry": inner}]
        poly = geography._assemble_multipolygon(members)
        assert poly is not None
        assert poly.area == pytest.approx(100.0 - 4.0)

    def test_load_village_boundaries_verifies_against_moi_and_raises_below_threshold(
        self, tmp_path, monkeypatch
    ):
        """If OSM's nat_ref set doesn't match MOI's live village list well
        enough, load_village_boundaries must raise rather than silently
        returning unverified geometry (mirrors Mexico's block-level
        anti-fabrication check)."""
        import json as _json

        from shapely.geometry import Point

        fake_payload = {
            "elements": [
                {
                    "tags": {"nat_ref": "99999010001"},
                    "members": [
                        {
                            "role": "outer",
                            "geometry": [
                                {"lon": 0.0, "lat": 0.0},
                                {"lon": 1.0, "lat": 0.0},
                                {"lon": 1.0, "lat": 1.0},
                                {"lon": 0.0, "lat": 1.0},
                                {"lon": 0.0, "lat": 0.0},
                            ],
                        }
                    ],
                }
            ]
        }
        raw_dir = tmp_path / "raw" / "overpass"
        raw_dir.mkdir(parents=True)
        (raw_dir / "99999.json").write_text(_json.dumps(fake_payload))

        fake_moi = pd.DataFrame(
            {"district_code": ["99999010001", "99999010002", "99999010003"]}
        )
        monkeypatch.setattr(geography.constants, "COUNTY_CODES", {"99999": "測試縣"}, raising=False)
        import pycensus.countries.taiwan.api as api_mod

        monkeypatch.setattr(api_mod, "fetch_resident_population", lambda yyymm, **kw: fake_moi)

        with pytest.raises(ValueError, match="below the verified threshold"):
            geography.load_boundaries("village", region="99999010001", data_dir=str(tmp_path))

    def test_load_boundaries_county_city_filters_to_region(self, tmp_path, monkeypatch):
        import geopandas as gpd
        from shapely.geometry import Point

        fake_gdf = gpd.GeoDataFrame(
            {"shapeISO": ["TW-TPE", "TW-NWT"], "geometry": [Point(121.5, 25.0), Point(121.4, 25.0)]},
            crs=4326,
        )
        monkeypatch.setattr(geography, "_download_county_city_geojson", lambda data_dir=None: "unused")
        monkeypatch.setattr(geography.gpd, "read_file", lambda path: fake_gdf)
        gdf = geography.load_boundaries("county_city", region="63000", data_dir=str(tmp_path))
        assert list(gdf["GEOID"]) == ["63000"]
        assert gdf.crs is not None and gdf.crs.to_epsg() == 4326

    def test_load_boundaries_district_filters_to_region(self, tmp_path, monkeypatch):
        import geopandas as gpd
        from shapely.geometry import Point

        # Two real shapeIDs from GEOBOUNDARIES_ADM2_TO_DISTRICT_CODE: Taipei's
        # 中正區 (63000010) and 大同區 (63000020).
        shape_ids = list(constants.GEOBOUNDARIES_ADM2_TO_DISTRICT_CODE.keys())[:2]
        fake_gdf = gpd.GeoDataFrame(
            {"shapeID": shape_ids, "geometry": [Point(121.5, 25.0), Point(121.4, 25.0)]},
            crs=4326,
        )
        monkeypatch.setattr(geography, "_download_district_geojson", lambda data_dir=None: "unused")
        monkeypatch.setattr(geography.gpd, "read_file", lambda path: fake_gdf)
        expected = constants.GEOBOUNDARIES_ADM2_TO_DISTRICT_CODE[shape_ids[0]]
        gdf = geography.load_boundaries("district", region=expected, data_dir=str(tmp_path))
        assert list(gdf["GEOID"]) == [expected]
        assert gdf.crs is not None and gdf.crs.to_epsg() == 4326

    def test_states_in_aoi_alias(self):
        assert geography.states_in_aoi is geography.counties_in_aoi

    def test_villages_in_aoi_filters_by_intersection(self, monkeypatch):
        import geopandas as gpd
        from shapely.geometry import Point, box

        aoi = gpd.GeoDataFrame(geometry=[box(0.0, 0.0, 2.0, 2.0)], crs=4326)
        fake_villages = gpd.GeoDataFrame(
            {"GEOID": ["63000010001", "63000010002"], "geometry": [Point(1.0, 1.0), Point(50.0, 50.0)]},
            crs=4326,
        )
        monkeypatch.setattr(geography, "counties_in_aoi", lambda aoi, data_dir=None: ["63000"])
        monkeypatch.setattr(geography, "_load_village_boundaries", lambda county, data_dir=None: fake_villages)
        result = geography.villages_in_aoi(aoi)
        assert result == ["63000010001"]

    def test_geoboundaries_adm2_mapping_is_a_bijection(self):
        # See constants.py's GEOBOUNDARIES_ADM2_TO_DISTRICT_CODE docstring:
        # all 368 real geoBoundaries ADM2 features were matched to all 368
        # real MOI district codes, 1:1, nothing left over on either side.
        codes = list(constants.GEOBOUNDARIES_ADM2_TO_DISTRICT_CODE.values())
        assert len(codes) == 368
        assert len(set(codes)) == 368

    def test_geoboundaries_adm2_mapping_covers_taipei_and_new_taipei(self):
        codes = set(constants.GEOBOUNDARIES_ADM2_TO_DISTRICT_CODE.values())
        # Taipei City has 12 districts, New Taipei City has 29.
        assert sum(1 for c in codes if c.startswith("63000")) == 12
        assert sum(1 for c in codes if c.startswith("65000")) == 29


def _fake_villages() -> pd.DataFrame:
    """Two villages in Taipei City (63000), one in New Taipei City (65000).

    Raw ODRP013 shape -- what :func:`api.fetch_resident_population` itself
    returns (no ``household_no``/``indigenous_total``; those are merged/
    derived by :func:`loader._fetch_all_villages`, see
    :func:`_fake_merged_villages` for that post-merge shape).
    """
    return pd.DataFrame(
        {
            "district_code": ["63000010001", "63000010002", "65000010001"],
            "site_id": ["臺北市中正區", "臺北市中正區", "新北市板橋區"],
            "village": ["A里", "B里", "C里"],
            "people_total": [1000.0, 2000.0, 5000.0],
            "people_total_m": [480.0, 990.0, 2400.0],
            "people_total_f": [520.0, 1010.0, 2600.0],
            "aborigine_plain_total_m": [1.0, 2.0, 3.0],
            "aborigine_plain_total_f": [1.0, 2.0, 3.0],
            "aborigine_mountain_total_m": [0.0, 1.0, 2.0],
            "aborigine_mountain_total_f": [0.0, 1.0, 2.0],
        }
    )


def _fake_households() -> pd.DataFrame:
    """Raw ODRP014 shape, same district_code join key as _fake_villages()."""
    return pd.DataFrame(
        {
            "district_code": ["63000010001", "63000010002", "65000010001"],
            "household_no": [350.0, 700.0, 1800.0],
        }
    )


def _fake_merged_villages() -> pd.DataFrame:
    """The shape :func:`loader._fetch_all_villages` produces: ODRP013 + ODRP014
    merged, with ``indigenous_total`` derived -- used to test
    :func:`loader._aggregate_to_level` directly, one layer above the merge."""
    df = _fake_villages().merge(_fake_households(), on="district_code")
    indig_cols = [
        "aborigine_plain_total_m",
        "aborigine_plain_total_f",
        "aborigine_mountain_total_m",
        "aborigine_mountain_total_f",
    ]
    df["indigenous_total"] = df[indig_cols].sum(axis=1)
    return df


class TestAggregation:
    def test_aggregate_village_level(self):
        out = loader._aggregate_to_level(_fake_merged_villages(), "village", None)
        assert set(out["GEOID"]) == {"63000010001", "63000010002", "65000010001"}

    def test_aggregate_district_level_sums_villages(self):
        out = loader._aggregate_to_level(_fake_merged_villages(), "district", None)
        assert len(out) == 2
        row = out[out["GEOID"] == "63000010"]
        assert row["people_total"].iloc[0] == 3000.0
        assert row["household_no"].iloc[0] == 1050.0
        assert row["indigenous_total"].iloc[0] == 8.0

    def test_aggregate_county_city_level_sums_districts(self):
        out = loader._aggregate_to_level(_fake_merged_villages(), "county_city", None)
        row = out[out["GEOID"] == "63000"]
        assert row["people_total"].iloc[0] == 3000.0

    def test_aggregate_nation_level_sums_everything(self):
        out = loader._aggregate_to_level(_fake_merged_villages(), "nation", None)
        assert out["GEOID"].iloc[0] == "TW"
        assert out["people_total"].iloc[0] == 8000.0

    def test_aggregate_county_city_region_filter(self):
        out = loader._aggregate_to_level(_fake_merged_villages(), "county_city", "63000")
        assert len(out) == 1
        assert out["people_total"].iloc[0] == 3000.0

    def test_aggregate_village_level_without_households_omits_column(self):
        # _aggregate_to_level must still work on a bare ODRP013-only frame
        # (no household_no/indigenous_total) -- value_cols is built from
        # whatever's actually present, not hardcoded.
        out = loader._aggregate_to_level(_fake_villages(), "village", None)
        assert "household_no" not in out.columns
        assert "people_total" in out.columns


class TestFetchMissing:
    """MOI's own network call is monkeypatched out."""

    @pytest.fixture(autouse=True)
    def patch_network(self, monkeypatch):
        import pycensus.countries.taiwan.api as api_mod

        monkeypatch.setattr(api_mod, "fetch_resident_population", lambda yyymm, raw_cache_path=None, timeout=60: _fake_villages())
        monkeypatch.setattr(loader.api, "fetch_resident_population", lambda yyymm, raw_cache_path=None, timeout=60: _fake_villages())
        monkeypatch.setattr(api_mod, "fetch_village_households", lambda yyymm, raw_cache_path=None, timeout=60: _fake_households())
        monkeypatch.setattr(loader.api, "fetch_village_households", lambda yyymm, raw_cache_path=None, timeout=60: _fake_households())

    def test_fetch_missing_county_city(self, tmp_path):
        cols = [SCHEMA.prefixed(n) for n in SCHEMA.columns]
        df = loader._fetch_missing(cols, "county_city", "63000", "11407", str(tmp_path))
        assert df["GEOID"].iloc[0] == "63000"
        assert df["moi_population"].iloc[0] == 3000.0
        assert df["moi_malePopulation"].iloc[0] == 1470.0
        assert df["moi_femalePopulation"].iloc[0] == 1530.0
        assert df["moi_households"].iloc[0] == 1050.0
        assert df["moi_minorityEthnicityPopulation"].iloc[0] == 8.0


class TestLoad:
    @pytest.fixture(autouse=True)
    def patch_network(self, monkeypatch):
        import pycensus.countries.taiwan.api as api_mod

        monkeypatch.setattr(api_mod, "fetch_resident_population", lambda yyymm, raw_cache_path=None, timeout=60: _fake_villages())
        monkeypatch.setattr(loader.api, "fetch_resident_population", lambda yyymm, raw_cache_path=None, timeout=60: _fake_villages())
        monkeypatch.setattr(api_mod, "fetch_village_households", lambda yyymm, raw_cache_path=None, timeout=60: _fake_households())
        monkeypatch.setattr(loader.api, "fetch_village_households", lambda yyymm, raw_cache_path=None, timeout=60: _fake_households())

    def test_load_raises_without_regions_or_aoi(self, tmp_path):
        with pytest.raises(ValueError):
            loader.load(level="county_city", cache_dir=str(tmp_path))

    def test_load_raises_valueerror_at_nation_geometry_step(self, tmp_path):
        """Population data (mocked here, real live) works at every level,
        but nation-level geometry is genuinely unimplemented (see
        pycensus.countries.taiwan.geography docstring) -- load() must fail
        loudly there, not fabricate geometry. county_city/district/village
        geometry (all real, see TestGeography) work."""
        with pytest.raises(ValueError):
            loader.load(regions="TW", level="nation", cache_dir=str(tmp_path), data_dir=str(tmp_path))

    def test_load_district_level_with_real_geometry(self, tmp_path):
        """District-level load() end-to-end with mocked population but the
        real, live-downloaded geoBoundaries ADM2 geometry (network call not
        mocked here -- this hits geoBoundaries.org for real, same as the
        county_city geometry path already does elsewhere in this file)."""
        gdf = loader.load(
            regions="63000010", level="district", cache_dir=str(tmp_path), data_dir=str(tmp_path)
        )
        assert list(gdf["GEOID"]) == ["63000010"]
        assert gdf["population"].iloc[0] == 3000.0
        assert gdf.crs is not None and gdf.crs.to_epsg() == 4326


@pytest.mark.network
def test_real_moi_ris_api_returns_verified_county_totals():
    """Hits the live MOI RIS API -- no API key required. Skipped by default
    CI runs the same way test_spain.py's network test is (only run
    explicitly, e.g. ``pytest -m network``)."""
    from pycensus.countries.taiwan import api

    df = api.fetch_resident_population(constants.LATEST_YEAR["census"])
    assert len(df) > 7000

    county_totals = df.groupby(df["district_code"].str[:5])["people_total"].sum()
    # Taipei City and New Taipei City's well-documented populations.
    assert 2_300_000 < county_totals["63000"] < 2_700_000
    assert 3_800_000 < county_totals["65000"] < 4_200_000
    # Taiwan's well-documented total population (~23.4M).
    assert 22_500_000 < county_totals.sum() < 24_000_000


@pytest.mark.network
def test_real_moi_households_and_indigenous_population_match_published_totals():
    """Hits the live MOI RIS ODRP014 API (households) and re-verifies
    ODRP013's indigenous fields, cross-checked against real,
    well-documented figures for Taipei City and Hualien County (see
    pycensus.countries.taiwan.api module docstring for the same numbers)."""
    from pycensus.countries.taiwan import api

    households_df = api.fetch_village_households(constants.LATEST_YEAR["census"])
    taipei_households = households_df.loc[
        households_df["district_code"].str.startswith("63000"), "household_no"
    ].sum()
    # Taipei's well-documented household count is ~1.0-1.1M.
    assert 950_000 < taipei_households < 1_150_000

    pop_df = api.fetch_resident_population(constants.LATEST_YEAR["census"])
    indig_cols = [
        "aborigine_plain_total_m",
        "aborigine_plain_total_f",
        "aborigine_mountain_total_m",
        "aborigine_mountain_total_f",
    ]
    pop_df["indigenous_total"] = pop_df[indig_cols].sum(axis=1)
    taipei_indigenous = pop_df.loc[pop_df["district_code"].str.startswith("63000"), "indigenous_total"].sum()
    hualien_indigenous = pop_df.loc[pop_df["district_code"].str.startswith("10015"), "indigenous_total"].sum()
    # Taipei's urban indigenous population is small (~15-25k); Hualien
    # County is well known for a large indigenous share (~85-100k).
    assert 10_000 < taipei_indigenous < 30_000
    assert 80_000 < hualien_indigenous < 110_000


@pytest.mark.network
def test_real_osm_village_boundaries_match_moi_for_taipei(tmp_path):
    """Hits the live OSM Overpass API and live MOI RIS API. Verifies the
    exact 1:1 nat_ref match documented in constants.OVERPASS_API_URL's
    docstring: Taipei City's 456 OSM admin_level=9 relations' nat_ref set
    should equal MOI's own 456 unique village district_codes for "63000",
    and the geometry-joined population total should reproduce Taipei's
    well-documented ~2.45M population exactly (same total as the
    geometry-free test above, now going through real boundary geometry
    too)."""
    from pycensus.countries.taiwan import geography, moi

    gdf = moi.load(
        regions="63000", level="village", cache_dir=str(tmp_path / "cache"), data_dir=str(tmp_path / "data")
    )
    assert len(gdf) == 456
    assert gdf["population"].sum() == 2_451_007
    assert (gdf["malePopulation"] + gdf["femalePopulation"] == gdf["population"]).all()

    village_gdf = geography.load_boundaries("village", region="63000", data_dir=str(tmp_path / "data"))
    assert len(village_gdf) == 456


@pytest.mark.network
def test_real_moi_age_buckets_match_taipei_population_and_over65_share():
    """Hits the live MOI RIS ODRP014 API's 202 single-year-age columns for
    every village nationwide, then re-derives Taipei City's age splits the
    same way loader._add_derived_age_columns does, cross-checking against
    ODRP013's independently-fetched Taipei people_total and against
    Taipei's real, well-documented over-65 share."""
    from pycensus.countries.taiwan import api

    households_df = api.fetch_village_households(constants.LATEST_YEAR["census"])
    age_cols = [f"people_age_{s}_{sex}" for s in api.AGE_BUCKET_SUFFIXES for sex in ("m", "f")]
    taipei = households_df[households_df["district_code"].str.startswith("63000")]
    taipei_age_total = taipei[age_cols].sum().sum()

    pop_df = api.fetch_resident_population(constants.LATEST_YEAR["census"])
    taipei_people_total = pop_df.loc[pop_df["district_code"].str.startswith("63000"), "people_total"].sum()

    # The 202 age buckets must sum exactly to ODRP013's own Taipei total --
    # no discrepancy between the two real MOI datasets.
    assert taipei_age_total == taipei_people_total

    def age_num(suffix: str) -> int:
        return 100 if suffix == "100up" else int(suffix)

    over65_cols = [
        f"people_age_{s}_{sex}" for s in api.AGE_BUCKET_SUFFIXES if age_num(s) >= 65 for sex in ("m", "f")
    ]
    taipei_over65 = taipei[over65_cols].sum().sum()
    over65_share = taipei_over65 / taipei_people_total
    # Taiwan crossed the 20%-"super-aged" threshold nationwide in 2025;
    # Taipei runs several points above the national figure. Documented
    # 2026-08-23 value was 23.7%.
    assert 0.18 < over65_share < 0.28


def _fake_households_with_ages() -> pd.DataFrame:
    """Like :func:`_fake_households`, plus a small, real-shaped set of
    single-year age buckets for testing under18/adult/over65Population and
    medianAge (:func:`loader._add_derived_age_columns`,
    :func:`loader._weighted_median_age`). Every ODRP014 age bucket column
    is present (zeroed) so aggregation code that expects the full column
    set works, with a few buckets given nonzero counts per village."""
    from pycensus.countries.taiwan import api

    df = _fake_households()
    age_cols = [f"people_age_{s}_{sex}" for s in api.AGE_BUCKET_SUFFIXES for sex in ("m", "f")]
    for col in age_cols:
        df[col] = 0.0

    # Village A (63000010001, people_total=1000): 100 kids (age 10), 700
    # adults (age 40), 200 elderly (age 70). 100 + 700 + 200 = 1000.
    df.loc[df["district_code"] == "63000010001", "people_age_010_m"] = 100.0
    df.loc[df["district_code"] == "63000010001", "people_age_040_m"] = 700.0
    df.loc[df["district_code"] == "63000010001", "people_age_070_m"] = 200.0

    # Village B (63000010002, people_total=2000): 200 kids (age 5), 1600
    # adults (age 30), 200 elderly (age 80). 200 + 1600 + 200 = 2000.
    df.loc[df["district_code"] == "63000010002", "people_age_005_f"] = 200.0
    df.loc[df["district_code"] == "63000010002", "people_age_030_f"] = 1600.0
    df.loc[df["district_code"] == "63000010002", "people_age_080_f"] = 200.0

    # Village C (65000010001, people_total=5000): 500 kids (age 2), 4000
    # adults (age 50), 500 elderly (age 90). 500 + 4000 + 500 = 5000.
    df.loc[df["district_code"] == "65000010001", "people_age_002_m"] = 500.0
    df.loc[df["district_code"] == "65000010001", "people_age_050_m"] = 4000.0
    df.loc[df["district_code"] == "65000010001", "people_age_090_f"] = 500.0

    return df


def _fake_merged_villages_with_ages() -> pd.DataFrame:
    df = _fake_villages().merge(_fake_households_with_ages(), on="district_code")
    indig_cols = [
        "aborigine_plain_total_m",
        "aborigine_plain_total_f",
        "aborigine_mountain_total_m",
        "aborigine_mountain_total_f",
    ]
    df["indigenous_total"] = df[indig_cols].sum(axis=1)
    from pycensus.countries.taiwan import api

    for suffix in api.AGE_BUCKET_SUFFIXES:
        m_col, f_col = f"people_age_{suffix}_m", f"people_age_{suffix}_f"
        df[f"people_age_{suffix}_total"] = df[m_col] + df[f_col]
    return df


class TestDerivedAgeColumns:
    def test_add_derived_age_columns_village_level(self):
        out = loader._aggregate_to_level(_fake_merged_villages_with_ages(), "village", None)
        row_a = out[out["GEOID"] == "63000010001"].iloc[0]
        assert row_a["under18_total"] == 100.0
        assert row_a["adult_total"] == 900.0
        assert row_a["over65_total"] == 200.0
        assert row_a["median_age"] == 40.0  # cumulative 50% falls in the age-40 bucket

    def test_add_derived_age_columns_sums_correctly_at_district_level(self):
        # District 63000010 combines villages A (100/700/200 @ 1000 total)
        # and B (200/1600/200 @ 2000 total) -- under18/adult/over65 must be
        # additive sums-of-sums.
        out = loader._aggregate_to_level(_fake_merged_villages_with_ages(), "district", None)
        row = out[out["GEOID"] == "63000010"].iloc[0]
        assert row["under18_total"] == 300.0
        assert row["adult_total"] == 2700.0
        assert row["over65_total"] == 400.0
        # adultPopulation (18+) already includes over65Population (65+) --
        # only under18 + adult (not + over65 again) reproduces the total.
        assert row["under18_total"] + row["adult_total"] == row["people_total"]

    def test_median_age_computed_from_summed_distribution_not_averaged_medians(self):
        # District-level median must come from the *combined* age
        # distribution (village A's 1000 people + village B's 2000
        # people), not from averaging village A's median (40) and village
        # B's median (30) -- a naive average would give 35, but the real
        # population-weighted combined median (2200 of 3000 people at or
        # below age 30, past the 1500-person halfway point) is 30.
        out = loader._aggregate_to_level(_fake_merged_villages_with_ages(), "district", None)
        row = out[out["GEOID"] == "63000010"].iloc[0]
        assert row["median_age"] == 30.0

    def test_add_derived_age_columns_omitted_without_full_age_bucket_set(self):
        # Without every age-bucket column present (e.g. plain ODRP013-only
        # data), _add_derived_age_columns must no-op rather than fabricate
        # partial totals.
        out = loader._aggregate_to_level(_fake_merged_villages(), "village", None)
        assert "under18_total" not in out.columns
        assert "median_age" not in out.columns


class TestFetchMissingAgeFields:
    @pytest.fixture(autouse=True)
    def patch_network(self, monkeypatch):
        import pycensus.countries.taiwan.api as api_mod

        monkeypatch.setattr(api_mod, "fetch_resident_population", lambda yyymm, raw_cache_path=None, timeout=60: _fake_villages())
        monkeypatch.setattr(loader.api, "fetch_resident_population", lambda yyymm, raw_cache_path=None, timeout=60: _fake_villages())
        monkeypatch.setattr(
            api_mod, "fetch_village_households", lambda yyymm, raw_cache_path=None, timeout=60: _fake_households_with_ages()
        )
        monkeypatch.setattr(
            loader.api, "fetch_village_households", lambda yyymm, raw_cache_path=None, timeout=60: _fake_households_with_ages()
        )

    def test_fetch_missing_age_fields_county_city(self, tmp_path):
        cols = [SCHEMA.prefixed(n) for n in SCHEMA.columns]
        df = loader._fetch_missing(cols, "county_city", "63000", "11407", str(tmp_path))
        assert df["GEOID"].iloc[0] == "63000"
        assert df["moi_under18Population"].iloc[0] == 300.0
        assert df["moi_adultPopulation"].iloc[0] == 2700.0
        assert df["moi_over65Population"].iloc[0] == 400.0
        assert df["moi_medianAge"].iloc[0] == 30.0
