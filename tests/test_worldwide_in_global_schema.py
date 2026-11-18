"""Each global schema covers its worldwide columns: census (WorldPop, GBA) and cadaster (GBA buildings)."""

import json
from pathlib import Path

import pycensus

PKG = Path(pycensus.__file__).resolve().parent


def test_census_worldwide_columns_are_global():
    glob = {f["feature_name"] for f in json.loads((PKG / "census" / "global_schema.json").read_text())}
    eq = json.loads((PKG / "reference" / "global_equivalents.json").read_text())["equivalents"]
    files = sorted((PKG / "census" / "worldwide" / "schema").glob("*_schema.json"))
    assert {f.name for f in files} >= {"worldpop_schema.json", "gba_schema.json"}
    for f in files:
        d = json.loads(f.read_text())
        for feat in d["features"]:
            name = feat["feature_name"]
            assert name in glob or eq.get(f"{d['source']}_{name}") in glob, (f.name, name)


def _names(fields):
    return set(fields) if isinstance(fields, dict) else {x["name"] if isinstance(x, dict) else x for x in fields}


def test_cadaster_worldwide_fields_are_global():
    glob = _names(json.loads((PKG / "cadaster" / "global_schema.json").read_text())["fields"])
    files = sorted((PKG / "cadaster" / "worldwide").glob("*/schema.json"))
    assert files
    for f in files:
        assert _names(json.loads(f.read_text())["fields"]) <= glob, f
