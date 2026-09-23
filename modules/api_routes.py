"""REST API blueprint — consumed by the Flutter desktop app and other API clients.

All endpoints return JSON. Authentication uses Bearer tokens issued at /api/v1/auth/login.
Tokens are stored in the `api_tokens` SQLite table with per-tenant scope.
"""
import json
import os
import secrets
import time
import zipfile
from functools import wraps
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file, current_app
from werkzeug.security import check_password_hash, generate_password_hash

from modules import db

api = Blueprint("api", __name__, url_prefix="/api/v1")

DATA_DIR = Path("data")
TENANTS_DIR = DATA_DIR / "tenants"


# ── Token helpers ─────────────────────────────────────────────────────────────

def _ensure_api_tokens_table() -> None:
    with db.get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                token TEXT NOT NULL UNIQUE,
                created_at INTEGER NOT NULL,
                expires_at INTEGER,
                last_used INTEGER
            )
        """)
        conn.commit()


def _create_token(tenant_id: int, user_id: int, ttl_days: int = 30) -> str:
    _ensure_api_tokens_table()
    token = secrets.token_urlsafe(48)
    expires = int(time.time()) + ttl_days * 86400
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO api_tokens (tenant_id, user_id, token, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (tenant_id, user_id, token, int(time.time()), expires),
        )
        conn.commit()
    return token


def _validate_token(token: str) -> dict | None:
    _ensure_api_tokens_table()
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT tenant_id, user_id, expires_at FROM api_tokens WHERE token = ?",
            (token,),
        ).fetchone()
    if not row:
        return None
    if row["expires_at"] and row["expires_at"] < int(time.time()):
        return None
    with db.get_db() as conn:
        conn.execute(
            "UPDATE api_tokens SET last_used = ? WHERE token = ?",
            (int(time.time()), token),
        )
        conn.commit()
    return {"tenant_id": row["tenant_id"], "user_id": row["user_id"]}


def _revoke_token(token: str) -> None:
    _ensure_api_tokens_table()
    with db.get_db() as conn:
        conn.execute("DELETE FROM api_tokens WHERE token = ?", (token,))
        conn.commit()


# ── Auth decorator ─────────────────────────────────────────────────────────────

def api_auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401
        token = auth_header.split(" ", 1)[1]
        context = _validate_token(token)
        if not context:
            return jsonify({"error": "Invalid or expired token"}), 401
        request.api_tenant_id = context["tenant_id"]
        request.api_user_id = context["user_id"]
        return f(*args, **kwargs)
    return decorated


def _tenant_dir(tenant_id: int) -> Path:
    return TENANTS_DIR / str(tenant_id)


def _load_settings(tenant_id: int) -> dict:
    try:
        return db.get_settings_blob(tenant_id) or {}
    except Exception:
        return {}


def _load_clients(tenant_id: int) -> list:
    try:
        return db.get_clients_blob(tenant_id) or []
    except Exception:
        return []


# ── Auth endpoints ────────────────────────────────────────────────────────────

@api.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json(force=True, silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    if not email or not password:
        return jsonify({"error": "email and password required"}), 400

    with db.get_db() as conn:
        user = conn.execute(
            "SELECT id, tenant_id, username, password_hash, role, is_active FROM users WHERE email = ?",
            (email,),
        ).fetchone()

    if not user or not user["is_active"]:
        return jsonify({"error": "Invalid credentials"}), 401
    if not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid credentials"}), 401

    token = _create_token(user["tenant_id"], user["id"])

    with db.get_db() as conn:
        tenant = conn.execute("SELECT name, slug FROM tenants WHERE id = ?", (user["tenant_id"],)).fetchone()

    settings = _load_settings(user["tenant_id"])
    return jsonify({
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "email": email,
            "role": user["role"],
        },
        "tenant": {
            "id": user["tenant_id"],
            "name": tenant["name"] if tenant else "",
            "slug": tenant["slug"] if tenant else "",
            "company_name": settings.get("company_name", ""),
            "brand_color": settings.get("brand_color", "#1976D2"),
        },
    })


@api.route("/auth/logout", methods=["POST"])
@api_auth_required
def logout():
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.split(" ", 1)[1]
    _revoke_token(token)
    return jsonify({"message": "Logged out successfully"})


@api.route("/auth/me", methods=["GET"])
@api_auth_required
def me():
    tenant_id = request.api_tenant_id
    user_id = request.api_user_id
    with db.get_db() as conn:
        user = conn.execute(
            "SELECT id, username, email, role FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        tenant = conn.execute("SELECT name, slug FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
    settings = _load_settings(tenant_id)
    return jsonify({
        "user": dict(user) if user else {},
        "tenant": {
            "id": tenant_id,
            "name": tenant["name"] if tenant else "",
            "slug": tenant["slug"] if tenant else "",
            "company_name": settings.get("company_name", ""),
            "brand_color": settings.get("brand_color", "#1976D2"),
        },
    })


# ── Clients ────────────────────────────────────────────────────────────────────

@api.route("/clients", methods=["GET"])
@api_auth_required
def list_clients():
    tenant_id = request.api_tenant_id
    clients = _load_clients(tenant_id)
    search = request.args.get("q", "").lower()
    if search:
        clients = [c for c in clients if search in str(c).lower()]
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))
    start = (page - 1) * per_page
    end = start + per_page
    return jsonify({
        "clients": clients[start:end],
        "total": len(clients),
        "page": page,
        "per_page": per_page,
    })


@api.route("/clients/<account_no>", methods=["GET"])
@api_auth_required
def get_client(account_no: str):
    tenant_id = request.api_tenant_id
    clients = _load_clients(tenant_id)
    for c in clients:
        if str(c.get("account_no", "")) == account_no:
            return jsonify(c)
    return jsonify({"error": "Client not found"}), 404


# ── Settings ────────────────────────────────────────────────────────────────────

@api.route("/settings", methods=["GET"])
@api_auth_required
def get_settings():
    tenant_id = request.api_tenant_id
    settings = _load_settings(tenant_id)
    # Never return SMTP password
    safe = {k: v for k, v in settings.items() if "password" not in k.lower()}
    return jsonify(safe)


@api.route("/settings", methods=["PUT"])
@api_auth_required
def update_settings():
    tenant_id = request.api_tenant_id
    data = request.get_json(force=True, silent=True) or {}
    current = _load_settings(tenant_id)
    # Deny password changes through this endpoint (use /settings/smtp)
    for key in ("smtp_password", "smtp_pass"):
        data.pop(key, None)
    current.update(data)
    db.set_settings_blob(tenant_id, current)
    return jsonify({"message": "Settings updated"})


@api.route("/settings/smtp", methods=["PUT"])
@api_auth_required
def update_smtp():
    tenant_id = request.api_tenant_id
    data = request.get_json(force=True, silent=True) or {}
    required = {"smtp_host", "smtp_port", "smtp_user", "smtp_password"}
    if not required.issubset(data.keys()):
        return jsonify({"error": f"Required fields: {required}"}), 400

    from cryptography.fernet import Fernet
    from config import Config

    fernet = Fernet(Config.ENCRYPTION_KEY.encode() if len(Config.ENCRYPTION_KEY) == 44 else Fernet.generate_key())
    encrypted_pw = fernet.encrypt(data["smtp_password"].encode()).decode()

    current = _load_settings(tenant_id)
    current.update({
        "smtp_host": data["smtp_host"],
        "smtp_port": int(data["smtp_port"]),
        "smtp_user": data["smtp_user"],
        "smtp_password": encrypted_pw,
        "smtp_use_tls": data.get("smtp_use_tls", True),
    })
    db.set_settings_blob(tenant_id, current)
    return jsonify({"message": "SMTP settings updated"})


# ── Integrations config ────────────────────────────────────────────────────────

@api.route("/integrations", methods=["GET"])
@api_auth_required
def list_integrations():
    tenant_id = request.api_tenant_id
    settings = _load_settings(tenant_id)
    integrations = settings.get("integrations", {})
    # Mask secrets
    safe = {}
    for name, cfg in integrations.items():
        safe[name] = {
            k: ("***" if any(w in k.lower() for w in ("secret", "password", "token", "key")) else v)
            for k, v in cfg.items()
        }
    return jsonify({"integrations": safe})


@api.route("/integrations/<name>", methods=["PUT"])
@api_auth_required
def save_integration(name: str):
    allowed = {
        "zoho", "gmail", "microsoft", "whatsapp", "twilio",
        "razorpay", "stripe", "telegram", "slack",
    }
    if name not in allowed:
        return jsonify({"error": f"Unknown integration: {name}"}), 400

    data = request.get_json(force=True, silent=True) or {}
    settings = _load_settings(tenant_id := request.api_tenant_id)
    integrations = settings.get("integrations", {})
    integrations[name] = {**integrations.get(name, {}), **data}
    settings["integrations"] = integrations
    db.set_settings_blob(tenant_id, settings)
    return jsonify({"message": f"{name} integration saved"})


@api.route("/integrations/<name>", methods=["DELETE"])
@api_auth_required
def remove_integration(name: str):
    tenant_id = request.api_tenant_id
    settings = _load_settings(tenant_id)
    settings.get("integrations", {}).pop(name, None)
    db.set_settings_blob(tenant_id, settings)
    return jsonify({"message": f"{name} integration removed"})


# ── OAuth callback helpers ─────────────────────────────────────────────────────

@api.route("/oauth/zoho/callback", methods=["GET"])
def zoho_oauth_callback():
    code = request.args.get("code", "")
    state = request.args.get("state", "")
    if not code:
        return jsonify({"error": "No code in callback"}), 400
    # state encodes tenant_id:user_id:token
    try:
        tenant_id, user_id, _ = state.split(":", 2)
        tenant_id = int(tenant_id)
    except Exception:
        return jsonify({"error": "Invalid state"}), 400

    settings = _load_settings(tenant_id)
    zoho_cfg = settings.get("integrations", {}).get("zoho", {})
    from modules.integrations.zoho import ZohoOAuth
    oauth = ZohoOAuth(
        zoho_cfg.get("client_id", ""),
        zoho_cfg.get("client_secret", ""),
        zoho_cfg.get("redirect_uri", ""),
    )
    tokens = oauth.exchange_code(code)
    zoho_cfg["access_token"] = tokens.get("access_token", "")
    zoho_cfg["refresh_token"] = tokens.get("refresh_token", "")
    zoho_cfg["token_expiry"] = int(time.time()) + tokens.get("expires_in", 3600)
    settings.setdefault("integrations", {})["zoho"] = zoho_cfg
    db.set_settings_blob(tenant_id, settings)
    return "<h3>Zoho connected successfully. You can close this window.</h3>"


@api.route("/oauth/google/callback", methods=["GET"])
def google_oauth_callback():
    code = request.args.get("code", "")
    state = request.args.get("state", "")
    if not code:
        return jsonify({"error": "No code in callback"}), 400
    try:
        tenant_id = int(state.split(":")[0])
    except Exception:
        return jsonify({"error": "Invalid state"}), 400

    settings = _load_settings(tenant_id)
    google_cfg = settings.get("integrations", {}).get("gmail", {})
    from modules.integrations.gmail_api import GoogleOAuth
    oauth = GoogleOAuth(
        google_cfg.get("client_id", ""),
        google_cfg.get("client_secret", ""),
        google_cfg.get("redirect_uri", ""),
    )
    tokens = oauth.exchange_code(code)
    google_cfg["access_token"] = tokens.get("access_token", "")
    google_cfg["refresh_token"] = tokens.get("refresh_token", "")
    google_cfg["token_expiry"] = int(time.time()) + tokens.get("expires_in", 3600)
    settings.setdefault("integrations", {})["gmail"] = google_cfg
    db.set_settings_blob(tenant_id, settings)
    return "<h3>Gmail connected successfully. You can close this window.</h3>"


@api.route("/oauth/microsoft/callback", methods=["GET"])
def microsoft_oauth_callback():
    code = request.args.get("code", "")
    state = request.args.get("state", "")
    if not code:
        return jsonify({"error": "No code in callback"}), 400
    try:
        tenant_id = int(state.split(":")[0])
    except Exception:
        return jsonify({"error": "Invalid state"}), 400

    settings = _load_settings(tenant_id)
    ms_cfg = settings.get("integrations", {}).get("microsoft", {})
    from modules.integrations.microsoft import MicrosoftOAuth
    oauth = MicrosoftOAuth(
        ms_cfg.get("client_id", ""),
        ms_cfg.get("client_secret", ""),
        ms_cfg.get("redirect_uri", ""),
    )
    tokens = oauth.exchange_code(code)
    ms_cfg["access_token"] = tokens.get("access_token", "")
    ms_cfg["refresh_token"] = tokens.get("refresh_token", "")
    ms_cfg["token_expiry"] = int(time.time()) + tokens.get("expires_in", 3600)
    settings.setdefault("integrations", {})["microsoft"] = ms_cfg
    db.set_settings_blob(tenant_id, settings)
    return "<h3>Microsoft 365 connected successfully. You can close this window.</h3>"


# ── Document generation ────────────────────────────────────────────────────────

@api.route("/generate/statements", methods=["POST"])
@api_auth_required
def generate_statements():
    tenant_id = request.api_tenant_id
    data = request.get_json(force=True, silent=True) or {}
    account_nos = data.get("account_nos", [])

    clients = _load_clients(tenant_id)
    if account_nos:
        clients = [c for c in clients if c.get("account_no", "") in account_nos]

    if not clients:
        return jsonify({"error": "No clients found"}), 404

    settings = _load_settings(tenant_id)
    tenant_dir = _tenant_dir(tenant_id)
    output_dir = tenant_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    from modules.statement_builder import StatementBuilder
    builder = StatementBuilder(settings, str(output_dir))
    results = []
    for client in clients:
        try:
            pdf_path = builder.build(client)
            results.append({
                "account_no": client.get("account_no", ""),
                "name": client.get("name", ""),
                "pdf": Path(pdf_path).name,
                "status": "ok",
            })
        except Exception as e:
            results.append({
                "account_no": client.get("account_no", ""),
                "name": client.get("name", ""),
                "status": "error",
                "error": str(e),
            })

    return jsonify({"results": results})


@api.route("/generate/invoice", methods=["POST"])
@api_auth_required
def generate_invoice():
    tenant_id = request.api_tenant_id
    data = request.get_json(force=True, silent=True) or {}
    settings = _load_settings(tenant_id)
    output_dir = _tenant_dir(tenant_id) / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    from modules.invoice_generator import generate_invoice as gen_inv
    try:
        pdf_path = gen_inv(data, settings, str(output_dir))
        return jsonify({"pdf": Path(pdf_path).name, "status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api.route("/generate/loan", methods=["POST"])
@api_auth_required
def generate_loan():
    tenant_id = request.api_tenant_id
    data = request.get_json(force=True, silent=True) or {}
    settings = _load_settings(tenant_id)
    output_dir = _tenant_dir(tenant_id) / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    from modules.loan_schedule import generate_loan_schedule
    try:
        pdf_path = generate_loan_schedule(data, settings, str(output_dir))
        return jsonify({"pdf": Path(pdf_path).name, "status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api.route("/generate/portfolio", methods=["POST"])
@api_auth_required
def generate_portfolio():
    tenant_id = request.api_tenant_id
    data = request.get_json(force=True, silent=True) or {}
    settings = _load_settings(tenant_id)
    output_dir = _tenant_dir(tenant_id) / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    from modules.portfolio_report import generate_portfolio_report
    try:
        pdf_path = generate_portfolio_report(data, settings, str(output_dir))
        return jsonify({"pdf": Path(pdf_path).name, "status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── File download ──────────────────────────────────────────────────────────────

@api.route("/files/<filename>", methods=["GET"])
@api_auth_required
def download_file(filename: str):
    tenant_id = request.api_tenant_id
    output_dir = _tenant_dir(tenant_id) / "output"
    file_path = output_dir / filename
    if not file_path.exists() or not file_path.is_file():
        return jsonify({"error": "File not found"}), 404
    return send_file(str(file_path), as_attachment=True)


@api.route("/files", methods=["GET"])
@api_auth_required
def list_files():
    tenant_id = request.api_tenant_id
    output_dir = _tenant_dir(tenant_id) / "output"
    if not output_dir.exists():
        return jsonify({"files": []})
    files = [
        {
            "name": f.name,
            "size": f.stat().st_size,
            "modified": int(f.stat().st_mtime),
        }
        for f in sorted(output_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)
        if f.is_file()
    ]
    return jsonify({"files": files})


# ── Email sending ──────────────────────────────────────────────────────────────

@api.route("/send/email", methods=["POST"])
@api_auth_required
def send_email():
    tenant_id = request.api_tenant_id
    data = request.get_json(force=True, silent=True) or {}
    settings = _load_settings(tenant_id)

    to = data.get("to", [])
    subject = data.get("subject", "")
    body = data.get("body", "")
    attachments = data.get("attachments", [])
    provider = data.get("provider", "smtp")  # smtp | gmail | microsoft | zoho

    if not to or not subject:
        return jsonify({"error": "to and subject are required"}), 400

    output_dir = _tenant_dir(tenant_id) / "output"
    attachment_paths = []
    for fname in attachments:
        fpath = output_dir / fname
        if fpath.exists():
            attachment_paths.append(str(fpath))

    try:
        if provider == "gmail":
            integrations = settings.get("integrations", {})
            gmail_cfg = integrations.get("gmail", {})
            _maybe_refresh_gmail(gmail_cfg, tenant_id, settings)
            from modules.integrations.gmail_api import GmailSender
            sender_obj = GmailSender(gmail_cfg["access_token"])
            atts = [{"path": p} for p in attachment_paths]
            sender_obj.send_email(gmail_cfg.get("email", ""), to, subject, body, atts)

        elif provider == "microsoft":
            integrations = settings.get("integrations", {})
            ms_cfg = integrations.get("microsoft", {})
            _maybe_refresh_microsoft(ms_cfg, tenant_id, settings)
            from modules.integrations.microsoft import OutlookSender
            sender_obj = OutlookSender(ms_cfg["access_token"])
            atts = [{"path": p} for p in attachment_paths]
            sender_obj.send_email(to, subject, body, atts)

        elif provider == "zoho":
            integrations = settings.get("integrations", {})
            zoho_cfg = integrations.get("zoho", {})
            from modules.integrations.zoho import ZohoMail
            mail = ZohoMail(zoho_cfg.get("access_token", ""), zoho_cfg.get("mail_account_id", ""))
            mail.send_email(to, subject, body)

        else:
            # Default SMTP
            from modules.email_sender import EmailSender
            from cryptography.fernet import Fernet
            from config import Config
            fernet = Fernet(Config.ENCRYPTION_KEY.encode() if len(Config.ENCRYPTION_KEY) == 44
                            else Fernet.generate_key())
            smtp_pass = ""
            try:
                smtp_pass = fernet.decrypt(settings.get("smtp_password", "").encode()).decode()
            except Exception:
                pass
            company = settings.get("company_name", "FinTech Desk")
            sender_obj = EmailSender(
                host=settings.get("smtp_host", ""),
                port=int(settings.get("smtp_port", 587)),
                username=settings.get("smtp_user", ""),
                password=smtp_pass,
                sender_name=company,
            )
            att_pairs = [(p, None) for p in attachment_paths]
            for recipient in (to if isinstance(to, list) else [to]):
                name = recipient if isinstance(recipient, str) else recipient.get("name", "")
                email_addr = recipient if isinstance(recipient, str) else recipient.get("email", "")
                sender_obj.send(
                    to_email=email_addr,
                    to_name=name,
                    subject=subject,
                    body=body,
                    html_body=body,
                    attachments=att_pairs,
                )

        return jsonify({"message": "Email sent successfully", "recipients": len(to)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _maybe_refresh_gmail(cfg: dict, tenant_id: int, settings: dict) -> None:
    if cfg.get("token_expiry", 0) < int(time.time()) + 60:
        from modules.integrations.gmail_api import GoogleOAuth
        oauth = GoogleOAuth(cfg.get("client_id", ""), cfg.get("client_secret", ""), cfg.get("redirect_uri", ""))
        tokens = oauth.refresh_token(cfg.get("refresh_token", ""))
        cfg["access_token"] = tokens.get("access_token", "")
        cfg["token_expiry"] = int(time.time()) + tokens.get("expires_in", 3600)
        settings.setdefault("integrations", {})["gmail"] = cfg
        db.set_settings_blob(tenant_id, settings)


def _maybe_refresh_microsoft(cfg: dict, tenant_id: int, settings: dict) -> None:
    if cfg.get("token_expiry", 0) < int(time.time()) + 60:
        from modules.integrations.microsoft import MicrosoftOAuth
        oauth = MicrosoftOAuth(cfg.get("client_id", ""), cfg.get("client_secret", ""), cfg.get("redirect_uri", ""))
        tokens = oauth.refresh_token(cfg.get("refresh_token", ""))
        cfg["access_token"] = tokens.get("access_token", "")
        cfg["token_expiry"] = int(time.time()) + tokens.get("expires_in", 3600)
        settings.setdefault("integrations", {})["microsoft"] = cfg
        db.set_settings_blob(tenant_id, settings)


# ── Send via WhatsApp ──────────────────────────────────────────────────────────

@api.route("/send/whatsapp", methods=["POST"])
@api_auth_required
def send_whatsapp():
    tenant_id = request.api_tenant_id
    data = request.get_json(force=True, silent=True) or {}
    settings = _load_settings(tenant_id)
    integrations = settings.get("integrations", {})
    wa_cfg = integrations.get("whatsapp", {})

    if not wa_cfg.get("phone_number_id") or not wa_cfg.get("access_token"):
        return jsonify({"error": "WhatsApp not configured"}), 400

    clients_filter = data.get("account_nos", [])
    message = data.get("message", "Please find your statement attached.")
    pdf_filename = data.get("pdf", "")

    clients = _load_clients(tenant_id)
    if clients_filter:
        clients = [c for c in clients if c.get("account_no", "") in clients_filter]

    from modules.integrations.whatsapp import WhatsAppBusiness
    wa = WhatsAppBusiness(wa_cfg["phone_number_id"], wa_cfg["access_token"])
    output_dir = _tenant_dir(tenant_id) / "output"
    results = []

    for client in clients:
        try:
            pdf_path = str(output_dir / (pdf_filename or f"statement_{client.get('account_no', '')}.pdf"))
            result = wa.send_statement_to_client(client, pdf_path, message)
            results.append({"name": client.get("name", ""), "status": "sent"})
        except Exception as e:
            results.append({"name": client.get("name", ""), "status": "failed", "error": str(e)})

    return jsonify({"results": results})


# ── Audit log ──────────────────────────────────────────────────────────────────

@api.route("/audit-log", methods=["GET"])
@api_auth_required
def audit_log():
    tenant_id = request.api_tenant_id
    limit = min(int(request.args.get("limit", 100)), 500)
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT ts, ip, who, action, detail FROM audit_log WHERE tenant_id = ? ORDER BY ts DESC LIMIT ?",
            (tenant_id, limit),
        ).fetchall()
    return jsonify({"log": [dict(r) for r in rows]})


# ── Team management ────────────────────────────────────────────────────────────

@api.route("/team", methods=["GET"])
@api_auth_required
def list_team():
    tenant_id = request.api_tenant_id
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT id, username, email, role, is_active, created_at FROM users WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchall()
    return jsonify({"team": [dict(r) for r in rows]})


@api.route("/team", methods=["POST"])
@api_auth_required
def add_team_member():
    tenant_id = request.api_tenant_id
    data = request.get_json(force=True, silent=True) or {}
    username = str(data.get("username", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    role = data.get("role", "staff")

    if not username or not email or not password:
        return jsonify({"error": "username, email, password required"}), 400
    if role not in ("owner", "staff"):
        return jsonify({"error": "role must be owner or staff"}), 400

    pw_hash = generate_password_hash(password)
    try:
        with db.get_db() as conn:
            conn.execute(
                "INSERT INTO users (tenant_id, username, email, password_hash, role, is_active, created_at) "
                "VALUES (?,?,?,?,?,1,?)",
                (tenant_id, username, email, pw_hash, role, int(time.time())),
            )
            conn.commit()
        return jsonify({"message": "Team member added"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@api.route("/team/<int:user_id>", methods=["DELETE"])
@api_auth_required
def remove_team_member(user_id: int):
    tenant_id = request.api_tenant_id
    with db.get_db() as conn:
        conn.execute(
            "UPDATE users SET is_active = 0 WHERE id = ? AND tenant_id = ?",
            (user_id, tenant_id),
        )
        conn.commit()
    return jsonify({"message": "Team member deactivated"})


# ── Zoho CRM sync ──────────────────────────────────────────────────────────────

@api.route("/integrations/zoho/sync-contacts", methods=["POST"])
@api_auth_required
def zoho_sync_contacts():
    tenant_id = request.api_tenant_id
    settings = _load_settings(tenant_id)
    zoho_cfg = settings.get("integrations", {}).get("zoho", {})
    if not zoho_cfg.get("access_token"):
        return jsonify({"error": "Zoho not connected"}), 400

    from modules.integrations.zoho import ZohoCRM
    crm = ZohoCRM(zoho_cfg["access_token"])
    try:
        contacts = crm.sync_clients_from_crm()
        return jsonify({"contacts": contacts, "count": len(contacts)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api.route("/integrations/zoho/push-contact", methods=["POST"])
@api_auth_required
def zoho_push_contact():
    tenant_id = request.api_tenant_id
    data = request.get_json(force=True, silent=True) or {}
    settings = _load_settings(tenant_id)
    zoho_cfg = settings.get("integrations", {}).get("zoho", {})
    if not zoho_cfg.get("access_token"):
        return jsonify({"error": "Zoho not connected"}), 400

    from modules.integrations.zoho import ZohoCRM
    crm = ZohoCRM(zoho_cfg["access_token"])
    try:
        result = crm.push_client_to_crm(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Payment links ──────────────────────────────────────────────────────────────

@api.route("/payments/razorpay/link", methods=["POST"])
@api_auth_required
def razorpay_create_link():
    tenant_id = request.api_tenant_id
    data = request.get_json(force=True, silent=True) or {}
    settings = _load_settings(tenant_id)
    rp_cfg = settings.get("integrations", {}).get("razorpay", {})
    if not rp_cfg.get("key_id") or not rp_cfg.get("key_secret"):
        return jsonify({"error": "Razorpay not configured"}), 400

    from modules.integrations.payments import RazorpayClient
    client = RazorpayClient(rp_cfg["key_id"], rp_cfg["key_secret"])
    try:
        url = client.create_invoice_link(
            data.get("client", {}),
            float(data.get("amount", 0)),
            data.get("description", ""),
        )
        return jsonify({"url": url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Health check ───────────────────────────────────────────────────────────────

@api.route("/health", methods=["GET"])
def health():
    from modules.monitoring import health_status
    return jsonify(health_status())
