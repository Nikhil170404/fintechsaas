import json
import os
import re
import secrets
import time
import zipfile
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv
from flask import (
    Flask, flash, jsonify, redirect, render_template,
    request, send_file, session, url_for,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from modules.column_detector import ColumnDetector, ALIASES, FIELD_LABELS
from modules.email_sender import EmailSender
from modules.excel_reader import ExcelReader
from modules.statement_builder import StatementBuilder

load_dotenv()

UPLOAD_DIR    = Path("uploads")
OUTPUT_DIR    = Path("output")
SESSION_FILE  = UPLOAD_DIR / "session_data.json"
SETTINGS_FILE = UPLOAD_DIR / "settings.json"
MAPPING_FILE  = UPLOAD_DIR / "column_mapping.json"
TEMPLATE_PATH = UPLOAD_DIR / "word_template.docx"
ACTIVITY_FILE = UPLOAD_DIR / "activity.json"
PROFILES_FILE = UPLOAD_DIR / "mapping_profiles.json"
AUDIT_LOG     = UPLOAD_DIR / "audit.log"
ENC_KEY_FILE  = UPLOAD_DIR / ".enc_key"

for d in (UPLOAD_DIR, OUTPUT_DIR):
    d.mkdir(exist_ok=True)

# ── Auto-generate strong secret key if default is still set ───────────────────
def _ensure_secret_key() -> str:
    key_file = UPLOAD_DIR / ".secret_key"
    if Config.SECRET_KEY != "dev-secret-change-in-production":
        return Config.SECRET_KEY
    if key_file.exists():
        return key_file.read_text().strip()
    new_key = secrets.token_hex(48)
    key_file.write_text(new_key)
    return new_key

_SECRET_KEY = _ensure_secret_key()

app = Flask(__name__)
app.secret_key = _SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    WTF_CSRF_TIME_LIMIT=None,
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,   # 16 MB upload limit
)

csrf    = CSRFProtect(app)
limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri="memory://")

# ── Security headers on every response ────────────────────────────────────────
@app.after_request
def _security_headers(response):
    response.headers["X-Frame-Options"]           = "DENY"
    response.headers["X-Content-Type-Options"]    = "nosniff"
    response.headers["X-XSS-Protection"]          = "1; mode=block"
    response.headers["Referrer-Policy"]           = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"]        = "camera=(), microphone=(), geolocation=()"
    return response

# ── Brute-force login protection ──────────────────────────────────────────────
_login_attempts: dict = {}
_MAX_ATTEMPTS  = 5
_LOCKOUT_SECS  = 900  # 15 minutes

def _check_lockout(ip: str) -> tuple[bool, int]:
    now = time.time()
    data = _login_attempts.get(ip, {})
    until = data.get("until", 0)
    if until > now:
        return True, int(until - now)
    return False, 0

def _record_failure(ip: str):
    now = time.time()
    data = _login_attempts.get(ip, {"n": 0, "until": 0})
    if data["until"] < now:
        data["n"] += 1
    if data["n"] >= _MAX_ATTEMPTS:
        data["until"] = now + _LOCKOUT_SECS
    _login_attempts[ip] = data

def _clear_attempts(ip: str):
    _login_attempts.pop(ip, None)

# ── Encryption for sensitive settings at rest ─────────────────────────────────
def _get_fernet() -> Fernet:
    if not ENC_KEY_FILE.exists():
        ENC_KEY_FILE.write_bytes(Fernet.generate_key())
    return Fernet(ENC_KEY_FILE.read_bytes())

def _encrypt(value: str) -> str:
    if not value:
        return ""
    return _get_fernet().encrypt(value.encode()).decode()

def _decrypt(value: str) -> str:
    if not value:
        return ""
    try:
        return _get_fernet().decrypt(value.encode()).decode()
    except (InvalidToken, Exception):
        return value   # migration: may be plain text

# ── Audit log ─────────────────────────────────────────────────────────────────
def _audit(action: str, detail: str = ""):
    ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ip  = (request.remote_addr or "?") if request else "system"
    who = "admin" if session.get("logged_in") else "anon"
    line = f"[{ts}] [{ip}] [{who}] {action}"
    if detail:
        line += f" — {detail}"
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ── Email validation ──────────────────────────────────────────────────────────
_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')

def _valid_email(addr: str) -> bool:
    return bool(_EMAIL_RE.match((addr or "").strip()))


