"""Tests for pycensus.euskadi: constants, schema, geography, and the (GISCO-backed) loader.

Technical aspects:
    Mirrors ``test_mexico.py``: the real network call
    (:func:`pycensus.countries.euskadi.geography._download_gisco_lau`, which pulls
    Eurostat/GISCO's ~65MB LAU 2021 GeoPackage) is monkeypatched out with a
    small synthetic GeoPackage covering three fake Araba/Bizkaia/Gipuzkoa
    municipalities. The real source was verified manually against the live
    network during development: downloading
    ``https://gisco-services.ec.europa.eu/distribution/v2/lau/gpkg/LAU_RG_01M_2021_4326.gpkg``
    and filtering to Spanish ``LAU_ID`` codes starting with "20" (Gipuzkoa)
    yields exactly 88 municipalities totalling ``POP_2021`` = 726,033 (a
    real, documented population figure for Gipuzkoa); "01" (Araba) yields
    51 municipalities / 333,626 people and "48" (Bizkaia) 112
    municipalities / 1,154,334 people -- both also match real documented
    totals. See ``pycensus/euskadi/geography.py``'s module docstring for
    the exact verification. Not re-run here, to keep the suite offline and
    fast like every other loader test in this repo.
"""

from __future__ import annotations

import geopandas as gpd
import pytest
from shapely.geometry import box

from pycensus.countries.euskadi import constants, geography, utils
from pycensus.countries.euskadi.eustat import loader
from pycensus.countries.euskadi.eustat.schema import SCHEMA


class TestConstants:
    def test_territory_codes(self):
        assert constants.TERRITORY_CODES == {"01": "Araba", "48": "Bizkaia", "20": "Gipuzkoa"}

    def test_territory_code_lookup(self):
        assert constants.territory_code("Gipuzkoa") == "20"
        assert constants.territory_code("gipuzkoa") == "20"
        assert constants.territory_code("20") == "20"
        assert constants.territory_code("GI") == "20"

    def test_territory_code_unknown_raises(self):
        with pytest.raises(ValueError):
            constants.territory_code("Nowhere")

    def test_level_fallback_has_no_dangling_targets(self):
        # Every fallback target must itself be a real implemented geometry
        # level (autonomous_community/territory/municipality) -- a dangling
        # target (e.g. the old "comarca"/"district" placeholder levels)
        # would silently break geography.load_boundaries for any caller
        # requesting a level via the fallback chain.
        from pycensus import geometry_levels

        for level in constants.LEVEL_FALLBACK:
            resolved = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK)
            assert resolved in geography.GEOMETRY_LEVELS


class TestSchema:
    def test_population_field_present_with_real_code(self):
        assert "population" in SCHEMA.columns
        assert SCHEMA.columns["population"].codes == ["POP_2021"]

    def test_only_real_verified_fields(self):
        # This schema was deliberately trimmed to only fields verified
        # against a real downloaded GISCO LAU file (see module docstring) --
        # guard against silently reintroducing fabricated fields.
        assert set(SCHEMA.columns) == {"population", "areaKm2", "populationDensity"}

    def test_prefix_is_eustat(self):
        assert SCHEMA.prefixed("population") == "eustat_population"


def _fake_gisco_gpkg(tmp_path):
    """Write a tiny synthetic GeoPackage shaped like the real GISCO LAU file."""
    rows = [
        {"CNTR_CODE": "ES", "LAU_ID": "20001", "LAU_NAME": "FakeMuni1", "POP_2021": 300.0, "AREA_KM2": 10.0},
        {"CNTR_CODE": "ES", "LAU_ID": "20002", "LAU_NAME": "FakeMuni2", "POP_2021": 700.0, "AREA_KM2": 5.0},
        {"CNTR_CODE": "ES", "LAU_ID": "01001", "LAU_NAME": "FakeAraba1", "POP_2021": 1000.0, "AREA_KM2": 20.0},
        {"CNTR_CODE": "ES", "LAU_ID": "48001", "LAU_NAME": "FakeBizkaia1", "POP_2021": 50.0, "AREA_KM2": 2.0},
    ]
    geoms = [
        box(-2.0, 43.0, -1.9, 43.1),
        box(-2.1, 43.0, -2.0, 43.1),
        box(-2.7, 42.9, -2.6, 43.0),
        box(-2.9, 43.2, -2.8, 43.3),
    ]
    gdf = gpd.GeoDataFrame(rows, geometry=geoms, crs=4326)
    path = tmp_path / "fake_gisco_lau.gpkg"
    gdf.to_file(path, driver="GPKG")
    return path


