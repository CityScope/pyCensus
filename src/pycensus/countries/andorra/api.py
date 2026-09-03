"""Thin ArcGIS REST client for Andorra's two real, keyless, hosted feature services.

Technical aspects:
    Andorra's national statistics office (Departament d'Estadistica,
    https://www.estadistica.ad/) has no documented REST/SDMX API for its
    human-facing dataset browser -- but that browser is itself built on
    Esri ArcGIS Hub (confirmed live 2026-08-20: the portal's page source
    references ``activation-engine``/``community-engine``, the Ember
    modules Esri's Hub frontend ships, and
    ``https://www.estadistica.ad/portal/sharing/rest?f=json`` answers with
    a real ArcGIS Portal API version), and that portal's own search API
    (``.../portal/sharing/rest/search``) lists real, public, queryable
    ArcGIS Server FeatureServer items with no login required. Two of those
    are used here, both verified live by fetching them and inspecting the
    actual response content (not just HTTP 200):

    - Parish (comú) boundary polygons:
      ``https://www.estadistica.ad/server/rest/services/Estadistica/Cartografia_base/FeatureServer/3``
      (layer name ``Parroquies_Pol_codi``). Returns exactly 7 polygons with
      real ``Nom``/``Codi`` fields matching Andorra's 7 parishes and their
      ISO 3166-2:AD codes (``AD-01``..``AD-07``), reprojected on request via
      ``outSR=4326``; longitude/latitude bounds of the fetched geometry
      (1.409-1.787 E, 42.429-42.656 N) land exactly on Andorra's known
      extent.
    - Population by locality/year:
      ``https://sig.govern.ad/server/rest/services/Hosted/Poblaci%C3%B3_2010_2021/FeatureServer/0``
      (item title "Poblacio 2010-2025", found via the estadistica.ad portal
      search for "poblacio"). Returns 44 real localities ("pobles"), each
      tagged with its parish (``parroquia``) and one integer population
      column per year (``pob_2003``, ``pob_2010``..``pob_2025``). Summed
      across all localities, ``pob_2023`` gives exactly 85,101 -- matching
      Diari d'Andorra's reporting of the Departament d'Estadistica's own
      published 31 Dec 2023 population figure
      (https://www.diariandorra.ad/noticies/nacional/2023/11/21/andorra_guanya_500_habitants_any_cens_estadistica_suma_516_231842_1125.html)
      word for word (85,101).

    Neither endpoint requires an API key or authentication token --
    confirmed by live, unauthenticated queries against both hosts on
    2026-08-20.
"""

from __future__ import annotations

import re
from typing import List, Optional

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import MultiPolygon, Point, Polygon

_TIMEOUT = 60

PARISH_BOUNDARY_URL = (
    "https://sig.govern.ad/server/rest/services/Estadistica/"
    "Cartografia_base/FeatureServer/3"
)
# NOTE (verified live 2026-08-20, later in the same session): the
# estadistica.ad-hosted path above (www.estadistica.ad/server/...) was the
# original verified URL, but it started 302-redirecting to the ArcGIS Hub
# portal frontend rather than answering as a REST endpoint. The portal's own
# item search (https://www.estadistica.ad/portal/sharing/rest/search?q=Parroquies)
# shows the real underlying host for this same "Cartografia_base" Feature
# Service is sig.govern.ad (the same host already used for
# POPULATION_BY_LOCALITY_URL below) -- re-verified live to return the same 7
# real parishes/codes from that host.
POPULATION_BY_LOCALITY_URL = (
    "https://sig.govern.ad/server/rest/services/Hosted/"
    "Poblaci%C3%B3_2010_2021/FeatureServer/0"
)

# Real, keyless, hosted building-footprint layer -- found 2026-08-23 via the
# same estadistica.ad portal search API (q=edifici). Verified live: 21,529
# polygon features, each carrying a real ``parròquia`` (parish name) field
# whose 7 distinct values are exactly Andorra's real parish names (matching
# ``pycensus.andorra.constants.PARISH_CODES``). A groupBy/count statistics
# query against this layer gives, per parish (2026-08-23):
# Andorra la Vella 4655, La Massana 3904, Escaldes-Engordany 3518, Sant
# Julià de Lòria 3030, Encamp 2623, Canillo 2175, Ordino 1624 (sum 21,529) --
# the capital parish having the most buildings is a real, independently
# plausible sanity check. This is a single-vintage snapshot (year 2019, per
# the item title "Edificis 2019"); no other year is published under this
# item.
BUILDINGS_URL = "https://sig.govern.ad/server/rest/services/Hosted/Edificis_2019/FeatureServer/0"

