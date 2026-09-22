"""
Fill a Word (.docx) template with client data and produce a PDF via LibreOffice.

Template placeholders (anywhere in text or tables):
  {{COMPANY_NAME}}, {{CLIENT_NAME}}, {{ACCOUNT_NO}}, {{EMAIL}}, {{PHONE}},
  {{ADDRESS}}, {{ACCOUNT_TYPE}}, {{STATEMENT_PERIOD}}, {{GENERATED_DATE}},
  {{OPENING_BALANCE}}, {{CLOSING_BALANCE}}, {{TOTAL_DEBIT}}, {{TOTAL_CREDIT}}

Transaction table:
  Put a table whose FIRST ROW has exactly these headers (any order):
    Date | Description | Reference | Debit | Credit | Balance
  The filler will detect it and append one data row per transaction.
"""

import datetime
import subprocess
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor


class WordFiller:
    TXN_HEADERS = {"date", "description", "reference", "debit", "credit", "balance"}

    def __init__(self, template_path: Path, output_dir: Path):
        self.template_path = template_path
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def fill_and_export(
        self, client: dict, company_name: str, statement_period: str
    ) -> Path:
        txns = client.get("transactions", [])
        total_debit = sum(t["debit"] for t in txns)
        total_credit = sum(t["credit"] for t in txns)
        opening = client.get("opening_balance", 0)
        closing = txns[-1]["balance"] if txns else opening

        replacements = {
            "{{COMPANY_NAME}}": company_name,
            "{{CLIENT_NAME}}": client.get("name", ""),
            "{{ACCOUNT_NO}}": client.get("account_no", ""),
            "{{EMAIL}}": client.get("email", ""),
            "{{PHONE}}": client.get("phone", ""),
            "{{ADDRESS}}": client.get("address", ""),
            "{{ACCOUNT_TYPE}}": client.get("account_type", ""),
            "{{STATEMENT_PERIOD}}": statement_period,
            "{{GENERATED_DATE}}": datetime.date.today().strftime("%d %B %Y"),
            "{{OPENING_BALANCE}}": f"₹{opening:,.2f}",
            "{{CLOSING_BALANCE}}": f"₹{closing:,.2f}",
            "{{TOTAL_DEBIT}}": f"₹{total_debit:,.2f}",
            "{{TOTAL_CREDIT}}": f"₹{total_credit:,.2f}",
        }

        doc = Document(self.template_path)
        self._replace_paragraphs(doc, replacements)
        self._fill_txn_table(doc, txns)

        acct = client["account_no"]
        docx_path = self.output_dir / f"statement_{acct}.docx"
        doc.save(docx_path)
        return self._to_pdf(docx_path)

    # ── helpers ────────────────────────────────────────────────────────────────

    def _replace_paragraphs(self, doc: Document, replacements: dict):
        for para in self._all_paragraphs(doc):
            for key, val in replacements.items():
                if key in para.text:
                    _replace_in_para(para, key, val)

    def _fill_txn_table(self, doc: Document, txns: list[dict]):
        for table in doc.tables:
            header_row = table.rows[0]
            headers = [c.text.strip().lower() for c in header_row.cells]
            if not self.TXN_HEADERS.issubset(set(headers)):
                continue
            # Map column index by header name
            col = {h: i for i, h in enumerate(headers)}
            for t in txns:
                new_row = _clone_row(table, table.rows[-1])
                _set_cell(new_row, col.get("date", 0), t.get("date", ""))
                _set_cell(new_row, col.get("description", 1), t.get("description", ""))
                _set_cell(new_row, col.get("reference", 2), t.get("reference", ""))
                _set_cell(new_row, col.get("debit", 3), f'₹{t["debit"]:,.2f}' if t["debit"] > 0 else "—")
                _set_cell(new_row, col.get("credit", 4), f'₹{t["credit"]:,.2f}' if t["credit"] > 0 else "—")
                _set_cell(new_row, col.get("balance", 5), f'₹{t["balance"]:,.2f}')
            break  # only fill the first matching table

    def _all_paragraphs(self, doc: Document):
        yield from doc.paragraphs
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    yield from cell.paragraphs

    def _to_pdf(self, docx_path: Path) -> Path:
        subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf",
             "--outdir", str(docx_path.parent), str(docx_path)],
            check=True, capture_output=True,
        )
        return docx_path.with_suffix(".pdf")


# ── low-level docx helpers ──────────────────────────────────────────────────────

def _replace_in_para(para, key: str, value: str):
    """Replace key with value inside a paragraph, preserving run formatting."""
    full = para.text
    if key not in full:
        return
    # Rebuild: clear all runs, write value into first run
    new_text = full.replace(key, value)
    for i, run in enumerate(para.runs):
        run.text = new_text if i == 0 else ""


def _clone_row(table, source_row):
    import copy
    new_tr = copy.deepcopy(source_row._tr)
    table._tbl.append(new_tr)
    return table.rows[-1]


def _set_cell(row, col_idx: int, text: str):
    if col_idx < len(row.cells):
        cell = row.cells[col_idx]
        for para in cell.paragraphs:
            for run in para.runs:
                run.text = ""
        if cell.paragraphs:
            if cell.paragraphs[0].runs:
                cell.paragraphs[0].runs[0].text = text
            else:
                cell.paragraphs[0].add_run(text)
        else:
            cell.add_paragraph(text)
