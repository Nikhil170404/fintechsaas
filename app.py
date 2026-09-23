import json
import os
import re
import secrets
import shutil
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
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from modules import db
from modules.column_detector import ColumnDetector, ALIASES, FIELD_LABELS
from modules.email_sender import EmailSender
from modules.excel_reader import ExcelReader
from modules.statement_builder import StatementBuilder
from modules import local_ai

load_dotenv()

DATA_DIR      = Path("data")
TENANTS_DIR   = DATA_DIR / "tenants"
LEGACY_UPLOAD = Path("uploads")   # pre-multi-tenant install, migrated on first boot
LEGACY_OUTPUT = Path("output")

DATA_DIR.mkdir(exist_ok=True)
TENANTS_DIR.mkdir(parents=True, exist_ok=True)

db.init_db()

# ── Auto-generate strong secret key if default is still set ───────────────────
def _ensure_secret_key() -> str:
    key_file = DATA_DIR / ".secret_key"
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

# ── Tenant-scoped storage ──────────────────────────────────────────────────────

def _tenant_id() -> int:
    return session["tenant_id"]

def _tenant_dirs(tenant_id: int = None) -> dict:
    tid = tenant_id or _tenant_id()
    base = TENANTS_DIR / str(tid)
    uploads = base / "uploads"
    output  = base / "output"
    documents = base / "documents"
    uploads.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    documents.mkdir(parents=True, exist_ok=True)
    return {"base": base, "uploads": uploads, "output": output, "documents": documents}

def _client_documents_dir(tenant_id: int = None) -> Path:
    path = _tenant_dirs(tenant_id)["documents"] / "clients"
    path.mkdir(parents=True, exist_ok=True)
    return path

def _safe_account_file_stem(account_no: str) -> str:
    # Account numbers are application-controlled Excel values; normalize them
    # before using them as a file name to prevent traversal and hidden files.
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", account_no).strip("._")
    if not safe:
        raise ValueError("Invalid client account number.")
    return safe

def _client_document_path(account_no: str) -> Path:
    return _client_documents_dir() / f"{_safe_account_file_stem(account_no)}.pdf"

def _template_path(tenant_id: int = None) -> Path:
    return _tenant_dirs(tenant_id)["uploads"] / "word_template.docx"

def _saved_doc_template_path(tenant_id: int = None) -> Path:
    return _tenant_dirs(tenant_id)["uploads"] / "document_template.html"

def _enc_key_file(tenant_id: int = None) -> Path:
    return _tenant_dirs(tenant_id)["uploads"] / ".enc_key"

# ── Encryption for sensitive settings at rest (per-tenant key) ────────────────
def _get_fernet(tenant_id: int = None) -> Fernet:
    key_file = _enc_key_file(tenant_id)
    if not key_file.exists():
        key_file.write_bytes(Fernet.generate_key())
    return Fernet(key_file.read_bytes())

def _encrypt(value: str, tenant_id: int = None) -> str:
    if not value:
        return ""
    return _get_fernet(tenant_id).encrypt(value.encode()).decode()

def _decrypt(value: str, tenant_id: int = None) -> str:
    if not value:
        return ""
    try:
        return _get_fernet(tenant_id).decrypt(value.encode()).decode()
    except (InvalidToken, Exception):
        return value   # migration: may be plain text

# ── Audit log ─────────────────────────────────────────────────────────────────
def _audit(action: str, detail: str = ""):
    ip  = (request.remote_addr or "?") if request else "system"
    who = session.get("username", "anon")
    tid = session.get("tenant_id")
    db.add_audit(tid, ip, who, action, detail)

# ── Email validation ──────────────────────────────────────────────────────────
_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')

def _valid_email(addr: str) -> bool:
    return bool(_EMAIL_RE.match((addr or "").strip()))

_SLUG_RE = re.compile(r'[^a-z0-9]+')

def _slugify(name: str) -> str:
    base = _SLUG_RE.sub("-", name.lower()).strip("-") or "company"
    slug = base
    n = 1
    while db.slug_exists(slug):
        n += 1
        slug = f"{base}-{n}"
    return slug


# ── auth ───────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapped


def owner_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        if session.get("role") != "owner":
            return "Forbidden — owner access required", 403
        return f(*args, **kwargs)
    return wrapped


