"""Tests for pycensus.countries.worldwide.worldpop -- offline (mocked network/rasters) + one live network check."""

from __future__ import annotations

import json
import os

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Point

from pycensus.countries.worldwide.worldpop import loader


def _write_fake_raster(path: str, value: float, nodata: float = -99999.0, shape=(2, 2)) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    transform = from_origin(0, 0, 0.01, 0.01)
    arr = np.full(shape, value, dtype="float32")
    with rasterio.open(
        path, "w", driver="GTiff", height=shape[0], width=shape[1], count=1,
        dtype="float32", crs="EPSG:4326", transform=transform, nodata=nodata,
    ) as dst:
        dst.write(arr, 1)


def _fake_aoi() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({"geometry": [Point(1.5, 42.5).buffer(0.01)]}, crs=4326)


class TestGlobalSchemaFeatures:
    def test_feature_names_match_declared_tuple(self):
        expected = {"population", "malePopulation", "femalePopulation", "under18Population", "over65Population", "adultPopulation"}
        assert set(loader.GLOBAL_SCHEMA_FEATURES) == expected

    def test_schema_json_features_match(self):
        schema_path = os.path.join(os.path.dirname(loader.__file__), "..", "schema", "worldpop_schema.json")
        data = json.load(open(schema_path))
        names = {f["feature_name"] for f in data["features"]}
        assert names == set(loader.GLOBAL_SCHEMA_FEATURES)


class TestDownloadAndUnzip:
    def test_plain_tif_passthrough(self, tmp_path, monkeypatch):
        def fake_download_to(url, dest_path, overwrite, chunk_size=1048576):
            _write_fake_raster(dest_path, 5.0)
            return dest_path

        monkeypatch.setattr(loader, "_download_to", fake_download_to)
        out = loader._download_and_unzip("https://example.com/x.tif", str(tmp_path), overwrite=False)
        assert out == str(tmp_path / "x.tif")
        assert os.path.isfile(out)

    def test_zip_with_single_tif_is_extracted(self, tmp_path, monkeypatch):
        import zipfile

        inner = tmp_path / "inner.tif"
        _write_fake_raster(str(inner), 1.0)
        zip_path = tmp_path / "bundle.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(inner, "inner.tif")

        monkeypatch.setattr(loader, "_download_to", lambda url, dest_path, overwrite, chunk_size=1048576: str(zip_path))
        out = loader._download_and_unzip("https://example.com/bundle.zip", str(tmp_path), overwrite=False)
        assert out.endswith("inner.tif")
        assert os.path.isfile(out)

    def test_zip_with_multiple_tifs_uses_prefer_substring(self, tmp_path, monkeypatch):
        import zipfile

        t_path = tmp_path / "and_T_2020.tif"
        m_path = tmp_path / "and_m_2020.tif"
        _write_fake_raster(str(t_path), 1.0)
        _write_fake_raster(str(m_path), 2.0)
        zip_path = tmp_path / "bundle2.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(t_path, "and_T_2020.tif")
            zf.write(m_path, "and_m_2020.tif")

        monkeypatch.setattr(loader, "_download_to", lambda url, dest_path, overwrite, chunk_size=1048576: str(zip_path))
        out = loader._download_and_unzip("https://example.com/bundle2.zip", str(tmp_path), overwrite=False, prefer_substring="_T_")
        assert "and_T_2020.tif" in out

    def test_zip_with_ambiguous_tifs_raises(self, tmp_path, monkeypatch):
        import zipfile

        a = tmp_path / "a.tif"
        b = tmp_path / "b.tif"
        _write_fake_raster(str(a), 1.0)
        _write_fake_raster(str(b), 2.0)
        zip_path = tmp_path / "bundle3.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(a, "a.tif")
            zf.write(b, "b.tif")

        monkeypatch.setattr(loader, "_download_to", lambda url, dest_path, overwrite, chunk_size=1048576: str(zip_path))
        with pytest.raises(ValueError):
            loader._download_and_unzip("https://example.com/bundle3.zip", str(tmp_path), overwrite=False)


class TestWeightedSumRasters:
    def test_simple_sum(self, tmp_path):
        p1 = tmp_path / "a.tif"
        p2 = tmp_path / "b.tif"
        _write_fake_raster(str(p1), 10.0)
        _write_fake_raster(str(p2), 5.0)
        out_path = str(tmp_path / "out.tif")

        loader._weighted_sum_rasters([(str(p1), 1.0), (str(p2), 0.5)], out_path, overwrite=False)
        with rasterio.open(out_path) as src:
            arr = src.read(1)
        assert np.allclose(arr, 12.5)

    def test_negative_weight_subtracts(self, tmp_path):
        p1 = tmp_path / "a.tif"
        p2 = tmp_path / "b.tif"
        _write_fake_raster(str(p1), 10.0)
        _write_fake_raster(str(p2), 3.0)
        out_path = str(tmp_path / "out2.tif")

        loader._weighted_sum_rasters([(str(p1), 1.0), (str(p2), -1.0)], out_path, overwrite=False)
        with rasterio.open(out_path) as src:
            arr = src.read(1)
        assert np.allclose(arr, 7.0)

    def test_reuses_cached_output(self, tmp_path):
        p1 = tmp_path / "a.tif"
        _write_fake_raster(str(p1), 10.0)
        out_path = str(tmp_path / "out3.tif")
        loader._weighted_sum_rasters([(str(p1), 1.0)], out_path, overwrite=False)
        mtime_1 = os.path.getmtime(out_path)

        loader._weighted_sum_rasters([(str(p1), 999.0)], out_path, overwrite=False)
        mtime_2 = os.path.getmtime(out_path)
        assert mtime_1 == mtime_2  # not re-derived


