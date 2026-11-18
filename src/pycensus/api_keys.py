# -*- coding: utf-8 -*-
"""Resolve API keys without hardcoding them.

One standard place for every key of every package of the project: ``~/.config/ptlos/api_keys.json``, a JSON object
``{"<key name>": "<key>"}`` outside every repository (so it can never be committed). Order: explicit argument, the source's
environment variable, then the keys file: ``API_KEYS_FILE`` (or ``PYCENSUS_API_KEYS_FILE``) if set, else
``~/.config/ptlos/api_keys.json``; older locations (``api_keys.json`` in the pyCensus folder, the working directory or its
parents, ``~/.pycensus/api_keys.json``) are still read. Key names: ``api_keys.example.json``.
"""

from pathlib import Path
from typing import Any, Dict, Optional

from geohierarchy import api_keys as _keys
from geohierarchy.api_keys import SHARED_FILE_ENV_VAR, STANDARD_PATH  # noqa: F401  (the lookup itself lives in geohierarchy)

CONFIG_FILE_ENV_VAR = "PYCENSUS_API_KEYS_FILE"
DEFAULT_CONFIG_PATH = Path.home() / ".pycensus" / "api_keys.json"


def _candidate_paths() -> list:
    """Keys files, highest priority first: geohierarchy's standard order, then pyCensus' older locations."""
    return _keys.candidate_paths(
        env_vars=[CONFIG_FILE_ENV_VAR],
        files=[Path(__file__).resolve().parents[2] / "api_keys.json", *(d / "api_keys.json" for d in (Path.cwd(), *Path.cwd().parents)), DEFAULT_CONFIG_PATH],
        standard_path=STANDARD_PATH,
    )


def _load_file() -> Dict[str, Any]:
    """Every readable keys file merged (see :func:`geohierarchy.api_keys.load_keys`)."""
    return _keys.load_keys(_candidate_paths())


def resolve_api_key(name: str, env_var: Optional[str] = None, explicit: Optional[str] = None) -> Optional[str]:
    """Return the key for ``name`` or None if none is configured.

    Args:
        name: Key name in ``api_keys.json``.
        env_var: Environment variable checked first.
        explicit: A key passed directly (wins).

    Returns:
        The key, or None.
    """
    return _keys.resolve_api_key(name, env_var, explicit, paths=_candidate_paths())
