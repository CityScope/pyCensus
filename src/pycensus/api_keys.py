# -*- coding: utf-8 -*-
"""Resolve API keys without hardcoding them.

One standard place for every key of every package of the project: ``~/.config/ptlos/api_keys.json``, a JSON object
``{"<key name>": "<key>"}`` outside every repository (so it can never be committed). Order: explicit argument, the source's
environment variable, then the keys file: ``API_KEYS_FILE`` (or ``PYCENSUS_API_KEYS_FILE``) if set, else
``~/.config/ptlos/api_keys.json``; older locations (``api_keys.json`` in the pyCensus folder, the working directory or its
parents, ``~/.pycensus/api_keys.json``) are still read. Key names: ``api_keys.example.json``.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

SHARED_FILE_ENV_VAR = "API_KEYS_FILE"
STANDARD_PATH = Path.home() / ".config" / "ptlos" / "api_keys.json"


def _load_keys(paths) -> Dict[str, Any]:
    """Every readable keys file merged; a file earlier in ``paths`` wins (unreadable files are skipped with a warning)."""
    merged: Dict[str, Any] = {}
    for path in reversed([Path(p) for p in paths]):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                merged.update(data)
        except (OSError, ValueError) as exc:
            logger.warning("Ignoring unreadable API keys file %s: %s", path, exc)
    return merged


def save_api_key(name: str, key: str, path: Optional[Path] = None) -> Path:
    """Store ``key`` under ``name`` in the standard keys file (``~/.config/ptlos/api_keys.json``, permissions 600), keeping the other keys.

    Args:
        name: Key name.
        key: The key.
        path: Keys file; default ``STANDARD_PATH``.

    Returns:
        The keys file.
    """
    path = Path(path) if path else STANDARD_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = _load_keys([path])
    keys[name] = key
    path.write_text(json.dumps(keys, indent=1))
    path.chmod(0o600)
    return path

CONFIG_FILE_ENV_VAR = "PYCENSUS_API_KEYS_FILE"
DEFAULT_CONFIG_PATH = Path.home() / ".pycensus" / "api_keys.json"


def _candidate_paths() -> list:
    """Keys files, highest priority first: ``API_KEYS_FILE``, ``PYCENSUS_API_KEYS_FILE``, the standard file, then pyCensus' older
    locations (the pyCensus folder, the working directory and its parents, ``~/.pycensus/api_keys.json``)."""
    paths = [Path(v) for v in (os.getenv(SHARED_FILE_ENV_VAR), os.getenv(CONFIG_FILE_ENV_VAR)) if v]
    return paths + [STANDARD_PATH, Path(__file__).resolve().parents[2] / "api_keys.json",
                    *(d / "api_keys.json" for d in (Path.cwd(), *Path.cwd().parents)), DEFAULT_CONFIG_PATH]


def _load_file() -> Dict[str, Any]:
    """Every readable keys file merged, earlier files winning."""
    return _load_keys(_candidate_paths())


def resolve_api_key(name: str, env_var: Optional[str] = None, explicit: Optional[str] = None) -> Optional[str]:
    """Return the key for ``name`` or None if none is configured.

    Args:
        name: Key name in ``api_keys.json``.
        env_var: Environment variable checked first.
        explicit: A key passed directly (wins).

    Returns:
        The key, or None.
    """
    if explicit:
        return explicit
    if env_var and os.getenv(env_var):
        return os.getenv(env_var)
    value = _load_file().get(name)
    return str(value) if value else None
