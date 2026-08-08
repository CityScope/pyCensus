"""Tests for pycensus.api_keys: explicit arg > environment variable > JSON file precedence."""

from __future__ import annotations

import json

from pycensus import api_keys


def test_explicit_key_wins_over_everything(monkeypatch, tmp_path):
    monkeypatch.setenv("SOME_KEY", "env-value")
    keys_file = tmp_path / "api_keys.json"
    keys_file.write_text(json.dumps({"some": "file-value"}))
    monkeypatch.setattr(api_keys, "_KEYS_FILE", keys_file)

    assert api_keys.resolve_api_key("some", "SOME_KEY", "explicit-value") == "explicit-value"


def test_env_var_wins_over_file(monkeypatch, tmp_path):
    monkeypatch.setenv("SOME_KEY", "env-value")
    keys_file = tmp_path / "api_keys.json"
    keys_file.write_text(json.dumps({"some": "file-value"}))
    monkeypatch.setattr(api_keys, "_KEYS_FILE", keys_file)

    assert api_keys.resolve_api_key("some", "SOME_KEY") == "env-value"


def test_falls_back_to_json_file(monkeypatch, tmp_path):
    monkeypatch.delenv("SOME_KEY", raising=False)
    keys_file = tmp_path / "api_keys.json"
    keys_file.write_text(json.dumps({"some": "file-value"}))
    monkeypatch.setattr(api_keys, "_KEYS_FILE", keys_file)

    assert api_keys.resolve_api_key("some", "SOME_KEY") == "file-value"


def test_returns_none_when_nowhere_found(monkeypatch, tmp_path):
    monkeypatch.delenv("SOME_KEY", raising=False)
    monkeypatch.setattr(api_keys, "_KEYS_FILE", tmp_path / "does_not_exist.json")

    assert api_keys.resolve_api_key("some", "SOME_KEY") is None


def test_empty_string_in_file_is_treated_as_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("SOME_KEY", raising=False)
    keys_file = tmp_path / "api_keys.json"
    keys_file.write_text(json.dumps({"some": ""}))
    monkeypatch.setattr(api_keys, "_KEYS_FILE", keys_file)

    assert api_keys.resolve_api_key("some", "SOME_KEY") is None


def test_malformed_json_file_does_not_raise(monkeypatch, tmp_path):
    monkeypatch.delenv("SOME_KEY", raising=False)
    keys_file = tmp_path / "api_keys.json"
    keys_file.write_text("{not valid json")
    monkeypatch.setattr(api_keys, "_KEYS_FILE", keys_file)

    assert api_keys.resolve_api_key("some", "SOME_KEY") is None


def test_missing_key_name_in_valid_file_returns_none(monkeypatch, tmp_path):
    monkeypatch.delenv("SOME_KEY", raising=False)
    keys_file = tmp_path / "api_keys.json"
    keys_file.write_text(json.dumps({"other": "value"}))
    monkeypatch.setattr(api_keys, "_KEYS_FILE", keys_file)

    assert api_keys.resolve_api_key("some", "SOME_KEY") is None
