# -*- coding: utf-8 -*-
"""Shared machinery for the per-country election loaders.

Pipeline (identical for every country):

1. The country loader downloads the *finest published* result unit
   (precinct / polling station / casilla / mesa / poll) plus its polygons and
   turns it into a ``counts`` frame indexed by unit id (see :func:`build_counts`).
2. :func:`units_to_h3` moves the counts to H3 res 8 **dasymetrically**: every
   unit's counts are split over the WorldPop 2025 (100 m) pixels whose centre
   lies inside the unit, proportionally to pixel population (uniformly if the
   unit has no population pixels), and the pixels are summed into their H3
   res-8 cell.  Mass-conserving for units that contain at least one pixel
   centre (tiny units fall back to their centroid cell).
3. :func:`h3_to_units` moves H3 counts onto census geometries, again weighted
   by WorldPop pixel population (cell value x share of the cell's population that
   lies in the census unit).
4. :func:`finalize` turns counts into the shared output columns
   ``elec_<scope>_<year>_*`` (shares are recomputed from the resampled counts,
   so they are exactly consistent at every geography).

Counts, not shares, are resampled; shares (0-1) are intensive.
"""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import geopandas as gpd
import h3
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

H3_RES = 8
PARTY_MIN_SHARE = 0.03
# Extra folders searched for WorldPop rasters (os.pathsep-separated env var), before the cache.
WORLDPOP_DIRS_ENV_VAR = "PYCENSUS_WORLDPOP_DIRS"
DEFAULT_WORLDPOP_DIRS: List[str] = []


def default_elections_cache(cache_dir: Optional[str] = None) -> Path:
    """The elections cache folder (created): ``<cache_dir>/elections`` or the pycensus ``elections`` namespace.

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        The folder.
    """
    from pycensus.cache import get_cache_dir

    p = Path(cache_dir) / "elections" if cache_dir else get_cache_dir("elections", create=False)
    p.mkdir(parents=True, exist_ok=True)
    return p


def slug(name: str) -> str:
    """Lower-case ASCII slug of a party or candidate name (at most 40 characters).

    Args:
        name: Any text.

    Returns:
        The slug.
    """
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s.lower()).strip("_")
    return s[:40] or "x"


def download(url: str, dest: Path, timeout: int = 300, headers: Optional[dict] = None) -> Path:
    """Download ``url`` to ``dest`` once (cached). Never bypasses bot challenges.

    Args:
        url: File URL.
        dest: Local file.
        timeout: Timeout in seconds.
        headers: Extra request headers.

    Returns:
        The local file.
    """
    import requests

    dest = Path(dest)
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    h = {"User-Agent": "Mozilla/5.0 (pycensus elections loader)"}
    h.update(headers or {})
    r = requests.get(url, timeout=timeout, headers=h, stream=True)
    r.raise_for_status()
    tmp = dest.with_suffix(dest.suffix + ".part")
    with open(tmp, "wb") as f:
        for chunk in r.iter_content(1 << 20):
            f.write(chunk)
    tmp.rename(dest)
    return dest


# --------------------------------------------------------------------- blocs
def load_blocs(path: Path, election_key: str) -> Dict[str, dict]:
    """Return ``{name: {"bloc": left|right|other, ...}}`` for one election key.

    Args:
        path: Blocs JSON file.
        election_key: Election key in the file.
    """
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return d["elections"][election_key]["entries"]


def bloc_of(name: str, blocs: Dict[str, dict]) -> str:
    """Bloc of a party or candidate (``"other"``, with a warning, when it is not in the file).

    Args:
        name: Party / candidate name.
        blocs: Dict from :func:`load_blocs`.

    Returns:
        ``"left"``, ``"right"`` or ``"other"``.
    """
    e = blocs.get(name)
    if e is None:
        e = blocs.get(str(name).upper())
    if e is None:
        logger.warning("unclassified party/candidate %r -> other", name)
        return "other"
    return e["bloc"]


