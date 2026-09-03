"""Tests for pycensus.raster_to_h3: generic raster/grid -> H3 resampling."""

from __future__ import annotations

import geopandas as gpd
import h3
import numpy as np
import pytest
from shapely.geometry import box

from pycensus.raster_to_h3 import best_h3_resolution_for_cell_size, resample_grid_to_h3


class TestBestH3ResolutionForCellSize:
    def test_100m_grid_picks_res_10(self):
        # 100m x 100m = 0.01 km^2/cell -> res 10 (~0.01505 km^2), the closest
        # real match that is not coarser than the source data (res 11 is
        # ~0.00218 km^2, finer than the source actually resolves).
        assert best_h3_resolution_for_cell_size(100.0) == 10

    def test_1km_grid_default_picks_res_7(self):
        # 1km x 1km = 1 km^2/cell -> nearest H3 average area *at or above*
        # 1 km^2 is res 7 (~5.16 km^2); res 8 (~0.737 km^2) is finer than the
        # source cell itself, excluded under the default "never claim more
        # precision than the source has" rule.
        assert best_h3_resolution_for_cell_size(1000.0) == 7

    def test_1km_grid_allow_finer_picks_closer_res_8(self):
        # With allow_finer=True, res 8's ~0.737 km^2 (delta ~0.263) beats
        # res 7's ~5.16 km^2 (delta ~4.16) as the closer absolute match.
        assert best_h3_resolution_for_cell_size(1000.0, allow_finer=True) == 8

    def test_matches_h3_average_area_table(self):
        # Cross-check against h3's own average_hexagon_area, not a hardcoded
        # table, for a spread of resolutions.
        for res in (7, 8, 9, 10, 11):
            area_km2 = h3.average_hexagon_area(res, unit="km^2")
            side_m = (area_km2 ** 0.5) * 1000.0
            # A cell sized almost exactly like this resolution's own average
            # area should map back to (at worst a neighboring) resolution.
            picked = best_h3_resolution_for_cell_size(side_m, allow_finer=True)
            assert abs(picked - res) <= 1

    def test_rejects_non_positive_cell_size(self):
        with pytest.raises(ValueError):
            best_h3_resolution_for_cell_size(0.0)


class TestResampleGridToH3:
    def _synthetic_grid(self, n_side=20, cell_m=100.0, lat0=48.13, lng0=11.57):
        """A small synthetic n_side x n_side grid of square cells near Munich.

        Cell size in degrees is approximated from `cell_m` at this latitude
        purely to give the polygons a realistic small footprint; only the
        cell *count* and *values* need to be exact for these tests, not the
        precise ground distance.
        """
        deg_per_m = 1.0 / 111_000.0
        step = cell_m * deg_per_m
        rows = []
        pop = 1
        for i in range(n_side):
            for j in range(n_side):
                x0 = lng0 + i * step
                y0 = lat0 + j * step
                rows.append({"population": float(pop), "geometry": box(x0, y0, x0 + step, y0 + step)})
                pop += 1
        return gpd.GeoDataFrame(rows, crs=4326)

    def test_picks_res_10_for_100m_cells(self):
        grid = self._synthetic_grid(n_side=5, cell_m=100.0)
        out = resample_grid_to_h3(grid, cell_size_m=100.0)
        assert (out["resolution"] == 10).all()

    def test_conserves_total_population_no_drop_no_double_count(self):
        grid = self._synthetic_grid(n_side=15, cell_m=100.0)
        out = resample_grid_to_h3(grid, cell_size_m=100.0, value_columns=("population",))
        # Sum conservation: every source cell contributes to exactly one H3
        # cell under "sum" aggregation.
        assert out["population"].sum() == pytest.approx(grid["population"].sum())

    def test_h3_cells_unique_no_duplicate_rows(self):
        grid = self._synthetic_grid(n_side=15, cell_m=100.0)
        out = resample_grid_to_h3(grid, cell_size_m=100.0)
        assert out["h3_cell"].is_unique

    def test_explicit_resolution_overrides_cell_size(self):
        grid = self._synthetic_grid(n_side=5, cell_m=100.0)
        out = resample_grid_to_h3(grid, resolution=8, cell_size_m=100.0)
        assert (out["resolution"] == 8).all()

    def test_empty_grid_returns_empty_geodataframe(self):
        empty = gpd.GeoDataFrame({"population": []}, geometry=[], crs=4326)
        out = resample_grid_to_h3(empty, cell_size_m=100.0)
        assert out.empty
        assert "h3_cell" in out.columns

    def test_requires_resolution_or_cell_size(self):
        grid = self._synthetic_grid(n_side=2, cell_m=100.0)
        with pytest.raises(ValueError):
            resample_grid_to_h3(grid)

    def test_returned_geometry_is_real_h3_polygon(self):
        grid = self._synthetic_grid(n_side=3, cell_m=100.0)
        out = resample_grid_to_h3(grid, cell_size_m=100.0)
        row = out.iloc[0]
        boundary = h3.cell_to_boundary(row["h3_cell"])
        expected = [(lng, lat) for lat, lng in boundary]
        got_coords = list(row.geometry.exterior.coords)[:-1]
        assert len(got_coords) == len(expected)
        for (glng, glat), (elng, elat) in zip(got_coords, expected):
            assert glng == pytest.approx(elng)
            assert glat == pytest.approx(elat)

    def test_mean_aggregation(self):
        grid = gpd.GeoDataFrame(
            {"value": [10.0, 20.0]},
            geometry=[box(11.57, 48.13, 11.5701, 48.1301), box(11.57005, 48.13005, 11.57015, 48.13015)],
            crs=4326,
        )
        out = resample_grid_to_h3(grid, resolution=10, value_columns=("value",), agg="mean")
        # Both tiny boxes likely land in the same res-10 cell given their
        # near-identical centroids -- either way, mean must stay within the
        # source value range (never sum-inflated).
        assert out["value"].max() <= 20.0
        assert out["value"].min() >= 10.0
