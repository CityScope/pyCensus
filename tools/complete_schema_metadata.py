"""Make every feature of every pyCensus country schema carry the metadata the maps' Metadata tab shows.

Adds `original_name` (the source's own variable name(s) / derivation) to each feature and fills a missing `definition` of the
USA combined schema from the per-source schemas. Idempotent: existing `original_name` values are never overwritten.
Run from the repo root:  python tools/complete_schema_metadata.py
"""
import glob
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "src" / "pycensus" / "countries"

_ELECTION = re.compile(r"^(\d{4})_(president|senate)_(total_votes|democrat_share|republican_share)$")
_CBS_FIELDS = ("Foreign_pcnt", "pop_approx", "religionCode", "religiosityCode")


def original_name(feat: dict) -> str:
    codes = feat.get("codes")
    if codes:
        return ", ".join(str(c) for c in codes)
    if feat.get("computed_from"):
        cf = feat["computed_from"]
        return "computed from " + (", ".join(map(str, cf)) if isinstance(cf, (list, tuple)) else str(cf))
    if feat.get("table"):  # Spain Censo 2021 (INE SDC21)
        parts = [f"table {feat['table']}", f"metric {feat['metric']}"]
        if feat.get("variable"):
            parts.append(f"{feat['variable']} = {feat.get('category_value')}")
        return "; ".join(parts)
    m = _ELECTION.match(feat.get("feature_name", ""))
    if m:  # MIT Election Lab (MEDSL) returns
        year, office, kind = m.groups()
        what = "totalvotes" if kind == "total_votes" else f"candidatevotes / totalvotes (party {kind.split('_')[0].upper()})"
        return f"MEDSL {year} {office}: {what}"
    definition = feat.get("definition") or ""
    found = [f for f in _CBS_FIELDS if f in definition]
    if found:
        return ", ".join(found) + " (derived)"
    return f"(derived) {feat.get('feature_name')}"


# Definitions for features of the USA combined schema whose name differs from the per-source schemas' (ACS 1/5-year, DHC).
_FALLBACK_DEFINITIONS = {
    "incomeMedianHousehold": "Median household income in the past 12 months (inflation-adjusted dollars).",
    "unemployed": "Civilian labor force aged 16 and over that is unemployed.",
    "workersCar": "Workers aged 16 and over who commute by car, truck or van.",
    "workersTransit": "Workers aged 16 and over who commute by public transportation (excluding taxicab).",
    "workersWalk": "Workers aged 16 and over who commute on foot.",
    "workersBike": "Workers aged 16 and over who commute by bicycle.",
    "age18to64Population": "People aged 18 to 64.",
    "whitePopulation": "People identifying as White alone.",
    "blackPopulation": "People identifying as Black or African American alone.",
    "nativePopulation": "People identifying as American Indian and Alaska Native alone.",
    "asianPopulation": "People identifying as Asian alone.",
    "otherRacePopulation": "People identifying as Native Hawaiian and Other Pacific Islander alone, some other race alone, or two or more races.",
    "hispanicPopulation": "People of Hispanic or Latino origin (of any race).",
    "housingUnits": "Total housing units.",
    "malePopulation": "Male population.",
    "femalePopulation": "Female population.",
    "under18Population": "Population under 18 years.",
    "over65Population": "Population aged 65 years and over.",
}

_FEATURE_LINE = re.compile(r'^(?P<indent>[ \t]*)"feature_name": "(?P<name>[^"]*)",[ \t]*$', re.M)


def main() -> None:
    """Insert the missing keys as text right after each `feature_name` line, so the files keep their formatting."""
    per_source = {}
    files = sorted(glob.glob(str(ROOT / "*" / "schema" / "*_schema.json")))
    for f in files:
        data = json.loads(Path(f).read_text(encoding="utf-8"))
        for feat in (data.get("features") if isinstance(data, dict) else data) or []:
            if feat.get("definition"):
                per_source.setdefault((feat.get("source"), feat.get("feature_name")), feat["definition"])
    changed = 0
    for f in files:
        path = Path(f)
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        feats = (data.get("features") if isinstance(data, dict) else data) or []
        matches = list(_FEATURE_LINE.finditer(text))
        if not feats or len(matches) != len(feats):
            print(f"skipped {path.relative_to(ROOT)} (feature lines {len(matches)} != features {len(feats)})")
            continue
        out, last = [], 0
        bounds = [m.start() for m in matches[1:]] + [len(text)]
        for m, nxt, feat in zip(matches, bounds, feats):
            extra = []
            if not feat.get("original_name"):
                extra.append(("original_name", original_name(feat)))
            definition = per_source.get((feat.get("source"), feat.get("feature_name"))) or _FALLBACK_DEFINITIONS.get(feat.get("feature_name"))
            block = text[m.end():nxt]
            if not feat.get("definition") and definition:
                if '"definition": ""' in block:   # an empty definition already exists: fill it in place
                    block = block.replace('"definition": ""', f'"definition": {json.dumps(definition, ensure_ascii=False)}', 1)
                else:
                    extra.append(("definition", definition))
            out.append(text[last:m.end()])
            for k, v in extra:
                out.append(f"\n{m.group('indent')}{json.dumps(k)}: {json.dumps(v, ensure_ascii=False)},")
            out.append(block)
            last = nxt
        out.append(text[last:])
        new = "".join(out)
        if new != text:
            json.loads(new)  # must stay valid JSON
            path.write_text(new, encoding="utf-8")
            changed += 1
            print("updated", path.relative_to(ROOT))
    print(f"{changed} schema files updated")


if __name__ == "__main__":
    main()
