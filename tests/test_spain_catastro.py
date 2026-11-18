"""Offline test of the Catastro building aggregation (synthetic buildings and sections)."""
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from pycensus.census.countries.spain.catastro import FEATURES, source_of_province
from pycensus.census.countries.spain.catastro.loader import aggregate


def test_aggregate_counts_and_rates():
    sections = gpd.GeoDataFrame({"GEOID": ["0000000001", "0000000002"], "geometry": [box(0, 0, 1, 1), box(1, 0, 2, 1)]}, crs=4326)
    b = pd.DataFrame({
        "lon": [0.2, 0.4, 0.6, 1.5], "lat": [0.5] * 4, "year": [1950, 1990, np.nan, 2005],
        "use": ["1_residential", "1_residential", "3_industrial", "1_residential"],
        "dwellings": [4, 2, 0, 1], "units": [5, 2, 1, 1], "floor_area": [400, 200, 100, 90], "footprint": [100, 80, 50, 90], "height": np.nan, "floors": np.nan})
    r = aggregate(b, sections).set_index("GEOID")
    assert list(r.columns) == list(FEATURES)
    a = r.loc["0000000001"]
    assert a["catastro_buildings"] == 3 and a["catastro_dwellings"] == 6 and a["catastro_floor_area_m2_total"] == 700
    assert a["catastro_year_built_median"] == 1970 and a["catastro_share_built_before_1960"] == 0.5
    assert abs(a["catastro_residential_share"] - 2 / 3) < 1e-9 and a["catastro_dwellings_per_building"] == 3
    assert r.loc["0000000002", "catastro_share_built_since_2000"] == 1.0


def test_sources():
    assert [source_of_province(p) for p in ("42", "20", "01", "31", "48")] == ["state", "gipuzkoa", "araba", "navarra", "bizkaia"]


def test_padron_counts_with_any_thousands_separator():
    import pandas as pd

    from pycensus.census.countries.spain.api import _parse_count, _parse_secciones_csv

    out = _parse_count(pd.Series(["1.944", "1,944", "1 944", "12", "", "-", "1.234.567"]))
    assert out.iloc[:4].tolist() == [1944, 1944, 1944, 12] and out.iloc[6] == 1234567 and out.iloc[4:6].isna().all()
    text = "Sexo\tSección\tEdad (grupos quinquenales)\tTotal\nAmbos Sexos\t0100100001\tTotal\t1,944\nAmbos Sexos\tTOTAL\tTotal\t9.999\n"
    assert _parse_secciones_csv(text)["TOTAL_POB"].tolist() == [1944.0]
