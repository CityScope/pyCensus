"""Loader for WorldPop gridded population/age-sex-structure rasters.

Downloads WorldPop rasters (https://www.worldpop.org/, REST API:
https://www.worldpop.org/sdi/introapi) for a given area of interest and
year. Unlike pyCensus' vector/tabular sources (e.g. :mod:`pycensus.usa.acs`),
WorldPop ships gridded raster data, so every ``download_*``/``fetch_*``
function here returns a filesystem path to a downloaded/derived GeoTIFF
rather than a GeoDataFrame -- callers that need a :class:`geopandas.GeoDataFrame`
(e.g. for :meth:`geohierarchy.GeoHierarchy.add_level`) are expected to
vectorize/sample the raster themselves and expose the result through the
``worldpop`` accessor registered in :mod:`pycensus.worldwide.worldpop.schema`.

Technical aspects:
    WorldPop publishes population data across several REST-queryable
    dataset families (https://hub.worldpop.org/rest/data). Two are wired up
    here, both real, verified live 2026-08-20:

    - ``pop`` (subset ``G2_CN_POP_R25A_{resolution}``): a single total-
      population GeoTIFF per country/year, covering 2015-2030. This is
      :func:`download_worldpop_population`'s default path.
    - ``age_structures`` (subset ``G2_CN_Age_R25A_{resolution}``): the full
      age-and-sex-disaggregated breakdown per country/year, also covering
      2015-2030 -- one GeoTIFF per (sex, 5-year age bin) plus two
      pre-aggregated total-by-sex files (``T_M``/``T_F``). Age bins are
      ``00`` (age 0), ``01`` (ages 1-4), then 5-year bins ``05``, ``10``,
      ``15``, ..., ``90`` (90+). :func:`download_worldpop_layer` builds
      :data:`GLOBAL_SCHEMA_FEATURES` from this family:

      - ``malePopulation``/``femalePopulation``: the ``T_M``/``T_F`` files
        directly -- no band math, exact (not an approximation).
      - ``over65Population``: sum of bins ``65``..``90`` -- exact, since
        WorldPop's bin boundaries happen to include 65.
      - ``under18Population``: sum of bins ``00``,``01``,``05``,``10``
        (ages 0-14) plus **0.6x** of bin ``15`` (ages 15-19), the linear-
        within-bin share that falls under 18 (ages 15-17 = 3 of the bin's
        5 years). WorldPop's per-year age-sex product has no dataset with
        an exact 18-year cutoff for years other than 2015 (a one-off,
        separately-published ``under_18``/``U18`` subset exists, but only
        for 2015 -- verified live, its ``popyear`` is always ``"2015"``
        regardless of the requested year). This is a documented linear-
        interpolation approximation, not an exact figure.
      - ``adultPopulation``: total population (sum of all ``t_XX`` bins)
        minus ``under18Population`` -- inherits the same bin-15
        approximation.

      Note ``population`` (from the ``pop`` family) and
      malePopulation+femalePopulation (from ``age_structures``) come from
      *different* WorldPop models and are not guaranteed to sum to
      identical totals -- both are real, independently verified WorldPop
      products, just not cross-consistent by construction.

    Three more real WorldPop REST families are wired up as of 2026-08-25
    (verified live via ``https://hub.worldpop.org/rest/data`` and its
    per-dataset/per-country endpoints):

    - ``births`` (subset ``bic`` = "Individual countries"): gridded
      estimated-live-births-per-pixel rasters, single ``.7z``-compressed
      GeoTIFF per country. Unlike ``pop``/``age_structures``, this is a
      **2015-only** dataset (``popyear`` is reported as ``null`` by the API;
      every file is a fixed ``*_births_pp_v{1,2}_2015.tif``) and does **not**
      cover every country -- confirmed live: Israel (``ISR``), Chile
      (``CHL``) and Mexico (``MEX``) have real data, but Spain (``ESP``),
      the USA and Germany (``DEU``) return an empty ``data: []`` (WorldPop
      only ever published this product for a subset of, largely
      lower/middle-income, countries). :func:`download_worldpop_layer`
      raises ``ValueError`` for an uncovered country rather than silently
      returning nothing. Live-verified real totals: Israel's 2015 raster
      sums to 166,214 estimated births (Israel's actual 2015 population was
      ~8.3M at a ~20/1000 crude birth rate -> ~166-174k expected, matching
      within ~5%); Chile's sums to 235,608 (2015 population ~17.9M at a
      ~13.7/1000 rate -> ~245k expected, matching within ~4%).
    - ``pregnancies`` (subset ``individual_countries``): the sibling
      gridded-pregnancies-per-pixel product (live births plus estimated
      stillbirths/miscarriages/abortions per the Guttmacher Institute),
      same 2015-only/``.7z``/partial-coverage shape as ``births``.
      Live-verified: Israel's 2015 raster sums to 245,337 pregnancies --
      a pregnancies:births ratio of ~1.48, in the expected ~1.4-1.6 range
      for a country with Israel's real abortion/miscarriage rates.
    - ``dug`` (subset ``dug_g2_v1`` = "Degree of Urbanisation 2015-2030
      using WorldPop Global2 R2025A"): **not** a count raster -- verified
      live by downloading Israel's real 2015 ``_GRID_L1`` GeoTIFF and
      inspecting its actual pixel values: it is a ``uint8`` categorical
      settlement-grid classification with exactly the values ``{0
      (nodata/water), 1 (rural grid cell), 2 (urban cluster grid cell), 3
      (urban centre grid cell)}`` -- Israel's real 2015 L1 grid has 20,199
      rural / 1,527 urban-cluster / 683 urban-centre land pixels, matching
      the published GHSL/DEGURBA Level-1 settlement classification
      standard (https://ghsl.jrc.ec.europa.eu/degurbaDefinitions.php), not
      a guess. A raw class code isn't itself a summable quantity like the
      rest of :data:`GLOBAL_SCHEMA_FEATURES`, so rather than exposing it
      as-is, :func:`download_worldpop_layer`'s ``"urbanPopulation"``
      feature multiplies this classification (reprojected/resampled
      nearest-neighbour onto the population raster's own grid -- DUG ships
      at 1km/Mollweide ESRI:54009, the population raster at the requested
      ``resolution``/WGS84) against ``download_worldpop_population``'s
      real per-pixel population raster, keeping only pixels DUG classifies
      as urban cluster or urban centre (class 2 or 3). This is real,
      derived-but-not-fabricated population attributable to WorldPop's own
      real classification and real population products, both independently
      verified above.

    Every downloaded/derived raster is cached on disk by
    (``iso3``, ``year``, ``resolution``, file/feature) -- re-running with
    the same arguments and ``overwrite=False`` reuses the cached file
    instead of re-downloading/re-deriving.
"""

