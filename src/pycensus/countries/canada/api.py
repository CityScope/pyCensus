"""StatCan Full Table Download client shared by Canada census sources.

Technical aspects:
    Statistics Canada's Web Data Service (WDS) is a per-vector/coordinate
    query API; for a bulk load matching the ITER/csv-bulk-file pattern
    already used by :mod:`pycensus.mexico.api`, the simpler and equally
    keyless route is the Full Table Download:

        https://www150.statcan.gc.ca/n1/en/tbl/csv/{PID}-eng.zip

    (verified real 2026-08-20 -- ``PID`` ``98100002`` is StatCan's 2021
    Census "Population and dwelling counts: Canada, provinces and
    territories, census divisions and census subdivisions" table. The
    downloaded zip contains ``98100002.csv`` (806,597 bytes, real data)
    and ``98100002_MetaData.csv`` -- confirmed by actually unzipping and
    reading both files, not just checking the HTTP status. Canada's
    national total row (``GEO == "Canada"``) reads ``36,991,981``, which
    matches Canada's own published 2021 Census national population
    figure exactly. Ontario's row reads ``14,223,942`` (matches its
    published figure), and the City of Toronto row reads ``2,794,356``
    (matches its known ~2.79M 2021 population).

    The CSV has a flat ``REF_DATE, GEO, DGUID, Coordinate, <value column>,
    Symbols, ...`` layout (one value/Symbols column pair per requested
    variable) rather than the transposed layout StatCan uses for some
    other cube families -- confirmed directly from the real downloaded
    file, not assumed from the User Guide.

    Every row's ``DGUID`` (Statistics Canada's globally unique geographic
    identifier) encodes both the geography *type* and its native StatCan
    id in one string:
        - Canada:                ``2021A000011124``
        - Province/territory:    ``2021A0002`` + 2-digit ``PRUID``
        - Census division:       ``2021A0003`` + 4-digit CD code
        - Census subdivision:    ``2021A0005`` + 7-digit ``CSDUID``
    (verified by grepping the real downloaded CSV for known real
    provinces/CSDs, e.g. Ontario -> ``2021A000235``, Toronto ->
    ``2021A00053520005`` -- the ``3520005`` matches Toronto's real
    ``CSDUID`` in the boundary shapefile, see
    :mod:`pycensus.canada.geography`). :func:`fetch_province_totals` and
    :func:`fetch_municipality_totals` use this to select the right rows.

Source:
    https://www150.statcan.gc.ca/n1/en/tbl/csv/98100002-eng.zip
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from . import constants

_PROVINCE_DGUID_RE = re.compile(r"^2021A0002(\d{2})$")
_CSD_DGUID_RE = re.compile(r"^2021A0005(\d{7})$")
# Dissemination area DGUID prefix, from PID 98-10-0015 (companion cube to
# 98100002, one level finer -- verified live 2026-08-20 against the real
# downloaded 98100015.csv: DA rows have 17-char DGUIDs of the form
# "2021S0512" + 8-digit DAUID, matching the boundary shapefile's DAUID
# column exactly).
_DA_DGUID_RE = re.compile(r"^2021S0512(\d{8})$")

# 2021 Geographic Attribute File (GAF) raw column names actually present in
# the downloaded 2021_92-151_X.csv header -- verified live 2026-08-22
# (see constants.GEOGRAPHIC_ATTRIBUTE_FILE_URL docstring). The GAF's own
# real column names are used directly as this source's schema "codes"
# (see statcan/schema.json's "dissemination-block"-only codes entries),
# rather than reusing the Full Table Download's "Population and dwelling
# counts (...): ..." labels, which the GAF does not have.
_GAF_PRUID_COL = "PRUID_PRIDU"
_GAF_DBUID_COL = "DBUID_IDIDU"
_GAF_USECOLS = [
    _GAF_PRUID_COL,
    _GAF_DBUID_COL,
    "DBPOP2021_IDPOP2021",
    "DBTDWELL2021_IDTLOG2021",
    "DBURDWELL2021_IDRHLOG2021",
    "DBAREA2021_IDSUP2021",
]


def _raw_dir(data_dir: Optional[str] = None) -> Path:
    base = Path(data_dir) if data_dir else Path(constants.DEFAULT_DATA_DIR)
    raw_dir = base / "raw" / "full_table"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


def download_full_table_csv(pid: str, data_dir: Optional[str] = None) -> Path:
    """Download (once, cached on disk) and extract StatCan's Full Table Download CSV for one PID.

    Args:
        pid: StatCan Product ID, e.g. ``"98100002"`` (no dashes).
        data_dir: Base directory for the raw file cache. Defaults to
            :data:`pycensus.canada.constants.DEFAULT_DATA_DIR`.

    Returns:
        Path to the extracted ``{pid}.csv`` file.

    Raises:
        requests.HTTPError: If the download fails.
        FileNotFoundError: If the zip doesn't contain the expected CSV.
    """
    raw_dir = _raw_dir(data_dir)
    csv_path = raw_dir / f"{pid}.csv"
    if csv_path.exists() and csv_path.stat().st_size > 0:
        return csv_path

    url = constants.FULL_TABLE_URL_TEMPLATE.format(pid=pid)
    zip_path = raw_dir / f"{pid}.zip"

    response = requests.get(url, stream=True, timeout=180)
    response.raise_for_status()
    with open(zip_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=1 << 16):
            if chunk:
                f.write(chunk)

    with zipfile.ZipFile(zip_path) as zf:
        candidates = [n for n in zf.namelist() if n == f"{pid}.csv"]
        if not candidates:
            raise FileNotFoundError(
                f"No '{pid}.csv' found inside {zip_path} -- StatCan may have changed the "
                f"Full Table Download zip layout"
            )
        with zf.open(candidates[0]) as src, open(csv_path, "wb") as dst:
            dst.write(src.read())

    zip_path.unlink(missing_ok=True)
    return csv_path


def download_geographic_attribute_file(data_dir: Optional[str] = None) -> Path:
    """Download (once, cached on disk) and extract the 2021 Geographic Attribute File.

    Unlike :func:`download_full_table_csv`, this hits a direct, fixed URL
    (:data:`pycensus.canada.constants.GEOGRAPHIC_ATTRIBUTE_FILE_URL`) --
    verified live 2026-08-22 to work with a plain GET, no form/session
    dance required despite the file only being discoverable through
    StatCan's interstitial "Continue" form in a browser.

    Returns:
        Path to the extracted ``2021_92-151_X.csv`` file (~298MB,
        latin-1 encoded).

    Raises:
        requests.HTTPError: If the download fails.
        FileNotFoundError: If the zip doesn't contain the expected CSV.
    """
    raw_dir = _raw_dir(data_dir)
    csv_name = constants.GEOGRAPHIC_ATTRIBUTE_FILE_CSV_NAME
    csv_path = raw_dir / csv_name
    if csv_path.exists() and csv_path.stat().st_size > 0:
        return csv_path

    zip_path = raw_dir / "2021_92-151_X.zip"
    response = requests.get(constants.GEOGRAPHIC_ATTRIBUTE_FILE_URL, stream=True, timeout=600)
    response.raise_for_status()
    with open(zip_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=1 << 20):
            if chunk:
                f.write(chunk)

    with zipfile.ZipFile(zip_path) as zf:
        candidates = [n for n in zf.namelist() if n == csv_name]
        if not candidates:
            raise FileNotFoundError(
                f"No '{csv_name}' found inside {zip_path} -- StatCan may have changed the "
                f"Geographic Attribute File zip layout"
            )
        with zf.open(candidates[0]) as src, open(csv_path, "wb") as dst:
            dst.write(src.read())

    zip_path.unlink(missing_ok=True)
    return csv_path


def _read_geographic_attribute_file(data_dir: Optional[str] = None) -> pd.DataFrame:
    csv_path = download_geographic_attribute_file(data_dir)
    # Real file is latin-1 encoded (verified live 2026-08-22: French
    # accented characters in e.g. province/CD names fail plain utf-8
    # decoding), and only the columns this source actually uses are read
    # to keep memory reasonable on this ~300MB, ~500k-row national file.
    return pd.read_csv(csv_path, usecols=_GAF_USECOLS, dtype={_GAF_PRUID_COL: str, _GAF_DBUID_COL: str}, encoding="latin-1")


def _read_census_profile(data_dir: Optional[str] = None) -> pd.DataFrame:
    csv_path = download_full_table_csv(constants.CENSUS_PROFILE_PID, data_dir)
    return pd.read_csv(csv_path, dtype={"DGUID": str})


def _read_dissemination_area_table(data_dir: Optional[str] = None) -> pd.DataFrame:
    csv_path = download_full_table_csv(constants.DISSEMINATION_AREA_PID, data_dir)
    return pd.read_csv(csv_path, dtype={"DGUID": str})


def fetch_province_totals(province: str, data_dir: Optional[str] = None) -> pd.DataFrame:
    """Fetch the single province/territory-total row for one province from the Census Profile table.

    Returns:
        One-row DataFrame with a ``GEOID`` column (2-digit PRUID) plus
        every raw column from the downloaded CSV.
    """
    pruid = constants.province_code(province)
    df = _read_census_profile(data_dir)
    geoids = df["DGUID"].map(lambda d: (m.group(1) if (m := _PROVINCE_DGUID_RE.match(d)) else None))
    row = df[geoids == pruid].copy()
    row["GEOID"] = pruid
    return row.reset_index(drop=True)


def fetch_municipality_totals(province: str, data_dir: Optional[str] = None) -> pd.DataFrame:
    """Fetch every census-subdivision-total row for one province from the Census Profile table.

    Returns:
        DataFrame with a ``GEOID`` column (7-digit CSDUID, matching the
        boundary shapefile's ``CSDUID``) plus every raw column from the
        downloaded CSV.
    """
    pruid = constants.province_code(province)
    df = _read_census_profile(data_dir)
    csduids = df["DGUID"].map(lambda d: (m.group(1) if (m := _CSD_DGUID_RE.match(d)) else None))
    rows = df[csduids.notna() & csduids.str.startswith(pruid)].copy()
    rows["GEOID"] = csduids[csduids.notna() & csduids.str.startswith(pruid)]
    return rows.reset_index(drop=True)


def fetch_dissemination_area_totals(province: str, data_dir: Optional[str] = None) -> pd.DataFrame:
    """Fetch every dissemination-area-total row for one province from PID 98-10-0015.

    Returns:
        DataFrame with a ``GEOID`` column (8-digit DAUID, matching the
        boundary shapefile's ``DAUID``) plus every raw column from the
        downloaded CSV. A DA's DAUID starts with its 2-digit PRUID, same
        convention as the CSDUID/DAUID StatCan numbering scheme -- used
        here to filter to one province (no per-region query exists, same
        as :func:`fetch_municipality_totals`).
    """
    pruid = constants.province_code(province)
    df = _read_dissemination_area_table(data_dir)
    dauids = df["DGUID"].map(lambda d: (m.group(1) if (m := _DA_DGUID_RE.match(d)) else None))
    rows = df[dauids.notna() & dauids.str.startswith(pruid)].copy()
    rows["GEOID"] = dauids[dauids.notna() & dauids.str.startswith(pruid)]
    return rows.reset_index(drop=True)


def fetch_block_totals(province: str, data_dir: Optional[str] = None) -> pd.DataFrame:
    """Fetch every dissemination-block-total row for one province from the Geographic Attribute File.

    Returns:
        DataFrame with a ``GEOID`` column (11-char DBUID, matching the
        boundary shapefile's ``DBUID``) plus the GAF's real
        ``DBPOP2021_IDPOP2021``/``DBTDWELL2021_IDTLOG2021``/
        ``DBURDWELL2021_IDRHLOG2021``/``DBAREA2021_IDSUP2021`` columns. A
        DBUID's first 2 characters are its PRUID (same convention as
        CSDUID/DAUID) -- used here to filter to one province, same as
        :func:`fetch_dissemination_area_totals`.
    """
    pruid = constants.province_code(province)
    df = _read_geographic_attribute_file(data_dir)
    rows = df[df[_GAF_PRUID_COL] == pruid].copy()
    rows["GEOID"] = rows[_GAF_DBUID_COL]
    return rows.reset_index(drop=True)


# English region-name suffix StatCan uses in the real
# "98-401-X2021006_English_CSV_data_<region>.csv" member name inside each
# per-province Census Profile zip -- only Ontario has actually been
# downloaded/verified (see constants.CENSUS_PROFILE_GEONO_BY_PROVINCE).
_CENSUS_PROFILE_REGION_NAME = {"35": "Ontario"}

# Real StatCan symbols observed in the downloaded 98-401-X2021006 CSV
# (see its own "Symbol" legend in 98-401-X2021006_English_meta.txt):
# ".." not available, "..." not applicable, "x" suppressed for
# confidentiality, "F" too unreliable to publish, "r"/"rE" revised
# (possibly with "use with caution"). None of these are numbers --
# pd.to_numeric(..., errors="coerce") already turns every one of them (and
# a blank cell) into NaN, which is what "missing" must mean here: never
# coerced to 0.


def _census_profile_zip_path(province: str, data_dir: Optional[str] = None) -> Path:
    """Path to (downloading if necessary) the real per-province Census Profile 2021 zip.

    Source product: catalogue 98-401-X2021006 ("Census Profile, 2021 --
    Canada, Provinces, Territories, Census Divisions, Census Subdivisions
    and Dissemination Areas"), downloaded via the real per-region
    GetFile.cfm link on
    https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/details/download-telecharger.cfm?Lang=E
    -- verified live 2026-08-23 for GEONO=006_Ontario (757,020,277 bytes,
    Content-Disposition: attachment;filename=98-401-X2021006_Ontario_eng_CSV.zip).

    Raises:
        NotImplementedError: For any province other than Ontario -- no
            other province's file has been downloaded/verified yet, even
            though StatCan publishes the same product for all of them at
            the same URL pattern (see
            :data:`pycensus.countries.canada.constants.CENSUS_PROFILE_GEONO_BY_PROVINCE`).
    """
    pruid = constants.province_code(province)
    geono = constants.CENSUS_PROFILE_GEONO_BY_PROVINCE.get(pruid)
    region_name = _CENSUS_PROFILE_REGION_NAME.get(pruid)
    if geono is None or region_name is None:
        raise NotImplementedError(
            f"StatCan Census Profile (98-401-X2021006) household size / income / education / "
            f"tenure / commute-mode data is only downloaded and verified for Ontario (PRUID 35) "
            f"in this codebase so far -- province '{province}' (PRUID {pruid}) is not implemented. "
            f"StatCan does publish the same real product for every province/territory at "
            f"{constants.CENSUS_PROFILE_URL_TEMPLATE.format(geono='006_<Region>')}; adding it here "
            f"just needs the real region-name suffix added to _CENSUS_PROFILE_REGION_NAME and "
            f"CENSUS_PROFILE_GEONO_BY_PROVINCE, then live-verified the same way Ontario was."
        )

    base = Path(data_dir) if data_dir else Path(constants.DEFAULT_DATA_DIR)
    raw_dir = base / "raw" / "census_profile"
    raw_dir.mkdir(parents=True, exist_ok=True)
    zip_path = raw_dir / f"98-401-X2021006_{region_name}_eng_CSV.zip"
    if zip_path.exists() and zip_path.stat().st_size > 0:
        return zip_path

    # This is a large (~757MB), static, expensive-to-fetch reference
    # dataset shared by every city in the same province -- callers outside
    # pyCensus (e.g. CS_transitLOS's `_join_census`) always pass their own
    # per-city `cache_dir`, which differs from `constants.DEFAULT_DATA_DIR`
    # (pyCensus's own persistent data directory, where this file was
    # originally downloaded and live-verified). Without this fallback,
    # every city re-attempts a fresh 757MB download on every run instead
    # of reusing the one real copy already on disk -- and a transient
    # download failure (e.g. StatCan's GetFile.cfm briefly returning 404,
    # observed live 2026-08-23) then silently degrades every DA-level
    # field (education/income/commute/foreign-born) to real NaN instead of
    # reusing data that's already there.
    if data_dir is not None:
        # `constants.DEFAULT_DATA_DIR` ("data/canada") is a CWD-relative
        # path -- resolving it directly here would only find the real
        # cached copy when the process happens to be running from inside
        # the pyCensus repo root, which isn't true for CS_transitLOS's
        # pipeline (it runs from its own directory). Resolve relative to
        # this file's real on-disk location instead (same pattern as
        # `pycensus.api_keys._KEYS_FILE`), so this fallback works
        # regardless of the caller's working directory.
        pycensus_root = Path(__file__).resolve().parents[4]
        default_zip_path = pycensus_root / constants.DEFAULT_DATA_DIR / "raw" / "census_profile" / zip_path.name
        if default_zip_path.exists() and default_zip_path.stat().st_size > 0:
            return default_zip_path

    url = constants.CENSUS_PROFILE_URL_TEMPLATE.format(geono=geono)
    response = requests.get(url, stream=True, timeout=600)
    response.raise_for_status()
    tmp_path = zip_path.with_suffix(".zip.tmp")
    with open(tmp_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=1 << 20):
            if chunk:
                f.write(chunk)
    tmp_path.rename(zip_path)
    return zip_path


def fetch_census_profile_da_totals(
    province: str,
    characteristic_names: "list[str]",
    data_dir: Optional[str] = None,
) -> pd.DataFrame:
    """Fetch dissemination-area-level rows for a set of real characteristics from 98-401-X2021006.

    Unlike :func:`fetch_dissemination_area_totals` (PID 98-10-0015, a flat
    wide table), this product is long/tall: one row per
    (geography, CHARACTERISTIC_ID) pair, ~2,631 characteristics per
    geography, ~8.8GB uncompressed for Ontario alone. This streams the CSV
    directly out of the still-zipped download (never extracts the full
    file to disk) in chunks via ``pandas.read_csv(..., chunksize=...)``,
    filtering to ``GEO_LEVEL == "Dissemination area"`` and
    ``CHARACTERISTIC_NAME.str.strip()`` in ``characteristic_names`` *before*
    accumulating anything -- this keeps peak memory bounded to roughly
    (target characteristics) x (Ontario's ~20,000 real DAs) rows, not the
    full ~50M-row file.

    Args:
        province: Province name/abbreviation/PRUID. Only Ontario (PRUID
            35) is implemented -- see :func:`_census_profile_zip_path`.
        characteristic_names: Real, verified ``CHARACTERISTIC_NAME`` text
            (already stripped of the source's hierarchical leading
            whitespace) to pivot into columns, e.g. ``"Average household
            size"`` or ``"Median total income of household in 2020 ($)"``.
        data_dir: Base directory for the raw zip cache.

    Returns:
        Wide DataFrame with a ``GEOID`` column (8-digit DAUID -- the raw
        ``ALT_GEO_CODE`` for "Dissemination area" rows in this product,
        verified live 2026-08-23 to already be the plain DAUID with no
        DGUID-prefix decoding needed, e.g. ALT_GEO_CODE "35204609" for the
        real downtown-Toronto DA) plus one column per matched
        characteristic name, values coerced numeric with StatCan's real
        non-numeric symbols (``..``, ``...``, ``x``, ``F``, ``r``, ``rE``)
        becoming ``NaN`` -- never a fabricated 0.
    """
    zip_path = _census_profile_zip_path(province, data_dir)
    pruid = constants.province_code(province)
    region_name = _CENSUS_PROFILE_REGION_NAME[pruid]
    member = constants.CENSUS_PROFILE_CSV_NAME_TEMPLATE.format(region=region_name)
    target = {name.strip() for name in characteristic_names}

    matched_chunks = []
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(member) as raw:
            text_stream = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
            reader = pd.read_csv(
                text_stream,
                usecols=["ALT_GEO_CODE", "GEO_LEVEL", "CHARACTERISTIC_NAME", "C1_COUNT_TOTAL"],
                dtype={"ALT_GEO_CODE": str},
                chunksize=500_000,
            )
            for chunk in reader:
                names_stripped = chunk["CHARACTERISTIC_NAME"].str.strip()
                mask = (chunk["GEO_LEVEL"] == "Dissemination area") & names_stripped.isin(target)
                if mask.any():
                    sub = chunk.loc[mask, ["ALT_GEO_CODE", "C1_COUNT_TOTAL"]].copy()
                    sub["CHARACTERISTIC_NAME"] = names_stripped[mask]
                    matched_chunks.append(sub)

    if not matched_chunks:
        # Real per-DA rows use GEO_LEVEL == "Dissemination area" for every
        # one of Ontario's ~20,000 real DAs -- if literally *nothing*
        # matched, every requested name failed to match, which is far
        # more likely a caller typo/encoding mismatch (curly vs straight
        # apostrophe, a stray trailing space, wrong dollar-sign escaping)
        # than "none of these characteristics exist anywhere in Ontario".
        # Silently returning an empty/GEOID-only frame here is exactly
        # the failure mode that lets a bad characteristic name degrade
        # every DA's value to a fabricated-looking, unflagged NaN/0
        # downstream with nothing in any log to say why -- raise instead.
        raise ValueError(
            f"None of the requested StatCan CHARACTERISTIC_NAME values {sorted(target)} "
            f"matched any 'Dissemination area' row in {member} -- check for a typo, stray "
            f"whitespace, or curly-vs-straight-apostrophe/dollar-sign mismatch against the "
            f"real CHARACTERISTIC_NAME text (see statcan_schema.json's 'codes')."
        )

    long_df = pd.concat(matched_chunks, ignore_index=True)
    # Real StatCan symbols (".."/"..."/"x"/"F"/"r"/"rE"/blank) become NaN
    # here, never a fabricated 0 -- see the module-level symbol note above.
    long_df["C1_COUNT_TOTAL"] = pd.to_numeric(long_df["C1_COUNT_TOTAL"], errors="coerce")
    wide = long_df.pivot_table(
        index="ALT_GEO_CODE", columns="CHARACTERISTIC_NAME", values="C1_COUNT_TOTAL", aggfunc="first"
    )
    wide = wide.reset_index().rename(columns={"ALT_GEO_CODE": "GEOID"})

    # Same silent-degradation risk as the "nothing matched at all" case
    # above, but per-characteristic: if one specific requested name never
    # appeared in any of the ~20,000 real DA rows (while others did), that
    # single column would otherwise just be absent from `wide` --
    # `_fetch_missing` in statcan/loader.py treats an absent column as
    # "not in this source", silently filling it with NaN for every real
    # DA in the province, with nothing to distinguish that from a
    # genuinely-published-blank StatCan field. Surface it loudly instead.
    missing_names = target - set(wide.columns)
    if missing_names:
        raise ValueError(
            f"Requested StatCan CHARACTERISTIC_NAME value(s) {sorted(missing_names)} matched "
            f"zero 'Dissemination area' rows in {member} (other requested names did match) -- "
            f"check for a typo, stray whitespace, or curly-vs-straight-apostrophe/dollar-sign "
            f"mismatch against the real CHARACTERISTIC_NAME text (see statcan_schema.json's "
            f"'codes'); silently returning fewer columns than requested would degrade this "
            f"characteristic to an unflagged all-NaN column for every real DA in the province."
        )

    return wide


_WORKPLACE_JOBS_COLUMN = "StatCan 98-10-0459 jobs by workplace CSD (usual place of work)"


@lru_cache(maxsize=1)
def _workplace_jobs_member_id_to_csduid() -> "dict[str, str]":
    """Load the bundled, static Place-of-work-memberId -> CSDUID lookup.

    Built once (2026-08-23) from a live call to StatCan's WDS
    ``getCubeMetadata`` for PID 98-10-0459 -- see
    :data:`pycensus.countries.canada.constants.WORKPLACE_JOBS_PID`'s
    docstring for how the "Place of work" dimension's member ids were
    confirmed to share the same id space/ordering as "Place of
    residence" (which does carry a real ``classificationCode`` ==
    CSDUID). Bundled as a package resource rather than fetched live so
    this source stays keyless/Full-Table-Download-only like the rest of
    this module.
    """
    path = Path(__file__).parent / "statcan" / constants.WORKPLACE_JOBS_MEMBER_ID_TO_CSDUID_FILE
    with open(path) as f:
        return json.load(f)


def fetch_workplace_jobs_totals(data_dir: Optional[str] = None) -> pd.DataFrame:
    """Fetch every census-subdivision total for real workplace-located jobs, from PID 98-10-0459.

    Unlike :func:`fetch_municipality_totals` (residence-based Census
    Profile data), this counts jobs by WHERE THE JOB IS, not where the
    worker lives -- Canada's real analog to the USA's LODES WAC (see
    :data:`pycensus.countries.canada.constants.WORKPLACE_JOBS_PID`'s
    docstring for the live verification: real 2.2GB download, Toronto
    CSDUID 3520005 = 753,185, cross-checked against the cube's own
    national total). This streams the Full Table CSV in chunks (it is
    national, ~80M rows, one row per residence-CSD x workplace-CSD x
    gender combination) rather than loading it whole, summing the
    "Total - Gender" flow value grouped by the workplace CSD parsed out
    of each row's ``Coordinate`` column.

    Args:
        data_dir: Base directory for the raw file cache.

    Returns:
        DataFrame with a ``GEOID`` column (7-digit CSDUID) and one column
        (:data:`_WORKPLACE_JOBS_COLUMN`) of real, workplace-geocoded job
        counts -- an UNDER-count of true total jobs, since it excludes
        workers who worked from home or had no fixed workplace address
        (a large share in the pandemic-affected 2021 Census); never
        fabricated up to a "true" total.
    """
    csv_path = download_full_table_csv(constants.WORKPLACE_JOBS_PID, data_dir)
    member_to_csduid = _workplace_jobs_member_id_to_csduid()

    sums: "dict[str, float]" = {}
    reader = pd.read_csv(
        csv_path,
        usecols=["Coordinate", "Gender (3):Total - Gender[1]"],
        dtype={"Coordinate": str},
        chunksize=2_000_000,
    )
    for chunk in reader:
        work_ids = chunk["Coordinate"].str.split(".").str[1]
        values = pd.to_numeric(chunk["Gender (3):Total - Gender[1]"], errors="coerce")
        grouped = values.groupby(work_ids).sum(min_count=1)
        for work_id, total in grouped.items():
            if work_id is None or (isinstance(work_id, float) and pd.isna(work_id)) or pd.isna(total):
                continue
            csduid = member_to_csduid.get(work_id)
            if csduid is None:
                continue
            sums[csduid] = sums.get(csduid, 0.0) + float(total)

    return pd.DataFrame({"GEOID": list(sums.keys()), _WORKPLACE_JOBS_COLUMN: list(sums.values())})


__all__ = [
    "download_full_table_csv",
    "download_geographic_attribute_file",
    "fetch_province_totals",
    "fetch_municipality_totals",
    "fetch_dissemination_area_totals",
    "fetch_block_totals",
    "fetch_census_profile_da_totals",
    "fetch_workplace_jobs_totals",
]