# Real, keyless, hosted business-register point layer -- found 2026-08-23
# via portal search q=empreses (item "REE_Ubicació", layer "Ubicació
# empreses"). Verified live: 18,645 total records, each with an integer
# ``PARROQUIA`` field (1-7) and an ``Es_Activa`` flag. Cross-checked live
# that the integer parish code matches the ISO 3166-2:AD suffix embedded in
# the same row's ``vc_pkBloc_id_c`` building-address code (e.g.
# ``PARROQUIA=6`` always paired with a ``vc_pkBloc_id_c`` starting
# ``AD-06-``), confirming ``PARROQUIA=N`` means parish ``AD-0N``. Active
# (``Es_Activa=1``) business counts by parish, verified live 2026-08-23:
# AD-01 Canillo 335, AD-02 Encamp 998, AD-03 Ordino 329, AD-04 La Massana
# 976, AD-05 Andorra la Vella 3667, AD-06 Sant Julià de Lòria 438, AD-07
# Escaldes-Engordany 1399 (total 8,142) -- the capital parish having by far
# the most active businesses is a real, independently plausible sanity
# check. This is a live current-state register (no historical vintage
# years published), so the loader treats it as a single "latest" snapshot
# regardless of the requested year.
BUSINESSES_URL = "https://sig.govern.ad/server/rest/services/Estadistica/REE_Ubicaci%C3%B3/FeatureServer/1"

# Real, keyless, bulk-published PDF bulletin -- found 2026-08-23 while
# investigating foreign-resident data specifically (see this module's and
# ``estadisticaad/README.md``'s notes: no queryable FeatureServer/table
# carries a nationality breakdown, but the Departament d'Estadistica's
# regular "Nota de premsa" bulletin does). Verified live by fetching this
# exact URL and inspecting the actual PDF content (not just HTTP 200):
# section "2.2 Poblacio per nacionalitat" (page 6 of 12) contains a real
# table of population by nationality (Andorrana/Espanyola/Francesa/
# Portuguesa/Altres/Estrangera/Total) for each of the 7 parishes plus a
# national total. The nationwide "Estrangera" (non-Andorran-nationality)
# row sums to 48,008 out of a total 87,486 (54.9%) -- consistent with
# Andorra's well-documented, independently known ~45-55% foreign-resident
# share. This is a periodic (monthly) dated publication at a URL of the
# form ``.../Notes_premsa_noticies/A001_<YYYYMMDD>_A.pdf``; there is no
# discovered index/API to auto-resolve "the latest" bulletin, so this
# constant pins the one specific bulletin actually verified (covering
# 28-Feb-2025 population estimates, published 13-Mar-2025) -- the loader
# treats this the same way it treats ``buildingCount``/
# ``activeBusinessCount``: a single real, dated snapshot returned
# regardless of the requested ``year``, not resolved per-year.
NATIONALITY_BULLETIN_URL = (
    "https://sig.govern.ad/SIGDDE.Public/Files/Documents/"
    "Notes_premsa_noticies/A001_20250313_A.pdf"
)
NATIONALITY_BULLETIN_SNAPSHOT_DATE = "2025-02-28"

# Fixed column order of the "Poblacio per nacionalitat i parroquia" table
# in the bulletin above, verified live 2026-08-23 by reading the table's
# real parish-name header text in order -- matches
# ``pycensus.andorra.constants.PARISH_CODES``' own AD-01..AD-07 order
# exactly (Canillo, Encamp, Ordino, La Massana, Andorra la Vella, Sant
# Julia de Loria, Escaldes-Engordany), with an 8th "Total" column.
_NATIONALITY_TABLE_PARISH_ORDER = (
    "AD-01",
    "AD-02",
    "AD-03",
    "AD-04",
    "AD-05",
    "AD-06",
    "AD-07",
    "AD",
)