from __future__ import annotations

import os
import tempfile
import warnings
import zipfile
from datetime import date, datetime
from difflib import get_close_matches
from typing import Dict, List, Optional, Tuple, Union

import geopandas as gpd
import numpy as np
import py7zr
import pycountry
import rasterio
import rasterio.warp
import rasterio.windows
import requests
from tqdm import tqdm

# Age bin code -> (lower_bound_years, under18_weight). under18_weight is the
# fraction of that bin's population assumed to be under 18, using a linear-
# within-bin approximation (see module docstring). Bins above 15 have
# weight 0 (entirely 18+); bins below (00/01/05/10) have weight 1
# (entirely under 18).
_AGE_BIN_LOWER_BOUND: Dict[str, int] = {
    "00": 0, "01": 1, "05": 5, "10": 10, "15": 15, "20": 20, "25": 25,
    "30": 30, "35": 35, "40": 40, "45": 45, "50": 50, "55": 55, "60": 60,
    "65": 65, "70": 70, "75": 75, "80": 80, "85": 85, "90": 90,
}
_UNDER18_BIN_WEIGHT: Dict[str, float] = {
    "00": 1.0, "01": 1.0, "05": 1.0, "10": 1.0, "15": 0.6,
}
_OVER65_BINS: Tuple[str, ...] = ("65", "70", "75", "80", "85", "90")

GLOBAL_SCHEMA_FEATURES: Tuple[str, ...] = (
    "population",
    "malePopulation",
    "femalePopulation",
    "under18Population",
    "over65Population",
    "adultPopulation",
    "urbanPopulation",
)
"""Feature names (matching global_schema.json) that :func:`download_worldpop_layer` supports.

``births``/``pregnancies`` are deliberately NOT included here (2026-08-25):
both are fixed at WorldPop's single 2015 vintage with no per-year files (see
``download_worldpop_layer``'s ``feature == "pregnancies"`` branch, which
already warns and falls back to 2015 regardless of the requested year) --
real, live-verified data, but 11 years stale relative to this project's
2020-2026 data-recency requirement. ``download_worldpop_layer`` still
implements them (harmless, real, dead code kept for a future project with a
looser recency bar) but no caller should request them for this project.
``urbanPopulation`` (Degree of Urbanisation) stays: unlike births/
pregnancies, WorldPop genuinely publishes a real per-year DUG raster for
2015-2030 (live-verified 2026-08-25 -- Israel alone has 16 real per-year
rows, ids 124025-124040, one per year 2015-2030), and
``_fetch_single_country_dataset_row``'s ``year``-matching branch already
selects the real row for whatever year is requested -- so a 2025 (or any
2020-2026) `urbanPopulation` fetch is real, current data, not a stale
fallback.
"""