# ── auth ───────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if session.get("logged_in"):
        return redirect(url_for("index"))

    ip = request.remote_addr or "unknown"
    locked, remaining = _check_lockout(ip)
    if locked:
        mins = remaining // 60 + 1
        flash(f"Too many failed attempts. Try again in {mins} minute(s).", "danger")
        return render_template("login.html", locked=True, remaining=remaining)

    cfg = _load_settings()
    first_run = not cfg.get("admin_password_hash")  # never changed from default

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        stored_user = cfg.get("admin_username", "admin")
        stored_hash = cfg.get("admin_password_hash", "")
        pw_ok = (
            check_password_hash(stored_hash, password) if stored_hash
            else password == "admin123"
        )
        if username == stored_user and pw_ok:
            session.permanent = True
            session["logged_in"] = True
            _clear_attempts(ip)
            _audit("LOGIN_SUCCESS", username)
            return redirect(url_for("index"))
        _record_failure(ip)
        _audit("LOGIN_FAILED", username)
        locked, remaining = _check_lockout(ip)
        if locked:
            flash(f"Account locked for 15 minutes after too many failed attempts.", "danger")
        else:
            attempts_left = _MAX_ATTEMPTS - _login_attempts.get(ip, {}).get("n", 0)
            flash(f"Invalid username or password. {attempts_left} attempt(s) remaining.", "danger")

    return render_template("login.html", first_run=first_run)


@app.route("/logout")
def logout():
    _audit("LOGOUT")
    session.pop("logged_in", None)
    return redirect(url_for("login"))


# ── persistence helpers ────────────────────────────────────────────────────────

def _load_clients():
    return json.loads(SESSION_FILE.read_text()) if SESSION_FILE.exists() else []

def _save_clients(clients):
    SESSION_FILE.write_text(json.dumps(clients, ensure_ascii=False))

def _load_mapping():
    return json.loads(MAPPING_FILE.read_text()) if MAPPING_FILE.exists() else {}

def _save_mapping(m):
    MAPPING_FILE.write_text(json.dumps(m))

def _load_activity():
    if ACTIVITY_FILE.exists():
        return json.loads(ACTIVITY_FILE.read_text())
    return {"emails_sent": 0}

def _save_activity(a):
    ACTIVITY_FILE.write_text(json.dumps(a))

def _load_profiles():
    return json.loads(PROFILES_FILE.read_text()) if PROFILES_FILE.exists() else {}

def _save_profiles(p):
    PROFILES_FILE.write_text(json.dumps(p))

def _load_settings():
    defaults = {
        "company_name":        Config.COMPANY_NAME,
        "sender_name":         Config.SENDER_NAME,
        "smtp_host":           Config.SMTP_HOST,
        "smtp_port":           Config.SMTP_PORT,
        "smtp_user":           Config.SMTP_USER,
        "smtp_pass":           Config.SMTP_PASS,
        "email_subject":       "Your Account Statement – {{STATEMENT_PERIOD}}",
        "email_type":          "plain",
        "email_body": (
            "Dear {{CLIENT_NAME}},\n\n"
            "Please find your account statement for {{STATEMENT_PERIOD}} attached.\n\n"
            "Account No : {{ACCOUNT_NO}}\n"
            "Closing Balance : {{CLOSING_BALANCE}}\n\n"
            "For any queries, please reply to this email.\n\n"
            "Regards,\n{{SENDER_NAME}}"
        ),
        "email_html":          _default_html_template(),
        "admin_username":      "admin",
        "admin_password_hash": "",
        "logo_filename":       "",
        "brand_color":         "#1E3A5F",
    }
    if SETTINGS_FILE.exists():
        saved = json.loads(SETTINGS_FILE.read_text())
        # Decrypt SMTP password if it was stored encrypted
        if saved.get("smtp_pass"):
            saved["smtp_pass"] = _decrypt(saved["smtp_pass"])
        defaults.update(saved)
    return defaults

def _save_settings(d: dict):
    to_save = dict(d)
    # Encrypt SMTP password before persisting
    plain = to_save.get("smtp_pass", "")
    if plain and not plain.startswith("gAAA"):  # not already Fernet-encoded
        to_save["smtp_pass"] = _encrypt(plain)
    SETTINGS_FILE.write_text(json.dumps(to_save))

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


# ── error handlers ─────────────────────────────────────────────────────────────

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template("500.html"), 500


# ── routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    clients = _load_clients()
    activity = _load_activity()
    return render_template("index.html",
        client_count=len(clients),
        pdf_count=len(list(OUTPUT_DIR.glob("statement_*.pdf"))),
        invoice_count=len(list(OUTPUT_DIR.glob("invoice_*.pdf"))),
        loan_count=len(list(OUTPUT_DIR.glob("loan_schedule_*.pdf"))),
        portfolio_count=len(list(OUTPUT_DIR.glob("portfolio_*.pdf"))),
        emails_sent=activity.get("emails_sent", 0),
    )


# ── Upload + column mapper ─────────────────────────────────────────────────────

@app.route("/upload", methods=["GET", "POST"])
@login_required
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
        return redirect(url_for("map_columns"))
    return render_template("upload.html")


@app.route("/map-columns")
@login_required
def map_columns():
    xlsx = UPLOAD_DIR / "clients.xlsx"
    if not xlsx.exists():
        flash("Upload an Excel file first.", "warning")
        return redirect(url_for("upload"))

    detector = ColumnDetector(xlsx)
    sheets = detector.sheet_names

    def guess(candidates):
        names_lower = {s.lower(): s for s in sheets}
        for c in candidates:
            if c.lower() in names_lower:
                return names_lower[c.lower()]
        return sheets[0]

    client_sheet = guess(["clients", "client", "master", "customers", "customer"])
    txn_sheet    = guess(["transactions", "transaction", "txn", "statement", "ledger"])

    client_cols = detector.columns_for(client_sheet)
    txn_cols    = detector.columns_for(txn_sheet)
    client_sug  = detector.auto_suggest(client_sheet, "clients")
    txn_sug     = detector.auto_suggest(txn_sheet, "transactions")
    flat_hint   = detector.detect_flat_mode(client_sheet)
    preview     = detector.preview_rows(client_sheet, 3)

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
@login_required
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
@login_required
def clients():
    data = _load_clients()
    settings = _load_settings()
    return render_template("clients.html", clients=data,
                           has_template=TEMPLATE_PATH.exists(),
                           settings=settings)


@app.route("/generate", methods=["POST"])
@login_required
def generate():
    clients = _load_clients()
    if not clients:
        return jsonify({"error": "No clients loaded."}), 400
    settings = _load_settings()
    company  = request.form.get("company_name") or settings["company_name"]
    period   = request.form.get("statement_period", "")
    mode     = request.form.get("mode", "auto")
    logo_p   = UPLOAD_DIR / settings.get("logo_filename", "") if settings.get("logo_filename") else None
    builder  = StatementBuilder(OUTPUT_DIR,
                                brand_color=settings.get("brand_color", ""),
                                logo_path=logo_p)
    results  = []
    for c in clients:
        try:
            pdf = builder.build(c, company, period, mode=mode,
                                word_template=TEMPLATE_PATH if mode == "template" else None)
            results.append({"account": c["account_no"], "name": c["name"],
                            "status": "ok", "file": pdf.name})
        except Exception as exc:
            results.append({"account": c["account_no"], "name": c["name"],
                            "status": "error", "error": str(exc)})
    return jsonify({"results": results, "period": period})


@app.route("/download/<account_no>")
@login_required
def download(account_no):
    path = OUTPUT_DIR / f"statement_{account_no}.pdf"
    if path.exists():
        return send_file(path, as_attachment=True, download_name=f"Statement_{account_no}.pdf")
    return "File not found", 404


@app.route("/download-all")
@login_required
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
@login_required
@limiter.limit("5 per 10 minutes")
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
    activity = _load_activity()
    results = []
    sent_count = 0
    for c in clients:
        acct = c["account_no"]
        if selected and acct not in selected:
            continue
        pdf_path = OUTPUT_DIR / f"statement_{acct}.pdf"
        if not pdf_path.exists():
            results.append({"account": acct, "name": c["name"],
                            "status": "skipped", "reason": "PDF not generated"})
            continue
        # Validate client email address before attempting send
        if not _valid_email(c.get("email", "")):
            results.append({"account": acct, "name": c["name"],
                            "status": "skipped", "reason": f"Invalid email: {c.get('email','')}"})
            continue
        try:
            plain = _render_content(settings["email_body"], c, settings, period)
            html  = _render_content(settings["email_html"], c, settings, period) \
                    if settings.get("email_type") == "html" else None
            sender.send(to_email=c["email"], to_name=c["name"],
                        subject=subject_t, body=plain, html_body=html,
                        attachment_path=pdf_path,
                        attachment_name=f"Statement_{acct}.pdf")
            results.append({"account": acct, "name": c["name"],
                            "status": "sent", "email": c["email"]})
            _audit("EMAIL_SENT", f"{c['name']} <{c['email']}> period={period}")
            sent_count += 1
        except Exception as exc:
            _audit("EMAIL_FAILED", f"{c['name']} <{c.get('email','')}> err={exc}")
            results.append({"account": acct, "name": c["name"],
                            "status": "error", "error": str(exc)})

    activity["emails_sent"] = activity.get("emails_sent", 0) + sent_count
    _save_activity(activity)
    return jsonify({"results": results})


