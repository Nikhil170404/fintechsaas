import json
import os
import zipfile
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from config import Config
from modules.email_sender import EmailSender
from modules.excel_reader import ExcelReader
from modules.statement_builder import StatementBuilder

load_dotenv()

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("output")
SESSION_FILE = UPLOAD_DIR / "session_data.json"
SETTINGS_FILE = UPLOAD_DIR / "settings.json"
TEMPLATE_PATH = UPLOAD_DIR / "word_template.docx"

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


# ── session helpers ────────────────────────────────────────────────────────────

def _load_clients() -> list[dict]:
    if SESSION_FILE.exists():
        with open(SESSION_FILE) as f:
            return json.load(f)
    return []


def _save_clients(clients: list[dict]):
    with open(SESSION_FILE, "w") as f:
        json.dump(clients, f, ensure_ascii=False)


def _load_settings() -> dict:
    defaults = {
        "company_name": Config.COMPANY_NAME,
        "sender_name": Config.SENDER_NAME,
        "smtp_host": Config.SMTP_HOST,
        "smtp_port": Config.SMTP_PORT,
        "smtp_user": Config.SMTP_USER,
        "smtp_pass": Config.SMTP_PASS,
        "email_subject": "Your Account Statement – {{STATEMENT_PERIOD}}",
        "email_body": (
            "Dear {{CLIENT_NAME}},\n\n"
            "Please find your account statement for {{STATEMENT_PERIOD}} attached.\n\n"
            "Account No : {{ACCOUNT_NO}}\n"
            "Closing Balance : {{CLOSING_BALANCE}}\n\n"
            "For any queries, please reply to this email.\n\n"
            "Regards,\n{{SENDER_NAME}}"
        ),
    }
    if SETTINGS_FILE.exists():
        with open(SETTINGS_FILE) as f:
            saved = json.load(f)
        defaults.update(saved)
    return defaults


def _save_settings(data: dict):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f)


def _render_body(template: str, client: dict, settings: dict, period: str) -> str:
    txns = client.get("transactions", [])
    total_debit = sum(t["debit"] for t in txns)
    total_credit = sum(t["credit"] for t in txns)
    closing = txns[-1]["balance"] if txns else client.get("opening_balance", 0)
    return (
        template
        .replace("{{CLIENT_NAME}}", client.get("name", ""))
        .replace("{{ACCOUNT_NO}}", client.get("account_no", ""))
        .replace("{{STATEMENT_PERIOD}}", period)
        .replace("{{CLOSING_BALANCE}}", f'₹{closing:,.2f}')
        .replace("{{TOTAL_DEBIT}}", f'₹{total_debit:,.2f}')
        .replace("{{TOTAL_CREDIT}}", f'₹{total_credit:,.2f}')
        .replace("{{SENDER_NAME}}", settings.get("sender_name", ""))
    )


# ── routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    clients = _load_clients()
    pdfs = list(OUTPUT_DIR.glob("statement_*.pdf"))
    return render_template("index.html", client_count=len(clients), pdf_count=len(pdfs))


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
        try:
            reader = ExcelReader(dest)
            clients = reader.get_clients()
            _save_clients(clients)
            flash(f"Loaded {len(clients)} client(s) successfully.", "success")
            return redirect(url_for("clients"))
        except Exception as exc:
            flash(f"Error reading Excel: {exc}", "danger")
            return redirect(request.url)

    return render_template("upload.html")


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
    company = request.form.get("company_name") or settings["company_name"]
    period = request.form.get("statement_period", "")
    mode = request.form.get("mode", "auto")

    builder = StatementBuilder(OUTPUT_DIR)
    results = []
    for c in clients:
        try:
            pdf = builder.build(
                c, company, period, mode=mode,
                word_template=TEMPLATE_PATH if mode == "template" else None,
            )
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

    settings = _load_settings()
    selected = set(request.form.getlist("selected"))
    period = request.form.get("statement_period", "")

    smtp_host = request.form.get("smtp_host") or settings["smtp_host"]
    smtp_port = int(request.form.get("smtp_port") or settings["smtp_port"])
    smtp_user = request.form.get("smtp_user") or settings["smtp_user"]
    smtp_pass = request.form.get("smtp_pass") or settings["smtp_pass"]
    sender_name = settings["sender_name"]
    subject_tpl = settings["email_subject"].replace("{{STATEMENT_PERIOD}}", period)
    body_tpl = settings["email_body"]

    sender = EmailSender(smtp_host, smtp_port, smtp_user, smtp_pass, sender_name)
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
            body = _render_body(body_tpl, c, settings, period)
            sender.send(
                to_email=c["email"],
                to_name=c["name"],
                subject=subject_tpl,
                body=body,
                attachment_path=pdf_path,
                attachment_name=f"Statement_{acct}.pdf",
            )
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


@app.route("/download-template")
def download_template():
    from generate_sample import make_sample_excel
    path = make_sample_excel(UPLOAD_DIR / "sample_template.xlsx")
    return send_file(path, as_attachment=True, download_name="client_data_template.xlsx")


@app.route("/test-smtp", methods=["POST"])
def test_smtp():
    settings = _load_settings()
    test_email = request.form.get("test_email", "")
    if not test_email:
        return jsonify({"ok": False, "error": "No email address provided."})
    try:
        sender = EmailSender(
            settings["smtp_host"], settings["smtp_port"],
            settings["smtp_user"], settings["smtp_pass"], settings["sender_name"],
        )
        sender.send(
            to_email=test_email,
            to_name="Test Recipient",
            subject=f"SMTP Test – {settings['company_name']}",
            body=f"This is a test email from {settings['company_name']} FinTech SaaS.\nSMTP is configured correctly.",
        )
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
