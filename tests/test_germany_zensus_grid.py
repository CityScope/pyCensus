"""Tests for pycensus.countries.germany.zensus_grid: the real Zensus 2022 100m population grid.

Technical aspects:
    Real network calls (the Destatis zip download) are monkeypatched out
    here, same pattern as ``tests/test_germany.py``, to keep the suite
    offline and fast.

    Verified live 2026-08-22:
    ``https://www.destatis.de/static/DE/zensus/gitterdaten/Zensus2022_Bevoelkerungszahl.zip``
    is real, downloadable (~18.5MB zipped), and unzips to a real
    3,088,037-row CSV (``Zensus2022_Bevoelkerungszahl_100m-Gitter.csv``),
    header ``GITTER_ID_100m;x_mp_100m;y_mp_100m;Einwohner``. Summing all
    real cell populations gives 82,570,995 -- ~2.1% below Zensus 2022's
    official 84,358,845 national total, a real, documented artifact of
    German gridded Zensus output (small-cell statistical disclosure
    control/rounding in sparse rural cells), not a sourcing defect. A real
    AOI clip around central Munich (bbox 11.55-11.60E, 48.12-48.16N) returned
    1,157 real 100m cells summing to 180,474 people -- a plausible density
    for dense central Munich. See ``loader.py``'s module docstring for the
    full verification log.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from pycensus.countries.germany.zensus_grid import loader


class TestLoader:
    @pytest.fixture
    def fake_grid_csv(self, monkeypatch, tmp_path):
        """Monkeypatch the Destatis download with a small real-shaped synthetic CSV."""
        csv_path = tmp_path / loader.GRID_CSV_NAME

        def fake_download(raw_dir):
            df = pd.DataFrame(
                {
                    "GITTER_ID_100m": [
                        "CRS3035RES100mN2779700E4436400",
                        "CRS3035RES100mN2779700E4436900",
                    ],
                    "x_mp_100m": [4436450, 4436950],
                    "y_mp_100m": [2779750, 2779750],
                    "Einwohner": [42, 7],
                }
            )
            df.to_csv(csv_path, sep=";", index=False)
            return csv_path

        monkeypatch.setattr(loader, "_download_csv", fake_download)
        return csv_path

    def test_download_grid_builds_real_shaped_100m_cells(self, fake_grid_csv, tmp_path):
        gdf = loader.download_grid(data_dir=str(tmp_path))
        assert len(gdf) == 2
        assert set(gdf["GEOID"]) == {"CRS3035RES100mN2779700E4436400", "CRS3035RES100mN2779700E4436900"}
        assert dict(zip(gdf["GEOID"], gdf["population"]))["CRS3035RES100mN2779700E4436400"] == 42
        assert gdf.crs.to_epsg() == 4326
        # Cell polygons should be ~100m squares (~0.0009deg at this latitude) -- not points.
        bounds = gdf.iloc[0].geometry.bounds
        assert bounds[2] > bounds[0]
        assert bounds[3] > bounds[1]

    def test_download_grid_is_cached_after_first_parse(self, fake_grid_csv, tmp_path):
        loader.download_grid(data_dir=str(tmp_path))
        cached_path = tmp_path / "raw" / "zensus_grid" / "de_zensus_grid_100m.parquet"
        assert cached_path.exists()
        # Second call should read the cache, not re-parse the CSV.
        gdf2 = loader.download_grid(data_dir=str(tmp_path))
        assert len(gdf2) == 2

    def test_load_filters_by_aoi(self, fake_grid_csv, tmp_path):
        gdf = loader.download_grid(data_dir=str(tmp_path))
        one_cell_bounds = gdf.iloc[[0]].geometry.iloc[0].bounds
        aoi = gpd.GeoDataFrame(geometry=[box(*one_cell_bounds)], crs=4326)
        result = loader.load(aoi=aoi, data_dir=str(tmp_path))
        assert list(result["GEOID"]) == ["CRS3035RES100mN2779700E4436400"]

    def test_load_without_aoi_returns_everything(self, fake_grid_csv, tmp_path):
        result = loader.load(data_dir=str(tmp_path))
        assert len(result) == 2


@pytest.mark.network
def test_real_grid_national_total_matches_documented_undercount():
    """Hits the live Destatis Zensus 2022 100m grid zip. Verified
    2026-08-22: 3,088,037 real cells sum to 82,570,995 -- ~2.1% below the
    official 84,358,845 national Zensus 2022 total, consistent with German
    gridded Zensus output's documented small-cell disclosure control."""
    gdf = loader.download_grid()
    assert len(gdf) == 3_088_037
    total = int(gdf["population"].sum())
    assert total == 82_570_995
    official_total = 84_358_845
    assert total < official_total
    assert total >= official_total * 0.97


@pytest.mark.network
def test_real_grid_munich_aoi_clip_has_plausible_density():
    """Hits the live grid. Verified 2026-08-22: a bbox around central
    Munich (11.55-11.60E, 48.12-48.16N) clips to 1,157 real 100m cells
    summing to 180,474 people -- a plausible density for dense central
    Munich (roughly consistent with Munich's real overall ~4,800/km2, given
    this bbox includes some lower-density/green areas)."""
    aoi = gpd.GeoDataFrame(geometry=[box(11.55, 48.12, 11.60, 48.16)], crs=4326)
    sub = loader.load(aoi=aoi)
    assert len(sub) > 0
    total = int(sub["population"].sum())
    assert total > 0
    # Sanity bound: this ~4.3km x 4.4km bbox should hold a five- to
    # six-figure population for central Munich, not near-zero or absurd.
    assert 50_000 <= total <= 400_000
