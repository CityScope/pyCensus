"""Detect year-suffixed column families and keep the latest member (data driven, no hard-coded column list).

Stored parquet files keep every historic variant; the MAPS only show the latest: the last municipal / state / national election and
the latest-period housing / rent / price / income / tourist / migration columns.

Rules (`latest_column_filter`):
  * election columns (`[<source>_]elec_<scope>_<year><suffix>_<metric>`): per scope (national / state / municipal) only the columns of the
    latest year are kept (a `2023leg` / `2023council` variant counts as year 2023);
  * every other column whose name carries a year token (`2016`, `FY2026`, `2025M08`, `cagr_2016_2025`) belongs to a family = the name with the
    year token(s) removed; inside a family only the latest period is kept; the un-suffixed member of a family (e.g. `rent_median` next to
    `rent_median_2016`) is the CURRENT period and wins over every suffixed one.
  * columns with two or more year tokens (ranges / bins such as `built_2011_a_2020_share`) and years glued to letters (`hhIncome20000To24999`) are never dropped;
  * `protect` (iterable of regexes) names columns never dropped.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

_TOKEN = re.compile(r"_?(?:(?<=_)|(?<=FY)|^)((?:19|20)\d{2})(?:M(\d{2}))?(?![0-9])")
_ELEC = re.compile(r"^(?P<pre>(?:[A-Za-z0-9]+_)?)elec_(?P<scope>national|state|municipal)_(?P<year>(?:19|20)\d{2})(?P<var>[A-Za-z]*)_(?P<metric>.+)$")
_INF = (10 ** 6, 0)


def parse_period(col: str) -> Tuple[str, Optional[Tuple[int, ...]]]:
    """`(family key, period)` of a column name; period is None when the name has no year token. Period = tuple of (year*100+month) per token.

    Args:
        col: Column name.
    """
    toks = list(_TOKEN.finditer(col))
    if not toks:
        return col, None
    key = _TOKEN.sub("", col)
    return key, tuple(int(m.group(1)) * 100 + int(m.group(2) or 0) for m in toks)


def election_parts(col: str) -> Optional[Tuple[str, int, str]]:
    """`(scope, year, variant)` for an election column (`elec_national_2023leg_left_share` -> ("national", 2023, "leg")), else None.

    Args:
        col: Column name.
    """
    m = _ELEC.match(col)
    return (m.group("scope"), int(m.group("year")), m.group("var")) if m else None


def latest_column_filter(columns: Iterable[str], protect: Sequence[str] = ()) -> Tuple[List[str], Dict[str, str]]:
    """`(kept columns in input order, {dropped column: reason})`.

    Args:
        columns: Column names.
        protect: Regexes of columns never dropped.
    """
    cols = [c for c in columns if isinstance(c, str)]
    prot = [re.compile(p) for p in protect]
    dropped: Dict[str, str] = {}
    latest_year: Dict[str, int] = {}
    for c in cols:
        e = election_parts(c)
        if e:
            latest_year[e[0]] = max(latest_year.get(e[0], 0), e[1])
    fam: Dict[str, List[Tuple[Tuple[int, ...], str]]] = {}
    for c in cols:
        if any(p.search(c) for p in prot):
            continue
        e = election_parts(c)
        if e:
            if e[1] < latest_year[e[0]]:
                dropped[c] = f"older {e[0]} election ({e[1]} < {latest_year[e[0]]})"
            continue
        key, per = parse_period(c)
        if per is not None and len(per) > 1:   # a range / bin (`built_2011_a_2020`, `cagr_2016_2025`): not a historic series, never dropped
            continue
        fam.setdefault(key, []).append((_INF if per is None else per, c))
    for key, members in fam.items():
        if len(members) < 2:
            continue
        best = max(p for p, _ in members)
        for p, c in members:
            if p != best:
                dropped[c] = "historic period (latest kept)"
    return [c for c in cols if c not in dropped], dropped


_PARTY = re.compile(r"^(?P<prefix>.*elec_(?:national|state|municipal)_\d{4}[A-Za-z]*)_party_(?P<party>.+?)_(?P<kind>votes|share)$")


_REGION_COLUMNS = ("state", "state_name", "state_fips", "ccaa", "ccaa_code", "region", "province", "provincia")


def _region_labels(frame):
    """One region label per row of `frame` (state / autonomous community) or None when the frame carries no region.

    Uses an explicit region column when there is one, otherwise the leading 2 digits of a numeric `geo_id` of the US/Spain
    census-unit lengths (state FIPS / province code)."""
    for c in _REGION_COLUMNS:
        if c in frame.columns:
            return frame[c].astype(str).to_numpy()
    if "geo_id" in frame.columns:
        ids = frame["geo_id"].astype(str)
        if len(ids) and ids.str.fullmatch(r"\d{10,12}").all():
            return ids.str[:2].to_numpy()
    return None


def _party_scores(frame, rows, w):
    import numpy as np

    groups: Dict[str, Dict[str, Dict[str, float]]] = {}
    for c in frame.columns:
        m = _PARTY.match(str(c))
        if not m:
            continue
        v = np.asarray(frame[c], dtype=float)[rows]
        ww = None if w is None else w[rows]
        tot = float(np.nansum(v)) if m.group("kind") == "votes" else float(np.nansum(v * ww if ww is not None else v))
        groups.setdefault(m.group("prefix"), {}).setdefault(m.group("party"), {})[m.group("kind")] = tot
    return groups


def _major_parties(groups, max_parties, min_share):
    """`{(prefix, party)}` of the parties kept per election: the `max_parties` most voted ones above `min_share` of the party votes."""
    keep = set()
    for prefix, parties in groups.items():
        score = {p: d.get("votes", d.get("share", 0.0)) for p, d in parties.items()}
        total = sum(score.values()) or 1.0
        keep.update((prefix, p) for p in sorted(score, key=score.get, reverse=True)[:max_parties] if score[p] / total > min_share)
    return keep


def minor_party_columns(frame, max_parties: int = 4, min_share: float = 0.05) -> set:
    """Party columns to drop, judged on `frame` (the finest one).

    Majority is judged nationwide AND within every region (state / autonomous community): a party is kept when it is among the
    `max_parties` most voted parties (above `min_share` of the party votes) of the whole country OR of any single region, so a party
    that wins one region but is small nationally stays. Every other `..._party_<name>_(votes|share)` column is minor.

    Args:
        frame: Finest frame.
        max_parties: Parties kept per area.
        min_share: Smallest share kept.
    """
    import numpy as np

    w = np.asarray(frame["population"], dtype=float) if "population" in frame.columns else None
    everything = np.arange(len(frame))
    national = _party_scores(frame, everything, w)
    keep = _major_parties(national, max_parties, min_share)
    regions = _region_labels(frame)
    if regions is not None:
        for r in np.unique(regions):
            keep |= _major_parties(_party_scores(frame, np.flatnonzero(regions == r), w), max_parties, min_share)
    drop = set()
    for prefix, parties in national.items():
        for p in parties:
            if (prefix, p) not in keep:
                drop.update(f"{prefix}_party_{p}_{k}" for k in ("votes", "share"))
    return drop


def drop_historic_columns(df, protect: Sequence[str] = (), report: Optional[dict] = None):
    """`df` without the historic variants (a new frame; `report["dropped"]` gets the dropped names).

    Args:
        df: Table.
        protect: Regexes of columns never dropped.
        report: Optional dict that receives the dropped names.
    """
    _, dropped = latest_column_filter(df.columns, protect)
    if report is not None:
        report.setdefault("historic_dropped", {}).update(dropped)
    return df.drop(columns=list(dropped)) if dropped else df


def filter_map_frames(groups: Dict[str, dict], protect: Sequence[str] = (), report_path=None) -> dict:
    """Drop historic variants from every frame of `groups` (`{"h3": {res: df}, "census": {level: df}, ...}`, dicts modified in place).

    Returns (and writes to `report_path` as JSON when given) `{"<group>/<key>": {"dropped": {col: reason}}}`; stored parquet files are untouched.

    Args:
        groups: Frames by group and key.
        protect: Regexes of columns never dropped.
        report_path: Optional JSON report file.
    """
    import json
    from pathlib import Path

    report: dict = {}
    for gname, frames in groups.items():
        for key, df in list(frames.items()):
            if df is None or not hasattr(df, "columns"):
                continue
            from .year_built import drop_intermediate_bands

            _, dropped = latest_column_filter(df.columns, protect)
            reduced = drop_intermediate_bands(df)
            bands = [c for c in df.columns if c not in reduced.columns]
            if dropped or bands:
                frames[key] = reduced.drop(columns=[c for c in dropped if c in reduced.columns])
                report[f"{gname}/{key}"] = {"dropped": {**dropped, **{c: "intermediate year-built band (shares kept)" for c in bands}}}
    with_parties = [df for fr in groups.values() for df in fr.values() if hasattr(df, "columns") and any(_PARTY.match(str(c)) for c in df.columns)]
    finest = max(with_parties, key=lambda d: len(d), default=None)   # the largest frame that carries party columns
    minor = minor_party_columns(finest) if finest is not None else set()
    if minor:
        for gname, frames in groups.items():
            for key, df in list(frames.items()):
                if hasattr(df, "columns"):
                    cut = [c for c in df.columns if c in minor]
                    if cut:
                        frames[key] = df.drop(columns=cut)
                        report.setdefault(f"{gname}/{key}", {"dropped": {}})["dropped"].update({c: "minor party (not top 4 above 5% nationally or in any region)" for c in cut})
    if report_path is not None:
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(json.dumps(report, indent=1, ensure_ascii=False))
    return report


MAP_INPUT_FRAME_DICTS = ("h3_by_resolution", "census_by_level", "special_levels", "stats_by_area")


def filter_map_inputs(inputs: dict, protect: Sequence[str] = (), report_path=None, add_globals: bool = True) -> dict:
    """`build_city_map(**inputs)`-shaped dict: add the period-free global columns, then drop historic variants (frames replaced in place).
    Returns the report `{"<dict>/<key>": {"dropped": {...}}}` (also written to `report_path`).

    Args:
        inputs: ``build_city_map`` keyword arguments.
        protect: Regexes of columns never dropped.
        report_path: Optional JSON report file.
        add_globals: Add the global columns first.
    """
    if add_globals:
        from .global_equivalents import add_global_equivalents

        for name in MAP_INPUT_FRAME_DICTS:
            for k, v in list((inputs.get(name) or {}).items()):
                if hasattr(v, "columns"):
                    inputs[name][k] = add_global_equivalents(v)
    groups = {n: inputs[n] for n in MAP_INPUT_FRAME_DICTS if isinstance(inputs.get(n), dict)}
    return filter_map_frames(groups, protect, report_path)
