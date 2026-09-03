"""Tests for pycensus.countries.chile.casen: schema, api parsing, and the loader.

Technical aspects:
    The real network call (:func:`pycensus.countries.chile.casen.api._fetch_xlsx`,
    against the live Observatorio Social bulk .xlsx download) is
    monkeypatched out with a small synthetic workbook here, to keep the
    suite offline and fast.

    That real endpoint was verified manually against the live network
    during development (2026-08-23): downloading
    ``Estimaciones_Tasa_Pobreza_Ingresos_Comunas_2022.xlsx`` and
    ``Estimaciones_Indice_Pobreza_Multidimensional_Comunas_2022.xlsx``
    from https://observatorio.ministeriodesarrollosocial.gob.cl/storage/docs/
    pobreza-comunal/2022/ and parsing them end-to-end returned, for real
    comuna codes: Santiago (13101) povertyRate=0.038648 (3.86%),
    Concepcion (08101) povertyRate=0.054067 (5.41%), Talcahuano (08110)
    povertyRate=0.050827 (5.08%); povertyRateMultidimensional for Santiago
    =0.164654, Concepcion=0.114778. 345 comunas were returned by the
    income-poverty table. See :mod:`pycensus.countries.chile.casen.api`'s
    module docstring for the full verification/provenance notes.
"""

from __future__ import annotations

import io

import geopandas as gpd
import openpyxl
import pandas as pd
import pytest
from shapely.geometry import box, mapping

from pycensus.countries.chile.casen import api, loader
from pycensus.countries.chile.casen.schema import SCHEMA


def _fake_workbook_bytes(value_col: str) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Estimaciones"
    ws.append(["Estimaciones de Tasa de Pobreza -- fake title row"])
    ws.append([])
    ws.append(["Código", "Región", "Nombre comuna", "N personas", "N pobres", value_col])
    ws.append([13101, "Metropolitana", "Santiago", 530538, 20504, 0.03864781172163236])
    ws.append([8101, "Biobío", "Concepción", 239074, 12926, 0.05406677251173651])
    ws.append(["Nota metodológica: texto explicativo, no es una fila de datos.", None, None, None, None, None])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestSchema:
    def test_schema_has_prefix(self):
        assert SCHEMA.prefix == "casen_cl"

    def test_schema_has_both_features(self):
        assert "povertyRate" in SCHEMA.columns
        assert "povertyRateMultidimensional" in SCHEMA.columns

    def test_column_codes_match_real_workbook_headers(self):
        """Regression guard: these codes were confirmed against the live
        .xlsx headers, not guessed."""
        assert SCHEMA.columns["povertyRate"].codes == [
            "Porcentaje de personas en situación de pobreza por ingresos 2022"
        ]
        assert SCHEMA.columns["povertyRateMultidimensional"].codes == [
            "Porcentaje de personas en situación de pobreza multidimensional 2022"
        ]

    def test_schema_prefixed_columns(self):
        assert SCHEMA.prefixed("povertyRate") == "casen_cl_povertyRate"


class TestApi:
    def test_fetch_table_parses_real_shape_and_drops_footnote_row(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            api,
            "_fetch_xlsx",
            lambda filename, data_dir=None: _write_fake_xlsx(tmp_path, filename),
        )
        df = api.fetch_table("povertyRate", data_dir=str(tmp_path))
        assert list(df.index) == ["13101", "08101"]
        assert df.loc["13101", "povertyRate"] == pytest.approx(0.03864781172163236)
        assert df.loc["08101", "povertyRate"] == pytest.approx(0.05406677251173651)

    def test_fetch_table_unknown_feature_raises(self):
        with pytest.raises(KeyError):
            api.fetch_table("not_a_real_feature")


def _write_fake_xlsx(tmp_path, filename):
    _, value_col = api.TABLES[
        "povertyRate" if "Ingresos" in filename else "povertyRateMultidimensional"
    ]
    path = tmp_path / filename
    path.write_bytes(_fake_workbook_bytes(value_col))
    return path


def _fake_boundary(level, region, year, data_dir=None):
    return gpd.GeoDataFrame(
        {"GEOID": ["08101"]},
        geometry=[box(0, 0, 1, 1)],
        crs=4326,
    )


class TestLoader:
    @pytest.fixture(autouse=True)
    def patch_network(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            api,
            "_fetch_xlsx",
            lambda filename, data_dir=None: _write_fake_xlsx(tmp_path, filename),
        )
        monkeypatch.setattr(loader.geography, "load_boundaries", _fake_boundary)

    def test_load_comuna_level_returns_schema_columns(self, tmp_path):
        gdf = loader.load(regions=["08"], level="comuna", cache_dir=str(tmp_path / "cache"))
        assert "casen_cl_povertyRate" in gdf.columns
        assert "casen_cl_povertyRateMultidimensional" in gdf.columns
        row = gdf[gdf["GEOID"] == "08101"].iloc[0]
        assert row["casen_cl_povertyRate"] == pytest.approx(0.05406677251173651)
        assert row["casen_cl_povertyRateMultidimensional"] == pytest.approx(0.05406677251173651)
        assert gdf.geometry.name == "geometry"
        assert gdf.crs is not None

    def test_load_non_comuna_level_raises(self, tmp_path):
        with pytest.raises(NotImplementedError):
            loader.load(regions=["08"], level="region", cache_dir=str(tmp_path / "cache"))

    def test_load_raises_without_regions_or_aoi(self, tmp_path):
        with pytest.raises(ValueError):
            loader.load(level="comuna", cache_dir=str(tmp_path / "cache"))


@pytest.mark.network
def test_real_casen_sae_matches_verified_comuna_figures(tmp_path):
    """Hits the live Observatorio Social bulk .xlsx downloads -- no API key
    required. Verified 2026-08-23: comuna Santiago (13101) real income
    povertyRate=0.038648 (3.86%), comuna Concepcion (08101)
    povertyRate=0.054067 (5.41%), comuna Talcahuano (08110)
    povertyRate=0.050827 (5.08%); Santiago povertyRateMultidimensional
    =0.164654, Concepcion=0.114778. 345 comunas returned by the income
    table (335 documented as having a direct Casen 2022 sample; the rest
    use the synthetic-only estimate)."""
    df = api.fetch_table("povertyRate", data_dir=str(tmp_path))
    assert len(df) > 300
    assert df.loc["13101", "povertyRate"] == pytest.approx(0.038648, abs=1e-5)
    assert df.loc["08101", "povertyRate"] == pytest.approx(0.054067, abs=1e-5)
    assert df.loc["08110", "povertyRate"] == pytest.approx(0.050827, abs=1e-5)

    df2 = api.fetch_table("povertyRateMultidimensional", data_dir=str(tmp_path))
    assert df2.loc["13101", "povertyRateMultidimensional"] == pytest.approx(0.164654, abs=1e-5)
    assert df2.loc["08101", "povertyRateMultidimensional"] == pytest.approx(0.114778, abs=1e-5)
