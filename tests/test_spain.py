"""Tests for pycensus.spain: constants, schema, geography, and the INE Padron loader.

Technical aspects:
    Network-touching functions (:func:`pycensus.countries.spain.api.fetch_padron_municipios`,
    :func:`pycensus.countries.spain.geography._load_spain_municipalities`) are
    monkeypatched out with small synthetic frames, same pattern as
    ``tests/test_mexico.py``. The real INE Tempus API and GISCO LAU
    download were verified manually against the live network during
    development:
        - ``GET https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/29005?nult=1&tip=AM``
          returns real per-municipality population with real INE codes
          (e.g. ``"44001"`` == Ababuj, Teruel, population 73) and the
          nationwide total sums to 49,114,494 (2025) / 47,385,107 when
          cross-checked against 2021 via INE table 2915's "Total Nacional".
        - GISCO's LAU 2021 zip (``ref-lau-2021-01m.geojson.zip``) filtered
          to ``CNTR_CODE='ES'`` gives 8,131 real municipality polygons
          whose ``LAU_ID`` are the same INE codes, and summing their
          ``POP_2021`` also gives exactly 47,385,107.
        - Loading Madrid province (INE code "28") through the real,
          un-mocked pipeline returned population 7,137,031 -- matching
          Comunidad de Madrid's well-documented ~7.1M 2025 population.
    See the pyCensus schema redesign memory for the exact commands.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from pycensus.countries.spain import constants, geography, utils
from pycensus.countries.spain.ine import loader
from pycensus.countries.spain.ine.schema import SCHEMA


class TestConstants:
    def test_autonomous_community_codes_count(self):
        assert len(constants.AUTONOMOUS_COMMUNITY_CODES) == 19

    def test_province_codes_count(self):
        assert len(constants.PROVINCE_CODES) == 52

    def test_province_code_matches_real_ine_codification(self):
        """Regression guard: an earlier version of this file had shifted/
        fabricated province codes (La Coruña=23, La Rioja=24, and was
        missing Asturias/Cantabria entirely) -- verified wrong against
        GISCO's real LAU_ID codes (e.g. "15030" is A Coruña city, in
        province 15, not 23)."""
        assert constants.PROVINCE_CODES["15"] == "La Coruña"
        assert constants.PROVINCE_CODES["26"] == "La Rioja"
        assert constants.PROVINCE_CODES["33"] == "Asturias"
        assert constants.PROVINCE_CODES["39"] == "Cantabria"
        assert constants.PROVINCE_CODES["51"] == "Ceuta"
        assert constants.PROVINCE_CODES["52"] == "Melilla"

    def test_autonomous_community_provinces_cover_every_province_exactly_once(self):
        seen = {}
        for ac, provs in constants.AUTONOMOUS_COMMUNITY_PROVINCES.items():
            for p in provs:
                seen.setdefault(p, []).append(ac)
        assert set(seen) == set(constants.PROVINCE_CODES)
        assert all(len(acs) == 1 for acs in seen.values())

    def test_level_fallback(self):
        assert constants.LEVEL_FALLBACK["state"] == "autonomous_community"
        assert constants.LEVEL_FALLBACK["county"] == "municipality"
        assert constants.LEVEL_FALLBACK["tract"] == "section"
        assert constants.LEVEL_FALLBACK["blockgroup"] == "section"

    def test_latest_year(self):
        assert constants.LATEST_YEAR["geography"] == 2021


class TestUtils:
    def test_province_code_lookup(self):
        assert utils.province_code("Madrid") == "28"
        assert utils.province_code("28") == "28"

    def test_autonomous_community_code_lookup(self):
        assert utils.autonomous_community_code("Madrid (Comunidad de Madrid)") == "13"
        assert utils.autonomous_community_code("13") == "13"


class TestSchema:
    def test_schema_has_prefix(self):
        assert SCHEMA.prefix == "ine"

    def test_essential_columns_exist(self):
        for col in ["population", "malePopulation", "femalePopulation"]:
            assert col in SCHEMA.columns

    def test_column_codes_match_real_padron_fields(self):
        assert SCHEMA.columns["population"].codes == ["TOTAL_POB"]
        assert SCHEMA.columns["malePopulation"].codes == ["POB_HOMBRES"]
        assert SCHEMA.columns["femalePopulation"].codes == ["POB_MUJERES"]

    def test_schema_prefixed_columns(self):
        assert SCHEMA.prefixed("population") == "ine_population"

    def test_schema_relative_to(self):
        # relative_to must be the unprefixed logical feature name (see
        # ColumnSchema.relative_to/prefixed) -- "spain_ine_population" was a
        # dangling reference that never matched any feature_name and was
        # fixed to "population".
        assert SCHEMA.columns["malePopulation"].relative_to == "population"
        assert "population" in SCHEMA.columns


class TestGeography:
    def test_implemented_levels(self):
        assert set(geography.IMPLEMENTED_LEVELS) == {
            "nation",
            "autonomous_community",
            "province",
            "municipality",
            "section",
        }

    def test_unimplemented_level_raises(self):
        with pytest.raises(NotImplementedError):
            geography.load_boundaries("district", region="28001", data_dir="/nonexistent")

    def test_section_level_without_region_raises(self):
        with pytest.raises(ValueError):
            geography.load_boundaries("section", region=None, data_dir="/nonexistent")


def _fake_municipalities() -> gpd.GeoDataFrame:
    """Two municipalities in province 28 (Madrid), one in province 08 (Barcelona)."""
    return gpd.GeoDataFrame(
        {
            "GEOID": ["28001", "28002", "08001"],
            "LAU_NAME": ["A", "B", "C"],
            "POP_2021": [100, 200, 300],
        },
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1), box(2, 0, 3, 1)],
        crs=4326,
    )


def _fake_padron() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "GEOID": ["28001", "28002", "08001"],
            "year": [2025, 2025, 2025],
            "TOTAL_POB": [1000.0, 2000.0, 5000.0],
            "POB_HOMBRES": [480.0, 990.0, 2400.0],
            "POB_MUJERES": [520.0, 1010.0, 2600.0],
        }
    )


class TestGeographyWithFakeMunicipalities:
    @pytest.fixture(autouse=True)
    def patch_network(self, monkeypatch):
        monkeypatch.setattr(geography, "_load_spain_municipalities", lambda data_dir=None: _fake_municipalities())

    def test_municipality_level_all(self):
        gdf = geography.load_boundaries("municipality")
        assert set(gdf["GEOID"]) == {"28001", "28002", "08001"}

    def test_province_level_dissolves_municipalities(self):
        gdf = geography.load_boundaries("province", region="28")
        assert len(gdf) == 1
        assert gdf["GEOID"].iloc[0] == "28"

    def test_autonomous_community_level_dissolves_provinces(self):
        gdf = geography.load_boundaries("autonomous_community", region="13")  # Madrid AC
        assert len(gdf) == 1
        assert gdf["GEOID"].iloc[0] == "13"

    def test_nation_level_dissolves_everything(self):
        gdf = geography.load_boundaries("nation")
        assert len(gdf) == 1
        assert gdf["GEOID"].iloc[0] == "ES"


class TestLoader:
    """INE's own network call (Tempus API) and GISCO's are monkeypatched out."""

    @pytest.fixture(autouse=True)
    def patch_network(self, monkeypatch):
        import pycensus.countries.spain.api as api_mod
        import pycensus.countries.spain.ine.loader as loader_mod

        monkeypatch.setattr(api_mod, "fetch_padron_municipios", lambda raw_cache_path=None, timeout=120: _fake_padron())
        monkeypatch.setattr(loader_mod.api, "fetch_padron_municipios", lambda raw_cache_path=None, timeout=120: _fake_padron())
        monkeypatch.setattr(geography, "_load_spain_municipalities", lambda data_dir=None: _fake_municipalities())
        monkeypatch.setattr(loader_mod.geography, "_load_spain_municipalities", lambda data_dir=None: _fake_municipalities())
        monkeypatch.setattr(
            loader_mod.geography,
            "_municipality_codes_in_region",
            geography._municipality_codes_in_region,
        )

    def test_load_municipality_level(self, tmp_path):
        gdf = loader.load(regions="28001", level="municipality", cache_dir=str(tmp_path), data_dir=str(tmp_path))
        assert gdf["population"].iloc[0] == 1000.0
        assert gdf["malePopulation"].iloc[0] == 480.0
        assert gdf["femalePopulation"].iloc[0] == 520.0

    def test_load_province_level_sums_municipalities(self, tmp_path):
        gdf = loader.load(regions="28", level="province", cache_dir=str(tmp_path), data_dir=str(tmp_path))
        assert len(gdf) == 1
        assert gdf["population"].iloc[0] == 3000.0  # 1000 + 2000

    def test_load_raises_without_regions_or_aoi(self, tmp_path):
        with pytest.raises(ValueError):
            loader.load(level="province", cache_dir=str(tmp_path))

    def test_load_writes_geoparquet_cache_file(self, tmp_path):
        loader.load(regions="28", level="province", cache_dir=str(tmp_path), data_dir=str(tmp_path))
        cache_file = tmp_path / "spain" / "province" / "28.parquet"
        assert cache_file.exists()
        cached = gpd.read_parquet(cache_file)
        # The cache stores the source-prefixed column names;
        # `apply_canonical_names` is only applied to the returned frame.
        assert "ine_population" in cached.columns

    def test_load_second_call_does_not_refetch(self, monkeypatch, tmp_path):
        calls = {"n": 0}

        def counting_fetch(raw_cache_path=None, timeout=120):
            calls["n"] += 1
            return _fake_padron()

        import pycensus.countries.spain.ine.loader as loader_mod

        monkeypatch.setattr(loader_mod.api, "fetch_padron_municipios", counting_fetch)
        loader.load(regions="28", level="province", cache_dir=str(tmp_path), data_dir=str(tmp_path))
        loader.load(regions="28", level="province", cache_dir=str(tmp_path), data_dir=str(tmp_path))
        assert calls["n"] == 1


def _section_geoid(province_code: str, n: int) -> str:
    """CPRO(2) + CMUN(3) + CDIS(2) + CSEC(3) = 10-digit CUSEC-format code."""
    return f"{province_code}001" + "01" + f"{n:03d}"


def _fake_sections(province_code: str) -> gpd.GeoDataFrame:
    """Two census sections within one fake province, matching CUSEC format."""
    return gpd.GeoDataFrame(
        {
            "GEOID": [_section_geoid(province_code, n) for n in (1, 2)],
            "CPRO": [province_code, province_code],
        },
        geometry=[box(0, 0, 0.5, 1), box(0.5, 0, 1, 1)],
        crs=4326,
    )


def _fake_secciones_padron(province_code: str) -> pd.DataFrame:
    geoids = [_section_geoid(province_code, n) for n in (1, 2)]
    return pd.DataFrame(
        {
            "GEOID": geoids,
            "TOTAL_POB": [150.0, 250.0],
            "POB_HOMBRES": [70.0, 120.0],
            "POB_MUJERES": [80.0, 130.0],
        }
    )


class TestGeographySections:
    @pytest.fixture(autouse=True)
    def patch_network(self, monkeypatch):
        monkeypatch.setattr(
            geography, "_load_spain_sections_for_province", lambda province_code, data_dir=None: _fake_sections(province_code)
        )

    def test_section_level_requires_region_but_then_fetches_per_province(self):
        gdf = geography.load_boundaries("section", region="28")
        assert len(gdf) == 2
        assert all(g.startswith("28") for g in gdf["GEOID"])

    def test_section_level_resolves_ac_to_multiple_provinces(self, monkeypatch):
        calls = []

        def fake_sections(province_code, data_dir=None):
            calls.append(province_code)
            return _fake_sections(province_code)

        monkeypatch.setattr(geography, "_load_spain_sections_for_province", fake_sections)
        geography.load_boundaries("section", region="16")  # País Vasco AC -> 3 provinces
        assert calls == ["01", "20", "48"]


class TestLoaderSections:
    """Section-level loader path: boundary + per-province population fetch are both mocked."""

    @pytest.fixture(autouse=True)
    def patch_network(self, monkeypatch):
        import pycensus.countries.spain.api as api_mod
        import pycensus.countries.spain.ine.loader as loader_mod

        monkeypatch.setattr(
            loader_mod.geography, "_load_spain_sections_for_province", lambda province_code, data_dir=None: _fake_sections(province_code)
        )
        monkeypatch.setattr(
            loader_mod.geography, "_province_codes_in_region", geography._province_codes_in_region
        )
        monkeypatch.setattr(
            api_mod,
            "fetch_padron_secciones",
            lambda province_code, year=2022, raw_cache_path=None, timeout=180: _fake_secciones_padron(province_code),
        )
        monkeypatch.setattr(
            loader_mod.api,
            "fetch_padron_secciones",
            lambda province_code, year=2022, raw_cache_path=None, timeout=180: _fake_secciones_padron(province_code),
        )

    def test_load_section_level(self, tmp_path):
        gdf = loader.load(regions="28", level="section", cache_dir=str(tmp_path), data_dir=str(tmp_path))
        assert len(gdf) == 2
        assert set(gdf["population"]) == {150.0, 250.0}

    def test_load_tract_falls_back_to_section(self, tmp_path):
        # "tract" has no native Spain level -- LEVEL_FALLBACK maps it to "section".
        gdf = loader.load(regions="28", level="tract", cache_dir=str(tmp_path), data_dir=str(tmp_path))
        assert len(gdf) == 2
        assert gdf["population"].sum() == 400.0


@pytest.mark.network
def test_real_ine_padron_secciones_gipuzkoa_matches_province_total():
    """Hits the live INE section-population CSV and section-boundary OGC API --
    no API key required. Verified 2026-08-20: summing 545 real Gipuzkoa
    (province '20') section rows for Sexo='Ambos Sexos'/Edad='Total' gives
    exactly 724,418, matching the file's own province-wide TOTAL row, and
    the boundary service returns 544 real 'SECCIONADO' (non-aggregate)
    polygons for the same province."""
    from pycensus.countries.spain import api, geography

    df = api.fetch_padron_secciones("20")
    assert len(df) > 500
    assert df["TOTAL_POB"].sum() == pytest.approx(724_418, abs=1)

    gdf = geography._load_spain_sections_for_province("20")
    assert len(gdf) > 500
    assert gdf.crs is not None
    assert gdf.crs.to_epsg() == 4326


@pytest.mark.network
def test_real_ine_padron_api_returns_verified_national_total():
    """Hits the live INE Tempus API -- no API key required. Skipped by
    default CI runs the same way tests/downloaders' BusMaps network test
    is (only run explicitly, e.g. ``pytest -m network``)."""
    from pycensus.countries.spain import api

    df = api.fetch_padron_municipios()
    assert len(df) > 8000
    # Spain's total population (padron) is well-documented public knowledge,
    # around 47-49 million in the mid-2020s -- a sanity range, not an exact
    # pin, since INE republishes a new "latest" year over time.
    total = df["TOTAL_POB"].sum()
    assert 46_000_000 < total < 51_000_000