# -------------------------------------------------------------------- counts
def build_counts(
    long: pd.DataFrame,
    blocs: Dict[str, dict],
    unit_col: str = "unit",
    name_col: str = "party",
    votes_col: str = "votes",
    blank: Optional[pd.Series] = None,
    electors: Optional[pd.Series] = None,
    ballots: Optional[pd.Series] = None,
    rejected: Optional[pd.Series] = None,
) -> pd.DataFrame:
    """Long (unit, party, votes) -> wide counts per unit.

    Columns: ``total_votes`` (candidate/party votes + blank votes ``blank``),
    ``electors`` (registered, if given), ``ballots`` (turnout numerator, if given;
    defaults to total_votes at finalize time), ``bloc_left/right/other`` and
    ``party_<slug>`` for every name.

    Args:
        long: Long table (unit, party, votes).
        blocs: Dict from :func:`load_blocs`.
        unit_col: Unit column.
        name_col: Party column.
        votes_col: Votes column.
        blank: Blank votes per unit.
        electors: Registered electors per unit.
        ballots: Ballots cast per unit.
        rejected: Rejected ballots per unit.
    """
    long = long.copy()
    long[votes_col] = pd.to_numeric(long[votes_col], errors="coerce").fillna(0)
    long["_bloc"] = [bloc_of(n, blocs) for n in long[name_col]]
    long["_slug"] = [slug(n) for n in long[name_col]]
    party = long.pivot_table(index=unit_col, columns="_slug", values=votes_col, aggfunc="sum", fill_value=0)
    party.columns = ["party_" + c for c in party.columns]
    bl = long.pivot_table(index=unit_col, columns="_bloc", values=votes_col, aggfunc="sum", fill_value=0)
    for b in ("left", "right", "other"):
        if b not in bl.columns:
            bl[b] = 0
    bl = bl[["left", "right", "other"]]
    bl.columns = ["bloc_left", "bloc_right", "bloc_other"]
    out = pd.concat([party, bl], axis=1)
    if blank is not None:
        b = blank.reindex(out.index).fillna(0)
        out["bloc_other"] = out["bloc_other"] + b
        out["party_blank"] = b
    out["total_votes"] = out[["bloc_left", "bloc_right", "bloc_other"]].sum(axis=1)
    if electors is not None:
        out["electors"] = electors.reindex(out.index)
    if ballots is not None:
        out["ballots"] = ballots.reindex(out.index)
    elif rejected is not None:
        out["ballots"] = out["total_votes"] + rejected.reindex(out.index).fillna(0)
    out.index.name = unit_col
    return out


POOL = "POOL:"


def allocate_pools(counts: pd.DataFrame, unit_group: pd.Series, weights: pd.Series, spread_electors: bool = False) -> pd.DataFrame:
    """Spread votes that have no polygon (advance/special/mobile/unlocated polls) over the polygons of the same district.

    Rows of ``counts`` whose index starts with ``POOL:`` (``POOL:<group>``) are pooled counts of district ``<group>``;
    they are split over the real units with ``unit_group == group`` proportionally to ``weights`` (e.g. registered electors;
    uniform if all weights are 0). Registered electors themselves are never redistributed. Mass-conserving per district.

    Args:
        counts: Counts per unit, pools included.
        unit_group: District of each real unit.
        weights: Weight of each real unit.
        spread_electors: Also spread the electors.
    """
    is_pool = counts.index.astype(str).str.startswith(POOL)
    pool, real = counts[is_pool], counts[~is_pool].astype(float)
    unit_group = unit_group[~unit_group.index.duplicated()]
    weights = weights[~weights.index.duplicated()]
    if pool.empty:
        return real
    cols = [c for c in real.columns if spread_electors or c != "electors"]
    g = unit_group.reindex(real.index)
    w = weights.reindex(real.index).fillna(0).astype(float)
    wsum = w.groupby(g).transform("sum")
    n = w.groupby(g).transform("size")
    share = np.where(wsum > 0, w / wsum.replace(0, np.nan), 1.0 / n)
    share = pd.Series(share, index=real.index).fillna(0)
    pool = pool.copy()
    pool.index = [i[len(POOL):] for i in pool.index]
    pool = pool.groupby(level=0).sum()
    lost = 0.0
    for grp, row in pool.iterrows():
        m = (g == grp).to_numpy()
        if not m.any():
            lost += row.get("total_votes", 0)
            continue
        real.loc[m, cols] = real.loc[m, cols].to_numpy() + np.outer(share[m].to_numpy(), row[cols].to_numpy(dtype=float))
    if lost:
        logger.warning("%.0f pooled votes belong to districts without polygons and were dropped", lost)
    return real


