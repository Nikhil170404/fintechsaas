import json
import os
import zipfile
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask, flash, jsonify, redirect, render_template,
    request, send_file, url_for,
)

from config import Config
from modules.column_detector import ColumnDetector, ALIASES, FIELD_LABELS
from modules.email_sender import EmailSender
from modules.excel_reader import ExcelReader
from modules.statement_builder import StatementBuilder

load_dotenv()

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY

UPLOAD_DIR   = Path("uploads")
OUTPUT_DIR   = Path("output")
SESSION_FILE = UPLOAD_DIR / "session_data.json"
SETTINGS_FILE= UPLOAD_DIR / "settings.json"
MAPPING_FILE = UPLOAD_DIR / "column_mapping.json"
TEMPLATE_PATH= UPLOAD_DIR / "word_template.docx"

for d in (UPLOAD_DIR, OUTPUT_DIR):
    d.mkdir(exist_ok=True)


# ── persistence helpers ────────────────────────────────────────────────────────

def _load_clients():
    return json.loads(SESSION_FILE.read_text()) if SESSION_FILE.exists() else []

def _save_clients(clients):
    SESSION_FILE.write_text(json.dumps(clients, ensure_ascii=False))

def _load_mapping():
    return json.loads(MAPPING_FILE.read_text()) if MAPPING_FILE.exists() else {}

def _save_mapping(m):
    MAPPING_FILE.write_text(json.dumps(m))

def _load_settings():
    defaults = {
        "company_name":  Config.COMPANY_NAME,
        "sender_name":   Config.SENDER_NAME,
        "smtp_host":     Config.SMTP_HOST,
        "smtp_port":     Config.SMTP_PORT,
        "smtp_user":     Config.SMTP_USER,
        "smtp_pass":     Config.SMTP_PASS,
        "email_subject": "Your Account Statement – {{STATEMENT_PERIOD}}",
        "email_type":    "plain",
        "email_body": (
            "Dear {{CLIENT_NAME}},\n\n"
            "Please find your account statement for {{STATEMENT_PERIOD}} attached.\n\n"
            "Account No : {{ACCOUNT_NO}}\n"
            "Closing Balance : {{CLOSING_BALANCE}}\n\n"
            "For any queries, please reply to this email.\n\n"
            "Regards,\n{{SENDER_NAME}}"
        ),
        "email_html": _default_html_template(),
    }
    if SETTINGS_FILE.exists():
        defaults.update(json.loads(SETTINGS_FILE.read_text()))
    return defaults

def _save_settings(d):
    SETTINGS_FILE.write_text(json.dumps(d))

