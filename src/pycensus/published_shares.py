"""Mode shares that exist only as figures in a published report (no table, no finer geography): each source module lists its figures and
the document they come from; :func:`fetch` downloads the document once into ``<cache>/published_shares/`` and checks that every figure
is printed in its text (pdftotext, else pypdf; HTML pages as text), so a changed or moved publication fails loudly instead of silently.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Dict, Optional


def _cache(cache_dir: Optional[str]) -> Path:
    from pycensus.cache import default_cache_dir

    d = (Path(cache_dir) if cache_dir else Path(default_cache_dir())) / "published_shares"
    d.mkdir(parents=True, exist_ok=True)
    return d


def document_text(url: str, cache_dir: Optional[str] = None) -> str:
    """Text of a published document (PDF or HTML), downloaded once into the cache.

    Args:
        url: Document URL.
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        The text.
    """
    d = _cache(cache_dir)
    f = d / (hashlib.sha1(url.encode()).hexdigest()[:16] + (".pdf" if url.lower().split("?")[0].endswith(".pdf") or "/blob/" in url else ".html"))
    if not f.is_file() or f.stat().st_size < 1000:
        import requests

        r = requests.get(url, timeout=180, headers={"User-Agent": "pycensus"})
        r.raise_for_status()
        f.write_bytes(r.content)
    raw = f.read_bytes()
    if raw[:4] == b"%PDF":
        try:
            return subprocess.run(["pdftotext", "-layout", str(f), "-"], check=True, capture_output=True, text=True).stdout
        except (OSError, subprocess.CalledProcessError):
            from pypdf import PdfReader

            return "\n".join(p.extract_text() or "" for p in PdfReader(str(f)).pages)
    return re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", raw.decode("utf-8", errors="ignore")))   # tags inside the sentences (bold figures)


def fetch(figures: Dict[str, dict], cache_dir: Optional[str] = None, verify: bool = True) -> Dict[str, dict]:
    """``figures``: {key: {"transit_share": 0-1, "url": ..., "pattern": regex that must occur in the document, ...}} -> the same, checked.

    Args:
        figures: Figures with their source and check pattern.
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        verify: Check each figure in its document.

    Returns:
        The figures.

    Raises:
        RuntimeError: If a figure's pattern is not found in its document.
    """
    out = {}
    for k, f in figures.items():
        if verify:
            txt = document_text(f["url"], cache_dir)
            if not re.search(f["pattern"], txt, flags=re.S):
                raise RuntimeError(f"{k}: figure pattern {f['pattern']!r} not found in {f['url']} -- the publication changed")
        out[k] = dict(f)
    return out
