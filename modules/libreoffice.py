"""Locate a usable LibreOffice headless binary.

Used by both the .docx -> HTML import (modules/docx_import.py) and the
Word-template -> PDF statement generator (modules/word_filler.py). Neither
can assume `soffice` is on PATH — it commonly isn't on macOS dev machines
even when LibreOffice.app is installed, and the exact binary name/location
varies by OS.
"""
import os
import shutil
import tempfile
from pathlib import Path

_KNOWN_SOFFICE_PATHS = (
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",  # macOS
    "/usr/bin/soffice",                                       # Debian/Ubuntu
    "/usr/lib/libreoffice/program/soffice",                   # Debian/Ubuntu (alt)
)


def find_soffice() -> str | None:
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return found
    for p in _KNOWN_SOFFICE_PATHS:
        if Path(p).exists():
            return p
    return None


def profile_dir() -> Path:
    """A persistent LibreOffice user profile, one per worker process.

    LibreOffice's first launch on a fresh profile is slow (builds its font
    cache, registers filters, etc.) — often 30-60+ seconds. Reusing the same
    profile across conversions in this process pays that cost once instead
    of on every single statement. Scoped per-process (not shared globally)
    so concurrent gunicorn workers never fight over the same profile lock.
    """
    path = Path(tempfile.gettempdir()) / "fintech_saas_lo_profile" / str(os.getpid())
    path.mkdir(parents=True, exist_ok=True)
    return path
