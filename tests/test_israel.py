"""Tests for pycensus.israel: constants, schema, geography, and the CBS loader.

Technical aspects:
    Mirrors ``tests/test_mexico.py``'s pattern: real network calls
    (:mod:`pycensus.countries.israel.arcgis`) are monkeypatched out with small
    synthetic responses so the suite stays offline and fast. The real,
    live CBS/iplan ArcGIS FeatureServer endpoints were verified manually
    during development (see the pyCensus schema redesign memory) --
    SETL_CODE=9000 (Be'er Sheva) returning real ``pop_approx=217580.0``,
    ``hh_total_approx=81560``, real jurisdiction polygon geometry
    (bounds roughly lon 34.73-34.85, lat 31.19-31.32, entirely within the
    Negev/Southern district, nowhere near the West Bank), and the iplan
    jurisdiction layer's ``Machoz`` field never returning a West Bank
    value -- but that live verification isn't re-run here.
"""

from __future__ import annotations

import geopandas as gpd
import pytest
from shapely.geometry import box

from pycensus.countries.israel import arcgis, constants, geography, utils
from pycensus.countries.israel.cbs import loader
from pycensus.countries.israel.cbs.schema import SCHEMA


class TestConstants:
    def test_district_codes_exclude_west_bank(self):
        # Code "7" (Judea and Samaria / West Bank) must never appear.
        assert "7" not in constants.DISTRICT_CODES
        assert len(constants.DISTRICT_CODES) == 6

    def test_district_code_lookup(self):
        assert constants.district_code("Southern (Darom)") == "6"
        assert constants.district_code("6") == "6"
        assert constants.district_code("SOUTH") == "6"

    def test_machoz_mapping_excludes_west_bank(self):
        assert "יהודה ושומרון" not in constants.MACHOZ_TO_DISTRICT_CODE
        assert set(constants.MACHOZ_TO_DISTRICT_CODE.values()) == set(constants.DISTRICT_CODES)

    def test_excluded_machoz_defensive_list_present(self):
        assert "יהודה ושומרון" in constants.EXCLUDED_MACHOZ

    def test_real_arcgis_urls_are_https(self):
        assert constants.STAT_AREAS_2022_URL.startswith("https://")
        assert constants.CENSUS_SETL_2022_URL.startswith("https://")
        assert constants.IPLAN_JURISDICTION_URL.startswith("https://")


class TestSchema:
    def test_schema_has_prefix(self):
        assert SCHEMA.prefix == "cbs"

    def test_schema_has_columns(self):
        assert len(SCHEMA.columns) > 0

    def test_essential_columns_exist(self):
        for col in ["population", "households", "populationDensity", "ageMedian"]:
            assert col in SCHEMA.columns, f"Missing essential column: {col}"

    def test_column_codes_match_real_arcgis_field_names(self):
        """Regression guard: verified live against CBS's ArcGIS-hosted
        census_2022_setl_all_2021 layer for SETL_CODE=9000 (Be'er Sheva),
        which really returns these exact field names."""
        assert SCHEMA.columns["population"].codes == ["pop_approx"]
        assert SCHEMA.columns["households"].codes == ["hh_total_approx"]
        assert SCHEMA.columns["populationDensity"].codes == ["pop_density"]
        assert SCHEMA.columns["ageMedian"].codes == ["age_median"]
        assert SCHEMA.columns["sexRatio"].codes == ["sexRatio"]

    def test_no_fabricated_fields_survive(self):
        """Earlier versions of this schema had ~90 fields (religion
        breakdown by country of origin, immigration by decade,
        disabilities, veteran status, ...) with codes like 'POP_JEWISH'/
        'POP_ARAB_DRUZE' that don't exist in any real, verified CBS
        source. All were removed; only fields verified against the real
        downloaded feature attributes remain."""
        fabricated_codes = {
            "POP_JEWISH", "POP_ARAB", "POP_ARAB_DRUZE", "POP_MUSLIM", "POP_CHRST",
            "POP_DISABILITY", "POP_VETERANS", "POP_IMM_1948_1959", "TOTAL_POP", "TOTAL_HH",
        }
        all_codes = {code for col in SCHEMA.columns.values() for code in col.codes}
        assert not (fabricated_codes & all_codes)

    def test_schema_prefixed_columns(self):
        assert SCHEMA.prefixed("population") == "cbs_population"

    def test_schema_strip_prefix(self):
        assert SCHEMA.strip_prefix("population") == "population"

    def test_2026_08_22_new_fields_match_real_arcgis_field_names(self):
        """Regression guard for the age/employment/household fields added
        2026-08-22, verified live against the same `census_2022_setl_all_2021`
        layer (SETL_CODE=9000, Be'er Sheva) and the `מפקד_2022`
        statistical-area layer (SEMEL_YISHUV=9000)."""
        expected_codes = {
            "institutionalizedResidentRate": ["inst_pcnt"],
            "ageMedianMale": ["m_age_median"],
            "ageMedianFemale": ["w_age_median"],
            "laborForceParticipationRate": ["WrkY_pcnt"],
            "workHoursMeanWeekly": ["HrsWrkWk_avg"],
            "selfEmployedMedianAnnualWage": ["SelfEmployedAnnual_medWage"],
            "topWageDecileEmployeesRate": ["EmployeesWage_decile9Up"],
            "householdsWithYoungChildrenRate": ["hh0_5_pcnt"],
            "householdsWithYoungAdultsRate": ["hh18_24_pcnt"],
            "childrenBornMean": ["ChldBorn_avg"],
            "householdsWithParkingRate": ["Parking_pcnt"],
        }
        for name, codes in expected_codes.items():
            assert name in SCHEMA.columns, f"Missing new column: {name}"
            assert SCHEMA.columns[name].codes == codes