class TestGeography:
    def test_load_boundaries_municipality(self, tmp_path, monkeypatch):
        fake_path = _fake_gisco_gpkg(tmp_path)
        monkeypatch.setattr(geography, "_download_gisco_lau", lambda cache_dir=None: fake_path)

        gdf = geography.load_boundaries("municipality", region="Gipuzkoa")
        assert set(gdf["GEOID"]) == {"20001", "20002"}
        assert gdf.crs.to_epsg() == 4326

    def test_load_boundaries_territory_is_union(self, tmp_path, monkeypatch):
        fake_path = _fake_gisco_gpkg(tmp_path)
        monkeypatch.setattr(geography, "_download_gisco_lau", lambda cache_dir=None: fake_path)

        gdf = geography.load_boundaries("territory", region="Gipuzkoa")
        assert list(gdf["GEOID"]) == ["20"]
        assert gdf.geometry.iloc[0].area > 0

    def test_load_boundaries_unknown_level_raises(self):
        with pytest.raises(KeyError):
            geography.load_boundaries("nonexistent_level", region="20")

    def test_load_boundaries_wrong_year_raises(self):
        with pytest.raises(ValueError):
            geography.load_boundaries("municipality", region="20", year=2020)


class TestLoader:
    def test_load_municipality_population_real_values(self, tmp_path, monkeypatch):
        fake_path = _fake_gisco_gpkg(tmp_path)
        monkeypatch.setattr(geography, "_download_gisco_lau", lambda cache_dir=None: fake_path)

        gdf = loader.load(regions="Gipuzkoa", level="municipality", cache_dir=str(tmp_path / "cache"))
        assert set(gdf["GEOID"]) == {"20001", "20002"}
        assert gdf.set_index("GEOID").loc["20001", "population"] == 300.0
        assert gdf.set_index("GEOID").loc["20002", "population"] == 700.0
        assert gdf.set_index("GEOID").loc["20001", "eustat_populationDensity"] == pytest.approx(30.0)

    def test_load_requires_regions_or_aoi(self):
        with pytest.raises(ValueError):
            loader.load()

    def test_load_autonomous_community_deduplicates_regions(self, tmp_path, monkeypatch):
        fake_path = _fake_gisco_gpkg(tmp_path)
        monkeypatch.setattr(geography, "_download_gisco_lau", lambda cache_dir=None: fake_path)

        gdf = loader.load(
            regions=["Araba", "Gipuzkoa"], level="autonomous_community", cache_dir=str(tmp_path / "cache")
        )
        assert len(gdf) == 1
        assert gdf.iloc[0]["GEOID"] == "EUS"
        assert gdf.iloc[0]["population"] == pytest.approx(2050.0)  # 300+700+1000+50

    def test_load_uses_cache_on_second_call(self, tmp_path, monkeypatch):
        fake_path = _fake_gisco_gpkg(tmp_path)
        calls = {"n": 0}

        def _tracked(cache_dir=None):
            calls["n"] += 1
            return fake_path

        monkeypatch.setattr(geography, "_download_gisco_lau", _tracked)
        cache_dir = str(tmp_path / "cache")
        loader.load(regions="Gipuzkoa", level="municipality", cache_dir=cache_dir)
        first_calls = calls["n"]
        loader.load(regions="Gipuzkoa", level="municipality", cache_dir=cache_dir)
        # Second call should hit the parquet cache, not re-download/re-read GISCO.
        assert calls["n"] == first_calls
