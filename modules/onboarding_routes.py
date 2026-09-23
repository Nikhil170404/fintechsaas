"""Guided onboarding wizard for new tenants (4 steps after signup)."""
import json
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from modules import db
from modules.audit_chain import add as audit
from modules import billing

onboarding_bp = Blueprint("onboarding", __name__, url_prefix="/onboarding")

STEPS = ["welcome", "company", "smtp", "first_upload", "done"]


def _login_required(f):
    from functools import wraps
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapped


def _get_progress(tenant_id: int) -> dict:
    settings = db.get_settings_blob(tenant_id) or {}
    return settings.get("onboarding", {})


def _save_progress(tenant_id: int, key: str, value=True):
    settings = db.get_settings_blob(tenant_id) or {}
    if "onboarding" not in settings:
        settings["onboarding"] = {}
    settings["onboarding"][key] = value
    db.set_settings_blob(tenant_id, settings)


def is_complete(tenant_id: int) -> bool:
    return bool(_get_progress(tenant_id).get("done"))


@onboarding_bp.route("/")
@_login_required
def index():
    progress = _get_progress(session["tenant_id"])
    if progress.get("done"):
        return redirect(url_for("dashboard"))
    # Find first incomplete step
    steps_done = {
        "company": progress.get("company_done"),
        "smtp": progress.get("smtp_done"),
        "first_upload": progress.get("first_upload_done"),
    }
    for step in ["company", "smtp", "first_upload"]:
        if not steps_done[step]:
            return redirect(url_for(f"onboarding.step_{step}"))
    return redirect(url_for("onboarding.step_done"))


@onboarding_bp.route("/company", methods=["GET", "POST"])
@_login_required
def step_company():
    tenant_id = session["tenant_id"]
    if request.method == "POST":
        company_name = request.form.get("company_name", "").strip()
        brand_color = request.form.get("brand_color", "#1565C0").strip()
        gst = request.form.get("gst_number", "").strip()
        address = request.form.get("address", "").strip()

        if not company_name:
            flash("Company name is required.", "error")
        else:
            settings = db.get_settings_blob(tenant_id) or {}
            settings.update({
                "company_name": company_name,
                "brand_color": brand_color,
                "gst_number": gst,
                "address": address,
            })
            if "onboarding" not in settings:
                settings["onboarding"] = {}
            settings["onboarding"]["company_done"] = True
            db.set_settings_blob(tenant_id, settings)
            audit(tenant_id, request.remote_addr, session.get("username"),
                  "ONBOARDING_COMPANY", company_name)
            return redirect(url_for("onboarding.step_smtp"))

    settings = db.get_settings_blob(tenant_id) or {}
    return render_template("onboarding/company.html", settings=settings, step=1, total=4)


@onboarding_bp.route("/smtp", methods=["GET", "POST"])
@_login_required
def step_smtp():
    tenant_id = session["tenant_id"]
    if request.method == "POST":
        if request.form.get("skip"):
            _save_progress(tenant_id, "smtp_done")
            return redirect(url_for("onboarding.step_first_upload"))

        host = request.form.get("smtp_host", "").strip()
        port = request.form.get("smtp_port", "587").strip()
        user = request.form.get("smtp_user", "").strip()
        password = request.form.get("smtp_password", "").strip()
        tls = bool(request.form.get("smtp_tls"))

        if not (host and user and password):
            flash("Fill host, username, and password (or skip for now).", "error")
        else:
            settings = db.get_settings_blob(tenant_id) or {}
            settings.update({
                "smtp_host": host,
                "smtp_port": int(port),
                "smtp_user": user,
                "smtp_password": password,
                "smtp_use_tls": tls,
            })
            if "onboarding" not in settings:
                settings["onboarding"] = {}
            settings["onboarding"]["smtp_done"] = True
            db.set_settings_blob(tenant_id, settings)
            audit(tenant_id, request.remote_addr, session.get("username"),
                  "ONBOARDING_SMTP", f"host={host}")
            return redirect(url_for("onboarding.step_first_upload"))

    return render_template("onboarding/smtp.html", step=2, total=4)


@onboarding_bp.route("/first-upload", methods=["GET", "POST"])
@_login_required
def step_first_upload():
    tenant_id = session["tenant_id"]
    if request.method == "POST":
        if request.form.get("skip"):
            _save_progress(tenant_id, "first_upload_done")
            return redirect(url_for("onboarding.step_done"))

        # Redirect to the main upload page with onboarding context
        _save_progress(tenant_id, "first_upload_done")
        return redirect(url_for("upload") + "?from=onboarding")

    return render_template("onboarding/first_upload.html", step=3, total=4)


@onboarding_bp.route("/done")
@_login_required
def step_done():
    tenant_id = session["tenant_id"]
    _save_progress(tenant_id, "done")
    _save_progress(tenant_id, "first_upload_done")
    sub = billing.get_subscription(tenant_id)
    audit(tenant_id, request.remote_addr, session.get("username"), "ONBOARDING_COMPLETE", "")
    return render_template("onboarding/done.html", sub=sub,
                           plan=billing.effective_plan(tenant_id),
                           trial_days=14)
