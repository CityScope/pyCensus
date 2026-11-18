"""Shared plumbing for election-result loaders (Spain, Andorra, Germany).

Column convention (``<scope>`` = national | state | municipal): ``elec_<scope>_<year>_total_votes`` (valid votes incl. blank, count),
``..._turnout_rate`` (votes cast / electors, only when electors are known), ``..._left_share``, ``..._right_share``, ``..._other_share``
(sum to 1; blank votes and unlisted parties count as other) and ``..._party_<slug>_share`` (share of valid votes) for every party above
``min_share`` of the loaded area. Also kept (counts, needed to re-aggregate shares exactly): ``..._electors``, ``..._votes_cast``,
``..._left_votes``, ``..._right_votes``, ``..._party_<slug>_votes``.

Bloc files (``schema/*_blocs.json``): ``{"parties": {KEY: {"bloc": "left|right|other", "uncertain": bool, "note": str}}, "default": "other"}``.

H3: polygons -> res-8 cells is AREA-weighted (no fine population surface is available for all three countries): each polygon is covered
with a finer H3 grid (res 8..11 chosen so it has >= ~30 sub-cells), sub-cells are mapped to their res-8 parent and the polygon's counts are
split in proportion to the sub-cells in each parent. Counts are summed in the cell, shares are recomputed from the summed counts.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Dict, Iterable, Optional

import numpy as np
import pandas as pd


def slugify(s: str) -> str:
    """Lower-case ASCII slug of a name (``_`` between words).

    Args:
        s: Any text.

    Returns:
        The slug (``"x"`` when empty).
    """
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "x"


def load_blocs(path) -> dict:
    """The party-to-bloc file of an election.

    Args:
        path: JSON file.

    Returns:
        The file's dict.
    """
    return json.loads(Path(path).read_text(encoding="utf-8"))


def bloc_of(blocs: dict, key: str) -> str:
    """Bloc (left / right / other) of a party.

    Args:
        blocs: Dict from :func:`load_blocs`.
        key: Party key.

    Returns:
        The bloc name.
    """
    return blocs["parties"].get(key, {}).get("bloc", blocs.get("default", "other"))


def build_frame(votes: pd.DataFrame, totals: pd.DataFrame, blocs: dict, scope: str, year: int, min_share: float = 0.03,
                keep_parties: Optional[Iterable[str]] = None) -> pd.DataFrame:
    """``votes``: long [GEOID, party, votes] (party = bloc-file key, candidacies only); ``totals``: [GEOID, blank, cast, electors]
    (``cast`` = valid + null votes; ``electors`` NaN/0 if unknown). Returns wide frame keyed by GEOID (see module doc).

    Args:
        votes: Long votes table.
        totals: Totals table.
        blocs: Dict from :func:`load_blocs`.
        scope: ``"national"``, ``"state"`` or ``"municipal"``.
        year: Election year.
        min_share: Parties above this share of the area get their own columns.
        keep_parties: Fixed list of parties.
    """
    p = f"elec_{scope}_{year}_"
    w = votes.pivot_table(index="GEOID", columns="party", values="votes", aggfunc="sum", fill_value=0)
    t = totals.set_index("GEOID").reindex(w.index.union(totals["GEOID"])).fillna(0)
    w = w.reindex(t.index, fill_value=0)
    area_share = w.sum() / (w.values.sum() + t["blank"].sum())
    keep = list(keep_parties) if keep_parties is not None else list(area_share[area_share > min_share].index)
    out = pd.DataFrame(index=t.index)
    valid = w.sum(axis=1) + t["blank"]
    out[p + "total_votes"] = valid
    out[p + "votes_cast"] = t["cast"]
    out[p + "electors"] = t["electors"].where(t["electors"] > 0)
    out[p + "turnout_rate"] = out[p + "votes_cast"] / out[p + "electors"]
    kinds = pd.Series({c: bloc_of(blocs, c) for c in w.columns})
    out[p + "left_votes"] = w.loc[:, kinds[kinds == "left"].index].sum(axis=1)
    out[p + "right_votes"] = w.loc[:, kinds[kinds == "right"].index].sum(axis=1)
    for c in keep:
        out[f"{p}party_{slugify(c)}_votes"] = w[c]
    out.index.name = "GEOID"
    return _add_shares(out.reset_index(), p)


def _add_shares(df: pd.DataFrame, p: str) -> pd.DataFrame:
    tv = df[p + "total_votes"].replace(0, np.nan)
    df[p + "left_share"] = df[p + "left_votes"] / tv
    df[p + "right_share"] = df[p + "right_votes"] / tv
    df[p + "other_share"] = 1 - df[p + "left_share"] - df[p + "right_share"]
    df[p + "turnout_rate"] = df[p + "votes_cast"] / df[p + "electors"]
    for c in [c for c in df.columns if c.startswith(p + "party_") and c.endswith("_votes")]:
        df[c[:-6] + "_share"] = df[c] / tv
    return df


def order_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Key columns (``GEOID``, ``h3_cell``) first.

    Args:
        df: Table.

    Returns:
        The reordered table.
    """
    keys = [c for c in ("GEOID", "h3_cell") if c in df.columns]
    return df[keys + [c for c in df.columns if c not in keys]]


def h3_weights(gdf, res: int = 8, id_col: str = "GEOID") -> pd.DataFrame:
    """Polygon -> res cell area weights: DataFrame [id_col, h3_cell, w] (w sums to 1 per polygon).

    Args:
        gdf: Polygons.
        res: H3 resolution.
        id_col: Id column.
    """
    import h3
    from shapely.geometry import mapping
    rows = []
    g = gdf.to_crs(4326)
    ea = g.to_crs(3035).geometry.area.values
    for gid, geom, a in zip(g[id_col], g.geometry, ea):
        if geom is None or geom.is_empty:
            continue
        fine = res
        while fine < 11 and a / h3.average_hexagon_area(fine, unit="m^2") < 30:
            fine += 1
        parts = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        cells = []
        for pg in parts:
            cells += list(h3.geo_to_cells(mapping(pg), fine))
        if not cells:
            pt = geom.representative_point()
            rows.append((gid, h3.latlng_to_cell(pt.y, pt.x, res), 1.0))
            continue
        par = pd.Series([h3.cell_to_parent(c, res) if fine > res else c for c in cells]).value_counts()
        for c, n in par.items():
            rows.append((gid, c, n / len(cells)))
    return pd.DataFrame(rows, columns=[id_col, "h3_cell", "w"])


def to_h3(df: pd.DataFrame, weights: pd.DataFrame, scope: str, year: int, id_col: str = "GEOID") -> pd.DataFrame:
    """Distribute a frame from :func:`build_frame` over H3 cells with ``weights`` and recompute rates/shares from summed counts.

    Args:
        df: Frame from :func:`build_frame`.
        weights: Weights from :func:`h3_weights`.
        scope: Election scope.
        year: Election year.
        id_col: Id column.
    """
    p = f"elec_{scope}_{year}_"
    cnt = [c for c in df.columns if c.endswith(("_votes", "_electors", "_votes_cast"))]
    m = weights.merge(df[[id_col] + cnt], on=id_col)
    for c in cnt:
        m[c] = m[c] * m["w"]
    g = m.groupby("h3_cell")[cnt].sum().reset_index()
    g[p + "electors"] = g[p + "electors"].where(g[p + "electors"] > 0)
    return order_columns(_add_shares(g, p))
