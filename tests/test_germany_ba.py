"""Tests for pycensus.countries.germany.ba: BA (Bundesagentur fuer Arbeit) jobs-by-workplace.

Technical aspects:
    Real network calls (the BA AMK zip download, GISCO LAU/NUTS geometry)
    are monkeypatched out here for the offline suite, same pattern as
    ``tests/test_germany.py``. The real source was verified live during
    development (2026-08-23) -- see ``germany/ba/loader.py`` and
    ``germany/schema/ba_schema.json`` module docstrings for the exact
    verified numbers this test's fixtures are modeled on:
        - Hamburg (single-Gemeinde Kreis/city-state, AGS 02000000), 2025
          workplace jobs: 1,084,974 (a real, monotonically-growing
          2021-2025 series).
        - Landkreis Merzig-Wadern (Kreis AGS 10042, Saarland), whose real
          ZIP contains 7 separate real per-Gemeinde workbooks (Beckingen
          AGS 10042111 = 1,883 jobs, ...), confirming AMK's real
          granularity is Gemeinde, not Kreis.
        - District-level totals were confirmed live to be an exact sum of
          their real Gemeinde rows (Saarland's 6 real district totals sum
          to the same 387,400 as all 52 real Gemeinde rows).
"""

from __future__ import annotations

import io
import zipfile

import geopandas as gpd
import openpyxl
import pandas as pd
import pytest
from shapely.geometry import Point, box

from pycensus.countries.germany import constants, geography, utils
from pycensus.countries.germany.ba import loader
from pycensus.countries.germany.ba.schema import SCHEMA


def _make_amk_workbook_bytes(ags8: str, name: str, jobs_by_year: dict) -> bytes:
    """Build a synthetic .xlsx matching the real AMK 'Daten' sheet shape."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Daten"
    years = sorted(jobs_by_year)
    ws.append([None] * 6 + ["Arbeitsmarkt kommunal"])
    ws.append([])
    ws.append(["Sozialversicherungspflichtig und geringfügig Beschäftigte und Arbeitslose\nnach ausgewählten Merkmalen"])
    ws.append([f"{ags8} {name} (Gebietsstand im Jahr {years[-1]})"])
    ws.append([years[-1]])
    ws.append([])
    ws.append(["Merkmale", None, *years])
    ws.append([None, None, *range(1, len(years) + 1)])
    ws.append(["Sozialversicherungspflichtig Beschäftigte\nam Arbeitsort (Stichtag 30.06.)"])
    ws.append(["Insgesamt", None, *[jobs_by_year[y] for y in years]])
    ws.append(["dar.", "Männer", *[0 for _ in years]])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _make_amk_zip_bytes(entries: dict) -> bytes:
    """entries: {filename: workbook_bytes}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for fname, content in entries.items():
            zf.writestr(fname, content)
    return buf.getvalue()