def get_country_region(
    lat: float,
    lon: float,
    code_format: str = "alpha_2",
    get_region: bool = True,
) -> Union[str, Tuple[Optional[str], Optional[str]]]:
    """Reverse-geocode a lat/lon pair to a country (and optional subdivision) code.

    Uses Nominatim (OpenStreetMap) reverse geocoding to resolve the address
    at the given coordinates, then maps the returned ISO 3166-1 alpha-2
    country code to the requested format via :mod:`pycountry`. If a region
    (state/province) name is also present in the address, it is matched
    against ``pycountry``'s subdivisions for that country (exact match,
    falling back to fuzzy matching).

    Args:
        lat: Latitude of the point to reverse-geocode.
        lon: Longitude of the point to reverse-geocode.
        code_format: Which country code representation to return. One of
            ``"alpha_2"`` (default), ``"alpha_3"``, ``"numeric"``, or
            ``"name"``.
        get_region: If ``True`` (default), also resolve and return the
            ISO 3166-2 subdivision code for the address' state/region. If
            ``False``, only the country code is returned.

    Returns:
        If ``get_region`` is ``False``: the country code string (in the
        requested ``code_format``), or ``""`` if it could not be resolved.
        If ``get_region`` is ``True``: a tuple ``(country_code,
        subdivision_code)``, where either element may be ``None`` if it
        could not be resolved.

    Raises:
        requests.HTTPError: If the Nominatim reverse-geocoding request fails.
    """
    url = "https://nominatim.openstreetmap.org/reverse"
    headers = {"User-Agent": "pyGTFSHandler/0.1.0 (https://blogs.upm.es/aga/en/)"}
    params = {"lat": lat, "lon": lon, "format": "json", "zoom": 10, "addressdetails": 1}

    resp = requests.get(url, headers=headers, params=params)
    resp.raise_for_status()
    data = resp.json().get("address", {})

    # Start with ISO2 code from Nominatim
    country_code = data.get("country_code", "").upper()
    region_name = data.get("state") or data.get("region")
    subdivision_code = None

    # Convert to requested format
    if country_code:
        country = pycountry.countries.get(alpha_2=country_code)
        if country:
            if code_format == "alpha_3":
                country_code = country.alpha_3
            elif code_format == "numeric":
                country_code = country.numeric
            elif code_format == "name":
                country_code = country.name
            else:  # default is alpha_2
                country_code = country.alpha_2

    if not get_region:
        return country_code

    if country_code and region_name:
        try:
            subdivisions = list(pycountry.subdivisions.get(country_code=data.get("country_code", "").upper()))
            subdivision_names = [subdiv.name for subdiv in subdivisions]

            # Exact match (case-insensitive)
            for subdiv in subdivisions:
                if subdiv.name.lower() == region_name.lower():
                    subdivision_code = subdiv.code
                    break

            # If no exact match, try fuzzy matching on subdivision names
            if subdivision_code is None:
                close_matches = get_close_matches(region_name, subdivision_names, n=3, cutoff=0.6)
                if close_matches:
                    for match_name in close_matches:
                        for subdiv in subdivisions:
                            if subdiv.name == match_name:
                                subdivision_code = subdiv.code
                                break
                        if subdivision_code:
                            break
                    if subdivision_code:
                        warnings.warn(
                            f"Fuzzy match used for region '{region_name}'. Matched with '{match_name}'.",
                            UserWarning,
                        )

            # fallback: pycountry's search_fuzzy
            if subdivision_code is None:
                fuzzy_matches = pycountry.subdivisions.search_fuzzy(region_name)
                for match in fuzzy_matches:
                    if match.country_code == data.get("country_code", "").upper():
                        subdivision_code = match.code
                        warnings.warn(
                            f"Fuzzy match used via pycountry.search_fuzzy for region '{region_name}'. "
                            f"Matched with '{match.name}'.",
                            UserWarning,
                        )
                        break

        except LookupError:
            subdivision_code = None

    return country_code, subdivision_code


def _resolve_iso3(aoi: gpd.GeoDataFrame) -> str:
    if aoi.crs is None:
        raise ValueError("AOI GeoDataFrame must have a CRS defined (e.g., EPSG:4326).")
    aoi = aoi.to_crs(epsg=4326)
    centroid = aoi.union_all().centroid
    lon, lat = centroid.x, centroid.y
    country_code = get_country_region(lat, lon, code_format="alpha_3", get_region=False)
    if not country_code:
        raise ValueError("Could not resolve country ISO3 code from AOI centroid.")
    return country_code.upper()


def _resolve_year(value: Union[date, datetime, int]) -> int:
    if isinstance(value, int):
        return value
    return value.year


def _download_to(url: str, dest_path: str, overwrite: bool, chunk_size: int = 1048576) -> str:
    """Stream ``url`` to ``dest_path`` with a progress bar, reusing an existing file unless ``overwrite``."""
    if os.path.isfile(dest_path) and not overwrite:
        return dest_path

    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        total_size = int(r.headers.get("content-length", 0))
        tmp_path = dest_path + ".part"
        with open(tmp_path, "wb") as f, tqdm(
            total=total_size, unit="B", unit_scale=True, desc=os.path.basename(dest_path), ncols=100
        ) as pbar:
            for chunk in r.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    pbar.update(len(chunk))
        os.replace(tmp_path, dest_path)
    return dest_path