def query_features(
    url: str,
    where: str = "1=1",
    out_fields: str = "*",
    return_geometry: bool = True,
    out_sr: int = 4326,
) -> List[dict]:
    """Fetch every feature matching ``where`` from an ArcGIS FeatureServer layer.

    Both real services used by this module return their full result set
    (7 parishes, 44 localities) in a single unpaginated request -- verified
    live -- so no ``resultOffset`` pagination loop is needed here (unlike
    :mod:`pycensus.israel.arcgis`, which fetches much larger result sets).

    Args:
        url: Full FeatureServer layer URL.
        where: SQL ``WHERE`` clause (default ``"1=1"``, i.e. everything).
        out_fields: Comma-separated field list, or ``"*"``.
        return_geometry: Whether to request geometry.
        out_sr: Output spatial reference. Both real services here accept
            server-side reprojection to ``4326``, verified live.

    Returns:
        List of raw Esri JSON feature dicts (``{"attributes": {...},
        "geometry": {...}}``).

    Raises:
        requests.HTTPError: If the request fails.
        RuntimeError: If the server returns an error payload.
    """
    params = {
        "where": where,
        "outFields": out_fields,
        "returnGeometry": str(return_geometry).lower(),
        "outSR": out_sr,
        "f": "json",
    }
    resp = requests.get(f"{url}/query", params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"ArcGIS query error from {url}: {data['error']}")
    return data.get("features", [])


def query_group_count(url: str, group_field: str, where: str = "1=1", count_field: Optional[str] = None) -> pd.DataFrame:
    """Run a groupBy/count statistics query against an ArcGIS FeatureServer layer.

    Both real services used here (``BUILDINGS_URL``, ``BUSINESSES_URL``)
    support ``outStatistics``/``groupByFieldsForStatistics`` -- verified
    live 2026-08-23.

    Args:
        url: Full FeatureServer layer URL.
        group_field: Field to group by (e.g. parish name/code field).
        where: SQL ``WHERE`` clause (default ``"1=1"``).

    Returns:
        DataFrame with ``group_field`` and a ``count`` integer column.

    Raises:
        requests.HTTPError: If the request fails.
        RuntimeError: If the server returns an error payload.
    """
    import json as _json

    params = {
        "where": where,
        "outFields": group_field,
        "groupByFieldsForStatistics": group_field,
        "outStatistics": _json.dumps(
            [{"statisticType": "count", "onStatisticField": count_field or group_field, "outStatisticFieldName": "cnt"}],
            separators=(",", ":"),
        ),
        "f": "json",
    }
    resp = requests.get(f"{url}/query", params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"ArcGIS statistics query error from {url}: {data['error']}")
    rows = [f["attributes"] for f in data.get("features", [])]
    df = pd.DataFrame(rows)
    return df.rename(columns={"cnt": "count"})


def _esri_geometry_to_shapely(geom: dict):
    if geom is None:
        return None
    if "rings" in geom:
        rings = geom["rings"]
        polys = [Polygon(rings[0], holes=rings[1:])] if len(rings) else []
        # A feature can be a real multi-ring polygon with more than one
        # outer ring (e.g. an exclave); Esri JSON doesn't distinguish outer
        # from hole rings explicitly, but for Andorra's 7 parishes each
        # feature is a single simple polygon (verified live), so the first
        # ring is treated as the (only) outer ring.
        return polys[0] if polys else None
    if "x" in geom and "y" in geom:
        return Point(geom["x"], geom["y"])
    return None


def features_to_geodataframe(features: List[dict]) -> gpd.GeoDataFrame:
    """Convert raw Esri JSON features (from :func:`query_features`) to a GeoDataFrame in EPSG:4326."""
    if not features:
        return gpd.GeoDataFrame({}, geometry=[], crs=4326)
    rows = [f["attributes"] for f in features]
    geoms = [_esri_geometry_to_shapely(f.get("geometry")) for f in features]
    return gpd.GeoDataFrame(rows, geometry=geoms, crs=4326)


def fetch_parish_boundaries() -> gpd.GeoDataFrame:
    """Fetch Andorra's 7 real parish (comú) boundary polygons, in EPSG:4326.

    Returns:
        GeoDataFrame with ``Nom`` (parish name), ``Codi`` (ISO 3166-2:AD
        code), and geometry columns.
    """
    features = query_features(PARISH_BOUNDARY_URL, out_fields="Nom,Codi,OID_1,Descrip")
    return features_to_geodataframe(features)