class TestParseAmkWorkbook:
    def test_parses_real_shape_hamburg(self):
        content = _make_amk_workbook_bytes(
            "02000000",
            "Hamburg, Freie und Hansestadt",
            {2021: 1_008_604, 2022: 1_038_507, 2023: 1_061_826, 2024: 1_073_152, 2025: 1_084_974},
        )
        parsed = loader._parse_amk_workbook(content)
        assert parsed["ags8"] == "02000000"
        assert parsed["name"] == "Hamburg, Freie und Hansestadt"
        assert parsed["year"] == 2025
        assert parsed["jobsTotal"] == 1_084_974

    def test_parses_real_shape_gemeinde(self):
        content = _make_amk_workbook_bytes("10042111", "Beckingen", {2024: 1_912, 2025: 1_883})
        parsed = loader._parse_amk_workbook(content)
        assert parsed["ags8"] == "10042111"
        assert parsed["jobsTotal"] == 1_883

    def test_raises_on_missing_workplace_row(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Daten"
        ws.append(["00000000 Nowhere (Gebietsstand im Jahr 2025)"])
        ws.append(["Merkmale", None, 2025])
        buf = io.BytesIO()
        wb.save(buf)
        with pytest.raises(ValueError):
            loader._parse_amk_workbook(buf.getvalue())


class TestFetchAmkZipEntries:
    def test_multi_gemeinde_zip_returns_all_entries(self, monkeypatch, tmp_path):
        entries = {
            "Arbeitsmarkt-kommunal_10042111_Beckingen.xlsx": _make_amk_workbook_bytes(
                "10042111", "Beckingen", {2025: 1_883}
            ),
            "Arbeitsmarkt-kommunal_10042112_Losheim_am_See.xlsx": _make_amk_workbook_bytes(
                "10042112", "Losheim am See", {2025: 4_409}
            ),
        }
        zip_bytes = _make_amk_zip_bytes(entries)

        class _FakeResp:
            status_code = 200
            content = zip_bytes

            def raise_for_status(self):
                pass

        monkeypatch.setattr(loader.requests, "get", lambda url, timeout=180: _FakeResp())
        result = loader._fetch_amk_zip_entries("10042", "202512", data_dir=str(tmp_path))
        assert set(result.keys()) == set(entries.keys())

    def test_404_returns_none(self, monkeypatch, tmp_path):
        class _FakeResp:
            status_code = 404

            def raise_for_status(self):
                raise AssertionError("should not be called on 404")

        monkeypatch.setattr(loader.requests, "get", lambda url, timeout=180: _FakeResp())
        assert loader._fetch_amk_zip_entries("99999", "202512", data_dir=str(tmp_path)) is None


class TestFetchMissing:
    def test_municipality_level(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            loader,
            "kreis_ags_in_state",
            lambda state, data_dir=None: ["10042"],
        )
        monkeypatch.setattr(
            loader,
            "_fetch_all_municipality_jobs",
            lambda ags5_list, period, data_dir: [
                ("10042111", "Beckingen", 1_883),
                ("10042112", "Losheim am See", 4_409),
            ],
        )
        result = loader._fetch_missing([], "municipality", "SL", "latest", None, str(tmp_path))
        assert list(result["GEOID"]) == ["10042111", "10042112"]
        assert list(result[SCHEMA.column_label("jobsTotal")]) == [1_883, 4_409]

    def test_district_level_aggregates_municipalities(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            loader,
            "kreis_ags_in_state",
            lambda state, data_dir=None: ["10042"],
        )
        monkeypatch.setattr(
            loader,
            "_fetch_all_municipality_jobs",
            lambda ags5_list, period, data_dir: [
                ("10042111", "Beckingen", 1_000),
                ("10042112", "Losheim am See", 2_000),
            ],
        )
        muni_gdf = gpd.GeoDataFrame(
            {"GEOID": ["10042111", "10042112"]},
            geometry=[Point(6.5, 49.4), Point(6.7, 49.5)],
            crs=4326,
        )
        district_gdf = gpd.GeoDataFrame(
            {"GEOID": ["DEC02"]},
            geometry=[box(6.0, 49.0, 7.0, 50.0)],
            crs=4326,
        )

        def _fake_load_boundaries(level, region=None, data_dir=None, **kw):
            return district_gdf.copy() if level == "district" else muni_gdf.copy()

        monkeypatch.setattr(geography, "load_boundaries", _fake_load_boundaries)
        result = loader._fetch_missing([], "district", "SL", "latest", None, str(tmp_path))
        assert list(result["GEOID"]) == ["DEC02"]
        assert result[SCHEMA.column_label("jobsTotal")].iloc[0] == 3_000

    def test_unimplemented_level_raises(self, tmp_path):
        with pytest.raises(NotImplementedError):
            loader._fetch_missing([], "state", "SL", "latest", None, str(tmp_path))

    def test_no_rows_raises(self, monkeypatch, tmp_path):
        monkeypatch.setattr(loader, "kreis_ags_in_state", lambda state, data_dir=None: ["99999"])
        monkeypatch.setattr(loader, "_fetch_all_municipality_jobs", lambda *a, **kw: [])
        with pytest.raises(ValueError):
            loader._fetch_missing([], "municipality", "SL", "latest", None, str(tmp_path))


class TestSchema:
    def test_jobs_total_is_a_real_registered_field(self):
        assert "jobsTotal" in SCHEMA.columns
        assert SCHEMA.column_label("jobsTotal") == "ba_jobsTotal"


class TestKreisAgsInState:
    def test_derives_from_real_gisco_lau_geoids(self, monkeypatch, tmp_path):
        fake_gdf = gpd.GeoDataFrame(
            {"GEOID": ["10041100", "10042111", "10042112"]},
            geometry=[Point(0, 0), Point(0, 0), Point(0, 0)],
            crs=4326,
        )
        monkeypatch.setattr(geography, "load_boundaries", lambda level, region=None, data_dir=None, **kw: fake_gdf)
        result = loader.kreis_ags_in_state("SL", data_dir=str(tmp_path))
        assert result == ["10041", "10042"]


@pytest.mark.network
def test_real_hamburg_workplace_jobs_matches_live_verified_series():
    """Hits the live BA AMK download. Verified 2026-08-23: Hamburg (single-
    Gemeinde Kreis, AGS 02000000) 2025 workplace jobs = 1,084,974, part of a
    real, monotonically-growing 2021-2025 series -- see module docstring."""
    gdf = loader.load(regions=["HH"], level="municipality")
    row = gdf[gdf["GEOID"] == "02000000"]
    assert len(row) == 1
    assert row["ba_jobsTotal"].iloc[0] == 1_084_974


@pytest.mark.network
def test_real_district_totals_equal_sum_of_real_municipality_totals():
    """Hits the live BA AMK download for Saarland (6 Kreise, 52 Gemeinden).
    Verified 2026-08-23: the 6 real district-level totals sum to exactly
    the same 387,400 as all 52 real Gemeinde-level rows -- confirms the
    district-level spatial aggregation drops/double-counts nothing real."""
    muni = loader.load(regions=["SL"], level="municipality")
    district = loader.load(regions=["SL"], level="district")
    assert muni["ba_jobsTotal"].sum() == district["ba_jobsTotal"].sum()
