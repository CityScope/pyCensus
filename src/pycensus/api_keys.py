# -*- coding: utf-8 -*-
"""Resolve API keys without hardcoding them.

Order: explicit argument, environment variable, then a gitignored
``api_keys.json`` (``PYCENSUS_API_KEYS_FILE``, else the repo root of pyCensus,
the CWD or its parents, else ``~/.pycensus/api_keys.json``).
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

CONFIG_FILE_ENV_VAR = "PYCENSUS_API_KEYS_FILE"
DEFAULT_CONFIG_PATH = Path.home() / ".pycensus" / "api_keys.json"


def _candidate_paths() -> list:
    paths = []
    env_path = os.getenv(CONFIG_FILE_ENV_VAR)
    if env_path:
        paths.append(Path(env_path))
    paths.append(Path(__file__).resolve().parents[2] / "api_keys.json")
    paths.extend(d / "api_keys.json" for d in (Path.cwd(), *Path.cwd().parents))
    paths.append(DEFAULT_CONFIG_PATH)
    return paths


def _load_file() -> Dict[str, Any]:
    for path in _candidate_paths():
        try:
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except (OSError, ValueError) as exc:
            logger.warning("Ignoring unreadable API keys file %s: %s", path, exc)
    return {}


def resolve_api_key(
    name: str, env_var: Optional[str] = None, explicit: Optional[str] = None
) -> Optional[str]:
    """Return the key for ``name`` or None if none is configured."""
    if explicit:
        return explicit
    if env_var and os.getenv(env_var):
        return os.getenv(env_var)
    value = _load_file().get(name)
    return str(value) if value else None
