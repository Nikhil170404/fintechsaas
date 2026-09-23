"""High-fidelity .docx → HTML conversion for the Email Template and
Template Designer "Import from Word" features.

mammoth (the previous converter) deliberately produces simplified, semantic
HTML and drops nearly all direct formatting (font colors, custom fonts,
alignment, table borders, blank-line spacing) by design — it's built for
"clean" HTML, not a faithful copy of the Word document.

This module instead shells out to LibreOffice headless, which actually
renders the document the way Word would and preserves that formatting.
If LibreOffice isn't installed on the host, it falls back to mammoth so
the feature still works, just with lower fidelity.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

from modules.html_utils import inline_and_extract_body

_KNOWN_SOFFICE_PATHS = (
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",  # macOS
    "/usr/bin/soffice",                                       # Debian/Ubuntu
    "/usr/lib/libreoffice/program/soffice",                   # Debian/Ubuntu (alt)
)


def _find_soffice() -> str | None:
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return found
    for p in _KNOWN_SOFFICE_PATHS:
        if Path(p).exists():
            return p
    return None


def _convert_with_libreoffice(soffice: str, file_storage) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        docx_path = tmp_path / "input.docx"
        file_storage.save(docx_path)
        subprocess.run(
            [soffice, "--headless", "--norestore", "--invisible",
             f"-env:UserInstallation=file://{tmp_path}/lo_profile",
             "--convert-to", "html", "--outdir", str(tmp_path), str(docx_path)],
            check=True, capture_output=True, timeout=60,
        )
        html_path = tmp_path / "input.html"
        raw_html = html_path.read_text(encoding="utf-8", errors="replace")
    return inline_and_extract_body(raw_html)


def _convert_with_mammoth(file_storage) -> str:
    import mammoth
    file_storage.stream.seek(0)
    result = mammoth.convert_to_html(file_storage)
    return result.value


def docx_to_html(file_storage) -> str:
    """Convert an uploaded .docx (a Flask FileStorage) to an HTML fragment
    suitable for the Quill editor / template designer body."""
    soffice = _find_soffice()
    if soffice:
        try:
            return _convert_with_libreoffice(soffice, file_storage)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            pass  # fall through to mammoth
    return _convert_with_mammoth(file_storage)