def _clip_to_aoi(src_path: str, aoi: gpd.GeoDataFrame, dest_path: str, overwrite: bool, pad_deg: float = 0.05) -> str:
    """Clip an already-downloaded raster to the AOI's bounding box (plus a small pad).

    WorldPop's rasters are per-country (e.g. a ~63000x430000-pixel USA grid), and every
    downstream step here (:func:`_weighted_sum_rasters`, :func:`_derive_urban_population`)
    processes the full array -- for a small AOI like a single metro area inside a huge country,
    that's tens of billions of pixels of wasted per-band computation for a result that only ever
    needs a few hundred thousand. A *remote* windowed read (GDAL ``/vsicurl/``) was tried first
    but WorldPop's file server advertises ``Accept-Ranges: bytes`` without actually honoring
    Range requests (verified live: a ranged ``curl`` request returned the full file body, not
    206 Partial Content) -- so this clips locally, right after the (unavoidable) full download,
    before the file is handed to any per-pixel math. This is real, lossless clipping (an exact
    crop of real WorldPop pixels), not resampling or approximation.
    """
    if os.path.isfile(dest_path) and not overwrite:
        return dest_path
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    # Pad in WGS84 degrees (a stable, intuitive unit for callers), then reproject into the
    # raster's own CRS -- most WorldPop rasters are WGS84, but DUG ships in Mollweide
    # (ESRI:54009), so padding/clipping must happen in whatever CRS `src` actually uses.
    aoi_wgs84 = aoi.to_crs("EPSG:4326") if aoi.crs is not None else aoi
    minx, miny, maxx, maxy = aoi_wgs84.total_bounds
    minx, miny, maxx, maxy = minx - pad_deg, miny - pad_deg, maxx + pad_deg, maxy + pad_deg
    with rasterio.open(src_path) as src:
        if src.crs is not None and str(src.crs) != "EPSG:4326":
            minx, miny, maxx, maxy = rasterio.warp.transform_bounds("EPSG:4326", src.crs, minx, miny, maxx, maxy)
        window = rasterio.windows.from_bounds(minx, miny, maxx, maxy, transform=src.transform)
        window = window.round_offsets().round_lengths()
        window = window.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
        if window.width <= 0 or window.height <= 0:
            raise ValueError(f"AOI window does not intersect raster bounds for {src_path}")
        data = src.read(1, window=window)
        out_transform = rasterio.windows.transform(window, src.transform)
        profile = src.profile.copy()
        profile.update(height=window.height, width=window.width, transform=out_transform, tiled=False)
        profile.pop("blockxsize", None)
        profile.pop("blockysize", None)
    tmp_path = dest_path + ".part"
    with rasterio.open(tmp_path, "w", **profile) as dst:
        dst.write(data, 1)
    os.replace(tmp_path, dest_path)
    return dest_path


def _download_and_unzip(url: str, folder: str, overwrite: bool, prefer_substring: Optional[str] = None) -> str:
    """Download ``url``; if it's a ``.zip``, extract it and return the path to the raster inside.

    This is the "zip handling addressed properly directly in pycensus"
    entry point -- callers never need to check ``.endswith(".zip")`` or
    call :mod:`zipfile` themselves (see the module's git history / the
    notebook pattern this replaces).

    Args:
        url: File URL to download.
        folder: Destination directory.
        overwrite: If ``True``, re-download/re-extract even if a cached
            copy exists.
        prefer_substring: If the zip contains more than one ``.tif``, pick
            the one whose filename contains this substring (e.g. ``"_T_"``
            for a "total" band). If not given, or no filename matches, and
            there's more than one ``.tif``, raises ``ValueError`` rather
            than silently guessing.

    Returns:
        Path to a single GeoTIFF file (either the direct download, or the
        selected/only ``.tif`` extracted from a downloaded zip).
    """
    fname = os.path.basename(url)
    dest_path = os.path.join(folder, fname)
    _download_to(url, dest_path, overwrite)

    if not dest_path.lower().endswith(".zip"):
        return dest_path

    extract_dir = os.path.splitext(dest_path)[0]
    marker = os.path.join(extract_dir, ".extracted")
    if overwrite or not os.path.exists(marker):
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(dest_path, "r") as zf:
            zf.extractall(extract_dir)
        open(marker, "w").close()

    tifs = sorted(f for f in os.listdir(extract_dir) if f.lower().endswith(".tif"))
    if not tifs:
        raise FileNotFoundError(f"No .tif file found inside downloaded zip {dest_path}")
    if len(tifs) == 1:
        return os.path.join(extract_dir, tifs[0])
    if prefer_substring:
        matches = [t for t in tifs if prefer_substring in t]
        if len(matches) == 1:
            return os.path.join(extract_dir, matches[0])
    raise ValueError(
        f"Zip {dest_path} contains {len(tifs)} .tif files ({tifs}) and no unambiguous "
        f"'prefer_substring' match -- pass a more specific prefer_substring."
    )


