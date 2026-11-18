"""Which global census columns does a result table fill, and how completely? (the census-gap monitor)

    python tools/census_coverage.py path/to/h3_res7.parquet            # one table (parquet / csv / gpkg)
    python tools/census_coverage.py city_science_network/*/results/downloads/h3_res7.parquet --population population

Prints, per file, the global columns that are missing, empty (all null/0) or partial (share of population-weighted rows with a value), and the
share of global columns filled. Elections (`elec_*`) and year-built (`dwellings_built_*`) columns are reported with the rest. Exit code 0 always:
it is a report, the work list for `AGENT_GUIDE_NEW_CITY_OR_COUNTRY.md`.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

SCHEMA = Path(__file__).resolve().parent.parent / "src" / "pycensus" / "schemas" / "global_schema.json"


def load(path: str) -> pd.DataFrame:
    p = Path(path)
    if p.suffix == ".parquet":
        return pd.read_parquet(p)
    if p.suffix == ".csv":
        return pd.read_csv(p)
    import geopandas as gpd
    return pd.DataFrame(gpd.read_file(p).drop(columns="geometry", errors="ignore"))


def coverage(df: pd.DataFrame, population: str = "population") -> pd.DataFrame:
    names = list(dict.fromkeys(g["feature_name"] for g in json.loads(SCHEMA.read_text(encoding="utf-8"))))
    w = pd.to_numeric(df[population], errors="coerce").fillna(0) if population in df else pd.Series(1.0, index=df.index)
    rows = []
    for n in names:
        if n not in df:
            rows.append((n, "missing", 0.0))
            continue
        v = pd.to_numeric(df[n], errors="coerce")
        have = v.notna() & (v != 0)
        share = float(w[have].sum() / w.sum()) if w.sum() else float(have.mean())
        rows.append((n, "empty" if share == 0 else ("filled" if share >= 0.95 else "partial"), round(share, 3)))
    return pd.DataFrame(rows, columns=["column", "status", "population_share_with_value"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--population", default="population")
    a = ap.parse_args()
    for f in a.files:
        c = coverage(load(f), a.population)
        print(f"\n{f}: {int((c.status == 'filled').sum())}/{len(c)} global columns filled")
        for st in ("missing", "empty", "partial"):
            sub = c[c.status == st]
            if len(sub):
                print(f"  {st} ({len(sub)}): " + ", ".join(sub.column if st != "partial" else (sub.column + "=" + sub.population_share_with_value.astype(str))))


if __name__ == "__main__":
    main()