def _default_html_template():
    return """\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f4f6fb;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0">
  <tr><td align="center" style="padding:30px 0;">
    <table width="580" cellpadding="0" cellspacing="0"
           style="background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08)">

      <!-- Header -->
      <tr><td style="background:#1E3A5F;padding:28px 32px;text-align:center;">
        <h1 style="margin:0;color:#fff;font-size:22px;">{{COMPANY_NAME}}</h1>
        <p style="margin:6px 0 0;color:rgba(255,255,255,.7);font-size:13px;">Account Statement</p>
      </td></tr>

      <!-- Greeting -->
      <tr><td style="padding:28px 32px 12px;">
        <p style="margin:0;font-size:15px;color:#2c3e50;">Dear <strong>{{CLIENT_NAME}}</strong>,</p>
        <p style="margin:12px 0 0;color:#555;font-size:14px;line-height:1.6;">
          Your account statement for <strong>{{STATEMENT_PERIOD}}</strong> is attached to this email.
          Please find a brief summary below.
        </p>
      </td></tr>

      <!-- Summary cards -->
      <tr><td style="padding:12px 32px;">
        <table width="100%" cellpadding="0" cellspacing="8">
          <tr>
            <td style="background:#EAF4FB;border-radius:6px;padding:14px;width:48%;vertical-align:top;">
              <p style="margin:0;font-size:11px;color:#7f8c8d;text-transform:uppercase;">Account No</p>
              <p style="margin:4px 0 0;font-size:16px;font-weight:bold;color:#1E3A5F;">{{ACCOUNT_NO}}</p>
            </td>
            <td width="4%"></td>
            <td style="background:#EAF4FB;border-radius:6px;padding:14px;width:48%;vertical-align:top;">
              <p style="margin:0;font-size:11px;color:#7f8c8d;text-transform:uppercase;">Closing Balance</p>
              <p style="margin:4px 0 0;font-size:16px;font-weight:bold;color:#27AE60;">{{CLOSING_BALANCE}}</p>
            </td>
          </tr>
          <tr><td height="8"></td></tr>
          <tr>
            <td style="background:#FEF9E7;border-radius:6px;padding:14px;vertical-align:top;">
              <p style="margin:0;font-size:11px;color:#7f8c8d;text-transform:uppercase;">Total Debits</p>
              <p style="margin:4px 0 0;font-size:15px;font-weight:bold;color:#E74C3C;">{{TOTAL_DEBIT}}</p>
            </td>
            <td width="4%"></td>
            <td style="background:#EAF7EF;border-radius:6px;padding:14px;vertical-align:top;">
              <p style="margin:0;font-size:11px;color:#7f8c8d;text-transform:uppercase;">Total Credits</p>
              <p style="margin:4px 0 0;font-size:15px;font-weight:bold;color:#27AE60;">{{TOTAL_CREDIT}}</p>
            </td>
          </tr>
        </table>
      </td></tr>

      <!-- CTA -->
      <tr><td style="padding:20px 32px 28px;text-align:center;">
        <p style="color:#555;font-size:13px;margin:0 0 16px;">
          Please open the attached PDF for the complete statement with all transactions.
        </p>
        <p style="color:#aaa;font-size:12px;margin:24px 0 0;">
          This is an automated email from {{COMPANY_NAME}}.
          For support, reply to this email.
        </p>
      </td></tr>

      <!-- Footer -->
      <tr><td style="background:#1E3A5F;padding:14px 32px;text-align:center;">
        <p style="margin:0;color:rgba(255,255,255,.5);font-size:11px;">
          &copy; {{COMPANY_NAME}} &bull; Sent by {{SENDER_NAME}}
        </p>
      </td></tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""

def _render_content(template: str, client: dict, settings: dict, period: str) -> str:
    txns = client.get("transactions", [])
    closing = txns[-1]["balance"] if txns else client.get("opening_balance", 0)
    total_debit = sum(t["debit"] for t in txns)
    total_credit = sum(t["credit"] for t in txns)
    return (
        template
        .replace("{{CLIENT_NAME}}",      client.get("name", ""))
        .replace("{{ACCOUNT_NO}}",       client.get("account_no", ""))
        .replace("{{STATEMENT_PERIOD}}", period)
        .replace("{{CLOSING_BALANCE}}",  f"₹{closing:,.2f}")
        .replace("{{TOTAL_DEBIT}}",      f"₹{total_debit:,.2f}")
        .replace("{{TOTAL_CREDIT}}",     f"₹{total_credit:,.2f}")
        .replace("{{SENDER_NAME}}",      settings.get("sender_name", ""))
        .replace("{{COMPANY_NAME}}",     settings.get("company_name", ""))
    )


# ── routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    clients = _load_clients()
    pdfs = list(OUTPUT_DIR.glob("statement_*.pdf"))
    return render_template("index.html", client_count=len(clients), pdf_count=len(pdfs))


# ── Upload + column mapper ─────────────────────────────────────────────────────

@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        f = request.files.get("excel_file")
        if not f or not f.filename:
            flash("No file selected.", "danger")
            return redirect(request.url)
        if not f.filename.lower().endswith((".xlsx", ".xls")):
            flash("Please upload an Excel file (.xlsx or .xls).", "danger")
            return redirect(request.url)
        dest = UPLOAD_DIR / "clients.xlsx"
        f.save(dest)
        # Go to column mapper
        return redirect(url_for("map_columns"))
    return render_template("upload.html")


@app.route("/map-columns")
def map_columns():
    xlsx = UPLOAD_DIR / "clients.xlsx"
    if not xlsx.exists():
        flash("Upload an Excel file first.", "warning")
        return redirect(url_for("upload"))

    detector = ColumnDetector(xlsx)
    sheets = detector.sheet_names

    # Auto-detect best sheet for clients and transactions
    def guess(candidates):
        names_lower = {s.lower(): s for s in sheets}
        for c in candidates:
            if c.lower() in names_lower:
                return names_lower[c.lower()]
        return sheets[0]

    client_sheet = guess(["clients", "client", "master", "customers", "customer"])
    txn_sheet    = guess(["transactions", "transaction", "txn", "statement", "ledger"])

    client_cols  = detector.columns_for(client_sheet)
    txn_cols     = detector.columns_for(txn_sheet)
    client_sug   = detector.auto_suggest(client_sheet, "clients")
    txn_sug      = detector.auto_suggest(txn_sheet, "transactions")
    flat_hint    = detector.detect_flat_mode(client_sheet)
    preview      = detector.preview_rows(client_sheet, 3)

    # If a saved mapping exists, pre-fill suggestions from it
    saved = _load_mapping()
    if saved.get("clients"):
        client_sug.update(saved["clients"])
    if saved.get("transactions"):
        txn_sug.update(saved["transactions"])

    return render_template(
        "map_columns.html",
        sheets=sheets,
        client_cols=client_cols,
        txn_cols=txn_cols,
        client_suggest=client_sug,
        txn_suggest=txn_sug,
        client_fields=FIELD_LABELS["clients"],
        txn_fields=FIELD_LABELS["transactions"],
        suggested_client_sheet=client_sheet,
        suggested_txn_sheet=txn_sheet,
        flat_hint=flat_hint,
        preview_rows=preview,
    )


@app.route("/save-mapping", methods=["POST"])
def save_mapping():
    flat = request.form.get("flat_mode", "0") == "1"
    mapping = {
        "client_sheet": request.form.get("client_sheet"),
        "txn_sheet":    request.form.get("txn_sheet"),
        "flat_mode":    flat,
        "clients": {
            f: request.form.get(f"c_{f}", "") for f in ALIASES["clients"]
            if request.form.get(f"c_{f}")
        },
        "transactions": {
            f: request.form.get(f"t_{f}", "") for f in ALIASES["transactions"]
            if request.form.get(f"t_{f}")
        },
    }
    _save_mapping(mapping)

    xlsx = UPLOAD_DIR / "clients.xlsx"
    try:
        reader = ExcelReader(xlsx, mapping)
        clients = reader.get_clients()
        _save_clients(clients)
        flash(f"Loaded {len(clients)} client(s) with your column mapping.", "success")
        return redirect(url_for("clients"))
    except Exception as exc:
        flash(f"Error reading Excel with this mapping: {exc}", "danger")
        return redirect(url_for("map_columns"))


# ── Clients + statements ───────────────────────────────────────────────────────

@app.route("/clients")
def clients():
    data = _load_clients()
    return render_template("clients.html", clients=data, has_template=TEMPLATE_PATH.exists())


@app.route("/generate", methods=["POST"])
def generate():
    clients = _load_clients()
    if not clients:
        return jsonify({"error": "No clients loaded."}), 400
    settings = _load_settings()
    company  = request.form.get("company_name") or settings["company_name"]
    period   = request.form.get("statement_period", "")
    mode     = request.form.get("mode", "auto")
    builder  = StatementBuilder(OUTPUT_DIR)
    results  = []
    for c in clients:
        try:
            pdf = builder.build(c, company, period, mode=mode,
                                word_template=TEMPLATE_PATH if mode == "template" else None)
            results.append({"account": c["account_no"], "name": c["name"], "status": "ok", "file": pdf.name})
        except Exception as exc:
            results.append({"account": c["account_no"], "name": c["name"], "status": "error", "error": str(exc)})
    return jsonify({"results": results, "period": period})


@app.route("/download/<account_no>")
def download(account_no):
    path = OUTPUT_DIR / f"statement_{account_no}.pdf"
    if path.exists():
        return send_file(path, as_attachment=True, download_name=f"Statement_{account_no}.pdf")
    return "File not found", 404


@app.route("/download-all")
def download_all():
    pdfs = list(OUTPUT_DIR.glob("statement_*.pdf"))
    if not pdfs:
        flash("No PDFs generated yet.", "warning")
        return redirect(url_for("clients"))
    zip_path = OUTPUT_DIR / "All_Statements.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in pdfs:
            zf.write(p, p.name)
    return send_file(zip_path, as_attachment=True, download_name="All_Statements.zip")


@app.route("/send", methods=["POST"])
def send_emails():
    clients = _load_clients()
    if not clients:
        return jsonify({"error": "No clients loaded."}), 400
    settings  = _load_settings()
    selected  = set(request.form.getlist("selected"))
    period    = request.form.get("statement_period", "")
    subject_t = settings["email_subject"].replace("{{STATEMENT_PERIOD}}", period)
    sender    = EmailSender(settings["smtp_host"], settings["smtp_port"],
                            settings["smtp_user"], settings["smtp_pass"],
                            settings["sender_name"])
    results = []
    for c in clients:
        acct = c["account_no"]
        if selected and acct not in selected:
            continue
        pdf_path = OUTPUT_DIR / f"statement_{acct}.pdf"
        if not pdf_path.exists():
            results.append({"account": acct, "name": c["name"], "status": "skipped", "reason": "PDF not generated"})
            continue
        try:
            plain = _render_content(settings["email_body"], c, settings, period)
            html  = _render_content(settings["email_html"], c, settings, period) \
                    if settings.get("email_type") == "html" else None
            sender.send(to_email=c["email"], to_name=c["name"],
                        subject=subject_t, body=plain, html_body=html,
                        attachment_path=pdf_path,
                        attachment_name=f"Statement_{acct}.pdf")
            results.append({"account": acct, "name": c["name"], "status": "sent", "email": c["email"]})
        except Exception as exc:
            results.append({"account": acct, "name": c["name"], "status": "error", "error": str(exc)})
    return jsonify({"results": results})


@app.route("/upload-template", methods=["POST"])
def upload_template():
    f = request.files.get("word_template")
    if not f or not f.filename.lower().endswith(".docx"):
        flash("Please upload a .docx Word template.", "danger")
        return redirect(url_for("clients"))
    f.save(TEMPLATE_PATH)
    flash("Word template uploaded successfully.", "success")
    return redirect(url_for("clients"))


# ── Settings ───────────────────────────────────────────────────────────────────

@app.route("/settings", methods=["GET", "POST"])
def settings():
    cfg = _load_settings()
    if request.method == "POST":
        for key in cfg:
            if key in request.form:
                cfg[key] = request.form[key]
        _save_settings(cfg)
        flash("Settings saved.", "success")
        return redirect(url_for("settings"))
    return render_template("settings.html", cfg=cfg)


@app.route("/test-smtp", methods=["POST"])
def test_smtp():
    s = _load_settings()
    test_email = request.form.get("test_email", "")
    if not test_email:
        return jsonify({"ok": False, "error": "No email address provided."})
    try:
        EmailSender(s["smtp_host"], s["smtp_port"], s["smtp_user"],
                    s["smtp_pass"], s["sender_name"]).send(
            to_email=test_email, to_name="Test",
            subject=f"SMTP Test – {s['company_name']}",
            body="SMTP is working correctly.",
        )
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})


# ── Fintech modules ────────────────────────────────────────────────────────────

@app.route("/invoices")
def invoices():
    return render_template("invoices.html")


@app.route("/generate-invoice", methods=["POST"])
def generate_invoice():
    from modules.invoice_generator import InvoiceGenerator
    data = request.get_json()
    try:
        gen = InvoiceGenerator(OUTPUT_DIR)
        pdf = gen.generate(data["client"], data["company"])
        return jsonify({"ok": True, "file": pdf.name, "invoice_no": data["client"].get("invoice_no")})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})


@app.route("/loans")
def loans():
    return render_template("loans.html")


@app.route("/generate-loan-schedule", methods=["POST"])
def generate_loan_schedule():
    from modules.loan_schedule import LoanScheduleGenerator
    data = request.get_json()
    s = _load_settings()
    try:
        gen = LoanScheduleGenerator(OUTPUT_DIR)
        pdf = gen.generate(data, s["company_name"])
        return jsonify({"ok": True, "file": pdf.name})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})


@app.route("/portfolio")
def portfolio():
    return render_template("portfolio.html")


@app.route("/generate-portfolio", methods=["POST"])
def generate_portfolio():
    from modules.portfolio_report import PortfolioReportGenerator
    data = request.get_json()
    s = _load_settings()
    try:
        gen = PortfolioReportGenerator(OUTPUT_DIR)
        pdf = gen.generate(data, s["company_name"])
        return jsonify({"ok": True, "file": pdf.name})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})


@app.route("/download-output/<filename>")
def download_output(filename):
    path = OUTPUT_DIR / filename
    if path.exists():
        return send_file(path, as_attachment=True)
    return "File not found", 404


# ── Template download ──────────────────────────────────────────────────────────

@app.route("/download-template")
def download_template():
    from generate_sample import make_sample_excel
    path = make_sample_excel(UPLOAD_DIR / "sample_template.xlsx")
    return send_file(path, as_attachment=True, download_name="client_data_template.xlsx")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