class TestGeography:
    def test_implemented_levels(self):
        assert set(geography.IMPLEMENTED_LEVELS) == {"nation", "district", "locality", "statistical_area"}

    def test_unimplemented_level_raises(self):
        with pytest.raises(ValueError):
            geography.load_boundaries("subdistrict", region="11")



def _fake_locality_feature(cr_lamas="9000", machoz="דרום"):
    return {
        "attributes": {"CR_LAMAS": cr_lamas, "Muni_Eng": "Be'er Sheva", "Machoz": machoz},
        "geometry": {"rings": [[[34.7, 31.2], [34.8, 31.2], [34.8, 31.3], [34.7, 31.3], [34.7, 31.2]]]},
    }


def _fake_census_feature(setl_code=9000):
    return {
        "attributes": {
            "SETL_CODE": setl_code,
            "ENG_NAME": "BE'ER SHEVA",
            "pop_approx": 217580.0,
            "hh_total_approx": 81560.0,
            "pop_density": 7202.2,
            "age_median": 34.0,
            "sexRatio": 97.1,
            "change_pcnt": 10.7,
            "age0_19_pcnt": 27.3,
            "age20_64_pcnt": 57.0,
            "age65_pcnt": 15.7,
            "DependencyRatio": 754.4,
            "size_avg": 2.6,
            "Empl_pcnt": 91.9,
            "SelfEmpl_pcnt": 8.0,
            "employeesAnnual_medWage": 95300.0,
            "WrkOutLoc_pcnt": 26.3,
            "AcadmCert_pcnt": 23.3,
            "own_pcnt": 57.6,
            "rent_pcnt": 36.7,
            "Vehicle0_pcnt": 33.3,
            "Vehicle2up_pcnt": 20.7,
            "Foreign_pcnt": 1.6,
        }
    }


def _fake_stat_area_boundary_feature(stat_id):
    return {
        "attributes": {
            "YISHUV_STAT_2022": stat_id,
            "SEMEL_YISHUV": 9000,
            "SHEM_YISHUV_ENGLISH": "BE'ER SHEVA",
        },
        "geometry": {"rings": [[[34.7, 31.2], [34.71, 31.2], [34.71, 31.21], [34.7, 31.21], [34.7, 31.2]]]},
    }


def _fake_stat_area_census_feature(stat_id, pop):
    return {
        "attributes": {
            "YISHUV_STAT_2022": stat_id,
            "SEMEL_YISHUV": 9000,
            "STAT_2022": stat_id % 1000,
            "pop_approx": pop,
            "hh_total_approx": pop / 2.6,
            "pop_density": 7202.2,
            "age_median": 34.0,
            "sexRatio": 97.1,
        }
    }