# ----------------------------------------------------------------- pop grid
POPULATION_RASTER_ENV_VAR = "PYCENSUS_POPULATION_RASTER"


def find_worldpop(iso3: str, worldpop_path: Optional[str] = None) -> str:
    """Path of the WorldPop 2025 100 m raster of a country (from the given path, ``$PYCENSUS_WORLDPOP_DIRS``, the default
    folders or the cache).

    Args:
        iso3: ISO 3166-1 alpha-3 code.
        worldpop_path: Explicit raster path (wins).

    Returns:
        The raster path.

    Raises:
        FileNotFoundError: If no raster is found.
    """
    if worldpop_path:
        return worldpop_path
    from pycensus.cache import get_worldpop_dir

    env_dirs = [d for d in os.environ.get(WORLDPOP_DIRS_ENV_VAR, "").split(os.pathsep) if d]
    for d in [*env_dirs, *DEFAULT_WORLDPOP_DIRS, get_worldpop_dir(create=False)]:
        p = Path(d) / f"{iso3.lower()}_pop_2025_CN_100m_R2025A_v1.tif"
        if p.is_file():
            return str(p)
    own = os.environ.get(POPULATION_RASTER_ENV_VAR, "")   # a run's own population raster (e.g. built from a fine census): the spreading surface when there is no WorldPop
    if own and Path(own).is_file():
        return own
    raise FileNotFoundError(
        f"WorldPop raster for {iso3} not found; pass worldpop_path, set {POPULATION_RASTER_ENV_VAR} to any population raster, or download with "
        "pycensus.census.worldwide.worldpop.loader.download_worldpop_population"
    )


class PopulationGrid:
    """WorldPop pixel centres (lon, lat, pop) inside a bbox, with H3 ids."""

    def __init__(self, tif: str, bbox: Sequence[float], res: int = H3_RES):
        import rasterio
        from rasterio.windows import from_bounds

        self.res = res
        with rasterio.open(tif) as src:
            w = from_bounds(*bbox, transform=src.transform).round_offsets().round_lengths()
            arr = src.read(1, window=w, masked=True)
            tr = src.window_transform(w)
        rows, cols = np.indices(arr.shape)
        xs, ys = rasterio.transform.xy(tr, rows.ravel(), cols.ravel(), offset="center")
        pop = np.ma.filled(arr.astype("float64"), 0.0).ravel()
        pop[~np.isfinite(pop) | (pop < 0)] = 0.0
        self.df = pd.DataFrame({"lon": np.asarray(xs), "lat": np.asarray(ys), "pop": pop})
        self.df["h3"] = [h3.latlng_to_cell(la, lo, res) for la, lo in zip(self.df.lat, self.df.lon)]
        self.gdf = gpd.GeoDataFrame(self.df, geometry=gpd.points_from_xy(self.df.lon, self.df.lat), crs=4326)

    def assign(self, units: gpd.GeoDataFrame, id_col: str) -> pd.DataFrame:
        """Pixels (index = pixel row) with the unit id that contains the centre.

        Args:
            units: Polygons.
            id_col: Id column.

        Returns:
            Pixels with ``pop``, ``h3`` and ``unit``.
        """
        u = units[[id_col, "geometry"]].to_crs(4326)
        j = gpd.sjoin(self.gdf[["pop", "h3", "geometry"]], u, how="inner", predicate="within")
        j = j[~j.index.duplicated(keep="first")]
        return j[["pop", "h3", id_col]].rename(columns={id_col: "unit"})