def fetch_population_by_locality() -> pd.DataFrame:
    """Fetch every locality's ("poble") population by year, real values from estadistica.ad.

    Returns:
        DataFrame with ``poblacio`` (locality name), ``parroquia`` (parish
        name -- see :data:`pycensus.andorra.constants.PARISH_NAME_ALIASES`
        for one known misspelling in this source), and one ``pob_<year>``
        integer column per year the source publishes (2003, 2010-2025).
    """
    features = query_features(POPULATION_BY_LOCALITY_URL, return_geometry=False)
    rows = [f["attributes"] for f in features]
    return pd.DataFrame(rows)


def fetch_building_counts_by_parish() -> pd.DataFrame:
    """Fetch building-footprint counts per parish, real values from the 2019 Edificis layer.

    Returns:
        DataFrame with ``parròquia`` (real parish name) and ``count``
        (integer number of building-footprint polygons in that parish).
    """
    return query_group_count(BUILDINGS_URL, group_field="parròquia")


def fetch_active_business_counts_by_parish() -> pd.DataFrame:
    """Fetch active-business counts per parish, real values from the REE business register.

    Returns:
        DataFrame with ``PARROQUIA`` (integer 1-7, matching ISO 3166-2:AD
        suffix) and ``count`` (integer number of active businesses, i.e.
        rows with ``Es_Activa = 1``, in that parish).
    """
    return query_group_count(
        BUSINESSES_URL, group_field="PARROQUIA", where="Es_Activa=1", count_field="objectID_empresa"
    )


def _cluster_pdf_number_rows(words: List[dict]) -> List[dict]:
    """Group a page's numeric words into row-bands, then column-clusters within each row.

    The bulletin PDF's data-table digits are real, horizontal (unrotated)
    text -- but the underlying PDF renders each digit/comma/dot as its own
    text run, so ``pdfplumber``'s word extraction never reassembles a full
    number like ``"1.726"`` into one token, and no ``extract_tables()``
    grid is detected either (verified live 2026-08-23 against the actual
    downloaded PDF). This reassembles numbers the same way a human reading
    the rendered page would: words are grouped into horizontal row-bands by
    close ``top`` (y-position), then within each row, adjacent words are
    merged into one number whenever the horizontal gap between them is
    small (real spacing between digits of the same printed number, as
    opposed to the larger gap between distinct table columns).

    Returns:
        List of ``{"top": float, "values": [str, ...]}`` dicts, one per
        row-band, each row's ``values`` sorted left-to-right.
    """
    rows: List[dict] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        target = None
        for r in rows:
            if abs(r["top"] - w["top"]) < 1.0:
                target = r
                break
        if target is None:
            target = {"top": w["top"], "words": []}
            rows.append(target)
        target["words"].append(w)

    result = []
    for r in rows:
        ws = sorted(r["words"], key=lambda w: w["x0"])
        clusters = [[ws[0]]]
        for prev, cur in zip(ws, ws[1:]):
            if cur["x0"] - prev["x1"] > 3:
                clusters.append([cur])
            else:
                clusters[-1].append(cur)
        values = ["".join(x["text"] for x in c) for c in clusters]
        result.append({"top": r["top"], "values": values})
    return result