# Two synthetic statistical areas within Be'er Sheva (SEMEL_YISHUV=9000)
# whose pop_approx values sum to 217580 -- matching the real, verified
# locality-level total (see module docstring / cbs.loader docstring for
# the live cross-check that motivated this).
_STAT_AREA_IDS = [90000111, 90000112]
_STAT_AREA_POPS = [108790.0, 108790.0]


class TestLoader:
    """Real ArcGIS network calls are monkeypatched out (see module docstring)."""

    @pytest.fixture(autouse=True)
    def patch_network(self, monkeypatch):
        def fake_query_features(url, where="1=1", out_fields="*", return_geometry=True, page_size=1000):
            if url == constants.IPLAN_JURISDICTION_URL:
                return [_fake_locality_feature()]
            if url == constants.CENSUS_SETL_2022_URL:
                return [_fake_census_feature()]
            if url == constants.STAT_AREAS_2022_URL:
                return [_fake_stat_area_boundary_feature(sid) for sid in _STAT_AREA_IDS]
            if url == constants.CENSUS_STAT_2022_URL:
                return [
                    _fake_stat_area_census_feature(sid, pop)
                    for sid, pop in zip(_STAT_AREA_IDS, _STAT_AREA_POPS)
                ]
            return []

        monkeypatch.setattr(arcgis, "query_features", fake_query_features)
        monkeypatch.setattr(geography.arcgis, "query_features", fake_query_features)

    def test_block_level_falls_back_to_statistical_area(self):
        # "block" has no real CBS block-level boundary source, but
        # constants.LEVEL_FALLBACK maps it to "statistical_area" (the finest
        # real implemented level) rather than raising -- every global level
        # must resolve to *something* real, per
        # tests/test_global_levels_coverage.py's cross-country guard.
        gdf = geography.load_boundaries("block", region="9000")
        assert gdf is not None and not gdf.empty

    def test_load_locality_level_returns_real_verified_columns(self, tmp_path):
        gdf = loader.load(localities="9000", level="locality", cache_dir=str(tmp_path), cache=False)
        assert "population" in gdf.columns
        assert gdf["population"].iloc[0] == 217580.0
        assert gdf["households"].iloc[0] == 81560.0
        assert gdf.geometry.name == "geometry"
        assert gdf.crs is not None

    def test_load_derives_foreign_born_population_count(self, tmp_path):
        """foreignBornPopulation has no native CBS field (empty 'codes') --
        it's derived by loader.load() as round(Foreign_pcnt/100 * pop_approx).
        Fixture: Foreign_pcnt=1.6, pop_approx=217580.0 -> 1.6/100*217580 = 3481.28 -> 3481."""
        gdf = loader.load(localities="9000", level="locality", cache_dir=str(tmp_path), cache=False)
        assert "foreignBornPopulation" in gdf.columns
        assert gdf["foreignBornPopulation"].iloc[0] == 3481.0

    def test_load_raises_without_localities_or_aoi(self, tmp_path):
        with pytest.raises(ValueError):
            loader.load(level="locality", cache_dir=str(tmp_path))

    def test_load_unimplemented_level_raises(self, tmp_path):
        with pytest.raises(ValueError):
            loader.load(localities="9000", level="district", cache_dir=str(tmp_path))

    def test_load_writes_geoparquet_cache_file(self, tmp_path):
        loader.load(localities="9000", level="locality", cache_dir=str(tmp_path))
        cache_file = tmp_path / "israel" / "locality" / "9000.parquet"
        assert cache_file.exists()

        cached = gpd.read_parquet(cache_file)
        assert cached.crs is not None
        # `apply_canonical_names` runs before the cache is written, so
        # the cached file already has bare canonical names too.
        assert "population" in cached.columns
        assert len(cached) == 1

    def test_load_statistical_area_level_returns_real_verified_columns(self, tmp_path):
        gdf = loader.load(localities="9000", level="statistical_area", cache_dir=str(tmp_path), cache=False)
        assert "population" in gdf.columns
        assert len(gdf) == len(_STAT_AREA_IDS)
        assert set(gdf["GEOID"]) == {str(sid) for sid in _STAT_AREA_IDS}
        assert gdf.geometry.name == "geometry"
        assert gdf.crs is not None

    def test_load_statistical_area_sums_to_locality_total(self, tmp_path):
        """Cross-check: statistical-area pop_approx sums to the verified
        locality-level total for Be'er Sheva (217580, see module docstring)."""
        gdf = loader.load(localities="9000", level="statistical_area", cache_dir=str(tmp_path), cache=False)
        assert gdf["population"].sum() == 217580.0

    def test_load_statistical_area_writes_geoparquet_cache_file(self, tmp_path):
        loader.load(localities="9000", level="statistical_area", cache_dir=str(tmp_path))
        cache_file = tmp_path / "israel" / "statistical_area" / "9000.parquet"
        assert cache_file.exists()

        cached = gpd.read_parquet(cache_file)
        assert cached.crs is not None
        # `apply_canonical_names` runs before the cache is written, so
        # the cached file already has bare canonical names too.
        assert "population" in cached.columns
        assert len(cached) == len(_STAT_AREA_IDS)

    def test_load_tract_resolves_to_statistical_area(self, tmp_path):
        """LEVEL_FALLBACK maps the generic 'tract' level to statistical_area."""
        gdf = loader.load(localities="9000", level="tract", cache_dir=str(tmp_path), cache=False)
        assert len(gdf) == len(_STAT_AREA_IDS)
        assert gdf["population"].sum() == 217580.0