class BlockPopulationGrid(PopulationGrid):
    """The same grid as `PopulationGrid`, with census blocks in place of WorldPop pixels: one point inside each block (its representative point)
    carrying the block's population. Blocks are the finest population count a census publishes (no model, no raster to download), so votes are
    spread over them wherever a census has blocks (the USA's decennial blocks)."""

    def __init__(self, blocks: gpd.GeoDataFrame, pop_col: str, res: int = H3_RES):
        self.res = res
        b = blocks.to_crs(4326)
        pts = b.geometry.representative_point()
        pop = pd.to_numeric(b[pop_col], errors="coerce").fillna(0.0).clip(lower=0.0).to_numpy()
        self.df = pd.DataFrame({"lon": pts.x.to_numpy(), "lat": pts.y.to_numpy(), "pop": pop})
        self.df["h3"] = [h3.latlng_to_cell(la, lo, res) for la, lo in zip(self.df.lat, self.df.lon)]
        self.gdf = gpd.GeoDataFrame(self.df, geometry=gpd.points_from_xy(self.df.lon, self.df.lat), crs=4326)


def usa_block_grid(bbox: Sequence[float], cache_dir: Optional[str] = None, res: int = H3_RES) -> BlockPopulationGrid:
    """`BlockPopulationGrid` of the decennial census blocks inside `bbox` (west, south, east, north)."""
    from shapely.geometry import box

    from pycensus.census.countries.usa import dhc

    aoi = gpd.GeoDataFrame(geometry=[box(*bbox)], crs=4326)
    blocks = dhc.load(aoi=aoi, level="block", cache_dir=cache_dir)
    pop = next(c for c in ("dhc_population", "population") if c in blocks.columns)
    return BlockPopulationGrid(blocks[[pop, "geometry"]], pop, res)


def _count_cols(counts: pd.DataFrame) -> List[str]:
    return [c for c in counts.columns if c not in ("year",)]


def units_to_h3(
    units: gpd.GeoDataFrame, counts: pd.DataFrame, grid: PopulationGrid, id_col: str = "unit"
) -> pd.DataFrame:
    """Dasymetric (WorldPop-weighted) split of unit counts onto H3 cells.

    Args:
        units: Unit polygons.
        counts: Counts per unit.
        grid: WorldPop pixels.
        id_col: Unit id column.

    Returns:
        Counts per H3 cell.
    """
    cols = _count_cols(counts)
    px = grid.assign(units, id_col)
    px = px[px.unit.isin(counts.index)]
    tot = px.groupby("unit")["pop"].transform("sum")
    n = px.groupby("unit")["pop"].transform("size")
    px["w"] = np.where(tot > 0, px["pop"] / tot.replace(0, np.nan), 1.0 / n)
    px["w"] = px["w"].fillna(1.0 / n)
    c = counts.loc[px.unit, cols].to_numpy() * px["w"].to_numpy()[:, None]
    out = pd.DataFrame(c, columns=cols)
    out["h3"] = px["h3"].to_numpy()
    out = out.groupby("h3").sum()
    # units without any pixel centre -> centroid cell
    missing = counts.index.difference(px.unit.unique())
    if len(missing):
        g = units[units[id_col].isin(missing)].drop_duplicates(id_col).set_index(id_col)
        cen = g.to_crs(3857).geometry.centroid.to_crs(4326)
        extra = counts.loc[g.index, cols].copy()
        extra["h3"] = [h3.latlng_to_cell(p.y, p.x, grid.res) for p in cen]
        out = out.add(extra.groupby("h3").sum(), fill_value=0)
        logger.info("%d units without pixel centres assigned to centroid cell", len(missing))
    return out


def h3_to_units(h3_counts: pd.DataFrame, census: gpd.GeoDataFrame, grid: PopulationGrid, id_col: str = "GEOID") -> pd.DataFrame:
    """Population-weighted split of H3 counts onto census geometries.

    Args:
        h3_counts: Counts per H3 cell.
        census: Census polygons.
        grid: WorldPop pixels.
        id_col: Census id column.

    Returns:
        Counts per census unit.
    """
    cols = _count_cols(h3_counts)
    px = grid.assign(census, id_col)
    # H3 cell population over the *whole* grid (so shares of a cell split across units are right)
    cell_pop = grid.df.groupby("h3")["pop"].sum()
    cell_n = grid.df.groupby("h3")["pop"].size()
    g = px.groupby(["h3", "unit"]).agg(pop=("pop", "sum"), n=("pop", "size")).reset_index()
    g["w"] = np.where(cell_pop.reindex(g.h3).to_numpy() > 0,
                      g["pop"] / cell_pop.reindex(g.h3).replace(0, np.nan).to_numpy(),
                      g["n"] / cell_n.reindex(g.h3).to_numpy())
    g = g[g.h3.isin(h3_counts.index)]
    c = h3_counts.loc[g.h3, cols].to_numpy() * g["w"].to_numpy()[:, None]
    out = pd.DataFrame(c, columns=cols)
    out["GEOID"] = g["unit"].to_numpy()
    out = out.groupby("GEOID").sum()
    kept = out["total_votes"].sum() / max(h3_counts["total_votes"].sum(), 1)
    logger.info("H3 -> census units conserved %.1f%% of votes", 100 * kept)
    out.attrs["conserved"] = kept
    return out


