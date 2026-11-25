"""Hamburg: share of public transport in residents' trips, Mobilitaet in Deutschland 2023 (MiD), Hamburg short report (hvv sample boost).
City of Hamburg 23 % of all trips (2017: 21 %); rest of the hvv area (Umland) 9 %. No Gemeinde breakdown of the Umland is published.

Per Bezirk and per Stadtregion (the finest published units of the city): the city's modal-split WFS (``HH_WFS_Modalsplit``, MiD 2023:
residents' trips by main mode, walking / cycling / public transport / car driver / car passenger). Around the city: the Kreise of the
Metropolregion, MiD 2017 regional report (``kreise``).

    from pycensus.census.countries.germany import mid_hamburg
    mid_hamburg.load()       # {"hamburg": {...}, "hvv_umland": {...}}
    mid_hamburg.bezirke()    # GeoDataFrame: 7 Bezirke, trip shares by mode (2023)
    mid_hamburg.kreise()     # GeoDataFrame: 13 Kreise of the Metropolregion around the city, trip shares by mode (MiD 2017 regional report)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pycensus.published_shares import fetch

URL = "https://www.hamburg.de/resource/blob/1132384/df391ad7f5773fe715e834e4926039e6/mid2023-kurzbericht-hamburg-data.pdf"
FIGURES = {
    "hamburg": {"transit_share": 0.23, "basis": "all trips of residents (main mode)", "year": 2023, "url": URL,
                "pattern": r"Anteil ÖPNV\s+21%\s+23%", "source": "MiD 2023, Hamburg short report: City of Hamburg, ÖPNV 23 % of trips"},
    "hvv_umland": {"transit_share": 0.09, "basis": "all trips of residents (main mode)", "year": 2023, "url": URL,
                   "pattern": r"hvv-Umland.*\b9%", "source": "MiD 2023, Hamburg short report: rest of the hvv area, ÖV 9 % of trips"},
}


def load(cache_dir: Optional[str] = None, verify: bool = True) -> dict:
    """Published travel-mode figures for Hamburg (MiD survey), checked against the source document.

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        verify: Check each figure in its document.

    Returns:
        ``{key: figure}``.
    """
    return fetch(FIGURES, cache_dir, verify)


WFS_URL = ("https://geodienste.hamburg.de/HH_WFS_Modalsplit?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=de.hh.up:{layer}"
           "&OUTPUTFORMAT=application/geo%2Bjson")
#: WFS field -> share column (the city's modal-split service: residents' trips by main mode, MiD 2023, per cent)
WFS_FIELDS = {"opv": "transit_trip_share", "zu_fuss": "walk_trip_share", "fahrrad": "bike_trip_share", "miv_fahrer": "car_driver_trip_share",
              "miv_mitfah": "car_passenger_trip_share"}
SHARES = tuple(WFS_FIELDS.values())


def _wfs(layer: str, name_field: str, cache_dir: Optional[str]):
    import geopandas as gpd
    import requests

    from pycensus import cache as cache_store

    d = Path(cache_dir or cache_store.default_cache_dir()) / "germany" / "mid_hamburg"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{layer}.geojson"
    if not f.is_file() or f.stat().st_size < 10_000:
        r = requests.get(WFS_URL.format(layer=layer), timeout=300)
        r.raise_for_status()
        f.write_bytes(r.content)
    g = gpd.read_file(f)
    # the city's WFS sends ETRS89 / UTM 32N (EPSG:25832) coordinates in GeoJSON, which readers take as WGS 84 (the GeoJSON default)
    if g.crs is None or (g.crs.to_epsg() == 4326 and abs(g.total_bounds).max() > 360):
        g = g.set_crs(25832, allow_override=True)
    g = g.to_crs(4326).rename(columns={name_field: "name"})
    g["GEOID"] = [str(i + 1) for i in range(len(g))] if "id" not in g else g["id"].astype(str).str.rsplit("_", n=1).str[-1]
    for f_, col in WFS_FIELDS.items():
        g[col] = g[f_].astype(float) / 100.0
    g["car_trip_share"] = g["car_driver_trip_share"] + g["car_passenger_trip_share"]
    return g[["GEOID", "name", *SHARES, "car_trip_share", "geometry"]]


def bezirke(cache_dir: Optional[str] = None):
    """The 7 Bezirke with the MiD 2023 shares of residents' trips by main mode (the city's WFS ``HH_WFS_Modalsplit``, layer
    ``modalsplit_bezirke``; the same values as slide 24 of the MiD 2023 Hamburg presentation).

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        GeoDataFrame (EPSG:4326): GEOID (Bezirk number), name, the five shares (0-1), ``car_trip_share`` (driver + passenger).
    """
    return _wfs("modalsplit_bezirke", "bezirk", cache_dir)


def stadtregionen(cache_dir: Optional[str] = None):
    """The 7 Stadtregionen (the MiD's own structural zoning of the city: Kernstadt, Äußerer Ring, ...) with the MiD 2023 shares of residents'
    trips by main mode (WFS layer ``modalsplit_stadtregion``). A second partition of the city, crossing the Bezirke.

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        GeoDataFrame (EPSG:4326), columns as :func:`bezirke`.
    """
    return _wfs("modalsplit_stadtregion", "stadtregion", cache_dir)


KREISE_URL = "https://metropolregion.hamburg.de/resource/blob/14320/b9af55d6f9f35c180f10d99447c308b6/mid-studie-data.pdf"
#: MiD 2017 regional report for the Metropolregion Hamburg and the hvv, Abbildung 17 (p. 35): residents' trips by main mode per Kreis
#: (survey values of the regional sample boost; Kreise whose sample was too small are not shown). Per cent: public transport, car
#: passenger, car driver, bicycle, walking. Keys: NUTS3 codes (GISCO), as `geography.district_names` names them.
KREISE_2017 = {
    "DEF06": ("Herzogtum Lauenburg", (7, 14, 46, 13, 20)), "DEF09": ("Pinneberg", (10, 13, 39, 16, 21)), "DEF0D": ("Segeberg", (10, 14, 46, 9, 21)),
    "DEF0F": ("Stormarn", (12, 14, 44, 10, 21)), "DE933": ("Harburg", (9, 15, 45, 12, 19)), "DE939": ("Stade", (6, 15, 44, 14, 21)),
    "DE935": ("Lüneburg", (7, 17, 45, 13, 18)), "DE932": ("Cuxhaven", (5, 15, 53, 14, 12)), "DE93A": ("Uelzen", (6, 21, 45, 13, 16)),
    "DE80M": ("Nordwestmecklenburg", (5, 17, 49, 9, 21)), "DE80O": ("Ludwigslust-Parchim", (9, 12, 47, 11, 21)),
    "DEF03": ("Lübeck", (12, 11, 33, 20, 25)), "DE804": ("Schwerin", (11, 14, 36, 11, 27)),
}


def kreise(data_dir: Optional[str] = None):
    """The Kreise of the Metropolregion Hamburg with the MiD 2017 shares of residents' trips by main mode (chart labels transcribed).

    Args:
        data_dir: Folder of the raw boundary downloads; ``None`` = the pycensus cache.

    Returns:
        GeoDataFrame (EPSG:4326): GEOID (NUTS3), name, transit / car passenger / car driver / bike / walk trip shares (0-1), car_trip_share.
    """
    import geopandas as gpd

    from pycensus.census.countries.germany import geography

    g = geography.load_boundaries("district", data_dir=data_dir).to_crs(4326)
    g = g[g["GEOID"].isin(KREISE_2017)].copy()
    cols = ("transit_trip_share", "car_passenger_trip_share", "car_driver_trip_share", "bike_trip_share", "walk_trip_share")
    g["name"] = g["GEOID"].map(lambda k: KREISE_2017[k][0])
    for i, c in enumerate(cols):
        g[c] = g["GEOID"].map(lambda k: KREISE_2017[k][1][i] / 100.0)
    g["car_trip_share"] = g["car_driver_trip_share"] + g["car_passenger_trip_share"]
    g["year"] = 2017
    if len(g) != len(KREISE_2017):
        raise RuntimeError(f"Kreise not found in the boundaries: {sorted(set(KREISE_2017) - set(g['GEOID']))}")
    return gpd.GeoDataFrame(g[["GEOID", "name", *cols, "car_trip_share", "year", "geometry"]], geometry="geometry", crs=4326)
