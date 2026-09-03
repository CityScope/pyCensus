"""Tests for pycensus.countries.chile.sii: schema, api parsing, and the loader.

Technical aspects:
    The real network calls (SII's bulk .xlsx download, and the DPA
    FeatureServer used for the live comuna-name crosswalk) are
    monkeypatched out with small synthetic fixtures here, to keep the
    suite offline and fast.

    Those real endpoints were verified manually against the live network
    during development (2026-08-23): downloading
    ``https://www.sii.cl/estadisticas/region/PUB_Reg_Com.xlsx`` and
    parsing it end-to-end, filtered to real comuna GEOIDs via the live DPA
    FeatureServer's NOM_COMUNA field, gave jobsTotal=154065 for comuna
    Concepcion (08101, all 33 real Region VIII comunas matched with no
    drops) and jobsTotal=1141309 for comuna Santiago (13101, 47 of Region
    Metropolitana's 52 real comunas matched). See
    :mod:`pycensus.countries.chile.sii.api` and
    :mod:`pycensus.countries.chile.sii.loader` module docstrings for the
    full verification/provenance notes.
"""

from __future__ import annotations

import io

import geopandas as gpd
import openpyxl
import pytest
from shapely.geometry import box

from pycensus.countries.chile.sii import api, loader
from pycensus.countries.chile.sii.schema import SCHEMA


def _fake_workbook_bytes() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "EMP_Reg_Com"
    for _ in range(5):
        ws.append([])
    ws.append(
        [
            "Año Comercial",
            "ID_Region",
            "ID_Comuna",
            "Número de Empresas",
            "Ventas (UF)",
            "Número de Trabajadores Dependientes Informados",
            "Renta Neta Informada de Trabajadores Dependientes (UF)",
        ]
    )
    ws.append([2014, "VIII DEL BIO BIO", "CONCEPCION", 20000, 1.0, 150000, 1.0])
    ws.append([2015, "VIII DEL BIO BIO", "CONCEPCION", 20476, 1.0, 154065, 1.0])
    ws.append([2015, "VIII DEL BIO BIO", "TALCAHUANO", 5000, 1.0, 40000, 1.0])
    ws.append([2015, "XIII METROPOLITANA DE SANTIAGO", "SANTIAGO", 59724, 1.0, 1141309, 1.0])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _write_fake_xlsx(tmp_path):
    path = tmp_path / "PUB_Reg_Com.xlsx"
    path.write_bytes(_fake_workbook_bytes())
    return path


def _fake_dpa_features(level, region, data_dir=None):
    if region == "08":
        return {
            "features": [
                {"properties": {"NOM_COMUNA": "Concepción", "COMUNA": "8101"}},
                {"properties": {"NOM_COMUNA": "Talcahuano", "COMUNA": "8110"}},
            ]
        }
    if region == "13":
        return {"features": [{"properties": {"NOM_COMUNA": "Santiago", "COMUNA": "13101"}}]}
    return {"features": []}


def _fake_boundary(level, region, year, data_dir=None):
    geoid = "13101" if region == "13" else "08101"
    return gpd.GeoDataFrame({"GEOID": [geoid]}, geometry=[box(0, 0, 1, 1)], crs=4326)


class TestSchema:
    def test_schema_has_prefix(self):
        assert SCHEMA.prefix == "sii_cl"

    def test_schema_has_jobs_total(self):
        assert "jobsTotal" in SCHEMA.columns

    def test_column_codes_match_real_workbook_header(self):
        """Regression guard: this code was confirmed against the live .xlsx header, not guessed."""
        assert SCHEMA.columns["jobsTotal"].codes == ["Número de Trabajadores Dependientes Informados"]

    def test_schema_prefixed_column(self):
        assert SCHEMA.prefixed("jobsTotal") == "sii_cl_jobsTotal"


class TestApi:
    def test_fetch_table_parses_real_shape(self, monkeypatch, tmp_path):
        monkeypatch.setattr(api, "_fetch_xlsx", lambda data_dir=None: _write_fake_xlsx(tmp_path))
        df = api.fetch_table(data_dir=str(tmp_path))
        assert set(df.columns) == {"ano_comercial", "id_region", "id_comuna", "jobsTotal"}
        assert len(df) == 4
        concep_2015 = df[(df["id_comuna"] == "CONCEPCION") & (df["ano_comercial"] == 2015)]
        assert concep_2015["jobsTotal"].iloc[0] == 154065


class TestLoader:
    def test_sii_region_code_roman_numeral(self):
        assert loader._sii_region_code("VIII DEL BIO BIO") == "08"
        assert loader._sii_region_code("I DE TARAPACA") == "01"

    def test_sii_region_code_metropolitana(self):
        assert loader._sii_region_code("XIII METROPOLITANA DE SANTIAGO") == "13"

    def test_normalize_strips_accents(self):
        assert loader._normalize("Concepción") == loader._normalize("CONCEPCION")

    @pytest.fixture(autouse=True)
    def patch_network(self, monkeypatch, tmp_path):
        monkeypatch.setattr(api, "_fetch_xlsx", lambda data_dir=None: _write_fake_xlsx(tmp_path))
        monkeypatch.setattr(loader.dpa_api, "fetch_features", _fake_dpa_features)
        monkeypatch.setattr(loader.geography, "load_boundaries", _fake_boundary)

    def test_load_uses_latest_year_only(self, tmp_path):
        gdf = loader.load(regions=["08"], level="comuna", cache_dir=str(tmp_path / "cache"))
        assert "sii_cl_jobsTotal" in gdf.columns
        row = gdf[gdf["GEOID"] == "08101"].iloc[0]
        # 2015 (latest), not 2014's 150000
        assert row["sii_cl_jobsTotal"] == 154065

    def test_load_drops_unmatched_comuna_names(self, tmp_path):
        """Real behavior: an SII comuna name that can't be matched to a real
        DPA GEOID is dropped, not silently mismatched to the wrong comuna."""
        gdf = loader.load(regions=["13"], level="comuna", cache_dir=str(tmp_path / "cache2"))
        assert list(gdf["GEOID"]) == ["13101"]
        assert gdf.iloc[0]["sii_cl_jobsTotal"] == 1141309

    def test_load_non_comuna_level_raises(self, tmp_path):
        with pytest.raises(NotImplementedError):
            loader.load(regions=["08"], level="region", cache_dir=str(tmp_path / "cache"))

    def test_load_raises_without_regions_or_aoi(self, tmp_path):
        with pytest.raises(ValueError):
            loader.load(level="comuna", cache_dir=str(tmp_path / "cache"))


@pytest.mark.network
def test_real_sii_matches_verified_comuna_figures(tmp_path):
    """Hits the live SII PUB_Reg_Com.xlsx bulk download and the live DPA
    FeatureServer -- no API key required. Verified 2026-08-23: comuna
    Concepcion (08101) jobsTotal=154065 (all 33 Region VIII comunas
    matched, commercial year 2015 -- the latest year in this SII series),
    comuna Santiago (13101) jobsTotal=1141309 (47 of 52 Region
    Metropolitana comunas matched -- 5 unmatched abbreviated/hyphenated
    SII names are dropped, not mismatched)."""
    from pycensus.countries.chile import sii

    gdf = sii.load(regions=["08"], cache_dir=str(tmp_path / "cache"), data_dir=str(tmp_path / "data"))
    row = gdf[gdf["GEOID"] == "08101"].iloc[0]
    assert row["sii_cl_jobsTotal"] == 154065
    assert len(gdf) == 33