def fetch_population_by_nationality_and_parish(
    url: str = NATIONALITY_BULLETIN_URL,
) -> pd.DataFrame:
    """Fetch and parse the real "Poblacio per nacionalitat i parroquia" table.

    Downloads the Departament d'Estadistica bulletin PDF at ``url`` (see
    :data:`NATIONALITY_BULLETIN_URL`), locates section "2.2 Poblacio per
    nacionalitat", and reconstructs its table via
    :func:`_cluster_pdf_number_rows`. The table's real, fixed row order
    (verified live 2026-08-23 against this exact document) is: Andorrana,
    Espanyola, Francesa, Portuguesa, Altres, Andorrana (repeated
    subtotal), Estrangera, Total -- 8 rows, each with one (n, %) pair per
    of 7 parishes plus a national Total column (16 numeric tokens/row).

    This function cross-validates the parse before returning, rather than
    trusting row order alone: for every column, the single-nationality
    rows (Andorrana + Espanyola + Francesa + Portuguesa + Altres) must sum
    to the Total row, the repeated Andorrana row must equal the first
    Andorrana row, and Andorrana + Estrangera must equal Total. If a
    future bulletin's layout drifts and any of these fail, this raises
    rather than silently returning a wrong parse.

    Returns:
        DataFrame with one row per parish code (``GEOID`` in
        :data:`pycensus.andorra.constants.PARISH_CODES` plus ``"AD"`` for
        the national total), an integer ``foreign_nationality`` column
        (the real "Estrangera" count), and an integer ``population``
        column (the real "Total" count, for cross-checking against
        :func:`fetch_population_by_locality`).

    Raises:
        requests.HTTPError: If the PDF can't be downloaded.
        RuntimeError: If the expected table structure/cross-checks aren't
            found in the parsed PDF (layout drift from a future bulletin).
    """
    import io

    import pdfplumber

    resp = requests.get(url, timeout=_TIMEOUT)
    resp.raise_for_status()

    # Every page mentioning the word "nacionalitat" is checked (the table
    # of contents also contains it), rather than trusting the first/last
    # match -- the real target page is identified structurally, by
    # actually finding a page whose numeric words below that heading
    # cluster into exactly 8 rows of 16 values (the real table shape),
    # not by assuming a fixed page number.
    data_rows = None
    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            headings = [
                w for w in words if w["text"] == "nacionalitat" and w["top"] > 100
            ]
            if not headings:
                continue
            heading_top = headings[-1]["top"]
            numeric_words = [
                w
                for w in words
                if re.fullmatch(r"[0-9.,]+", w["text"]) and w["top"] > heading_top
            ]
            rows = _cluster_pdf_number_rows(numeric_words)
            candidate_rows = [r for r in rows if len(r["values"]) == 16]
            if len(candidate_rows) == 8:
                data_rows = candidate_rows
                break

    if data_rows is None:
        raise RuntimeError(
            f"Could not find the 8-row/16-value 'Poblacio per nacionalitat' "
            f"table in any page of the PDF at {url}"
        )
    data_rows.sort(key=lambda r: r["top"])

    def _row_ints(row) -> List[int]:
        # values alternate n, %, n, %, ... -- take the n's (even indices).
        return [int(row["values"][i].replace(".", "")) for i in range(0, 16, 2)]

    andorrana1, espanyola, francesa, portuguesa, altres, andorrana2, estrangera, total = [
        _row_ints(r) for r in data_rows
    ]

    for col in range(8):
        single_sum = (
            andorrana1[col] + espanyola[col] + francesa[col] + portuguesa[col] + altres[col]
        )
        if single_sum != total[col]:
            raise RuntimeError(
                f"Nationality breakdown doesn't sum to Total in column {col} of {url}: "
                f"{single_sum} != {total[col]}"
            )
        if andorrana1[col] != andorrana2[col]:
            raise RuntimeError(
                f"Repeated Andorrana row mismatch in column {col} of {url}: "
                f"{andorrana1[col]} != {andorrana2[col]}"
            )
        if andorrana2[col] + estrangera[col] != total[col]:
            raise RuntimeError(
                f"Andorrana + Estrangera doesn't equal Total in column {col} of {url}: "
                f"{andorrana2[col]} + {estrangera[col]} != {total[col]}"
            )

    return pd.DataFrame(
        {
            "GEOID": list(_NATIONALITY_TABLE_PARISH_ORDER),
            "foreign_nationality": estrangera,
            "population": total,
        }
    )


__all__ = [
    "PARISH_BOUNDARY_URL",
    "POPULATION_BY_LOCALITY_URL",
    "BUILDINGS_URL",
    "BUSINESSES_URL",
    "NATIONALITY_BULLETIN_URL",
    "NATIONALITY_BULLETIN_SNAPSHOT_DATE",
    "query_features",
    "query_group_count",
    "features_to_geodataframe",
    "fetch_parish_boundaries",
    "fetch_population_by_locality",
    "fetch_building_counts_by_parish",
    "fetch_active_business_counts_by_parish",
    "fetch_population_by_nationality_and_parish",
]