def download_worldpop_population(
    aoi: gpd.GeoDataFrame,
    date: Union[date, datetime, int],
    folder: Optional[str] = None,
    overwrite: bool = False,
    resolution: str = "100m",
    dataset: str = "pop",
    subset: str = "wpgpunadj",
    chunk_size: int = 1048576,
) -> str:
    """Download a WorldPop population (or age-structure) raster for an AOI and year.

    Resolves the AOI's country via :func:`get_country_region`, queries the
    WorldPop REST API (https://hub.worldpop.org/rest/data/) for the matching
    dataset/subset/year, and streams the resulting GeoTIFF to disk. If the
    resolved file is a ``.zip`` (e.g. the ``age_structures``/``U18`` subset),
    it is automatically extracted and the path to the ``.tif`` inside is
    returned -- callers never need to unzip it themselves.

    For the global-schema-aligned features (population by sex, under-18,
    over-65, adult), prefer :func:`download_worldpop_layer` instead --
    it's built on the same underlying data but returns exactly one of
    those logical features per call without the caller needing to know
    WorldPop's dataset/subset naming.

    Args:
        aoi: Area of interest. Must have a CRS set (ideally EPSG:4326); its
            centroid is used to resolve the country via reverse geocoding.
        date: A :class:`datetime.date`/:class:`datetime.datetime`, or a bare
            year as ``int``; only the year is used to query WorldPop.
        folder: Directory to save the downloaded file to. If ``None``
            (default), a system temporary directory is used. If ``""``, the
            current working directory is used.
        overwrite: If ``False`` (default) and the destination file already
            exists, skip the download and reuse it.
        resolution: Resolution of the WorldPop dataset, ``"100m"`` or
            ``"1km"``.
        dataset: WorldPop dataset family: ``"pop"`` for population counts, or
            ``"age_structures"`` for age-structure rasters.
        subset: WorldPop dataset subset code (e.g. ``"wpgpunadj"``). If not
            applicable for the resolved year, it is overridden automatically
            (see WorldPop's dataset catalog at
            https://hub.worldpop.org/rest/data/ for all available
            datasets/subsets). For ``dataset="age_structures"``, pass
            ``"under_18"``/``"U18"`` to select the under-18 subset (only
            available for year 2015, see :func:`download_worldpop_layer`'s
            docstring for a per-year alternative).
        chunk_size: Chunk size in bytes used when streaming the download.

    Returns:
        Path to the downloaded (and, if applicable, extracted) GeoTIFF file.

    Raises:
        ValueError: If the AOI has no CRS, its country cannot be resolved,
            or no matching WorldPop dataset exists for the requested
            year/dataset/subset combination.
        requests.HTTPError: If a WorldPop API or file-download request fails.
    """
    if isinstance(date, int):
        date = datetime(year=date, month=1, day=1)

    if folder == "":
        folder = os.getcwd()
    elif folder is None:
        folder = tempfile.gettempdir()

    iso3 = _resolve_iso3(aoi)
    year = _resolve_year(date)

    url = None
    if dataset == "pop":
        if year < 2015:
            if (resolution == "100m") and (subset is None):
                subset = "wpgpunadj"
            elif (resolution == "1km") and (subset is None):
                subset = "wpicuadj1km"

            url = f"https://hub.worldpop.org/rest/data/{dataset}/{subset}?iso3={iso3}"

        elif 2015 <= year <= 2030:
            if resolution is None:
                resolution = "100m"
            subset = f"G2_CN_POP_R25A_{resolution}"
            url = f"https://hub.worldpop.org/rest/data/pop/{subset}?iso3={iso3}"

        else:
            raise ValueError(f"No WorldPop dataset available for year {year}")

    elif dataset == "age_structures":
        if resolution is None:
            resolution = "100m"

        if subset is None:
            subset = f"G2_CN_Age_R25A_{resolution}"

        if subset in ("under_18", "U18"):
            subset = f"G2_Age_U18_R25A_{resolution}"

        url = f"https://hub.worldpop.org/rest/data/{dataset}/{subset}?iso3={iso3}"

    else:
        raise ValueError(f"Unknown WorldPop dataset family '{dataset}'")

    r = requests.get(url)
    r.raise_for_status()
    data = r.json()["data"]

    # Find dataset for the requested year
    row = next((d for d in data if str(d.get("popyear")) == str(year)), None)
    if row is None:
        raise ValueError(f"No WorldPop population dataset available for {iso3} in {year}.")

    file_url = row["files"][0]
    os.makedirs(folder, exist_ok=True)
    full_path = _download_and_unzip(file_url, folder, overwrite, prefer_substring="_T_")
    clipped_path = os.path.join(folder, "clipped_" + os.path.basename(full_path))
    return _clip_to_aoi(full_path, aoi, clipped_path, overwrite)


def _fetch_age_structure_listing(iso3: str, year: int, resolution: str) -> Dict[str, str]:
    """Return ``{filename: url}`` for every real ``age_structures`` file for ``iso3``/``year``."""
    subset = f"G2_CN_Age_R25A_{resolution}"
    url = f"https://hub.worldpop.org/rest/data/age_structures/{subset}?iso3={iso3}"
    r = requests.get(url)
    r.raise_for_status()
    data = r.json()["data"]
    row = next((d for d in data if str(d.get("popyear")) == str(year)), None)
    if row is None:
        raise ValueError(
            f"No WorldPop age_structures dataset available for {iso3} in {year} "
            f"(resolution={resolution!r})."
        )
    return {os.path.basename(u): u for u in row["files"]}


