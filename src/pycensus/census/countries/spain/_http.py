"""Browser-like HTTP helper shared by the Spain loaders that hit ministry sites (some answer 403 to curl's default User-Agent)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import requests

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.5",
}


def download(url: str, dest: Path, timeout: int = 600, force: bool = False) -> Path:
    """Stream ``url`` to ``dest`` (skipped if it exists) with browser headers; raises ``requests.HTTPError`` on 4xx/5xx.

    Args:
        url: File URL.
        dest: Local file.
        timeout: Timeout in seconds.
        force: Download again.

    Returns:
        The local file.
    """
    dest = Path(dest)
    if dest.exists() and not force:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, headers=BROWSER_HEADERS, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    tmp.replace(dest)
    return dest