# ------------------------------------------------------------------ finalize
def kept_parties(counts: pd.DataFrame, min_share: float = PARTY_MIN_SHARE) -> List[str]:
    """Party columns above ``min_share`` of the total votes.

    Args:
        counts: Counts table.
        min_share: Smallest share kept.

    Returns:
        Column names.
    """
    tot = counts["total_votes"].sum()
    pc = [c for c in counts.columns if c.startswith("party_")]
    return [c for c in pc if counts[c].sum() / tot > min_share]


def finalize(counts: pd.DataFrame, scope: str, year: int, parties: Optional[List[str]] = None) -> pd.DataFrame:
    """counts -> ``elec_<scope>_<year>_*`` output columns.

    Args:
        counts: Counts table.
        scope: Election scope.
        year: Election year.
        parties: Party columns kept.
    """
    p = f"elec_{scope}_{year}_"
    tv = counts["total_votes"].astype(float)
    d = tv.where(tv > 0)
    out = pd.DataFrame(index=counts.index)
    out[p + "total_votes"] = tv
    if "electors" in counts and counts["electors"].notna().any():
        num = counts["ballots"] if "ballots" in counts else tv
        out[p + "turnout_rate"] = (num / counts["electors"].where(counts["electors"] > 0)).clip(upper=1.0)
    out[p + "left_share"] = counts["bloc_left"] / d
    out[p + "right_share"] = counts["bloc_right"] / d
    out[p + "other_share"] = counts["bloc_other"] / d
    for c in (parties if parties is not None else kept_parties(counts)):
        out[p + c + "_share"] = counts[c] / d
    return out


def finalize_all(unit_counts: pd.DataFrame, h3_counts: pd.DataFrame, census_counts: Optional[pd.DataFrame], scope: str, year: int):
    """Same party list for every geography (selected on the study-area totals).

    Args:
        unit_counts: Counts per unit.
        h3_counts: Counts per H3 cell.
        census_counts: Counts per census unit (or None).
        scope: Election scope.
        year: Election year.

    Returns:
        ``{"unit", "h3"[, "census"]: frame}``.
    """
    parties = kept_parties(unit_counts)
    res = {"unit": finalize(unit_counts, scope, year, parties), "h3": finalize(h3_counts, scope, year, parties)}
    if census_counts is not None:
        res["census"] = finalize(census_counts, scope, year, parties)
    return res


def sanity(frame: pd.DataFrame, scope: str, year: int) -> dict:
    """Checks of a finished frame: rows, total votes, bloc shares adding to 1, overall left / right shares.

    Args:
        frame: Output of :func:`finalize`.
        scope: Election scope.
        year: Election year.

    Returns:
        Dict of the checks.
    """
    p = f"elec_{scope}_{year}_"
    shares = frame[[p + "left_share", p + "right_share", p + "other_share"]].sum(axis=1)
    return {
        "rows": len(frame),
        "total_votes": float(frame[p + "total_votes"].sum()),
        "bloc_share_sum_min": float(shares[frame[p + "total_votes"] > 0].min()),
        "bloc_share_sum_max": float(shares[frame[p + "total_votes"] > 0].max()),
        "left": float((frame[p + "left_share"] * frame[p + "total_votes"]).sum() / frame[p + "total_votes"].sum()),
        "right": float((frame[p + "right_share"] * frame[p + "total_votes"]).sum() / frame[p + "total_votes"].sum()),
    }