class TestUtils:
    def test_locality_code_passthrough_numeric(self):
        assert utils.locality_code("9000") == "9000"
        assert utils.locality_code(9000) == "9000"

    def test_locality_code_lookup_by_name(self, monkeypatch):
        def fake_query_features(url, where="1=1", out_fields="*", return_geometry=True, page_size=1000):
            return [_fake_census_feature()]

        monkeypatch.setattr(arcgis, "query_features", fake_query_features)
        assert utils.locality_code("Be'er Sheva") == "9000"


class TestAccessor:
    def test_accessor_registered(self):
        poly_gdf = gpd.GeoDataFrame(
            {"GEOID": ["9000"], "population": [217580], "households": [81560]},
            geometry=[box(0, 0, 1, 1)],
            crs="EPSG:4326",
        )
        assert hasattr(poly_gdf, "cbs")
        assert poly_gdf.cbs["population"].tolist() == [217580]


@pytest.mark.network
def test_real_cbs_new_fields_for_beersheba_locality():
    """Hits the live `census_2022_setl_all_2021` ArcGIS FeatureServer layer
    (no API key). Verified 2026-08-22: SETL_CODE=9000 (Be'er Sheva) returns
    inst_pcnt=2.9, m_age_median=32, w_age_median=35, WrkY_pcnt=67.2,
    HrsWrkWk_avg=38.2, hh0_5_pcnt=16.5, hh18_24_pcnt=21, ChldBorn_avg=1.9,
    Parking_pcnt=62.9, EmployeesWage_decile9Up=15.6,
    SelfEmployedAnnual_medWage=69800 -- all plausible for a mid-size Israeli
    city (median ages in the low-to-mid 30s, ~2/3 labour-force participation,
    ~38hr work week)."""
    gdf = loader.load(localities="9000", level="locality", cache=False)
    row = gdf.iloc[0]
    # These new feature names have no global_schema.json equivalent, so
    # apply_canonical_names leaves them "cbs_"-prefixed (see canonical.py).
    assert row["cbs_institutionalizedResidentRate"] == pytest.approx(2.9)
    assert row["cbs_ageMedianMale"] == pytest.approx(32)
    assert row["cbs_ageMedianFemale"] == pytest.approx(35)
    assert row["cbs_laborForceParticipationRate"] == pytest.approx(67.2)
    assert row["cbs_workHoursMeanWeekly"] == pytest.approx(38.2)
    assert row["cbs_householdsWithYoungChildrenRate"] == pytest.approx(16.5)
    assert row["cbs_householdsWithYoungAdultsRate"] == pytest.approx(21)
    assert row["cbs_childrenBornMean"] == pytest.approx(1.9)
    assert row["cbs_householdsWithParkingRate"] == pytest.approx(62.9)
    assert row["cbs_topWageDecileEmployeesRate"] == pytest.approx(15.6)
    assert row["cbs_selfEmployedMedianAnnualWage"] == pytest.approx(69800)
    # foreignBornPopulation is derived (round(Foreign_pcnt/100 * pop_approx))
    # -- see cbs_schema.json's docstring and cbs/loader.py's load(). Live
    # 2026-08-23: Foreign_pcnt=1.6, pop_approx=217580.00000000003.
    assert row["foreignBornPopulation"] == pytest.approx(3481, abs=1)


