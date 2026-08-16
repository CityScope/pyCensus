"""Loader for WorldPop gridded population/age-structure rasters.

Downloads WorldPop population and age-structure GeoTIFFs
(https://www.worldpop.org/, REST API: https://www.worldpop.org/sdi/introapi)
for a given area of interest and year. Unlike pyCensus' vector/tabular
sources (e.g. :mod:`pycensus.USA.acs`), WorldPop ships gridded raster data,
so :func:`download_worldpop_population` returns a filesystem path to the
downloaded GeoTIFF rather than a GeoDataFrame -- callers that need a
:class:`geopandas.GeoDataFrame` (e.g. for
:meth:`geohierarchy.GeoHierarchy.add_level`) are expected to vectorize/sample
the raster themselves and expose the result through the ``worldpop``
accessor registered in :mod:`pycensus.worldwide.worldpop.schema`.
"""

from __future__ import annotations

import os
import tempfile
import warnings
from datetime import date, datetime
from difflib import get_close_matches
from typing import Optional, Tuple, Union

import geopandas as gpd
import pycountry
import requests
from tqdm import tqdm


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
    dataset/subset/year, and streams the resulting GeoTIFF to disk.

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
            ``"under_18"``/``"U18"`` to select the under-18 subset.
        chunk_size: Chunk size in bytes used when streaming the download.

    Returns:
        Path to the downloaded GeoTIFF file.

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

    # Ensure CRS is WGS84
    if aoi.crs is None:
        raise ValueError("AOI GeoDataFrame must have a CRS defined (e.g., EPSG:4326).")

    aoi = aoi.to_crs(epsg=4326)

    # Use centroid to get country ISO3
    centroid = aoi.union_all().centroid
    lon, lat = centroid.x, centroid.y

    country_code = get_country_region(lat, lon, code_format="alpha_3", get_region=False)
    if not country_code:
        raise ValueError("Could not resolve country ISO3 code from AOI centroid.")

    iso3 = country_code.upper()
    if date is datetime:
        date = date.date

    year = date.year

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
            subset = f"G2_CN_Age_2024_{resolution}"

        if (subset == "under_18") or (subset == "U18"):
            subset = f"G2_Age_U18_R25A_{resolution}"

        url = f"https://hub.worldpop.org/rest/data/{dataset}/{subset}?iso3={iso3}"

    r = requests.get(url)
    r.raise_for_status()
    data = r.json()["data"]

    # Find dataset for the requested year
    dataset = next((d for d in data if str(d.get("popyear")) == str(year)), None)
    if dataset is None:
        raise ValueError(f"No WorldPop population dataset available for {iso3} in {year}.")

    # Get download link (first file URL)
    file_url = dataset["files"][0]

    if folder is None:
        # Prepare output path
        out_dir = tempfile.gettempdir()
        raster_path = os.path.join(out_dir, os.path.basename(file_url))
        base_path, fname = os.path.split(raster_path)
        name, _ = os.path.splitext(fname)
        raster_path = os.path.join(base_path, name) + ".tif"
    else:
        os.makedirs(folder, exist_ok=True)
        raster_path = os.path.join(folder, os.path.basename(file_url))

    if os.path.isfile(raster_path) and (not overwrite):
        print(f"Raster population path {raster_path} exists. Skipping download...")

    else:
        # Download file
        with requests.get(file_url, stream=True) as rfile:
            rfile.raise_for_status()
            total_size = int(rfile.headers.get("content-length", 0))

            with open(raster_path, "wb") as f, tqdm(
                total=total_size,
                unit="B",
                unit_scale=True,
                desc="Downloading",
                ncols=100,
            ) as pbar:
                for chunk in rfile.iter_content(chunk_size=chunk_size):
                    if chunk:  # skip keep-alive chunks
                        f.write(chunk)
                        pbar.update(len(chunk))

    return raster_path
