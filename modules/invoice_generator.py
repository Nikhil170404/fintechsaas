"""
GST-compliant Tax Invoice PDF generator (India).

company dict keys:
  name, address, state, gst_no, phone, email,
  bank_name, account_no, ifsc, upi (optional)

client dict keys:
  name, address, state, email, phone, client_gst,
  invoice_no, invoice_date, due_date, po_no (optional),
  supply_type: 'intra' (CGST+SGST) | 'inter' (IGST)  [default: intra]
  place_of_supply (optional, shown on invoice)
  items: [{description, hsn, unit, qty, rate, gst_pct}]
  terms: [str, ...]   (optional, overrides defaults)
"""
import re
import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    HRFlowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

_DEFAULT_BRAND = "#1E3A5F"

_DEFAULT_TERMS = [
    "Payment is due within 30 days of invoice date.",
    "Goods once sold will not be taken back.",
    "Interest @18% p.a. will be charged on overdue amounts.",
    "Subject to local jurisdiction only.",
    "E. & O.E.",
]


def _lighten(hex_color: str, f: float = 0.40) -> HexColor:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return HexColor(f"#{int(r+(255-r)*f):02x}{int(g+(255-g)*f):02x}{int(b+(255-b)*f):02x}")


def _s(name, **kw):
    return ParagraphStyle(name, fontName=kw.pop("font", "Helvetica"),
                          fontSize=kw.pop("size", 9), **kw)


# ── Amount in words (Indian numbering) ────────────────────────────────────────
_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
         "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
         "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _two(n: int) -> str:
    return _ONES[n] if n < 20 else _TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else "")