@app.route("/signup", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def signup():
    if session.get("user_id"):
        return redirect(url_for("index"))

    if request.method == "POST":
        company  = request.form.get("company_name", "").strip()
        username = request.form.get("username", "").strip()
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm_password", "")

        if not company or not username or not email or not password:
            flash("All fields are required.", "danger")
            return render_template("signup.html")
        if not _valid_email(email):
            flash("Please enter a valid email address.", "danger")
            return render_template("signup.html")
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return render_template("signup.html")
        if password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("signup.html")
        if db.username_or_email_taken(username, email):
            flash("That username or email is already registered.", "danger")
            return render_template("signup.html")

        slug = _slugify(company)
        tenant_id = db.create_tenant(company, slug)
        user_id = db.create_user(tenant_id, username, email,
                                  generate_password_hash(password), role="owner")
        db.set_settings_blob(tenant_id, _default_settings(company))

        session.permanent = True
        session["user_id"]   = user_id
        session["tenant_id"] = tenant_id
        session["username"]  = username
        session["role"]      = "owner"
        _audit("SIGNUP", f"company={company}")
        flash("Welcome! Your account has been created.", "success")
        return redirect(url_for("index"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if session.get("user_id"):
        return redirect(url_for("index"))

    ip = request.remote_addr or "unknown"
    locked, remaining = _check_lockout(ip)
    if locked:
        mins = remaining // 60 + 1
        flash(f"Too many failed attempts. Try again in {mins} minute(s).", "danger")
        return render_template("login.html", locked=True, remaining=remaining)

    no_accounts_yet = db.tenant_count() == 0

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = db.get_user_by_username(username)
        pw_ok = user is not None and check_password_hash(user["password_hash"], password)
        if pw_ok:
            session.permanent = True
            session["user_id"]   = user["id"]
            session["tenant_id"] = user["tenant_id"]
            session["username"]  = user["username"]
            session["role"]      = user["role"]
            _clear_attempts(ip)
            _audit("LOGIN_SUCCESS", username)
            return redirect(url_for("index"))
        _record_failure(ip)
        db.add_audit(None, ip, username or "anon", "LOGIN_FAILED", username)
        locked, remaining = _check_lockout(ip)
        if locked:
            flash("Account locked for 15 minutes after too many failed attempts.", "danger")
        else:
            attempts_left = _MAX_ATTEMPTS - _login_attempts.get(ip, {}).get("n", 0)
            flash(f"Invalid username or password. {attempts_left} attempt(s) remaining.", "danger")

    return render_template("login.html", no_accounts_yet=no_accounts_yet)


@app.route("/logout")
def logout():
    _audit("LOGOUT")
    session.clear()
    return redirect(url_for("login"))


@app.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per 10 minutes")
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        user = db.get_user_by_email(email) if _valid_email(email) else None
        if user:
            token = secrets.token_urlsafe(32)
            expires_at = int(time.time()) + 3600
            db.create_password_reset(user["id"], token, expires_at)
            reset_url = url_for("reset_password", token=token, _external=True)
            sent = False
            if Config.SYS_SMTP_HOST and Config.SYS_SMTP_USER and Config.SYS_SMTP_PASS:
                try:
                    EmailSender(Config.SYS_SMTP_HOST, Config.SYS_SMTP_PORT,
                                Config.SYS_SMTP_USER, Config.SYS_SMTP_PASS,
                                "FinTech SaaS").send(
                        to_email=user["email"], to_name=user["username"],
                        subject="Reset your FinTech SaaS password",
                        body=f"Click the link below to reset your password (valid 1 hour):\n\n{reset_url}\n\n"
                             "If you didn't request this, ignore this email.",
                    )
                    sent = True
                except Exception as exc:
                    db.add_audit(user["tenant_id"], request.remote_addr, user["username"],
                                 "PASSWORD_RESET_EMAIL_FAILED", str(exc))
            if not sent:
                # No system SMTP configured (or send failed) — log the link so local/dev use still works.
                db.add_audit(user["tenant_id"], request.remote_addr, user["username"],
                             "PASSWORD_RESET_LINK", reset_url)
        flash("If that email is registered, a reset link has been sent (or logged for the admin).", "info")
        return redirect(url_for("login"))
    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit("10 per 10 minutes")
def reset_password(token):
    reset = db.get_valid_reset(token)
    if not reset:
        flash("This reset link is invalid or has expired.", "danger")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm_password", "")
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return render_template("reset_password.html", token=token)
        if password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("reset_password.html", token=token)
        db.update_password(reset["user_id"], generate_password_hash(password))
        db.mark_reset_used(token)
        user = db.get_user_by_id(reset["user_id"])
        db.add_audit(user["tenant_id"], request.remote_addr, user["username"], "PASSWORD_RESET_OK")
        flash("Password updated. Please sign in.", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html", token=token)


# ── Team management (owner only) ───────────────────────────────────────────────

@app.route("/team/add", methods=["POST"])
@owner_required
def team_add():
    username = request.form.get("username", "").strip()
    email    = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    if not username or not email or not password:
        flash("Username, email and password are all required.", "danger")
        return redirect(url_for("settings", tab="team"))
    if not _valid_email(email):
        flash("Please enter a valid email address.", "danger")
        return redirect(url_for("settings", tab="team"))
    if len(password) < 8:
        flash("Password must be at least 8 characters.", "danger")
        return redirect(url_for("settings", tab="team"))
    if db.username_or_email_taken(username, email):
        flash("That username or email is already taken.", "danger")
        return redirect(url_for("settings", tab="team"))
    db.create_user(_tenant_id(), username, email, generate_password_hash(password), role="staff")
    _audit("TEAM_MEMBER_ADDED", username)
    flash(f"Added {username} as a staff member.", "success")
    return redirect(url_for("settings", tab="team"))


@app.route("/team/remove/<int:user_id>", methods=["POST"])
@owner_required
def team_remove(user_id):
    target = db.get_user_by_id(user_id)
    if not target or target["tenant_id"] != _tenant_id():
        flash("User not found.", "danger")
        return redirect(url_for("settings", tab="team"))
    if user_id == session["user_id"]:
        flash("You can't remove your own account.", "danger")
        return redirect(url_for("settings", tab="team"))
    if target["role"] == "owner" and db.count_owners(_tenant_id()) <= 1:
        flash("You can't remove the last owner.", "danger")
        return redirect(url_for("settings", tab="team"))
    db.deactivate_user(_tenant_id(), user_id)
    _audit("TEAM_MEMBER_REMOVED", target["username"])
    flash(f"Removed {target['username']}.", "success")
    return redirect(url_for("settings", tab="team"))


# ── persistence helpers (per-tenant, backed by SQLite JSON blobs) ─────────────

def _load_clients():
    return db.get_clients_blob(_tenant_id()) or []

def _save_clients(clients):
    db.set_clients_blob(_tenant_id(), clients)

def _load_mapping():
    return db.get_mapping_blob(_tenant_id()) or {}

def _save_mapping(m):
    db.set_mapping_blob(_tenant_id(), m)

def _load_activity():
    return db.get_activity_blob(_tenant_id()) or {"emails_sent": 0}

def _save_activity(a):
    db.set_activity_blob(_tenant_id(), a)

def _load_profiles():
    return db.get_profiles_blob(_tenant_id()) or {}

def _save_profiles(p):
    db.set_profiles_blob(_tenant_id(), p)

def _default_settings(company_name: str = None):
    return {
        "company_name":        company_name or Config.COMPANY_NAME,
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
        "logo_filename":       "",
        "brand_color":         "#1E3A5F",
        # AI is off until an owner explicitly enables it.  The endpoint is
        # deliberately fixed in modules/local_ai.py to localhost only.
        "local_ai_enabled":    False,
        "local_ai_model":      "",
    }

def _load_settings():
    defaults = _default_settings()
    saved = db.get_settings_blob(_tenant_id())
    if saved:
        if saved.get("smtp_pass"):
            saved["smtp_pass"] = _decrypt(saved["smtp_pass"])
        defaults.update(saved)
    return defaults

def _save_settings(d: dict):
    to_save = dict(d)
    plain = to_save.get("smtp_pass", "")
    if plain and not plain.startswith("gAAA"):  # not already Fernet-encoded
        to_save["smtp_pass"] = _encrypt(plain)
    db.set_settings_blob(_tenant_id(), to_save)

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

_TAG_RE = re.compile(r'\{\{\s*([^{}]+?)\s*\}\}')

def _normalize_tag(s: str) -> str:
    """CLIENT_NAME, client_name, Client Name, {{ Client-Name }} all match the
    same tag — templates shouldn't have to match an exact spelling/casing."""
    return re.sub(r'[^A-Z0-9]', '', s.upper())

def _placeholder_values(client: dict, settings: dict, period: str) -> dict:
    txns = client.get("transactions", [])
    closing = txns[-1]["balance"] if txns else client.get("opening_balance", 0)
    total_debit = sum(t["debit"] for t in txns)
    total_credit = sum(t["credit"] for t in txns)
    values = {
        "CLIENTNAME":      client.get("name", ""),
        "NAME":            client.get("name", ""),
        "ACCOUNTNO":       client.get("account_no", ""),
        "EMAIL":           client.get("email", ""),
        "PHONE":           client.get("phone", ""),
        "ADDRESS":         client.get("address", ""),
        "ACCOUNTTYPE":     client.get("account_type", ""),
        "OPENINGBALANCE":  f"₹{client.get('opening_balance', 0):,.2f}",
        "STATEMENTPERIOD": period,
        "CLOSINGBALANCE":  f"₹{closing:,.2f}",
        "TOTALDEBIT":      f"₹{total_debit:,.2f}",
        "TOTALCREDIT":     f"₹{total_credit:,.2f}",
        "SENDERNAME":      settings.get("sender_name", ""),
        "COMPANYNAME":     settings.get("company_name", ""),
    }
    # Any other column from the uploaded Excel that isn't one of the fixed
    # fields above — this is what lets a template use {{AnyColumnName}} for
    # whatever the company's sheet actually has (branch, RM name, GST no...),
    # not just a fixed list. Fixed fields above always win on a name clash.
    for col, val in client.get("extra_columns", {}).items():
        values.setdefault(_normalize_tag(col), val)
    return values

def _render_content(template: str, client: dict, settings: dict, period: str) -> str:
    values = _placeholder_values(client, settings, period)
    def _sub(m: re.Match) -> str:
        key = _normalize_tag(m.group(1))
        return str(values[key]) if key in values else m.group(0)
    return _TAG_RE.sub(_sub, template)


# ── one-time legacy migration (pre-multi-tenant single-admin install) ─────────

def _migrate_legacy_if_needed():
    legacy_settings = LEGACY_UPLOAD / "settings.json"
    if db.tenant_count() > 0 or not legacy_settings.exists():
        return

    old = json.loads(legacy_settings.read_text())
    company = old.get("company_name") or "Legacy Company"
    slug = _slugify(company)
    tenant_id = db.create_tenant(company, slug)

    username = old.get("admin_username", "admin")
    pw_hash = old.get("admin_password_hash") or generate_password_hash("admin123")
    email = f"{username}@{slug}.local"
    db.create_user(tenant_id, username, email, pw_hash, role="owner")

    old.pop("admin_username", None)
    old.pop("admin_password_hash", None)
    db.set_settings_blob(tenant_id, old)

    legacy_session = LEGACY_UPLOAD / "session_data.json"
    if legacy_session.exists():
        db.set_clients_blob(tenant_id, json.loads(legacy_session.read_text()))
    legacy_mapping = LEGACY_UPLOAD / "column_mapping.json"
    if legacy_mapping.exists():
        db.set_mapping_blob(tenant_id, json.loads(legacy_mapping.read_text()))
    legacy_activity = LEGACY_UPLOAD / "activity.json"
    if legacy_activity.exists():
        db.set_activity_blob(tenant_id, json.loads(legacy_activity.read_text()))
    legacy_profiles = LEGACY_UPLOAD / "mapping_profiles.json"
    if legacy_profiles.exists():
        db.set_profiles_blob(tenant_id, json.loads(legacy_profiles.read_text()))

    dirs = _tenant_dirs(tenant_id)
    for item in LEGACY_UPLOAD.iterdir():
        if item.name in ("settings.json", "session_data.json", "column_mapping.json",
                          "activity.json", "mapping_profiles.json", "audit.log"):
            continue
        dest = dirs["uploads"] / item.name
        if item.is_file():
            shutil.copy2(item, dest)
    if LEGACY_OUTPUT.exists():
        for item in LEGACY_OUTPUT.iterdir():
            if item.is_file():
                shutil.copy2(item, dirs["output"] / item.name)

    legacy_audit = LEGACY_UPLOAD / "audit.log"
    if legacy_audit.exists():
        for line in legacy_audit.read_text(encoding="utf-8").splitlines():
            db.add_audit(tenant_id, "migration", "system", "LEGACY_AUDIT", line)

    db.add_audit(tenant_id, "system", "system", "LEGACY_MIGRATION_COMPLETE",
                 f"migrated from uploads/ → tenant {tenant_id}")

_migrate_legacy_if_needed()


# ── error handlers ─────────────────────────────────────────────────────────────

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template("500.html"), 500

@app.errorhandler(CSRFError)
def csrf_error(e):
    # A stale/expired form (long-open tab, browser back-button, cleared
    # cookies, cross-device session mismatch) is expected to happen
    # occasionally — bounce back to a fresh form instead of a raw 400.
    flash("Your session expired or the page was open too long. Please try again.", "warning")
    if request.path.startswith(("/login", "/signup", "/forgot-password", "/reset-password")):
        return redirect(request.path)
    if session.get("user_id"):
        return redirect(request.referrer or url_for("index"))
    return redirect(url_for("login"))


# ── routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    clients = _load_clients()
    activity = _load_activity()
    output_dir = _tenant_dirs()["output"]
    return render_template("index.html",
        client_count=len(clients),
        pdf_count=len(list(output_dir.glob("statement_*.pdf"))),
        invoice_count=len(list(output_dir.glob("invoice_*.pdf"))),
        loan_count=len(list(output_dir.glob("loan_schedule_*.pdf"))),
        portfolio_count=len(list(output_dir.glob("portfolio_*.pdf"))),
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
        dest = _tenant_dirs()["uploads"] / "clients.xlsx"
        f.save(dest)
        return redirect(url_for("map_columns"))
    return render_template("upload.html")


@app.route("/map-columns")
@login_required
def map_columns():
    xlsx = _tenant_dirs()["uploads"] / "clients.xlsx"
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

    xlsx = _tenant_dirs()["uploads"] / "clients.xlsx"
    try:
        reader = ExcelReader(xlsx, mapping)
        clients = reader.get_clients()
        _save_clients(clients)
        flash(f"Loaded {len(clients)} client(s) with your column mapping.", "success")
        return redirect(url_for("wizard_template"))
    except Exception as exc:
        flash(f"Error reading Excel with this mapping: {exc}", "danger")
        return redirect(url_for("map_columns"))


# ── Wizard step 3: drag-and-drop email template ────────────────────────────────

MERGE_TAGS = [
    ("CLIENT_NAME",      "Client Name"),
    ("ACCOUNT_NO",       "Account No"),
    ("EMAIL",            "Email"),
    ("PHONE",            "Phone"),
    ("ADDRESS",          "Address"),
    ("ACCOUNT_TYPE",     "Account Type"),
    ("OPENING_BALANCE",  "Opening Balance"),
    ("CLOSING_BALANCE",  "Closing Balance"),
    ("TOTAL_DEBIT",      "Total Debit"),
    ("TOTAL_CREDIT",     "Total Credit"),
    ("STATEMENT_PERIOD", "Statement Period"),
    ("COMPANY_NAME",     "Company Name"),
    ("SENDER_NAME",      "Sender Name"),
]


@app.route("/wizard/template", methods=["GET", "POST"])
@login_required
def wizard_template():
    cfg = _load_settings()
    if request.method == "POST":
        cfg["email_subject"] = request.form.get("email_subject", cfg["email_subject"])
        cfg["email_type"]    = request.form.get("email_type", cfg["email_type"])
        cfg["email_body"]    = request.form.get("email_body_plain", cfg["email_body"])
        raw_html = request.form.get("email_html", cfg["email_html"])
        try:
            from modules.html_utils import inline_and_extract_body
            cfg["email_html"] = inline_and_extract_body(f"<html><body>{raw_html}</body></html>")
        except Exception:
            cfg["email_html"] = raw_html
        _save_settings(cfg)
        _audit("EMAIL_TEMPLATE_SAVED")
        flash("Email template saved.", "success")
        return redirect(url_for("clients"))

    clients_list = _load_clients()
    body_match = re.search(r'<body[^>]*>([\s\S]*?)</body>', cfg["email_html"], re.IGNORECASE)
    editor_html = body_match.group(1).strip() if body_match else cfg["email_html"]

    # Any column the company's own Excel actually has — beyond the fixed set
    # above — shows up here too, so {{AnyColumnName}} works for whatever they
    # uploaded (branch, RM name, GST no, ...), not just a fixed field list.
    all_tags = list(MERGE_TAGS)
    seen = {_normalize_tag(t) for t, _ in MERGE_TAGS}
    if clients_list:
        for col in clients_list[0].get("extra_columns", {}):
            tag = _normalize_tag(col)
            if tag and tag not in seen:
                all_tags.append((col, col))
                seen.add(tag)

    return render_template("wizard_template.html", cfg=cfg, editor_html=editor_html,
                           clients=clients_list, merge_tags=all_tags)


@app.route("/wizard/template/preview", methods=["POST"])
@login_required
def wizard_template_preview():
    data = request.get_json(force=True) or {}
    html = data.get("html", "")
    account_no = data.get("account_no", "")
    period = data.get("period", "August 2026")

    clients_list = _load_clients()
    if not clients_list:
        return jsonify({"error": "Upload client data first."}), 400
    client = next((c for c in clients_list if c["account_no"] == account_no), clients_list[0])
    settings = _load_settings()
    merged = _render_content(html, client, settings, period)
    return jsonify({"ok": True, "html": merged, "client": {
        "account_no": client["account_no"], "name": client["name"],
    }})


# ── Clients + statements ───────────────────────────────────────────────────────

@app.route("/clients")
@login_required
def clients():
    data = _load_clients()
    settings = _load_settings()
    return render_template("clients.html", clients=data,
                           has_template=_template_path().exists(),
                           settings=settings,
                           client_document_accounts={
                               path.stem for path in _client_documents_dir().glob("*.pdf")
                           },
                           account_file_stem=_safe_account_file_stem)


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
    dirs     = _tenant_dirs()
    logo_p   = dirs["uploads"] / settings.get("logo_filename", "") if settings.get("logo_filename") else None
    builder  = StatementBuilder(dirs["output"],
                                brand_color=settings.get("brand_color", ""),
                                logo_path=logo_p)
    results  = []
    for c in clients:
        try:
            pdf = builder.build(c, company, period, mode=mode,
                                word_template=_template_path() if mode == "template" else None)
            results.append({"account": c["account_no"], "name": c["name"],
                            "status": "ok", "file": pdf.name})
        except Exception as exc:
            results.append({"account": c["account_no"], "name": c["name"],
                            "status": "error", "error": str(exc)})
    return jsonify({"results": results, "period": period})


@app.route("/download/<account_no>")
@login_required
def download(account_no):
    path = _tenant_dirs()["output"] / f"statement_{account_no}.pdf"
    if path.exists():
        return send_file(path, as_attachment=True, download_name=f"Statement_{account_no}.pdf")
    return "File not found", 404


@app.route("/download-all")
@login_required
def download_all():
    output_dir = _tenant_dirs()["output"]
    pdfs = list(output_dir.glob("statement_*.pdf"))
    if not pdfs:
        flash("No PDFs generated yet.", "warning")
        return redirect(url_for("clients"))
    zip_path = output_dir / "All_Statements.zip"
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
    selected  = set(request.form.getlist("selected"))
    if not selected:
        # An empty selection must mean "send to no one" — never silently fall
        # back to sending everyone, which would send statements to clients
        # the user did not choose.
        return jsonify({"error": "No clients selected. Select at least one client before sending."}), 400
    settings  = _load_settings()
    output_dir = _tenant_dirs()["output"]
    period    = request.form.get("statement_period", "")
    attach_client_document = request.form.get("attach_client_document") == "1"
    subject_t = settings["email_subject"].replace("{{STATEMENT_PERIOD}}", period)
    sender    = EmailSender(settings["smtp_host"], settings["smtp_port"],
                            settings["smtp_user"], settings["smtp_pass"],
                            settings["sender_name"])
    activity = _load_activity()
    results = []
    sent_count = 0
    for c in clients:
        acct = c["account_no"]
        if acct not in selected:
            continue
        pdf_path = output_dir / f"statement_{acct}.pdf"
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
            attachments = [(pdf_path, f"Statement_{acct}.pdf")]
            if attach_client_document:
                client_pdf = _client_document_path(acct)
                if not client_pdf.exists():
                    results.append({"account": acct, "name": c["name"],
                                    "status": "skipped", "reason": "Client PDF is required but missing"})
                    continue
                attachments.append((client_pdf, f"Client_document_{acct}.pdf"))
            sender.send(to_email=c["email"], to_name=c["name"],
                        subject=subject_t, body=plain, html_body=html,
                        attachments=attachments)
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


@app.route("/client-documents/upload", methods=["POST"])
@login_required
def upload_client_document():
    """Store one explicitly mapped client PDF inside the tenant's local folder."""
    account_no = request.form.get("account_no", "").strip()
    document = request.files.get("document")
    known_accounts = {client.get("account_no") for client in _load_clients()}
    if account_no not in known_accounts:
        flash("Choose a client from the current imported data.", "danger")
        return redirect(url_for("clients"))
    if not document or not document.filename.lower().endswith(".pdf"):
        flash("Upload a PDF document for the selected client.", "danger")
        return redirect(url_for("clients"))
    header = document.stream.read(5)
    document.stream.seek(0)
    if header != b"%PDF-":
        flash("The uploaded file is not a valid PDF.", "danger")
        return redirect(url_for("clients"))
    document.save(_client_document_path(account_no))
    _audit("CLIENT_DOCUMENT_UPLOADED", f"account={account_no}")
    flash("Client PDF attached locally. It will be available in campaign review.", "success")
    return redirect(url_for("clients"))


@app.route("/upload-template", methods=["POST"])
@login_required
def upload_template():
    f = request.files.get("word_template")
    if not f or not f.filename.lower().endswith(".docx"):
        flash("Please upload a .docx Word template.", "danger")
        return redirect(url_for("clients"))
    f.save(_template_path())
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
        cfg["local_ai_enabled"] = request.form.get("local_ai_enabled") == "on"
        cfg["local_ai_model"] = request.form.get("local_ai_model", "").strip()

        # Username / password change apply to the logged-in user's own account
        new_user = request.form.get("admin_username", "").strip()
        new_pass = request.form.get("new_password", "").strip()
        confirm_pass = request.form.get("confirm_password", "").strip()

        if new_pass:
            if new_pass != confirm_pass:
                flash("Passwords do not match. Settings not saved.", "danger")
                return render_template("settings.html", cfg=cfg,
                                       team=db.list_users_for_tenant(_tenant_id()))
            db.update_password(session["user_id"], generate_password_hash(new_pass))
            flash("Password updated successfully.", "success")

        if new_user and new_user != session["username"]:
            if db.username_or_email_taken(new_user, ""):
                flash("That username is already taken.", "danger")
                return render_template("settings.html", cfg=cfg,
                                       team=db.list_users_for_tenant(_tenant_id()))
            db.update_username(session["user_id"], new_user)
            session["username"] = new_user

        _save_settings(cfg)
        _audit("SETTINGS_SAVED")
        if not new_pass:
            flash("Settings saved.", "success")
        return redirect(url_for("settings"))

    team = db.list_users_for_tenant(_tenant_id()) if session.get("role") == "owner" else []
    return render_template("settings.html", cfg=cfg, team=team)


@app.route("/local-ai/status")
@login_required
def local_ai_status():
    """Health check for the fixed loopback AI service; no client data is sent."""
    return jsonify(local_ai.status())


@app.route("/local-ai/draft", methods=["POST"])
@login_required
@limiter.limit("20 per minute")
def local_ai_draft():
    """Draft text only. It cannot send mail, alter financial records, or run tools."""
    cfg = _load_settings()
    if not cfg.get("local_ai_enabled") or not cfg.get("local_ai_model"):
        return jsonify({"error": "Local AI is not enabled in Company settings."}), 403
    data = request.get_json(silent=True) or {}
    task = (data.get("task") or "").strip()
    context = (data.get("context") or "").strip()
    if not task or len(task) > 1_000 or len(context) > 20_000:
        return jsonify({"error": "Enter a short task and a valid amount of local context."}), 400

    prompt = (
        "You are a writing assistant inside local financial software. "
        "Return only a concise draft. Never send email, give investment advice, "
        "change records, make compliance claims, or invent client data.\n\n"
        f"Task: {task}\n\nContext:\n{context}"
    )
    try:
        draft = local_ai.generate(cfg["local_ai_model"], prompt)
    except local_ai.LocalAIError as exc:
        return jsonify({"error": str(exc)}), 503
    _audit("LOCAL_AI_DRAFT", "User requested a local AI draft")
    return jsonify({"draft": draft})


@app.route("/audit-log")
@login_required
def audit_log():
    rows = db.get_audit(_tenant_id())
    lines = [f"[{datetime.fromtimestamp(r['ts']).strftime('%Y-%m-%d %H:%M:%S')}] "
             f"[{r['ip']}] [{r['who']}] {r['action']}" + (f" — {r['detail']}" if r['detail'] else "")
             for r in rows]
    return jsonify({"lines": lines})


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
    s = _load_settings()
    dirs = _tenant_dirs()
    logo = dirs["uploads"] / s.get("logo_filename", "") if s.get("logo_filename") else None
    try:
        gen = InvoiceGenerator(dirs["output"],
                               brand_color=s.get("brand_color", ""),
                               logo_path=logo)
        pdf = gen.generate(data["client"], data["company"])
        _audit("INVOICE_GENERATED", data["client"].get("invoice_no", ""))
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
    dirs = _tenant_dirs()
    logo = dirs["uploads"] / s.get("logo_filename", "") if s.get("logo_filename") else None
    try:
        gen = LoanScheduleGenerator(dirs["output"],
                                    brand_color=s.get("brand_color", ""),
                                    logo_path=logo)
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
    dirs = _tenant_dirs()
    logo = dirs["uploads"] / s.get("logo_filename", "") if s.get("logo_filename") else None
    try:
        gen = PortfolioReportGenerator(dirs["output"],
                                       brand_color=s.get("brand_color", ""),
                                       logo_path=logo)
        pdf = gen.generate(data, s["company_name"])
        return jsonify({"ok": True, "file": pdf.name})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})


@app.route("/merge-pdfs", methods=["POST"])
@login_required
def merge_pdfs():
    try:
        from pypdf import PdfWriter, PdfReader
    except ImportError:
        return jsonify({"error": "pypdf not installed — run: pip install pypdf"}), 500

    data = request.get_json(force=True) or {}
    account_nos = data.get("account_nos", [])
    doc_type    = data.get("type", "statement")   # statement | invoice | loan | portfolio

    prefix_map = {
        "statement":  "statement_",
        "invoice":    "invoice_",
        "loan":       "loan_schedule_",
        "portfolio":  "portfolio_",
    }
    prefix = prefix_map.get(doc_type, "statement_")
    output_dir = _tenant_dirs()["output"]

    if account_nos:
        pdfs = [output_dir / f"{prefix}{a}.pdf" for a in account_nos]
        pdfs = [p for p in pdfs if p.exists()]
    else:
        pdfs = sorted(output_dir.glob(f"{prefix}*.pdf"))

    if not pdfs:
        return jsonify({"error": "No PDFs found to merge"}), 400

    out = output_dir / f"merged_{doc_type}_{len(pdfs)}.pdf"
    writer = PdfWriter()
    for path in pdfs:
        reader = PdfReader(str(path))
        for page in reader.pages:
            writer.add_page(page)
    with open(out, "wb") as f:
        writer.write(f)

    _audit("PDF_MERGED", f"{len(pdfs)} {doc_type} PDFs → {out.name}")
    return jsonify({"ok": True, "file": out.name, "count": len(pdfs)})


@app.route("/download-output/<filename>")
@login_required
def download_output(filename):
    # Prevent path traversal — keep only the bare filename
    safe = Path(filename).name
    if not re.match(r'^[a-zA-Z0-9_\-\.]{1,120}$', safe):
        return "Invalid filename", 400
    path = _tenant_dirs()["output"] / safe
    if path.exists() and path.is_file():
        return send_file(path, as_attachment=True)
    return "File not found", 404


# ── Logo ───────────────────────────────────────────────────────────────────────

@app.route("/logo")
@login_required
def serve_logo():
    cfg = _load_settings()
    logo_file = cfg.get("logo_filename", "")
    if logo_file:
        path = _tenant_dirs()["uploads"] / logo_file
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
    uploads_dir = _tenant_dirs()["uploads"]
    for old in uploads_dir.glob("logo.*"):
        old.unlink(missing_ok=True)
    logo_path = uploads_dir / f"logo{ext}"
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
        from modules.docx_import import docx_to_html
        html = docx_to_html(f)
        return jsonify({"ok": True, "html": html})
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

@app.route("/template-designer")
@login_required
def template_designer():
    path = _saved_doc_template_path()
    saved_html = path.read_text(encoding="utf-8") if path.exists() else ""
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
    f = request.files.get("word_file")
    if not f:
        return jsonify({"error": "No file"}), 400
    try:
        from modules.docx_import import docx_to_html
        html = docx_to_html(f)
        return jsonify({"ok": True, "html": html})
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
    _saved_doc_template_path().write_text(html, encoding="utf-8")
    _audit("TEMPLATE_SAVED", f"document_template.html ({len(html)} chars)")
    return jsonify({"ok": True})


# ── Template download ──────────────────────────────────────────────────────────

@app.route("/download-template")
@login_required
def download_template():
    from generate_sample import make_sample_excel
    path = make_sample_excel(_tenant_dirs()["uploads"] / "sample_template.xlsx")
    return send_file(path, as_attachment=True, download_name="client_data_template.xlsx")


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1", port=int(os.environ.get("PORT", 5000)))