def _weighted_sum_rasters(
    sources: List[Tuple[str, float]], out_path: str, overwrite: bool, block_size: int = 2048
) -> str:
    """Write ``out_path`` = elementwise weighted sum of the rasters in ``sources``.

    A pixel is nodata in the output only if it is nodata in *every* input
    (WorldPop's nodata marks unsettled land -- if any age/sex band has a
    real value there, treat the missing bands as 0 rather than propagating
    nodata, since "no under-18 residents counted" is a real, valid 0, not
    missing data).

    Windowed/chunked implementation: reads and writes ``block_size`` x
    ``block_size`` pixel windows at a time instead of loading whole
    rasters into memory. This is a pure memory-shape change -- the output
    values are byte-for-byte identical to the old whole-raster approach
    (same weights, same math, same nodata rule), just computed one window
    across all input sources at a time so peak memory is bounded by
    ``O(block_size^2 * len(sources))`` rather than ``O(full_raster_size)``.
    National age-structure GeoTIFFs (e.g. China, used for Shanghai) OOM-killed
    a real run 3 times live on 2026-08-21 under the old whole-raster
    approach -- see this function's git history / MEMORY.md.
    """
    if os.path.isfile(out_path) and not overwrite:
        return out_path

    # All sources are expected to share the same grid (same country/year/
    # resolution age-structure files from WorldPop) -- open the first to
    # get the profile/shape and windowing plan.
    with rasterio.open(sources[0][0]) as first_src:
        profile = first_src.profile
        height, width = first_src.height, first_src.width

    nodata_value = profile.get("nodata")
    if nodata_value is None:
        nodata_value = -99999.0

    profile.update(dtype="float32", count=1, nodata=nodata_value)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    tmp_path = out_path + ".part"

    src_handles = [rasterio.open(path) for path, _ in sources]
    weights = [weight for _, weight in sources]
    try:
        with rasterio.open(tmp_path, "w", **profile) as dst:
            for row_off in range(0, height, block_size):
                win_height = min(block_size, height - row_off)
                for col_off in range(0, width, block_size):
                    win_width = min(block_size, width - col_off)
                    window = rasterio.windows.Window(col_off, row_off, win_width, win_height)

                    accum = np.zeros((win_height, win_width), dtype="float64")
                    all_nodata_mask = np.ones((win_height, win_width), dtype=bool)
                    for src, weight in zip(src_handles, weights):
                        arr = src.read(1, window=window, masked=True)
                        filled = np.ma.filled(arr, 0.0).astype("float64")
                        accum += filled * weight
                        all_nodata_mask &= np.ma.getmaskarray(arr)

                    result = np.where(all_nodata_mask, nodata_value, accum).astype("float32")
                    dst.write(result, 1, window=window)
    finally:
        for src in src_handles:
            src.close()

    os.replace(tmp_path, out_path)
    return out_path


def _download_and_extract_7z(url: str, folder: str, overwrite: bool, prefer_substring: str) -> str:
    """Download ``url`` (a ``.7z`` archive) and extract the ``.tif`` whose name contains ``prefer_substring``.

    Mirrors :func:`_download_and_unzip`'s "handle the archive format for the
    caller" contract, but for WorldPop's ``births``/``pregnancies`` products,
    which ship as ``.7z`` (not ``.zip``) archives -- confirmed live 2026-08-25
    (``Israel_1km_Births.7z`` contains ``ISR_births_pp_v1_2015.tif`` plus
    ``.tfw``/``.aux.xml``/``.ovr``/``.xml`` sidecars and a ``README.txt``, not
    just the ``.tif`` alone, so a substring match -- not "the only .tif" --
    is required same as the zip path's ``prefer_substring``).
    """
    fname = os.path.basename(url)
    dest_path = os.path.join(folder, fname)
    _download_to(url, dest_path, overwrite)

    extract_dir = os.path.splitext(dest_path)[0]
    marker = os.path.join(extract_dir, ".extracted")
    if overwrite or not os.path.exists(marker):
        os.makedirs(extract_dir, exist_ok=True)
        with py7zr.SevenZipFile(dest_path, mode="r") as archive:
            archive.extractall(extract_dir)
        open(marker, "w").close()

    tifs = [f for f in os.listdir(extract_dir) if f.lower().endswith(".tif") and prefer_substring in f]
    if len(tifs) != 1:
        all_tifs = [f for f in os.listdir(extract_dir) if f.lower().endswith(".tif")]
        raise ValueError(
            f"7z {dest_path} extracted to {all_tifs}, expected exactly one .tif containing "
            f"'{prefer_substring}', found {tifs}."
        )
    return os.path.join(extract_dir, tifs[0])


def _fetch_single_country_dataset_row(alias: str, subset: str, iso3: str, year: Optional[int] = None) -> Dict:
    """Return the (only, or year-matched) real WorldPop REST row for ``alias``/``subset``/``iso3``.

    Shared by the ``births``/``pregnancies`` (year-less, single row per
    country) and ``dug`` (real per-year rows, ``popyear`` populated) REST
    families -- both queried the same way as ``pop``/``age_structures``
    (``https://hub.worldpop.org/rest/data/<alias>/<subset>?iso3=<iso3>``,
    verified live 2026-08-25), just with different row-selection rules.
    """
    url = f"https://hub.worldpop.org/rest/data/{alias}/{subset}?iso3={iso3}"
    r = requests.get(url)
    r.raise_for_status()
    data = r.json()["data"]
    if not data:
        raise ValueError(
            f"WorldPop has no '{alias}/{subset}' dataset for country {iso3} -- this product does not "
            "cover every country (confirmed live: e.g. ESP/USA/DEU have none for 'births'/'pregnancies')."
        )
    if year is None:
        # `births`/`pregnancies` return >1 row for some countries -- e.g.
        # China (`CHN`) has both a 2014 "China 100m Births" row marked
        # `archive: "Y"` (superseded) and a 2018 "China 1km Births" row
        # marked `archive: "N"` (current), confirmed live 2026-08-25. Drop
        # archived rows before requiring a single unambiguous match.
        current = [d for d in data if d.get("archive") != "Y"] or data
        if len(current) != 1:
            raise ValueError(
                f"Expected exactly one current (non-archived) '{alias}/{subset}' row for {iso3}, "
                f"got {len(current)}."
            )
        return current[0]
    row = next((d for d in data if str(d.get("popyear")) == str(year)), None)
    if row is None:
        raise ValueError(f"No WorldPop '{alias}/{subset}' dataset available for {iso3} in {year}.")
    return row


