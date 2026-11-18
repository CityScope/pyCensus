"""Official metropolitan-area boundaries for any city in the world, following the United Nations definition.

The UN Statistical Commission endorsed the *Degree of Urbanisation* method in 2020 (EC, FAO, ILO, OECD, UN-Habitat, World Bank) as the
global definition of cities and urban areas. The Global Human Settlement Layer (European Commission, JRC) applies it worldwide, and this module
downloads its two boundary products:

* ``"urban_centre"`` -- the *city* of the Degree of Urbanisation: contiguous 1 km grid cells of >= 1,500 inhabitants per km2 (or >= 50%
  built-up) with a total of >= 50,000 inhabitants (GHS-UCDB R2024A, population 2025).
* ``"functional_urban_area"`` -- the *metropolitan area*: the urban centre plus the surrounding commuting zone (cells sending >= 15% of
  their workers to the centre) (GHS-FUA, with R2019A boundaries on 2015 population; the only global release of the commuting zone).

Both come back as GeoDataFrames in EPSG:4326 with the same columns (``name``, ``country_iso``, ``country``, ``population``, ``area_km2``,
``kind``, ``source`` and the product's own id).

    from pycensus.worldwide import un_metro_areas
    un_metro_areas.find("Toronto", country="CAN")                       # functional urban area by name
    un_metro_areas.find(point=(-79.38, 43.65), kind="urban_centre")     # the city containing a point
    un_metro_areas.load_functional_urban_areas()                        # all ~9,000 areas

`find` and `for_aoi` return solid polygons (no interior rings) unless called with ``fill_holes=False``; separate parts stay separate.
"""

from __future__ import annotations

import logging
import unicodedata
import zipfile
from pathlib import Path
from typing import Optional, Sequence, Tuple, Union

import geopandas as gpd
import pandas as pd
import requests

from ..cache import default_cache_dir

logger = logging.getLogger(__name__)

JRC = "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL"
UCDB_URL = JRC + "/GHS_UCDB_GLOBE_R2024A/GHS_UCDB_GLOBE_R2024A/{version}/GHS_UCDB_GLOBE_R2024A_{vfile}.zip"
FUA_URL = JRC + "/GHS_FUA_UCDB2015_GLOBE_R2019A/V1-0/GHS_FUA_UCDB2015_GLOBE_R2019A_54009_1K_V1_0.zip"
UCDB_LAYER = "GHSL_UCDB_THEME_GENERAL_CHARACTERISTICS_GLOBE_R2024A"
ATTRIBUTION = ("European Commission, Joint Research Centre (JRC), Global Human Settlement Layer: GHS-UCDB R2024A Urban Centre Database and GHS-FUA "
               "R2019A Functional Urban Areas, Degree of Urbanisation method endorsed by the UN Statistical Commission (2020).")
KINDS = ("functional_urban_area", "urban_centre")
_MOLLWEIDE = "ESRI:54009"


def _root(cache_dir: Optional[str]) -> Path:
    root = Path(cache_dir or default_cache_dir()) / "un_metro_areas"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _download(url: str, dest: Path) -> Path:
    if dest.exists():
        return dest
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    tmp.replace(dest)
    return dest


def _unzip_member(zip_path: Path, suffix: str, dest_dir: Path) -> Path:
    with zipfile.ZipFile(zip_path) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(suffix))
        out = dest_dir / Path(name).name
        if not out.exists():
            z.extract(name, dest_dir)
            if (dest_dir / name) != out:
                (dest_dir / name).replace(out)
        return out


def _iso3(name: str) -> Optional[str]:
    """ISO 3166 alpha-3 code of a country name as the UCDB writes it (None when unknown or pycountry is missing)."""
    try:
        import pycountry
        return pycountry.countries.lookup(name).alpha_3
    except Exception:  # noqa: BLE001
        return None


def load_urban_centres(cache_dir: Optional[str] = None, version: str = "V1-2") -> gpd.GeoDataFrame:
    """Cities (urban centres) of the Degree of Urbanisation, GHS-UCDB R2024A (population 2025), EPSG:4326.

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        version: GHS-UCDB version.

    Returns:
        The urban centres.
    """
    root = _root(cache_dir)
    cached = root / f"urban_centres_{version}.parquet"
    if cached.is_file():
        return gpd.read_parquet(cached)
    z = _download(UCDB_URL.format(version=version, vfile=version.replace("-", "_")), root / f"GHS_UCDB_GLOBE_R2024A_{version}.zip")
    gpkg = _unzip_member(z, ".gpkg", root)
    g = gpd.read_file(gpkg, layer=UCDB_LAYER)
    g = g.set_crs(_MOLLWEIDE, allow_override=True).to_crs(4326)
    out = gpd.GeoDataFrame({
        "id": g["ID_UC_G0"].astype(str), "name": g["GC_UCN_MAI_2025"], "other_names": g["GC_UCN_LIS_2025"],
        "country_iso": g["GC_CNT_UNN_2025"].map({n: _iso3(n) for n in g["GC_CNT_UNN_2025"].dropna().unique()}).fillna(g["GC_CNT_GAD_2025"].map({n: _iso3(n) for n in g["GC_CNT_GAD_2025"].dropna().unique()})),
        "country": g["GC_CNT_UNN_2025"], "population": pd.to_numeric(g["GC_POP_TOT_2025"], errors="coerce"),
        "area_km2": pd.to_numeric(g["GC_UCA_KM2_2025"], errors="coerce"), "kind": "urban_centre", "source": "GHS-UCDB R2024A " + version,
    }, geometry=g.geometry.make_valid(), crs=4326)
    out.to_parquet(cached)
    return out