# -------------------------------------------------------------------- schema
def schema_features(columns: Iterable[str], country: str, source: str, native_level: str, scope_desc: Dict[str, str]) -> list:
    """Schema feature dicts (usa/schema/housing_schema.json format) for election columns.

    Args:
        columns: Election columns.
        country: Country code.
        source: Source name.
        native_level: Geometry the results come at.
        scope_desc: ``{scope: description}``.
    """
    feats = []
    for c in columns:
        m = re.match(r"elec_(national|state|municipal)_(\d{4})_(.*)$", c)
        scope, year, rest = m.group(1), m.group(2), m.group(3)
        base = dict(category="elections", feature_name=c, original_name=c, country=country, source=source, codes=[c], native_level=native_level)
        if rest == "total_votes":
            base.update(type="count", unit="votes", definition=f"Valid votes cast (candidates + blank), {scope_desc[scope]}", resampling_up="sum", resampling_down="weighted_divide")
        elif rest == "turnout_rate":
            base.update(type="rate", unit="0-1", definition=f"Ballots cast / registered electors, {scope_desc[scope]}", resampling_up="weighted_mean", resampling_down="weighted_mean", resampling_weight=f"elec_{scope}_{year}_total_votes")
        else:
            what = "bloc" if rest in ("left_share", "right_share", "other_share") else "party/candidate"
            base.update(type="share", unit="0-1", definition=f"Share of total votes for {what} {rest[:-6]}, {scope_desc[scope]}", resampling_up="weighted_mean", resampling_down="weighted_mean", resampling_weight=f"elec_{scope}_{year}_total_votes")
        feats.append(base)
    return feats


def write_schema(path: Path, country: str, source: str, full_name: str, years: list, levels: list, features: list) -> None:
    """Write an election schema JSON.

    Args:
        path: Output file.
        country: Country code.
        source: Source name.
        full_name: Source full name.
        years: Election years.
        levels: Geometry levels.
        features: Features from :func:`schema_features`.
    """
    d = dict(country=country, source=source, full_name=full_name, years=sorted(set(years)), levels=levels, features=features)
    Path(path).write_text(json.dumps(d, indent=1, ensure_ascii=False))


def run_pipeline(
    geom: gpd.GeoDataFrame,
    counts: pd.DataFrame,
    scope: str,
    year: int,
    iso3: str,
    census_geometry: Dict[str, gpd.GeoDataFrame],
    worldpop_path: Optional[str] = None,
    unit_label: str = "unit",
) -> Dict[str, pd.DataFrame]:
    """unit counts (+polygons) -> ``{unit_label, "h3", <census level>...}`` frames of ``elec_*`` columns.

    ``geom``: GeoDataFrame(unit, geometry) of the finest result units; ``counts``: build_counts() output (index unit);
    ``census_geometry``: level -> GeoDataFrame(GEOID, geometry).

    Args:
        geom: Unit polygons (``unit``, geometry).
        counts: Output of :func:`build_counts`.
        scope: Election scope.
        year: Election year.
        iso3: Country ISO3 code (WorldPop).
        census_geometry: ``{level: polygons}``.
        worldpop_path: Explicit WorldPop raster.
        unit_label: Name of the unit level in the output.
    """
    if geom["unit"].duplicated().any():
        geom = geom.dissolve(by="unit", as_index=False)
    counts = counts[counts.index.isin(geom["unit"])]
    if "electors" in counts and (counts["electors"].fillna(0) == 0).all():
        counts = counts.drop(columns=["electors", "ballots"], errors="ignore")
    b = geom.total_bounds
    pad = 0.01
    grid = PopulationGrid(find_worldpop(iso3, worldpop_path), (b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad))
    h3c = units_to_h3(geom, counts, grid)
    parties = kept_parties(counts)
    res = {unit_label: counts, "h3": h3c}
    for lvl, cg in census_geometry.items():
        res[lvl] = h3_to_units(h3c, cg[["GEOID", "geometry"]], grid)
    fin = {}
    for k, v in res.items():
        f = finalize(v, scope, year, parties)
        f.index.name = {unit_label: unit_label, "h3": "h3_cell"}.get(k, "GEOID")
        if k not in (unit_label, "h3"):
            f = f[f.iloc[:, 0] > 0]
        fin[k] = f
    return fin