class TestDownloadWorldpopLayer:
    """Mocks the network-touching layer (_resolve_iso3, _fetch_age_structure_listing, _download_to)."""

    @pytest.fixture(autouse=True)
    def patch_network(self, monkeypatch, tmp_path):
        self.tmp_path = tmp_path
        monkeypatch.setattr(loader, "_resolve_iso3", lambda aoi: "AND")

        bins = ["00", "01", "05", "10", "15", "20", "25", "30", "35", "40", "45", "50", "55", "60", "65", "70", "75", "80", "85", "90"]
        listing = {f"and_T_M_2025.tif": "https://example.com/and_T_M_2025.tif", f"and_T_F_2025.tif": "https://example.com/and_T_F_2025.tif"}
        for b in bins:
            listing[f"and_t_{b}_2025.tif"] = f"https://example.com/and_t_{b}_2025.tif"
        monkeypatch.setattr(loader, "_fetch_age_structure_listing", lambda iso3, year, resolution: listing)

        def fake_download_to(url, dest_path, overwrite, chunk_size=1048576):
            fname = os.path.basename(dest_path)
            # deterministic per-bin value so band math is checkable
            if "_t_" in fname:
                value = 100.0
            elif "_T_M_" in fname:
                value = 500.0
            elif "_T_F_" in fname:
                value = 480.0
            else:
                value = 1.0
            _write_fake_raster(dest_path, value)
            return dest_path

        monkeypatch.setattr(loader, "_download_to", fake_download_to)

    def _sum(self, path):
        with rasterio.open(path) as src:
            return float(np.sum(src.read(1)))

    def test_male_population_is_direct_file(self):
        p = loader.download_worldpop_layer(_fake_aoi(), 2025, "malePopulation", folder=str(self.tmp_path))
        assert self._sum(p) == pytest.approx(500.0 * 4)  # 2x2 fake raster

    def test_female_population_is_direct_file(self):
        p = loader.download_worldpop_layer(_fake_aoi(), 2025, "femalePopulation", folder=str(self.tmp_path))
        assert self._sum(p) == pytest.approx(480.0 * 4)

    def test_over65_sums_six_bins(self):
        p = loader.download_worldpop_layer(_fake_aoi(), 2025, "over65Population", folder=str(self.tmp_path))
        assert self._sum(p) == pytest.approx(100.0 * 6 * 4)

    def test_under18_uses_bin15_weight(self):
        p = loader.download_worldpop_layer(_fake_aoi(), 2025, "under18Population", folder=str(self.tmp_path))
        # bins 00,01,05,10 full (4 * 100) + bin 15 at 0.6 weight = 460, per pixel; x4 pixels
        assert self._sum(p) == pytest.approx(460.0 * 4)

    def test_adult_is_total_minus_under18(self):
        p = loader.download_worldpop_layer(_fake_aoi(), 2025, "adultPopulation", folder=str(self.tmp_path))
        total = 100.0 * 20  # 20 bins full weight
        under18 = 460.0
        assert self._sum(p) == pytest.approx((total - under18) * 4)

    def test_unknown_feature_raises(self):
        with pytest.raises(ValueError):
            loader.download_worldpop_layer(_fake_aoi(), 2025, "not_a_real_feature", folder=str(self.tmp_path))


@pytest.mark.network
def test_real_worldpop_andorra_layers():
    """Hits the live WorldPop API for tiny Andorra -- run explicitly via `pytest -m network`."""
    import os as _os

    aoi_path = _os.path.join(_os.path.dirname(__file__), "..", "examples", "CSnetwork", "aois", "andorra.gpkg")
    if not _os.path.exists(aoi_path):
        pytest.skip("examples/CSnetwork/aois/andorra.gpkg not present")

    aoi = gpd.read_file(aoi_path)
    male_path = loader.download_worldpop_layer(aoi, 2025, "malePopulation")
    female_path = loader.download_worldpop_layer(aoi, 2025, "femalePopulation")

    with rasterio.open(male_path) as src:
        male_total = float(np.ma.sum(src.read(1, masked=True)))
    with rasterio.open(female_path) as src:
        female_total = float(np.ma.sum(src.read(1, masked=True)))

    # Real Andorra population is ~80,000; sanity-range check, not an exact figure.
    assert 30000 < male_total < 60000
    assert 30000 < female_total < 60000
