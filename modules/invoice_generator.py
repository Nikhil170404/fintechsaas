"""
Generate a GST-compliant invoice PDF from a client dict.

Expected client fields (beyond the standard ones):
  invoice_no, invoice_date, due_date, gst_no (seller), client_gst,
  items: list of {description, hsn, qty, rate, gst_pct}
"""
import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

BLUE = HexColor("#1E3A5F")
LIGHT = HexColor("#2E86AB")
ACCENT = HexColor("#EAF4FB")
RULE = HexColor("#BDC3C7")
RED = HexColor("#E74C3C")
GREEN = HexColor("#27AE60")
GRAY = HexColor("#7F8C8D")


def _s(name, **kw):
    return ParagraphStyle(name, fontName=kw.pop("font", "Helvetica"),
                          fontSize=kw.pop("size", 9), **kw)


class InvoiceGenerator:
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, client: dict, company: dict) -> Path:
        """
        company = {name, address, gst_no, phone, email, bank_name, account_no, ifsc}
        client  = {name, address, email, client_gst, invoice_no, invoice_date,
                   due_date, items: [{description, hsn, qty, rate, gst_pct}]}
        """
        inv_no = client.get("invoice_no", "INV-001")
        out = self.output_dir / f"invoice_{inv_no}.pdf"
        doc = SimpleDocTemplate(str(out), pagesize=A4,
                                leftMargin=1.5*cm, rightMargin=1.5*cm,
                                topMargin=1.5*cm, bottomMargin=2*cm)
        story = (
            self._header(company, client)
            + self._party_info(company, client)
            + self._items_table(client)
            + self._totals(client)
            + self._bank_footer(company)
        )
        doc.build(story, onFirstPage=self._deco, onLaterPages=self._deco)
        return out

    def _deco(self, canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(LIGHT)
        canvas.setLineWidth(1.5)
        canvas.rect(0.7*cm, 0.7*cm, A4[0]-1.4*cm, A4[1]-1.4*cm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(GRAY)
        canvas.drawCentredString(A4[0]/2, 0.4*cm, f"Page {doc.page}")
        canvas.restoreState()

    def _header(self, company, client):
        inv_no = client.get("invoice_no", "INV-001")
        inv_date = client.get("invoice_date", datetime.date.today().strftime("%d %b %Y"))
        due_date = client.get("due_date", "")

        data = [
            [Paragraph(company.get("name", ""), _s("co", font="Helvetica-Bold", size=16, textColor=BLUE)),
             "", "TAX INVOICE"],
            ["", "", f"Invoice No: {inv_no}"],
            [company.get("address", ""), "", f"Date: {inv_date}"],
            [f'GSTIN: {company.get("gst_no", "")}', "", f'Due: {due_date}'],
        ]
        tbl = Table(data, colWidths=[10*cm, 1*cm, 8.5*cm])
        tbl.setStyle(TableStyle([
            ("FONTNAME", (2, 0), (2, 0), "Helvetica-Bold"),
            ("FONTSIZE", (2, 0), (2, 0), 14),
            ("TEXTCOLOR", (2, 0), (2, 0), BLUE),
            ("ALIGN", (2, 0), (2, -1), "RIGHT"),
            ("FONTSIZE", (2, 1), (2, -1), 9),
            ("FONTSIZE", (0, 1), (0, -1), 8.5),
            ("TEXTCOLOR", (0, 1), (0, -1), GRAY),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("PADDING", (0, 0), (-1, -1), 3),
        ]))
        return [tbl, Spacer(1, 3*mm),
                HRFlowable(width="100%", thickness=2, color=BLUE), Spacer(1, 4*mm)]

    def _party_info(self, company, client):
        data = [
            ["BILL TO", "", "SHIP TO"],
            [Paragraph(f'<b>{client.get("name","")}</b>', _s("n", size=9)), "",
             Paragraph(f'<b>{client.get("name","")}</b>', _s("n", size=9))],
            [client.get("address", ""), "", client.get("address", "")],
            [f'Email: {client.get("email","")}', "",
             f'GSTIN: {client.get("client_gst","")}'],
        ]
        tbl = Table(data, colWidths=[9.5*cm, 0.5*cm, 9.5*cm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), BLUE),
            ("BACKGROUND", (2, 0), (2, 0), LIGHT),
            ("TEXTCOLOR", (0, 0), (0, 0), colors.white),
            ("TEXTCOLOR", (2, 0), (2, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("PADDING", (0, 0), (-1, 0), 6),
            ("FONTSIZE", (0, 1), (-1, -1), 8.5),
            ("BACKGROUND", (0, 1), (0, -1), ACCENT),
            ("BACKGROUND", (2, 1), (2, -1), HexColor("#F0F8FF")),
            ("GRID", (0, 0), (0, -1), 0.5, RULE),
            ("GRID", (2, 0), (2, -1), 0.5, RULE),
            ("PADDING", (0, 1), (-1, -1), 5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        return [tbl, Spacer(1, 5*mm)]

    def _items_table(self, client):
        items = client.get("items", [])
        headers = ["#", "Description", "HSN", "Qty", "Rate (₹)", "GST%", "GST Amt (₹)", "Total (₹)"]
        widths = [0.7*cm, 6*cm, 1.8*cm, 1.5*cm, 2.5*cm, 1.5*cm, 2.5*cm, 3*cm]
        rows = [headers]
        for i, item in enumerate(items, 1):
            qty = float(item.get("qty", 1))
            rate = float(item.get("rate", 0))
            gst = float(item.get("gst_pct", 18)) / 100
            base = qty * rate
            gst_amt = base * gst
            total = base + gst_amt
            rows.append([
                str(i),
                item.get("description", ""),
                item.get("hsn", ""),
                str(qty),
                f"₹{rate:,.2f}",
                f'{item.get("gst_pct", 18)}%',
                f"₹{gst_amt:,.2f}",
                f"₹{total:,.2f}",
            ])
        tbl = Table(rows, colWidths=widths, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BLUE),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ACCENT]),
            ("GRID", (0, 0), (-1, -1), 0.5, RULE),
            ("PADDING", (0, 0), (-1, -1), 5),
        ]))
        return [Paragraph("ITEMS", _s("sh", font="Helvetica-Bold", size=9, textColor=BLUE)),
                Spacer(1, 2*mm), tbl, Spacer(1, 4*mm)]

    def _totals(self, client):
        items = client.get("items", [])
        subtotal = sum(float(i.get("qty", 1)) * float(i.get("rate", 0)) for i in items)
        gst_total = sum(
            float(i.get("qty", 1)) * float(i.get("rate", 0)) * float(i.get("gst_pct", 18)) / 100
            for i in items
        )
        grand = subtotal + gst_total

        data = [
            ["Subtotal",   f"₹{subtotal:,.2f}"],
            ["Total GST",  f"₹{gst_total:,.2f}"],
            ["GRAND TOTAL", f"₹{grand:,.2f}"],
        ]
        tbl = Table(data, colWidths=[14.5*cm, 5*cm])
        tbl.setStyle(TableStyle([
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, -1), (-1, -1), 10),
            ("BACKGROUND", (0, -1), (-1, -1), BLUE),
            ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
            ("FONTSIZE", (0, 0), (-1, -2), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, RULE),
            ("PADDING", (0, 0), (-1, -1), 6),
        ]))
        return [tbl, Spacer(1, 5*mm)]

    def _bank_footer(self, company):
        bank = (
            f'Bank: {company.get("bank_name","")}  |  '
            f'A/C: {company.get("account_no","")}  |  '
            f'IFSC: {company.get("ifsc","")}'
        )
        disclaimer = "This is a computer-generated invoice. Thank you for your business."
        return [
            HRFlowable(width="100%", thickness=1, color=BLUE),
            Spacer(1, 2*mm),
            Paragraph(bank, _s("bk", size=8, textColor=GRAY, alignment=TA_CENTER)),
            Paragraph(disclaimer, _s("dis", size=7.5, textColor=GRAY, alignment=TA_CENTER)),
        ]
