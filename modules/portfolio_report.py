"""
Generate an investment portfolio statement PDF.

Client dict:
  name, email, account_no, pan, risk_profile, as_of_date,
  holdings: list of {
      scheme, category, units, nav, current_value,
      invested_amount, returns_pct
  }
"""
import re
from pathlib import Path
import datetime

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    HRFlowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

_DEFAULT_BRAND = "#1E3A5F"

def _lighten(hex_color: str, f: float = 0.40) -> HexColor:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return HexColor(f"#{int(r+(255-r)*f):02x}{int(g+(255-g)*f):02x}{int(b+(255-b)*f):02x}")

BLUE = HexColor("#1E3A5F")
LIGHT = HexColor("#2E86AB")
ACCENT = HexColor("#EAF4FB")
GREEN = HexColor("#27AE60")
RED = HexColor("#E74C3C")
GRAY = HexColor("#7F8C8D")
RULE = HexColor("#BDC3C7")
GOLD = HexColor("#F39C12")


def _s(name, **kw):
    return ParagraphStyle(name, fontName=kw.pop("font", "Helvetica"),
                          fontSize=kw.pop("size", 9), **kw)


class PortfolioReportGenerator:
    def __init__(self, output_dir: Path,
                 brand_color: str = "",
                 logo_path: Path | None = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        bc = brand_color if re.match(r"^#[0-9a-fA-F]{6}$", brand_color or "") else _DEFAULT_BRAND
        self.logo_path = logo_path if logo_path and Path(logo_path).exists() else None
        global BLUE, LIGHT, ACCENT
        BLUE = HexColor(bc)
        LIGHT = _lighten(bc, 0.40)
        ACCENT = _lighten(bc, 0.90)

    def generate(self, client: dict, company_name: str) -> Path:
        acct = client.get("account_no", "PORT-001")
        out = self.output_dir / f"portfolio_{acct}.pdf"
        doc = SimpleDocTemplate(str(out), pagesize=A4,
                                leftMargin=1.5*cm, rightMargin=1.5*cm,
                                topMargin=1.5*cm, bottomMargin=2*cm)
        story = (
            self._header(company_name, client)
            + self._summary_cards(client)
            + self._holdings_table(client)
            + self._allocation_footer(client)
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

    def _header(self, company_name, client):
        as_of = client.get("as_of_date", datetime.date.today().strftime("%d %B %Y"))
        title_s = _s("t", font="Helvetica-Bold", size=17, textColor=BLUE, alignment=TA_CENTER)
        sub_s = _s("s", size=9, textColor=GRAY, alignment=TA_CENTER)
        pre = []
        if self.logo_path:
            try:
                img = Image(str(self.logo_path), width=5*cm, height=1.5*cm)
                img.hAlign = "CENTER"
                pre += [img, Spacer(1, 2*mm)]
            except Exception:
                pass
        info = [
            ["Investor Name", client.get("name", ""), "Account No", client.get("account_no", "")],
            ["PAN", client.get("pan", ""), "Risk Profile", client.get("risk_profile", "Moderate")],
            ["Email", client.get("email", ""), "As of Date", as_of],
        ]
        tbl = Table(info, colWidths=[3*cm, 7*cm, 3.5*cm, 6*cm])
        tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [ACCENT, colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.5, RULE),
            ("PADDING", (0, 0), (-1, -1), 5),
        ]))
        return pre + [
            Paragraph(company_name, title_s),
            Paragraph("Investment Portfolio Statement", sub_s),
            Spacer(1, 3*mm),
            HRFlowable(width="100%", thickness=2, color=BLUE),
            Spacer(1, 4*mm),
            tbl,
            Spacer(1, 5*mm),
        ]

    def _summary_cards(self, client):
        holdings = client.get("holdings", [])
        invested = sum(float(h.get("invested_amount", 0)) for h in holdings)
        current = sum(float(h.get("current_value", 0)) for h in holdings)
        gain = current - invested
        gain_pct = (gain / invested * 100) if invested else 0

        data = [
            ["PORTFOLIO OVERVIEW", "", "", ""],
            ["Total Invested", f"₹{invested:,.2f}",
             "Current Value", f"₹{current:,.2f}"],
            ["Total Gain/Loss",
             Paragraph(f'<font color="{"#27AE60" if gain >= 0 else "#E74C3C"}">₹{gain:+,.2f}</font>', _s("g", size=9)),
             "Absolute Returns",
             Paragraph(f'<font color="{"#27AE60" if gain_pct >= 0 else "#E74C3C"}">{gain_pct:+.2f}%</font>', _s("g", size=9))],
        ]
        tbl = Table(data, colWidths=[4*cm, 5.5*cm, 4*cm, 6*cm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BLUE),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("SPAN", (0, 0), (-1, 0)),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (2, 1), (2, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("FONTNAME", (1, 1), (1, 1), "Helvetica-Bold"),
            ("FONTSIZE", (1, 1), (1, 1), 11),
            ("FONTNAME", (3, 1), (3, 1), "Helvetica-Bold"),
            ("FONTSIZE", (3, 1), (3, 1), 11),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [ACCENT, colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.5, RULE),
            ("PADDING", (0, 0), (-1, -1), 7),
        ]))
        return [tbl, Spacer(1, 5*mm)]

    def _holdings_table(self, client):
        holdings = client.get("holdings", [])
        headers = ["#", "Scheme / Asset", "Category", "Units", "NAV (₹)", "Invested (₹)", "Value (₹)", "Returns"]
        widths = [0.7*cm, 5.5*cm, 2.5*cm, 1.8*cm, 2.3*cm, 2.8*cm, 2.8*cm, 2*cm]
        rows = [headers]
        for i, h in enumerate(holdings, 1):
            inv = float(h.get("invested_amount", 0))
            cur = float(h.get("current_value", 0))
            ret = float(h.get("returns_pct", (cur - inv) / inv * 100 if inv else 0))
            rows.append([
                str(i),
                h.get("scheme", ""),
                h.get("category", ""),
                str(h.get("units", "")),
                f'₹{float(h.get("nav", 0)):,.4f}',
                f"₹{inv:,.2f}",
                f"₹{cur:,.2f}",
                f"{ret:+.2f}%",
            ])
        tbl = Table(rows, colWidths=widths, repeatRows=1)
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), BLUE),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ACCENT]),
            ("GRID", (0, 0), (-1, -1), 0.5, RULE),
            ("PADDING", (0, 0), (-1, -1), 4),
        ]
        # Color returns column
        for idx, h in enumerate(holdings, 1):
            inv = float(h.get("invested_amount", 0))
            cur = float(h.get("current_value", 0))
            ret = (cur - inv) / inv * 100 if inv else 0
            c = GREEN if ret >= 0 else RED
            style.append(("TEXTCOLOR", (7, idx), (7, idx), c))
            style.append(("FONTNAME", (7, idx), (7, idx), "Helvetica-Bold"))

        tbl.setStyle(TableStyle(style))
        return [Paragraph("HOLDINGS", _s("sh", font="Helvetica-Bold", size=9, textColor=BLUE)),
                Spacer(1, 2*mm), tbl, Spacer(1, 4*mm)]

    def _allocation_footer(self, client):
        holdings = client.get("holdings", [])
        # Category-wise breakup
        cats: dict[str, float] = {}
        total = 0.0
        for h in holdings:
            c = h.get("category", "Other")
            v = float(h.get("current_value", 0))
            cats[c] = cats.get(c, 0) + v
            total += v

        rows = [["Category", "Value (₹)", "Allocation %"]]
        for cat, val in sorted(cats.items(), key=lambda x: -x[1]):
            rows.append([cat, f"₹{val:,.2f}", f"{val/total*100:.1f}%" if total else "0%"])

        tbl = Table(rows, colWidths=[7*cm, 6*cm, 6*cm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [ACCENT, colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.5, RULE),
            ("PADDING", (0, 0), (-1, -1), 5),
        ]))
        return [
            HRFlowable(width="100%", thickness=1, color=RULE),
            Spacer(1, 3*mm),
            Paragraph("ASSET ALLOCATION", _s("aa", font="Helvetica-Bold", size=9, textColor=BLUE)),
            Spacer(1, 2*mm),
            tbl,
        ]