def load_functional_urban_areas(cache_dir: Optional[str] = None) -> gpd.GeoDataFrame:
    """Metropolitan areas (urban centre + commuting zone), GHS-FUA R2019A (population 2015), EPSG:4326.

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        The functional urban areas.
    """
    root = _root(cache_dir)
    cached = root / "functional_urban_areas_R2019A.parquet"
    if cached.is_file():
        return gpd.read_parquet(cached)
    z = _download(FUA_URL, root / "GHS_FUA_UCDB2015_GLOBE_R2019A_54009_1K_V1_0.zip")
    gpkg = _unzip_member(z, ".gpkg", root)
    g = gpd.read_file(gpkg)
    g = g.set_crs(_MOLLWEIDE, allow_override=True).to_crs(4326)
    out = gpd.GeoDataFrame({
        "id": g["eFUA_ID"].astype(str), "name": g["eFUA_name"], "other_names": "", "country_iso": g["Cntry_ISO"], "country": g["Cntry_name"],
        "population": pd.to_numeric(g["FUA_p_2015"], errors="coerce"), "area_km2": pd.to_numeric(g["FUA_area"], errors="coerce"),
        "urban_centre_population": pd.to_numeric(g["UC_p_2015"], errors="coerce"), "commuting_zone_population": pd.to_numeric(g["Com_p_2015"], errors="coerce"),
        "urban_centre_ids": g["UC_IDs"], "kind": "functional_urban_area", "source": "GHS-FUA R2019A",
    }, geometry=g.geometry.make_valid(), crs=4326)
    out.to_parquet(cached)
    return out


def load(kind: str = "functional_urban_area", cache_dir: Optional[str] = None) -> gpd.GeoDataFrame:
    """Functional urban areas (``"functional_urban_area"``) or urban centres (``"urban_centre"``).

    Args:
        kind: Which layer.
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        The layer.

    Raises:
        ValueError: For an unknown kind.
    """
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    return load_functional_urban_areas(cache_dir) if kind == "functional_urban_area" else load_urban_centres(cache_dir)


def _fold(s) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(s or "")) if not unicodedata.combining(c)).lower().strip()


def find(name: Optional[str] = None, country: Optional[str] = None, point: Optional[Tuple[float, float]] = None,
         kind: str = "functional_urban_area", cache_dir: Optional[str] = None, fill_holes: bool = True) -> gpd.GeoDataFrame:
    """Metro areas matching ``name`` (accent/case-insensitive, also against alternative names), ``country`` (ISO3 or name) and/or containing
    ``point`` = (lon, lat). Largest population first.

    Args:
        name: Name to look for.
        country: ISO3 code or country name.
        point: ``(lon, lat)`` the area must contain.
        kind: Which layer.
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        fill_holes: Remove interior rings.
    """
    g = load(kind, cache_dir)
    keep = pd.Series(True, index=g.index)
    if name:
        n = _fold(name)
        keep &= g["name"].map(_fold).str.contains(n, regex=False) | g["other_names"].map(_fold).str.contains(n, regex=False)
    if country:
        c = _fold(country)
        keep &= (g["country_iso"].map(_fold) == c) | (g["country"].map(_fold) == c)
    if point is not None:
        from shapely.geometry import Point
        keep &= g.geometry.contains(Point(*point))
    out = g[keep].sort_values("population", ascending=False).reset_index(drop=True)
    return globals()["fill_holes"](out) if fill_holes and len(out) else out


def for_aoi(aoi: Union[gpd.GeoDataFrame, gpd.GeoSeries], kind: str = "functional_urban_area", cache_dir: Optional[str] = None,
            fill_holes: bool = True) -> gpd.GeoDataFrame:
    """Metro areas intersecting an area of interest, with the share of the AOI each covers (``aoi_share``) and of itself inside the AOI (``area_share_in_aoi``).

    Args:
        aoi: Area of interest (GeoDataFrame).
        kind: Which layer.
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        fill_holes: Remove interior rings.
    """
    g = load(kind, cache_dir)
    if fill_holes:
        g = globals()["fill_holes"](g)
    a = aoi.to_crs(4326).union_all() if hasattr(aoi, "union_all") else aoi.to_crs(4326).unary_union
    hit = g[g.intersects(a)].copy()
    if hit.empty:
        return hit
    eq = "EPSG:6933"
    ae, he = gpd.GeoSeries([a], crs=4326).to_crs(eq).iloc[0], hit.to_crs(eq)
    inter = he.geometry.intersection(ae).area
    hit["aoi_share"] = (inter / ae.area).to_numpy()
    hit["area_share_in_aoi"] = (inter / he.geometry.area).to_numpy()
    return hit.sort_values("aoi_share", ascending=False).reset_index(drop=True)


def fill_holes(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Copy of ``gdf`` with every interior ring removed, so each part is a solid polygon (parts stay separate: a few areas are multipart islands).

    Args:
        gdf: Polygons.
    """
    from shapely.geometry import MultiPolygon, Polygon

    def solid(geom):
        parts = geom.geoms if isinstance(geom, MultiPolygon) else [geom]
        filled = [Polygon(p.exterior) for p in parts]
        return filled[0] if len(filled) == 1 else MultiPolygon(filled)

    out = gdf.copy()
    out["geometry"] = out.geometry.map(solid)
    return out