def _three(n: int) -> str:
    if n >= 100:
        return _ONES[n // 100] + " Hundred" + (" " + _two(n % 100) if n % 100 else "")
    return _two(n)


def amount_in_words(amount: float) -> str:
    rupees = int(amount)
    paise = round((amount - rupees) * 100)
    if rupees == 0 and paise == 0:
        return "Zero Rupees Only"
    parts = []
    for divisor, label in [(10_000_000, "Crore"), (100_000, "Lakh"), (1_000, "Thousand")]:
        q = rupees // divisor
        rupees %= divisor
        if q:
            parts.append(_three(q) + " " + label)
    if rupees:
        parts.append(_three(rupees))
    result = "Rupees " + " ".join(parts) if parts else "Zero Rupees"
    if paise:
        result += f" and {_two(paise)} Paise"
    return result + " Only"


# ── Generator class ────────────────────────────────────────────────────────────

class InvoiceGenerator:
    def __init__(self, output_dir: Path,
                 brand_color: str = "",
                 logo_path: Path | None = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        bc = brand_color if re.match(r"^#[0-9a-fA-F]{6}$", brand_color or "") else _DEFAULT_BRAND
        self.brand_blue  = HexColor(bc)
        self.brand_light = _lighten(bc, 0.40)
        self.accent_bg   = _lighten(bc, 0.90)
        self.logo_path   = logo_path if logo_path and Path(logo_path).exists() else None
        self.rule        = HexColor("#BDC3C7")
        self.gray        = HexColor("#7F8C8D")
        self.red         = HexColor("#E74C3C")
        self.green       = HexColor("#27AE60")

    def generate(self, client: dict, company: dict) -> Path:
        inv_no = client.get("invoice_no", "INV-001")
        out = self.output_dir / f"invoice_{inv_no}.pdf"
        supply = client.get("supply_type", "intra").lower()

        doc = SimpleDocTemplate(
            str(out), pagesize=A4,
            leftMargin=1.5*cm, rightMargin=1.5*cm,
            topMargin=1.5*cm, bottomMargin=2*cm,
        )
        story = (
            self._header(company, client)
            + self._party_box(company, client)
            + self._items_table(client, supply)
            + self._gst_summary(client, supply)
            + self._totals(client, supply)
            + self._footer_bank_terms(company, client)
        )
        doc.build(story, onFirstPage=self._deco, onLaterPages=self._deco)
        return out

    # ── Page border + page number ──────────────────────────────────────────────
    def _deco(self, canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(self.brand_light)
        canvas.setLineWidth(1.5)
        canvas.rect(0.7*cm, 0.7*cm, A4[0]-1.4*cm, A4[1]-1.4*cm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(self.gray)
        canvas.drawCentredString(A4[0]/2, 0.4*cm, f"Page {doc.page}")
        canvas.restoreState()

    # ── Header: logo + company + "TAX INVOICE" badge + meta ──────────────────
    def _header(self, company, client):
        inv_no   = client.get("invoice_no", "INV-001")
        inv_date = client.get("invoice_date", datetime.date.today().strftime("%d %b %Y"))
        due_date = client.get("due_date", "")
        po_no    = client.get("po_no", "")
        supply   = client.get("supply_type", "intra").upper()
        pos      = client.get("place_of_supply", "")

        items = []

        # logo
        if self.logo_path:
            try:
                img = Image(str(self.logo_path), width=5*cm, height=1.5*cm)
                img.hAlign = "LEFT"
                items.append(img)
                items.append(Spacer(1, 1*mm))
            except Exception:
                pass

        co_name_s = _s("cn", font="Helvetica-Bold", size=17, textColor=self.brand_blue)
        co_sub_s  = _s("cs", size=8.5, textColor=self.gray)

        meta_rows = [
            ["Invoice No :", inv_no],
            ["Date :", inv_date],
        ]
        if due_date:
            meta_rows.append(["Due Date :", due_date])
        if po_no:
            meta_rows.append(["P.O. No :", po_no])
        if pos:
            meta_rows.append(["Place of Supply :", pos])
        meta_rows.append(["Supply Type :", supply + "-STATE"])

        co_cell = [
            Paragraph(company.get("name", ""), co_name_s),
            Paragraph(company.get("address", ""), co_sub_s),
            Paragraph(f'GSTIN: <b>{company.get("gst_no", "")}</b>  |  {company.get("phone", "")}', co_sub_s),
            Paragraph(company.get("email", ""), co_sub_s),
        ]

        badge = Paragraph('<font color="white"><b>TAX INVOICE</b></font>',
                          _s("badge", font="Helvetica-Bold", size=14, alignment=TA_RIGHT))

        meta_tbl = Table(meta_rows, colWidths=[3.2*cm, 5*cm])
        meta_tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("TEXTCOLOR", (0, 0), (-1, -1), self.gray),
            ("TEXTCOLOR", (1, 0), (1, 0), self.brand_blue),
            ("FONTNAME", (1, 0), (1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (1, 0), (1, 0), 9),
            ("PADDING", (0, 0), (-1, -1), 2),
        ]))

        top = Table([[co_cell, [badge, Spacer(1, 4*mm), meta_tbl]]],
                    colWidths=[10*cm, 9.5*cm])
        top.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (1, 0), (1, 0), self.brand_blue),
            ("PADDING", (0, 0), (-1, -1), 6),
            ("ROUNDEDCORNERS", [4]),
        ]))
        items.append(top)
        items.append(Spacer(1, 3*mm))
        items.append(HRFlowable(width="100%", thickness=2, color=self.brand_blue))
        items.append(Spacer(1, 4*mm))
        return items

    # ── Bill to / Ship to box ─────────────────────────────────────────────────
    def _party_box(self, company, client):
        hdr_s = _s("ph", font="Helvetica-Bold", size=8.5, textColor=colors.white)
        val_s = _s("pv", size=8.5)

        def cell(label, *lines):
            return [Paragraph(label, hdr_s)] + [Paragraph(l, val_s) for l in lines if l]

        bill = cell("BILL TO",
                    f'<b>{client.get("name","")}</b>',
                    client.get("address",""),
                    f'GSTIN: {client.get("client_gst","")}' if client.get("client_gst") else "",
                    f'State: {client.get("state","")}',
                    f'Ph: {client.get("phone","")}',
                    client.get("email",""))

        seller = cell("SELLER",
                      f'<b>{company.get("name","")}</b>',
                      company.get("address",""),
                      f'GSTIN: {company.get("gst_no","")}',
                      f'State: {company.get("state","")}')

        tbl = Table([[bill, Spacer(0.3*cm, 1), seller]],
                    colWidths=[9.5*cm, 0.5*cm, 9.5*cm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), self.brand_blue),
            ("BACKGROUND", (2, 0), (2, 0), self.brand_light),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("PADDING", (0, 0), (0, 0), 8),
            ("PADDING", (2, 0), (2, 0), 8),
            ("ROUNDEDCORNERS", [4]),
        ]))
        return [tbl, Spacer(1, 5*mm)]

    # ── Items table ───────────────────────────────────────────────────────────
    def _items_table(self, client, supply):
        items = client.get("items", [])
        headers = ["#", "Description / Service", "HSN/SAC", "Unit", "Qty",
                   "Rate (₹)", "Taxable Value (₹)", "GST%", "Total (₹)"]
        widths = [0.6*cm, 4.8*cm, 1.5*cm, 1.2*cm, 1.0*cm, 2.2*cm, 2.8*cm, 1.3*cm, 2.6*cm]

        rows = [headers]
        for i, item in enumerate(items, 1):
            qty   = float(item.get("qty", 1))
            rate  = float(item.get("rate", 0))
            gst   = float(item.get("gst_pct", 18))
            base  = qty * rate
            total = base * (1 + gst / 100)
            rows.append([
                str(i),
                item.get("description", ""),
                item.get("hsn", ""),
                item.get("unit", "Nos"),
                f"{qty:g}",
                f"₹{rate:,.2f}",
                f"₹{base:,.2f}",
                f"{gst:g}%",
                f"₹{total:,.2f}",
            ])
        if not items:
            rows.append(["", "No items", "", "", "", "", "", "", ""])

        tbl = Table(rows, colWidths=widths, repeatRows=1)
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), self.brand_blue),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (4, 1), (-1, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, self.accent_bg]),
            ("GRID", (0, 0), (-1, -1), 0.5, self.rule),
            ("PADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]
        tbl.setStyle(TableStyle(style))
        return [
            Paragraph("ITEMS / SERVICES",
                      _s("sh", font="Helvetica-Bold", size=9, textColor=self.brand_blue)),
            Spacer(1, 2*mm), tbl, Spacer(1, 3*mm),
        ]

    # ── GST breakdown by rate ─────────────────────────────────────────────────
    def _gst_summary(self, client, supply):
        items = client.get("items", [])
        # Group by gst_pct
        buckets: dict[float, dict] = {}
        for item in items:
            pct  = float(item.get("gst_pct", 18))
            qty  = float(item.get("qty", 1))
            rate = float(item.get("rate", 0))
            base = qty * rate
            if pct not in buckets:
                buckets[pct] = {"taxable": 0.0, "tax": 0.0}
            buckets[pct]["taxable"] += base
            buckets[pct]["tax"] += base * pct / 100

        if not buckets:
            return []

        intra = supply == "intra"
        if intra:
            headers = ["GST Rate", "Taxable Amount (₹)",
                       "CGST%", "CGST Amount (₹)",
                       "SGST%", "SGST Amount (₹)",
                       "Total GST (₹)"]
            widths = [2.2*cm, 3.6*cm, 1.4*cm, 3.2*cm, 1.4*cm, 3.2*cm, 2.5*cm]
        else:
            headers = ["GST Rate", "Taxable Amount (₹)",
                       "IGST%", "IGST Amount (₹)", "Total GST (₹)"]
            widths = [2.5*cm, 4.5*cm, 2.0*cm, 4.5*cm, 4.0*cm]

        rows = [headers]
        for pct in sorted(buckets):
            b = buckets[pct]
            taxable = b["taxable"]
            tax     = b["tax"]
            if intra:
                half = tax / 2
                rows.append([
                    f"{pct:g}%",
                    f"₹{taxable:,.2f}",
                    f"{pct/2:g}%", f"₹{half:,.2f}",
                    f"{pct/2:g}%", f"₹{half:,.2f}",
                    f"₹{tax:,.2f}",
                ])
            else:
                rows.append([
                    f"{pct:g}%",
                    f"₹{taxable:,.2f}",
                    f"{pct:g}%", f"₹{tax:,.2f}",
                    f"₹{tax:,.2f}",
                ])

        tbl = Table(rows, colWidths=widths, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), self.brand_light),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [self.accent_bg, colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.5, self.rule),
            ("PADDING", (0, 0), (-1, -1), 4),
        ]))
        return [
            Paragraph("GST SUMMARY",
                      _s("gs", font="Helvetica-Bold", size=9, textColor=self.brand_blue)),
            Spacer(1, 2*mm), tbl, Spacer(1, 3*mm),
        ]

    # ── Totals + amount in words ───────────────────────────────────────────────
    def _totals(self, client, supply):
        items = client.get("items", [])
        subtotal  = sum(float(i.get("qty", 1)) * float(i.get("rate", 0)) for i in items)
        total_tax = sum(
            float(i.get("qty", 1)) * float(i.get("rate", 0)) * float(i.get("gst_pct", 18)) / 100
            for i in items
        )
        grand = subtotal + total_tax

        right_s = _s("r", alignment=TA_RIGHT)
        bold_r  = _s("rb", font="Helvetica-Bold", alignment=TA_RIGHT)
        label_s = _s("l", font="Helvetica-Bold", size=8.5, textColor=self.gray)
        grand_s = _s("g", font="Helvetica-Bold", size=10)
        grand_v = _s("gv", font="Helvetica-Bold", size=10, alignment=TA_RIGHT)

        W = [12.5*cm, 3.0*cm, 4.0*cm]

        if supply == "intra":
            rows = [
                ["", Paragraph("Subtotal", label_s), Paragraph(f"₹{subtotal:,.2f}", right_s)],
                ["", Paragraph("CGST", label_s), Paragraph(f"₹{total_tax/2:,.2f}", right_s)],
                ["", Paragraph("SGST", label_s), Paragraph(f"₹{total_tax/2:,.2f}", right_s)],
            ]
        else:
            rows = [
                ["", Paragraph("Subtotal", label_s), Paragraph(f"₹{subtotal:,.2f}", right_s)],
                ["", Paragraph("IGST", label_s), Paragraph(f"₹{total_tax:,.2f}", right_s)],
            ]

        rows += [
            ["", HRFlowable(width="100%", thickness=1, color=self.rule), ""],
            ["", Paragraph("GRAND TOTAL", grand_s), Paragraph(f"₹{grand:,.2f}", grand_v)],
            [Paragraph(f'<b>Amount in Words:</b> {amount_in_words(grand)}',
                       _s("aw", size=8.5, textColor=self.brand_blue)), "", ""],
        ]

        tbl = Table(rows, colWidths=W)
        tbl.setStyle(TableStyle([
            ("ALIGN", (2, 0), (2, -1), "RIGHT"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("BACKGROUND", (1, -2), (2, -2), self.brand_blue),
            ("TEXTCOLOR", (1, -2), (2, -2), colors.white),
            ("BACKGROUND", (0, -1), (-1, -1), self.accent_bg),
            ("SPAN", (0, -1), (-1, -1)),
            ("PADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (1, -2), (2, -2), 6),
            ("BOTTOMPADDING", (1, -2), (2, -2), 6),
            ("GRID", (1, 0), (2, -2), 0.5, self.rule),
        ]))
        return [
            HRFlowable(width="100%", thickness=1, color=self.rule),
            Spacer(1, 2*mm), tbl, Spacer(1, 4*mm),
        ]

    # ── Bank + Terms + Signature ──────────────────────────────────────────────
    def _footer_bank_terms(self, company, client):
        terms = client.get("terms") or _DEFAULT_TERMS
        hdr_s  = _s("fh", font="Helvetica-Bold", size=8, textColor=self.brand_blue)
        val_s  = _s("fv", size=7.5, textColor=self.gray)
        sig_s  = _s("sig", font="Helvetica-Bold", size=8, alignment=TA_CENTER, textColor=self.brand_blue)

        bank_lines = [
            Paragraph("BANK DETAILS", hdr_s),
            Paragraph(f'Bank: <b>{company.get("bank_name","")}</b>', val_s),
            Paragraph(f'A/C No: <b>{company.get("account_no","")}</b>', val_s),
            Paragraph(f'IFSC: <b>{company.get("ifsc","")}</b>', val_s),
        ]
        if company.get("upi"):
            bank_lines.append(Paragraph(f'UPI: <b>{company.get("upi","")}</b>', val_s))

        terms_lines = [Paragraph("TERMS & CONDITIONS", hdr_s)]
        for i, t in enumerate(terms, 1):
            terms_lines.append(Paragraph(f"{i}. {t}", val_s))

        sig_lines = [
            Paragraph(f'For {company.get("name","")}', hdr_s),
            Spacer(1, 18*mm),
            Paragraph("Authorized Signatory", sig_s),
            Paragraph("(Signature &amp; Seal)", _s("ss", size=7, textColor=self.gray, alignment=TA_CENTER)),
        ]

        tbl = Table([[bank_lines, terms_lines, sig_lines]],
                    colWidths=[5*cm, 9*cm, 5.5*cm])
        tbl.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (0, 0), self.accent_bg),
            ("BACKGROUND", (2, 0), (2, 0), HexColor("#F0F8FF")),
            ("GRID", (0, 0), (-1, -1), 0.5, self.rule),
            ("PADDING", (0, 0), (-1, -1), 7),
            ("ALIGN", (2, 0), (2, 0), "CENTER"),
        ]))
        disclaimer = ("This is a computer-generated invoice and does not require a physical signature "
                      "unless signed above. Subject to applicable laws and regulations.")
        return [
            HRFlowable(width="100%", thickness=2, color=self.brand_blue),
            Spacer(1, 3*mm), tbl, Spacer(1, 3*mm),
            Paragraph(disclaimer, _s("disc", size=7, textColor=self.gray, alignment=TA_CENTER)),
        ]
