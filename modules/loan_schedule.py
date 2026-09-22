"""
Generate an EMI amortization schedule PDF.

Input dict:
  borrower_name, email, loan_no, loan_amount, interest_rate (annual %),
  tenure_months, start_date (YYYY-MM-DD), disbursement_date
"""
import re
import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER
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
RED = HexColor("#E74C3C")
GREEN = HexColor("#27AE60")
GRAY = HexColor("#7F8C8D")
RULE = HexColor("#BDC3C7")


def _s(name, **kw):
    return ParagraphStyle(name, fontName=kw.pop("font", "Helvetica"),
                          fontSize=kw.pop("size", 9), **kw)


def _emi(principal: float, annual_rate: float, months: int) -> float:
    r = annual_rate / 12 / 100
    if r == 0:
        return principal / months
    return principal * r * (1 + r) ** months / ((1 + r) ** months - 1)


def _schedule(principal: float, annual_rate: float, months: int,
              start_date: datetime.date) -> list[dict]:
    r = annual_rate / 12 / 100
    emi = _emi(principal, annual_rate, months)
    bal = principal
    rows = []
    for i in range(1, months + 1):
        interest = bal * r
        principal_part = emi - interest
        bal = max(bal - principal_part, 0)
        due = start_date + datetime.timedelta(days=30 * i)
        rows.append({
            "no": i,
            "due_date": due.strftime("%d %b %Y"),
            "emi": emi,
            "principal": principal_part,
            "interest": interest,
            "balance": bal,
            "status": "Upcoming",
        })
    return rows


class LoanScheduleGenerator:
    def __init__(self, output_dir: Path,
                 brand_color: str = "",
                 logo_path: Path | None = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        bc = brand_color if re.match(r"^#[0-9a-fA-F]{6}$", brand_color or "") else _DEFAULT_BRAND
        self._blue  = HexColor(bc)
        self._light = _lighten(bc, 0.40)
        self._accent = _lighten(bc, 0.90)
        self.logo_path = logo_path if logo_path and Path(logo_path).exists() else None
        # update module-level constants so existing _header/_schedule_table etc. work
        global BLUE, LIGHT, ACCENT
        BLUE = self._blue; LIGHT = self._light; ACCENT = self._accent

    def generate(self, loan: dict, company_name: str) -> Path:
        loan_no = loan.get("loan_no", "LOAN-001")
        out = self.output_dir / f"loan_schedule_{loan_no}.pdf"

        principal = float(loan.get("loan_amount", 0))
        rate = float(loan.get("interest_rate", 12))
        months = int(loan.get("tenure_months", 12))
        try:
            start = datetime.date.fromisoformat(loan.get("start_date", str(datetime.date.today())))
        except ValueError:
            start = datetime.date.today()

        emi = _emi(principal, rate, months)
        schedule = _schedule(principal, rate, months, start)

        doc = SimpleDocTemplate(str(out), pagesize=A4,
                                leftMargin=1.5*cm, rightMargin=1.5*cm,
                                topMargin=1.5*cm, bottomMargin=2*cm)
        story = (
            self._header(company_name, loan, emi, principal, months)
            + self._schedule_table(schedule)
            + self._summary(schedule, emi, months)
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

    def _header(self, company_name, loan, emi, principal, months):
        title_s = _s("t", font="Helvetica-Bold", size=17, textColor=BLUE, alignment=TA_CENTER)
        sub_s = _s("sub", size=9, textColor=GRAY, alignment=TA_CENTER)
        items = []
        if self.logo_path:
            try:
                img = Image(str(self.logo_path), width=5*cm, height=1.5*cm)
                img.hAlign = "CENTER"
                items.append(img)
                items.append(Spacer(1, 2*mm))
            except Exception:
                pass
        items += [Paragraph(company_name, title_s),
                  Paragraph("Loan Amortization Schedule", sub_s),
                  Spacer(1, 3*mm),
                  HRFlowable(width="100%", thickness=2, color=BLUE),
                  Spacer(1, 4*mm)]

        info = [
            ["Borrower", loan.get("borrower_name", ""), "Loan No.", loan.get("loan_no", "")],
            ["Email", loan.get("email", ""), "Loan Amount", f'₹{principal:,.2f}'],
            ["Phone", loan.get("phone", ""), "Interest Rate", f'{loan.get("interest_rate", 12)}% p.a.'],
            ["Disbursement", loan.get("disbursement_date", ""), "Tenure", f'{months} months'],
            ["", "", "Monthly EMI", f'₹{emi:,.2f}'],
        ]
        tbl = Table(info, colWidths=[3*cm, 7*cm, 3.5*cm, 6*cm])
        tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (2, -1), (2, -1), BLUE),
            ("FONTNAME", (3, -1), (3, -1), "Helvetica-Bold"),
            ("FONTSIZE", (3, -1), (3, -1), 11),
            ("TEXTCOLOR", (3, -1), (3, -1), BLUE),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [ACCENT, colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.5, RULE),
            ("PADDING", (0, 0), (-1, -1), 5),
        ]))
        items.append(tbl)
        items.append(Spacer(1, 5*mm))
        return items

    def _schedule_table(self, schedule):
        headers = ["#", "Due Date", "EMI (₹)", "Principal (₹)", "Interest (₹)", "Balance (₹)", "Status"]
        widths = [0.8*cm, 2.8*cm, 3*cm, 3.2*cm, 3*cm, 3.5*cm, 2.2*cm]
        rows = [headers]
        for r in schedule:
            rows.append([
                str(r["no"]),
                r["due_date"],
                f'₹{r["emi"]:,.2f}',
                f'₹{r["principal"]:,.2f}',
                f'₹{r["interest"]:,.2f}',
                f'₹{r["balance"]:,.2f}',
                r["status"],
            ])
        tbl = Table(rows, colWidths=widths, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BLUE),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (2, 1), (5, -1), "RIGHT"),
            ("ALIGN", (0, 1), (0, -1), "CENTER"),
            ("ALIGN", (6, 1), (6, -1), "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ACCENT]),
            ("GRID", (0, 0), (-1, -1), 0.5, RULE),
            ("PADDING", (0, 0), (-1, -1), 4),
        ]))
        return [Paragraph("EMI SCHEDULE", _s("sh", font="Helvetica-Bold", size=9, textColor=BLUE)),
                Spacer(1, 2*mm), tbl, Spacer(1, 4*mm)]

    def _summary(self, schedule, emi, months):
        total_paid = emi * months
        total_interest = sum(r["interest"] for r in schedule)
        principal = schedule[0]["emi"] + schedule[0]["balance"] - schedule[0]["balance"] if schedule else 0
        # simpler: principal = total_paid - total_interest
        principal = total_paid - total_interest

        data = [
            ["REPAYMENT SUMMARY", "", "", ""],
            ["Total EMI Payments", f"₹{total_paid:,.2f}", "Principal Amount", f"₹{principal:,.2f}"],
            ["Total Interest Paid", f"₹{total_interest:,.2f}", "Cost of Credit", f"{total_interest/principal*100:.1f}%"],
        ]
        tbl = Table(data, colWidths=[4.5*cm, 4.5*cm, 4.5*cm, 6*cm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("SPAN", (0, 0), (-1, 0)),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (2, 1), (2, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 1), (-1, -1), ACCENT),
            ("GRID", (0, 0), (-1, -1), 0.5, RULE),
            ("PADDING", (0, 0), (-1, -1), 6),
        ]))
        return [HRFlowable(width="100%", thickness=1, color=RULE),
                Spacer(1, 3*mm), tbl]
