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
import subprocess
import tempfile
from pathlib import Path

from modules.html_utils import inline_and_extract_body
from modules.libreoffice import find_soffice, profile_dir


def _convert_path_with_libreoffice(soffice: str, docx_path: Path) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        subprocess.run(
            [soffice, "--headless", "--norestore", "--invisible",
             f"-env:UserInstallation=file://{profile_dir()}",
             "--convert-to", "html", "--outdir", str(tmp_path), str(docx_path)],
            check=True, capture_output=True, timeout=120,
        )
        html_path = tmp_path / f"{docx_path.stem}.html"
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
    soffice = find_soffice()
    if soffice:
        with tempfile.TemporaryDirectory() as tmp:
            docx_path = Path(tmp) / "input.docx"
            file_storage.save(docx_path)
            try:
                return _convert_path_with_libreoffice(soffice, docx_path)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                pass  # fall through to mammoth
    return _convert_with_mammoth(file_storage)


def docx_file_to_html(docx_path: Path) -> str:
    """Convert an already-saved .docx file (e.g. the active PDF statement
    template) to an HTML fragment, for previewing it in the wizard."""
    soffice = find_soffice()
    if not soffice:
        raise RuntimeError(
            "LibreOffice is required to preview this template but wasn't "
            "found on this server."
        )
    return _convert_path_with_libreoffice(soffice, docx_path)
