"""Every country's levels.json must map all 7 canonical global levels.

Regression guard for a real gap found 2026-08-20: Canada's and Israel's
levels.json each covered only 5-6 of the 7 canonical levels from
global_levels.json (missing "block"), and Israel's runtime
LEVEL_FALLBACK/levels.json disagreed with each other on where "state"
resolves ("nation" in levels.json's stale global_to_country_mapping vs
"district" in the actual pycensus.israel.constants.LEVEL_FALLBACK used at
runtime). This test enforces the doc's requirement ("pycensus should always
admit a global levels/schema mapping to equivalents in each country
census") going forward for every levels.json in the repo, not just the ones
audited this round.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_SRC = Path(__file__).resolve().parents[1] / "src" / "pycensus"

with open(REPO_SRC / "schemas" / "global_levels.json") as f:
    _GLOBAL_LEVELS_DATA = json.load(f)

GLOBAL_LEVELS = {entry["geometry_level"] for entry in _GLOBAL_LEVELS_DATA["geometry_levels"]}

LEVELS_JSON_PATHS = sorted((REPO_SRC / "countries").glob("*/schema/levels.json"))


def test_global_levels_json_has_seven_canonical_levels():
    # Sanity check on the fixture itself, so a change to global_levels.json's
    # own shape fails loudly here instead of silently passing every
    # per-country test below with a shrunk set.
    assert GLOBAL_LEVELS == {
        "nation", "state", "province", "municipality", "tract", "blockgroup", "block",
    }


@pytest.mark.parametrize("path", LEVELS_JSON_PATHS, ids=lambda p: str(p.relative_to(REPO_SRC)))
def test_levels_json_maps_every_global_level(path: Path):
    data = json.loads(path.read_text())
    mapping = data.get("global_to_country_mapping", {})
    missing = GLOBAL_LEVELS - set(mapping)
    assert not missing, (
        f"{path.relative_to(REPO_SRC)}'s global_to_country_mapping is missing "
        f"{sorted(missing)} -- every country/source must map all 7 canonical "
        f"global_levels.json levels, even to an unimplemented finest level as "
        f"a documented fallback (see IMPLEMENTING_A_COUNTRY.md)."
    )


@pytest.mark.parametrize("path", LEVELS_JSON_PATHS, ids=lambda p: str(p.relative_to(REPO_SRC)))
def test_levels_json_mapping_targets_are_real_native_levels(path: Path):
    data = json.loads(path.read_text())
    mapping = data.get("global_to_country_mapping", {})
    native_levels = set(data.get("levels", []))
    if not native_levels:
        pytest.skip(f"{path} has no 'levels' list to validate against")
    bad_targets = {v for v in mapping.values() if v not in native_levels}
    assert not bad_targets, (
        f"{path.relative_to(REPO_SRC)}'s global_to_country_mapping points at "
        f"{sorted(bad_targets)}, which aren't in its own 'levels' list "
        f"{sorted(native_levels)} -- a dangling level reference."
    )