@app.route("/upload-template", methods=["POST"])
@login_required
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
@login_required
def settings():
    cfg = _load_settings()
    if request.method == "POST":
        # Update standard settings fields
        for key in ("company_name", "sender_name", "smtp_host", "smtp_port",
                    "smtp_user", "smtp_pass", "email_subject", "email_type",
                    "email_body", "email_html"):
            if key in request.form:
                cfg[key] = request.form[key]

        # Username change (always apply if provided)
        new_user = request.form.get("admin_username", "").strip()
        if new_user:
            cfg["admin_username"] = new_user

        # Password change
        new_pass = request.form.get("new_password", "").strip()
        confirm_pass = request.form.get("confirm_password", "").strip()
        if new_pass:
            if new_pass != confirm_pass:
                flash("Passwords do not match. Settings not saved.", "danger")
                return render_template("settings.html", cfg=cfg)
            cfg["admin_password_hash"] = generate_password_hash(new_pass)
            flash("Password updated successfully.", "success")

        _save_settings(cfg)
        _audit("SETTINGS_SAVED")
        if not new_pass:
            flash("Settings saved.", "success")
        return redirect(url_for("settings"))
    return render_template("settings.html", cfg=cfg)


@app.route("/audit-log")
@login_required
def audit_log():
    if not AUDIT_LOG.exists():
        return jsonify({"lines": []})
    lines = AUDIT_LOG.read_text(encoding="utf-8").splitlines()
    return jsonify({"lines": lines[-100:]})


@app.route("/test-smtp", methods=["POST"])
@login_required
@limiter.limit("5 per minute")
def test_smtp():
    s = _load_settings()
    test_email = request.form.get("test_email", "").strip()
    if not test_email or not _valid_email(test_email):
        return jsonify({"ok": False, "error": "Enter a valid email address."})
    try:
        EmailSender(s["smtp_host"], s["smtp_port"], s["smtp_user"],
                    s["smtp_pass"], s["sender_name"]).send(
            to_email=test_email, to_name="Test",
            subject=f"SMTP Test – {s['company_name']}",
            body="SMTP is working correctly. Your FinTech SaaS email configuration is set up.",
        )
        _audit("SMTP_TEST_OK", test_email)
        return jsonify({"ok": True})
    except Exception as exc:
        _audit("SMTP_TEST_FAILED", str(exc))
        return jsonify({"ok": False, "error": str(exc)})


# ── Fintech modules ────────────────────────────────────────────────────────────

@app.route("/invoices")
@login_required
def invoices():
    settings = _load_settings()
    return render_template("invoices.html", settings=settings)


@app.route("/generate-invoice", methods=["POST"])
@login_required
def generate_invoice():
    from modules.invoice_generator import InvoiceGenerator
    data = request.get_json()
    try:
        gen = InvoiceGenerator(OUTPUT_DIR)
        pdf = gen.generate(data["client"], data["company"])
        return jsonify({"ok": True, "file": pdf.name,
                        "invoice_no": data["client"].get("invoice_no")})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})


@app.route("/loans")
@login_required
def loans():
    settings = _load_settings()
    return render_template("loans.html", settings=settings)


@app.route("/generate-loan-schedule", methods=["POST"])
@login_required
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
@login_required
def portfolio():
    settings = _load_settings()
    return render_template("portfolio.html", settings=settings)


@app.route("/generate-portfolio", methods=["POST"])
@login_required
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
@login_required
def download_output(filename):
    # Prevent path traversal — keep only the bare filename
    safe = Path(filename).name
    if not re.match(r'^[a-zA-Z0-9_\-\.]{1,120}$', safe):
        return "Invalid filename", 400
    path = OUTPUT_DIR / safe
    if path.exists() and path.is_file():
        return send_file(path, as_attachment=True)
    return "File not found", 404


# ── Logo ───────────────────────────────────────────────────────────────────────

@app.route("/logo")
def serve_logo():
    cfg = _load_settings()
    logo_file = cfg.get("logo_filename", "")
    if logo_file:
        path = UPLOAD_DIR / logo_file
        if path.exists():
            return send_file(path)
    return "Not found", 404


