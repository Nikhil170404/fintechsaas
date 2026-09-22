from pathlib import Path

from .pdf_generator import PDFGenerator
from .word_filler import WordFiller


class StatementBuilder:
    """
    Generates client statements in two modes:
      - 'auto'     → ReportLab PDF (no template needed)
      - 'template' → fill a Word template, convert to PDF via LibreOffice
    """

    def __init__(self, output_dir: Path, brand_color: str = "", logo_path: Path | None = None):
        self.output_dir = output_dir
        self._pdf_gen = PDFGenerator(output_dir, brand_color=brand_color, logo_path=logo_path)

    def build(
        self,
        client: dict,
        company_name: str,
        statement_period: str,
        mode: str = "auto",
        word_template: Path | None = None,
    ) -> Path:
        if mode == "template" and word_template and word_template.exists():
            filler = WordFiller(word_template, self.output_dir)
            return filler.fill_and_export(client, company_name, statement_period)
        return self._pdf_gen.generate(client, company_name, statement_period)