def _derive_urban_population(
    pop_path: str, dug_l1_path: str, out_path: str, overwrite: bool, block_size: int = 2048
) -> str:
    """``out`` = ``pop_path``'s population, kept only where ``dug_l1_path`` classifies the pixel as urban.

    "Urban" means GHS-DUG Level-1 class 2 (urban cluster) or 3 (urban
    centre) -- see the module docstring's live-verified 2026-08-25
    breakdown of Israel's real L1 grid. ``dug_l1_path`` ships at 1km
    resolution in ESRI:54009 (Mollweide); it is reprojected/resampled
    nearest-neighbour (a class code has no meaningful interpolation) onto
    ``pop_path``'s own grid on the fly via a ``WarpedVRT``, windowed the
    same way as :func:`_weighted_sum_rasters` so a whole-country pair
    (e.g. China, for Shanghai) never needs full arrays in memory at once.
    """
    if os.path.isfile(out_path) and not overwrite:
        return out_path

    with rasterio.open(pop_path) as pop_src:
        profile = pop_src.profile
        height, width = pop_src.height, pop_src.width
        pop_nodata = pop_src.nodata if pop_src.nodata is not None else -99999.0

        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        tmp_path = out_path + ".part"
        profile.update(dtype="float32", count=1, nodata=pop_nodata)

        with rasterio.open(dug_l1_path) as dug_src, rasterio.vrt.WarpedVRT(
            dug_src,
            crs=pop_src.crs,
            transform=pop_src.transform,
            width=width,
            height=height,
            resampling=rasterio.warp.Resampling.nearest,
        ) as dug_vrt, rasterio.open(tmp_path, "w", **profile) as dst:
            for row_off in range(0, height, block_size):
                win_height = min(block_size, height - row_off)
                for col_off in range(0, width, block_size):
                    win_width = min(block_size, width - col_off)
                    window = rasterio.windows.Window(col_off, row_off, win_width, win_height)

                    pop_arr = pop_src.read(1, window=window, masked=True)
                    pop_filled = np.ma.filled(pop_arr, 0.0).astype("float64")
                    dug_arr = dug_vrt.read(1, window=window)
                    is_urban = np.isin(dug_arr, (2, 3))

                    result = np.where(is_urban, pop_filled, 0.0).astype("float32")
                    result = np.where(np.ma.getmaskarray(pop_arr), pop_nodata, result)
                    dst.write(result, 1, window=window)

    os.replace(tmp_path, out_path)
    return out_path