@app.route("/upload-logo", methods=["POST"])
@login_required
def upload_logo():
    f = request.files.get("logo_file")
    if not f or not f.filename:
        return jsonify({"error": "No file provided"}), 400
    ext = Path(f.filename).suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"):
        return jsonify({"error": "Only PNG/JPG/GIF/SVG/WEBP allowed"}), 400
    for old in UPLOAD_DIR.glob("logo.*"):
        old.unlink(missing_ok=True)
    logo_path = UPLOAD_DIR / f"logo{ext}"
    f.save(logo_path)
    cfg = _load_settings()
    cfg["logo_filename"] = logo_path.name
    _save_settings(cfg)
    return jsonify({"ok": True, "url": url_for("serve_logo")})


# ── Email template import from Word ────────────────────────────────────────────

@app.route("/import-email-template", methods=["POST"])
@login_required
def import_email_template():
    f = request.files.get("template_file")
    if not f or not f.filename.lower().endswith(".docx"):
        return jsonify({"error": "Please upload a .docx file."}), 400
    try:
        import mammoth
        result = mammoth.convert_to_html(f)
        return jsonify({"ok": True, "html": result.value})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


# ── Mapping profiles ────────────────────────────────────────────────────────────

@app.route("/mapping-profiles")
@login_required
def get_mapping_profiles():
    return jsonify(_load_profiles())


@app.route("/save-mapping-profile", methods=["POST"])
@login_required
def save_mapping_profile():
    data = request.get_json()
    name = (data or {}).get("name", "").strip()
    mapping = (data or {}).get("mapping")
    if not name or not mapping:
        return jsonify({"error": "Name and mapping required"}), 400
    profiles = _load_profiles()
    profiles[name] = mapping
    _save_profiles(profiles)
    return jsonify({"ok": True})


@app.route("/delete-mapping-profile", methods=["POST"])
@login_required
def delete_mapping_profile():
    data = request.get_json()
    name = (data or {}).get("name", "")
    profiles = _load_profiles()
    profiles.pop(name, None)
    _save_profiles(profiles)
    return jsonify({"ok": True})


# ── Template Designer ─────────────────────────────────────────────────────────

SAVED_DOC_TEMPLATE = UPLOAD_DIR / "document_template.html"

@app.route("/template-designer")
@login_required
def template_designer():
    saved_html = SAVED_DOC_TEMPLATE.read_text(encoding="utf-8") if SAVED_DOC_TEMPLATE.exists() else ""
    return render_template("template_designer.html", saved_html=saved_html)


@app.route("/template-designer/load-excel", methods=["POST"])
@login_required
def td_load_excel():
    import pandas as pd
    f = request.files.get("excel_file")
    if not f:
        return jsonify({"error": "No file uploaded"}), 400
    try:
        df = pd.read_excel(f, nrows=10)
        columns = [str(c) for c in df.columns]
        sample = {}
        if len(df) > 0:
            row = df.iloc[0]
            for col in columns:
                val = row[col]
                sample[col] = "" if pd.isna(val) else str(val)
        return jsonify({"columns": columns, "sample": sample})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/template-designer/import-word", methods=["POST"])
@login_required
def td_import_word():
    import mammoth
    f = request.files.get("word_file")
    if not f:
        return jsonify({"error": "No file"}), 400
    try:
        result = mammoth.convert_to_html(f)
        return jsonify({"ok": True, "html": result.value})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/template-designer/preview", methods=["POST"])
@login_required
def td_preview():
    data = request.get_json(force=True)
    html = data.get("html", "")
    sample = data.get("sample", {})
    for col, val in sample.items():
        html = html.replace("{{" + col + "}}", str(val))
        html = html.replace("{{ " + col + " }}", str(val))
    return jsonify({"html": html})


@app.route("/template-designer/save", methods=["POST"])
@login_required
def td_save():
    data = request.get_json(force=True)
    html = data.get("html", "").strip()
    if not html:
        return jsonify({"error": "Template is empty"}), 400
    SAVED_DOC_TEMPLATE.write_text(html, encoding="utf-8")
    _audit("TEMPLATE_SAVED", f"document_template.html ({len(html)} chars)")
    return jsonify({"ok": True})


# ── Template download ──────────────────────────────────────────────────────────

@app.route("/download-template")
@login_required
def download_template():
    from generate_sample import make_sample_excel
    path = make_sample_excel(UPLOAD_DIR / "sample_template.xlsx")
    return send_file(path, as_attachment=True, download_name="client_data_template.xlsx")


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1", port=5000)
