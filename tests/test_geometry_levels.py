"""Tests for pycensus.geometry_levels.resolve_level."""

from __future__ import annotations

from pycensus.geometry_levels import resolve_level


def test_returns_level_unchanged_when_not_in_fallback():
    assert resolve_level("tract", {"province": "county"}) == "tract"


def test_resolves_single_hop_fallback():
    assert resolve_level("province", {"province": "county"}) == "county"


def test_resolves_chained_fallback():
    fallback = {"province": "region", "region": "county"}
    assert resolve_level("province", fallback) == "county"


def test_does_not_loop_forever_on_a_cycle():
    fallback = {"a": "b", "b": "a"}
    # Should terminate (visiting each level at most once), not hang.
    result = resolve_level("a", fallback)
    assert result in ("a", "b")


def test_empty_fallback_map_returns_level_unchanged():
    assert resolve_level("province", {}) == "province"
