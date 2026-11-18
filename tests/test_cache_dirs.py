"""Cache/data directory resolution: explicit > PYCENSUS_CACHE_DIR > temp folder; never the CWD."""

from __future__ import annotations

import tempfile
from pathlib import Path

from pycensus.cache import CACHE_ENV_VAR, default_cache_dir, get_cache_dir, get_data_dir


def test_default_is_temp_folder(monkeypatch):
    monkeypatch.delenv(CACHE_ENV_VAR, raising=False)
    p = get_cache_dir("elections", create=False)
    assert p == Path(tempfile.gettempdir()) / "pycensus-cache" / "elections"
    assert default_cache_dir() == str(Path(tempfile.gettempdir()) / "pycensus-cache" / "parquet")


def test_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv(CACHE_ENV_VAR, str(tmp_path))
    assert get_cache_dir("elections") == tmp_path / "elections"
    assert (tmp_path / "elections").is_dir()  # created lazily on request
    assert get_data_dir("spain") == tmp_path / "data" / "spain"


def test_explicit_wins_and_is_unchanged(monkeypatch, tmp_path):
    monkeypatch.setenv(CACHE_ENV_VAR, str(tmp_path / "env"))
    assert get_cache_dir("x", tmp_path / "explicit") == tmp_path / "explicit"
    assert get_data_dir("spain", str(tmp_path / "d")) == tmp_path / "d"


def test_no_cwd_pollution(monkeypatch, tmp_path):
    monkeypatch.delenv(CACHE_ENV_VAR, raising=False)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    from pycensus.census.countries.spain.catastro import loader as catastro
    from pycensus.census.countries.usa.housing import loader as housing
    from pycensus.elections_common import default_elections_cache

    default_elections_cache()
    assert catastro._cache(None) == Path(tempfile.gettempdir()) / "pycensus-cache" / "data" / "spain" / "raw" / "catastro"
    housing._raw(None)
    assert list(cwd.iterdir()) == []