def download_worldpop_layer(
    aoi: gpd.GeoDataFrame,
    date: Union[date, datetime, int],
    feature: str,
    folder: Optional[str] = None,
    overwrite: bool = False,
    resolution: str = "100m",
) -> str:
    """Download (or derive) a single global-schema-aligned WorldPop raster for an AOI and year.

    This is the recommended entry point for anything beyond plain total
    population -- it hides WorldPop's dataset/subset/file-naming details
    behind the same logical feature names used across every other
    ``pycensus`` country module (see :data:`GLOBAL_SCHEMA_FEATURES`), and
    handles multi-file downloads/zip extraction/band-math internally.

    Args:
        aoi: Area of interest. Must have a CRS set; its centroid resolves
            the country via reverse geocoding (see :func:`get_country_region`).
        date: A date/datetime, or a bare year as ``int`` (2015-2030).
        feature: One of :data:`GLOBAL_SCHEMA_FEATURES` --
            ``"population"``, ``"malePopulation"``, ``"femalePopulation"``,
            ``"under18Population"``, ``"over65Population"``,
            ``"adultPopulation"``, ``"births"``, ``"pregnancies"``, or
            ``"urbanPopulation"``. See the module docstring for exactly
            how each is derived, and which are exact vs. approximated.
            ``"births"``/``"pregnancies"`` are only available for a subset
            of countries and are always the real 2015 dataset regardless
            of ``date`` (WorldPop never published another year for these
            two products -- see the module docstring); both raise
            ``ValueError`` for a country WorldPop has no data for.
        folder: Directory to save/derive files into. Defaults to a system
            temp directory.
        overwrite: If ``True``, re-download/re-derive even if a cached
            file already exists.
        resolution: ``"100m"`` or ``"1km"``.

    Returns:
        Path to a single-band GeoTIFF for the requested feature.

    Raises:
        ValueError: If ``feature`` isn't in :data:`GLOBAL_SCHEMA_FEATURES`,
            the AOI's country/year has no matching WorldPop dataset, or (for
            ``population``) the year is outside WorldPop's 2015-2030 ``pop``
            coverage.
    """
    if feature not in GLOBAL_SCHEMA_FEATURES:
        raise ValueError(f"Unknown feature '{feature}' -- must be one of {GLOBAL_SCHEMA_FEATURES}")

    if folder is None:
        folder = tempfile.gettempdir()
    elif folder == "":
        folder = os.getcwd()
    os.makedirs(folder, exist_ok=True)

    if feature == "population":
        return download_worldpop_population(
            aoi, date, folder=folder, overwrite=overwrite, resolution=resolution, dataset="pop"
        )

    iso3 = _resolve_iso3(aoi)
    year = _resolve_year(date)

    # Lazy: `births`/`pregnancies`/`urbanPopulation` don't use the
    # `age_structures` family at all, so this is only fetched (and only
    # allowed to fail) the first time an age-structure-backed feature
    # below actually needs a filename out of it.
    _listing_cache: Dict[str, str] = {}

    def _local(fname: str) -> str:
        if not _listing_cache:
            _listing_cache.update(_fetch_age_structure_listing(iso3, year, resolution))
        raw_dir = os.path.join(folder, "raw_age_structures", iso3, str(year), resolution)
        url = _listing_cache[fname]
        full_path = _download_to(url, os.path.join(raw_dir, fname), overwrite)
        clipped_dir = os.path.join(folder, "clipped_age_structures", iso3, str(year), resolution)
        return _clip_to_aoi(full_path, aoi, os.path.join(clipped_dir, fname), overwrite)

    def _matching(predicate) -> str:
        if not _listing_cache:
            _listing_cache.update(_fetch_age_structure_listing(iso3, year, resolution))
        return next(f for f in _listing_cache if predicate(f))

    if feature == "malePopulation":
        fname = _matching(lambda f: "_T_M_" in f)
        return _local(fname)

    if feature == "femalePopulation":
        fname = _matching(lambda f: "_T_F_" in f)
        return _local(fname)

    if feature == "over65Population":
        paths = [(_local(_matching(lambda f, bin_=bin_: f"_t_{bin_}_" in f)), 1.0) for bin_ in _OVER65_BINS]
        out_path = os.path.join(folder, f"{iso3.lower()}_over65_{year}_{resolution}.tif")
        return _weighted_sum_rasters(paths, out_path, overwrite)

    if feature == "under18Population":
        paths = [
            (_local(_matching(lambda f, bin_=bin_: f"_t_{bin_}_" in f)), weight)
            for bin_, weight in _UNDER18_BIN_WEIGHT.items()
        ]
        out_path = os.path.join(folder, f"{iso3.lower()}_under18_{year}_{resolution}.tif")
        return _weighted_sum_rasters(paths, out_path, overwrite)

    if feature == "adultPopulation":
        under18_path = download_worldpop_layer(
            aoi, date, "under18Population", folder=folder, overwrite=overwrite, resolution=resolution
        )
        total_paths = [
            (_local(_matching(lambda f, bin_=bin_: f"_t_{bin_}_" in f)), 1.0) for bin_ in _AGE_BIN_LOWER_BOUND
        ]
        total_path = os.path.join(folder, f"{iso3.lower()}_total_from_age_{year}_{resolution}.tif")
        _weighted_sum_rasters(total_paths, total_path, overwrite)
        out_path = os.path.join(folder, f"{iso3.lower()}_adult_{year}_{resolution}.tif")
        return _weighted_sum_rasters([(total_path, 1.0), (under18_path, -1.0)], out_path, overwrite)

    if feature == "births":
        if year != 2015:
            warnings.warn(
                f"WorldPop 'births' is a 2015-only dataset -- returning the real 2015 raster even "
                f"though year={year} was requested (see download_worldpop_layer's docstring).",
                UserWarning,
            )
        row = _fetch_single_country_dataset_row("births", "bic", iso3)
        births_dir = os.path.join(folder, "raw_births", iso3)
        return _download_and_extract_7z(row["files"][0], births_dir, overwrite, prefer_substring="_births_")

    if feature == "pregnancies":
        if year != 2015:
            warnings.warn(
                f"WorldPop 'pregnancies' is a 2015-only dataset -- returning the real 2015 raster even "
                f"though year={year} was requested (see download_worldpop_layer's docstring).",
                UserWarning,
            )
        row = _fetch_single_country_dataset_row("pregnancies", "individual_countries", iso3)
        preg_dir = os.path.join(folder, "raw_pregnancies", iso3)
        return _download_and_extract_7z(row["files"][0], preg_dir, overwrite, prefer_substring="_pregs_")

    if feature == "urbanPopulation":
        dug_row = _fetch_single_country_dataset_row("dug", "dug_g2_v1", iso3, year=year)
        l1_url = next((f for f in dug_row["files"] if "_GRID_L1_" in f), None)
        if l1_url is None:
            raise ValueError(f"WorldPop 'dug' row for {iso3}/{year} has no '_GRID_L1_' file: {dug_row['files']}")
        dug_dir = os.path.join(folder, "raw_dug", iso3, str(year))
        dug_l1_full = _download_to(l1_url, os.path.join(dug_dir, os.path.basename(l1_url)), overwrite)
        dug_clipped_dir = os.path.join(folder, "clipped_dug", iso3, str(year))
        dug_l1_path = _clip_to_aoi(
            dug_l1_full, aoi, os.path.join(dug_clipped_dir, os.path.basename(l1_url)), overwrite
        )

        pop_path = download_worldpop_population(
            aoi, date, folder=folder, overwrite=overwrite, resolution=resolution, dataset="pop"
        )
        out_path = os.path.join(folder, f"{iso3.lower()}_urban_population_{year}_{resolution}.tif")
        return _derive_urban_population(pop_path, dug_l1_path, out_path, overwrite)

    raise AssertionError(f"unreachable: feature={feature!r}")


__all__ = [
    "GLOBAL_SCHEMA_FEATURES",
    "get_country_region",
    "download_worldpop_population",
    "download_worldpop_layer",
]
