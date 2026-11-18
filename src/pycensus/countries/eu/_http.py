"""Cached, resumable downloads for the EU sources (GISCO files are 30-600 MB)."""

from __future__ import annotations

import time
from pathlib import Path

import requests


def download(url: str, folder: Path, name: str | None = None, tries: int = 6, timeout: int = 300) -> Path:
    """Download ``url`` into ``folder`` once; later calls return the cached file.

    Interrupted transfers are resumed with an HTTP ``Range`` request (GISCO serves large files that time out on slow
    links). The file is written under a ``.part`` name and renamed only when its size matches ``Content-Length``.

    Args:
        url: File URL.
        folder: Cache folder (created if missing).
        name: Local file name (default: the last URL segment).
        tries: Attempts before giving up.
        timeout: Seconds per attempt.

    Returns:
        Path of the complete local file.

    Raises:
        RuntimeError: if the file could not be completed, or the server answered with an HTML page instead of data.
    """
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / (name or url.rsplit("/", 1)[-1])
    if out.exists():
        return out
    part = out.with_name(out.name + ".part")
    total = None
    for attempt in range(tries):
        have = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={have}-"} if have else {}
        try:
            with requests.get(url, headers=headers, stream=True, timeout=timeout) as r:
                if r.status_code == 416:   # already complete
                    break
                r.raise_for_status()
                if "text/html" in r.headers.get("Content-Type", ""):
                    raise RuntimeError(f"{url} returned an HTML page, not data")
                if r.status_code == 206:
                    total = have + int(r.headers.get("Content-Length", 0))
                else:
                    have = 0
                    total = int(r.headers.get("Content-Length", 0)) or None
                with open(part, "ab" if have else "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            if total is None or part.stat().st_size >= total:
                break
        except requests.RequestException:
            time.sleep(5 * (attempt + 1))
    if not part.exists() or (total is not None and part.stat().st_size < total):
        raise RuntimeError(f"could not download {url} after {tries} attempts")
    part.rename(out)
    return out
