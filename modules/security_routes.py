"""2FA setup and challenge routes."""
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from modules import db
from modules import security_2fa
from modules.audit_chain import add as audit

security_bp = Blueprint("security_2fa", __name__, url_prefix="/security/2fa")


def _login_required(f):
    from functools import wraps
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapped


@security_bp.route("/setup")
@_login_required
def setup():
    user_id = session["user_id"]
    user = db.get_user_by_id(user_id)
    enabled = security_2fa.is_enabled(user_id)

    if enabled:
        return render_template("security/setup_2fa.html", totp_enabled=True,
                               qr_data_uri=None, secret=None)

    data = security_2fa.generate_secret(user_id, user["email"])
    return render_template("security/setup_2fa.html", totp_enabled=False,
                           qr_data_uri=data["qr_data_uri"], secret=data["secret"])


@security_bp.route("/enable", methods=["POST"])
@_login_required
def verify_enable():
    code = request.form.get("code", "").strip()
    user_id = session["user_id"]
    result = security_2fa.verify_and_enable(user_id, code)
    if not result:
        flash("Invalid code. Try again.", "error")
        return redirect(url_for("security_2fa.setup"))

    backup_codes = result if isinstance(result, list) else []
    audit(session.get("tenant_id"), request.remote_addr, session.get("username"), "2FA_ENABLED", "")
    session["2fa_verified"] = True
    flash("Two-factor authentication enabled!", "success")
    return render_template("security/backup_codes.html", codes=backup_codes)


@security_bp.route("/disable", methods=["POST"])
@_login_required
def disable():
    code = request.form.get("code", "").strip()
    user_id = session["user_id"]
    if security_2fa.disable(user_id, code):
        audit(session.get("tenant_id"), request.remote_addr, session.get("username"), "2FA_DISABLED", "")
        flash("Two-factor authentication has been disabled.", "info")
    else:
        flash("Invalid code.", "error")
    return redirect(url_for("security_2fa.setup"))


@security_bp.route("/challenge")
def challenge():
    if not session.get("2fa_pending_user_id"):
        return redirect(url_for("login"))
    next_url = request.args.get("next", url_for("dashboard"))
    return render_template("security/2fa_challenge.html", next=next_url)


@security_bp.route("/challenge/verify", methods=["POST"])
def challenge_verify():
    user_id = session.get("2fa_pending_user_id")
    if not user_id:
        return redirect(url_for("login"))

    code = request.form.get("code", "").strip()
    if security_2fa.verify_code(user_id, code):
        # Complete login
        user = db.get_user_by_id(user_id)
        session.pop("2fa_pending_user_id", None)
        session["user_id"] = user_id
        session["tenant_id"] = user["tenant_id"]
        session["username"] = user["username"]
        session["role"] = user["role"]
        session["2fa_verified"] = True
        session.permanent = True
        audit(user["tenant_id"], request.remote_addr, user["username"], "LOGIN_2FA_OK", "")
        next_url = request.form.get("next", url_for("dashboard"))
        return redirect(next_url)
    else:
        audit(None, request.remote_addr, str(user_id), "LOGIN_2FA_FAIL", "invalid code")
        flash("Invalid verification code.", "error")
        return redirect(url_for("security_2fa.challenge"))
