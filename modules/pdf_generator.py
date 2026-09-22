import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Brand palette ──────────────────────────────────────────────────────────────
BRAND_BLUE = HexColor("#1E3A5F")
BRAND_LIGHT = HexColor("#2E86AB")
ACCENT_BG = HexColor("#EAF4FB")
ROW_ALT = HexColor("#F5F9FC")
TEXT_DARK = HexColor("#2C3E50")
TEXT_GRAY = HexColor("#7F8C8D")
GREEN = HexColor("#27AE60")
RED = HexColor("#E74C3C")
RULE_COLOR = HexColor("#BDC3C7")


class PDFGenerator:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._init_styles()

    def _init_styles(self):
        self.co_name_style = ParagraphStyle(
            "CoName", fontName="Helvetica-Bold", fontSize=18,
            textColor=BRAND_BLUE, alignment=TA_CENTER, spaceAfter=2,
        )
        self.subtitle_style = ParagraphStyle(
            "Sub", fontName="Helvetica", fontSize=9,
            textColor=TEXT_GRAY, alignment=TA_CENTER, spaceAfter=1,
        )
        self.section_style = ParagraphStyle(
            "Section", fontName="Helvetica-Bold", fontSize=9,
            textColor=BRAND_BLUE, spaceBefore=4,
        )
        self.footer_style = ParagraphStyle(
            "Footer", fontName="Helvetica", fontSize=7.5,
            textColor=TEXT_GRAY, alignment=TA_CENTER,
        )

    def generate(self, client: dict, company_name: str, statement_period: str) -> Path:
        out = self.output_dir / f'statement_{client["account_no"]}.pdf'
        doc = SimpleDocTemplate(
            str(out), pagesize=A4,
            leftMargin=1.5 * cm, rightMargin=1.5 * cm,
            topMargin=1.5 * cm, bottomMargin=2 * cm,
        )
        story = (
            self._header(company_name, statement_period)
            + self._client_box(client)
            + self._txn_table(client)
            + self._summary(client)
            + self._footer(company_name)
        )
        doc.build(story, onFirstPage=self._page_deco, onLaterPages=self._page_deco)
        return out

    # ── Page decorator ─────────────────────────────────────────────────────────
    def _page_deco(self, canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(BRAND_LIGHT)
        canvas.setLineWidth(1.5)
        canvas.rect(0.7 * cm, 0.7 * cm, A4[0] - 1.4 * cm, A4[1] - 1.4 * cm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(TEXT_GRAY)
        canvas.drawCentredString(A4[0] / 2, 0.4 * cm, f"Page {doc.page}")
        canvas.restoreState()

    # ── Section builders ────────────────────────────────────────────────────────
    def _header(self, company_name, period):
        return [
            Paragraph(company_name, self.co_name_style),
            Paragraph("Account Statement", self.subtitle_style),
            Paragraph(f"Statement Period: <b>{period}</b>", self.subtitle_style),
            Spacer(1, 3 * mm),
            HRFlowable(width="100%", thickness=2, color=BRAND_BLUE),
            Spacer(1, 4 * mm),
        ]

    def _client_box(self, client):
        today = datetime.date.today().strftime("%d %B %Y")
        data = [
            ["CLIENT DETAILS", "", "ACCOUNT INFORMATION", ""],
            ["Name :", client.get("name", ""), "Account No :", client.get("account_no", "")],
            ["Email :", client.get("email", ""), "Account Type :", client.get("account_type", "")],
            ["Phone :", client.get("phone", ""), "Generated On :", today],
            ["Address :", client.get("address", ""), "", ""],
        ]
        w = [3 * cm, 7 * cm, 3.5 * cm, 6 * cm]
        tbl = Table(data, colWidths=w)
        tbl.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (1, 0), BRAND_BLUE),
                ("BACKGROUND", (2, 0), (3, 0), BRAND_LIGHT),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("SPAN", (0, 0), (1, 0)),
                ("SPAN", (2, 0), (3, 0)),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 1), (2, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 1), (-1, -1), 9),
                ("TEXTCOLOR", (0, 1), (-1, -1), TEXT_DARK),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [ACCENT_BG, colors.white]),
                ("GRID", (0, 0), (-1, -1), 0.5, RULE_COLOR),
                ("PADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ])
        )
        return [tbl, Spacer(1, 5 * mm)]

    def _txn_table(self, client):
        txns = client.get("transactions", [])
        headers = ["#", "Date", "Description", "Reference", "Debit (₹)", "Credit (₹)", "Balance (₹)"]
        widths = [0.7 * cm, 2.4 * cm, 5.8 * cm, 2.4 * cm, 2.5 * cm, 2.5 * cm, 3 * cm]

        rows = [headers]
        for i, t in enumerate(txns, 1):
            rows.append([
                str(i),
                t.get("date", ""),
                t.get("description", ""),
                t.get("reference", ""),
                f'₹{t["debit"]:,.2f}' if t["debit"] > 0 else "—",
                f'₹{t["credit"]:,.2f}' if t["credit"] > 0 else "—",
                f'₹{t["balance"]:,.2f}',
            ])

        if not txns:
            rows.append(["", "No transactions in this period", "", "", "", "", ""])

        style = [
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_BLUE),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 8.5),
            ("TEXTCOLOR", (0, 1), (-1, -1), TEXT_DARK),
            ("ALIGN", (0, 1), (0, -1), "CENTER"),
            ("ALIGN", (4, 1), (6, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT]),
            ("GRID", (0, 0), (-1, -1), 0.5, RULE_COLOR),
            ("PADDING", (0, 0), (-1, -1), 5),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]
        # Color-code debit/credit cells
        for idx, t in enumerate(txns, 1):
            if t["debit"] > 0:
                style += [
                    ("TEXTCOLOR", (4, idx), (4, idx), RED),
                    ("FONTNAME", (4, idx), (4, idx), "Helvetica-Bold"),
                ]
            if t["credit"] > 0:
                style += [
                    ("TEXTCOLOR", (5, idx), (5, idx), GREEN),
                    ("FONTNAME", (5, idx), (5, idx), "Helvetica-Bold"),
                ]

        tbl = Table(rows, colWidths=widths, repeatRows=1)
        tbl.setStyle(TableStyle(style))
        return [
            Paragraph("TRANSACTION HISTORY", self.section_style),
            Spacer(1, 2 * mm),
            tbl,
            Spacer(1, 4 * mm),
        ]

    def _summary(self, client):
        txns = client.get("transactions", [])
        total_debit = sum(t["debit"] for t in txns)
        total_credit = sum(t["credit"] for t in txns)
        opening = client.get("opening_balance", 0)
        closing = txns[-1]["balance"] if txns else opening

        data = [
            ["ACCOUNT SUMMARY", "", "", ""],
            ["Opening Balance", f"₹{opening:,.2f}", "Total Debits", f"₹{total_debit:,.2f}"],
            ["Closing Balance", f"₹{closing:,.2f}", "Total Credits", f"₹{total_credit:,.2f}"],
        ]
        w = [4 * cm, 5 * cm, 4 * cm, 5 * cm]
        tbl = Table(data, colWidths=w)
        tbl.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), BRAND_LIGHT),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("SPAN", (0, 0), (-1, 0)),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 1), (2, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 1), (-1, -1), 9),
                ("ALIGN", (1, 1), (1, -1), "RIGHT"),
                ("ALIGN", (3, 1), (3, -1), "RIGHT"),
                ("TEXTCOLOR", (1, 1), (1, 1), BRAND_BLUE),
                ("TEXTCOLOR", (1, 2), (1, 2), GREEN),
                ("TEXTCOLOR", (3, 1), (3, 1), RED),
                ("TEXTCOLOR", (3, 2), (3, 2), GREEN),
                ("FONTNAME", (1, 1), (3, -1), "Helvetica-Bold"),
                ("BACKGROUND", (0, 1), (-1, -1), ACCENT_BG),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [ACCENT_BG, colors.white]),
                ("GRID", (0, 0), (-1, -1), 0.5, RULE_COLOR),
                ("PADDING", (0, 0), (-1, -1), 7),
            ])
        )
        return [
            HRFlowable(width="100%", thickness=1, color=RULE_COLOR),
            Spacer(1, 3 * mm),
            tbl,
            Spacer(1, 4 * mm),
        ]

    def _footer(self, company_name):
        text = (
            f"This is a computer-generated statement and does not require a signature. "
            f"For queries, contact {company_name}. "
            f"All transactions are subject to applicable terms and conditions."
        )
        return [
            HRFlowable(width="100%", thickness=1, color=BRAND_BLUE),
            Spacer(1, 2 * mm),
            Paragraph(text, self.footer_style),
        ]