@pytest.mark.network
def test_real_cbs_has_no_foreign_born_count_field_or_workplace_jobs_field():
    """Confirms (rather than assumes) that CBS's live ArcGIS layers still
    have no real foreign-resident COUNT field (only the Foreign_pcnt rate)
    and no workplace-location jobs field -- the basis for
    foreignBornPopulation being derived (not fetched) and for no Israel
    jobs-by-workplace source being wired in CS_transitLOS's
    ISRAEL_KEEP_COLUMNS. Enumerates both layers' real field lists live via
    a plain '?f=json' metadata query (no API key), same as every other
    live check in this module."""
    import json
    import urllib.parse
    import urllib.request

    for url in (constants.CENSUS_SETL_2022_URL, constants.CENSUS_STAT_2022_URL):
        base, service = url.split("/arcgis/rest/services/", 1)
        meta_url = base + "/arcgis/rest/services/" + urllib.parse.quote(service) + "?f=json"
        with urllib.request.urlopen(meta_url, timeout=15) as resp:
            data = json.load(resp)
        fields = {f["name"] for f in data.get("fields", [])}
        assert "Foreign_pcnt" in fields
        no_count_or_workplace_field = {
            f
            for f in fields
            if ("oreign" in f or "job" in f.lower() or "workplace" in f.lower())
            and f != "Foreign_pcnt"
            and "WrkOutLoc" not in f  # residence-based "works outside locality" rate, not a jobs count
        }
        assert not no_count_or_workplace_field, f"unexpected new field(s) on {url}: {no_count_or_workplace_field}"


@pytest.mark.network
def test_real_cbs_new_fields_present_at_statistical_area_level():
    """Same live layer as the locality test, but the `מפקד_2022`
    statistical-area FeatureServer -- confirms the new fields are real at
    statistical_area granularity too, not just locality. Verified
    2026-08-22: statistical area 90000111 (within Be'er Sheva,
    SEMEL_YISHUV=9000) returns pop_approx=2260, WrkY_pcnt=55.2,
    hh0_5_pcnt=11.3, m_age_median=34, w_age_median=35, ChldBorn_avg=1.8 --
    plausible values distinct from the locality-wide average, confirming
    real neighborhood-level variation rather than a locality value copied
    down."""
    gdf = loader.load(localities="9000", level="statistical_area", cache=False)
    assert len(gdf) > 1
    assert gdf["cbs_laborForceParticipationRate"].notna().any()
    assert gdf["cbs_childrenBornMean"].notna().any()
    # Real per-area variation, not one flat locality-wide value repeated.
    assert gdf["cbs_ageMedianFemale"].nunique() > 1


@pytest.mark.network
def test_no_finer_real_population_geography_below_statistical_area():
    """Task 1 finding, recorded as a live regression check: CBS's own
    'שכונות' (neighborhoods) ArcGIS layer -- the only real, live,
    finer-than-statistical_area boundary layer found on either CBS's
    (JcXY3lLZni6BK4El) or the general municipal-GIS
    (b6zSqPB0TQc3mBgU) ArcGIS Online orgs used elsewhere in this module --
    carries only locality/neighborhood codes and names, no population or
    demographic attribute of any kind. Verified live 2026-08-22: its field
    list is exactly {FID, shchuna, yishuv, nyb_name, Shape__Area,
    Shape__Length}. statistical_area remains pyCensus Israel's real ceiling
    for finer-than-locality geography with actual demographic data."""
    import urllib.request

    url = (
        "https://services.arcgis.com/b6zSqPB0TQc3mBgU/arcgis/rest/services/"
        "%D7%A9%D7%9B%D7%95%D7%A0%D7%95%D7%AA/FeatureServer/0?f=json"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    import json as _json

    data = _json.load(urllib.request.urlopen(req, timeout=30))
    field_names = {f["name"] for f in data.get("fields", [])}
    population_like = {
        n for n in field_names if "pop" in n.lower() or "hh" in n.lower() or "household" in n.lower()
    }
    assert not population_like, f"Unexpected population field(s) found: {population_like}"
