"""Billing routes — plan management, Razorpay webhooks, usage dashboard."""
import hashlib
import hmac
import json
import os
import time

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from modules import billing, db
from modules.audit_chain import add as audit

billing_bp = Blueprint("billing", __name__, url_prefix="/billing")

# ── Auth guard ────────────────────────────────────────────────────────────────

def _owner_required(f):
    from functools import wraps
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        if session.get("role") != "owner":
            flash("Owner access required.", "error")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return wrapped


# ── Pages ─────────────────────────────────────────────────────────────────────

@billing_bp.route("/")
@_owner_required
def overview():
    tenant_id = session["tenant_id"]
    sub = billing.get_subscription(tenant_id)
    usage = billing.get_usage_summary(tenant_id)
    plans = billing.PLANS
    return render_template("billing/overview.html", sub=sub, usage=usage, plans=plans,
                           current_plan=billing.effective_plan(tenant_id))


@billing_bp.route("/upgrade/<plan>", methods=["POST"])
@_owner_required
def upgrade(plan: str):
    if plan not in billing.PLANS:
        flash("Invalid plan.", "error")
        return redirect(url_for("billing.overview"))

    tenant_id = session["tenant_id"]
    key_id = os.environ.get("RAZORPAY_KEY_ID", "")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "")

    if not key_id:
        flash("Razorpay is not configured. Please contact support.", "error")
        return redirect(url_for("billing.overview"))

    if plan == "free":
        billing.update_subscription(tenant_id, "free", "active")
        audit(tenant_id, request.remote_addr, session.get("username"), "PLAN_CHANGE", "downgraded to free")
        flash("Downgraded to Free plan.", "info")
        return redirect(url_for("billing.overview"))

    plan_id = os.environ.get(f"RAZORPAY_PLAN_{plan.upper()}")
    if not plan_id:
        flash(f"Plan {plan} is not configured. Contact support.", "error")
        return redirect(url_for("billing.overview"))

    try:
        client = billing.RazorpayBilling(key_id, key_secret)
        user = db.get_user_by_id(session["user_id"])
        tenant = db.get_tenant(tenant_id)

        # Get or create Razorpay customer
        sub = billing.get_subscription(tenant_id)
        customer_id = sub.get("razorpay_customer_id")
        if not customer_id:
            cust = client.create_customer(
                name=tenant["name"] if tenant else user["username"],
                email=user["email"],
            )
            customer_id = cust["id"]

        rz_sub = client.create_subscription(plan_id, customer_id,
                                             notes={"tenant_id": str(tenant_id)})
        billing.update_subscription(tenant_id, plan, "pending",
                                     razorpay_sub_id=rz_sub["id"],
                                     razorpay_customer_id=customer_id)
        audit(tenant_id, request.remote_addr, session.get("username"),
              "PLAN_UPGRADE_INITIATED", f"plan={plan} rz_sub={rz_sub['id']}")

        # Redirect to Razorpay checkout
        return redirect(rz_sub.get("short_url", url_for("billing.overview")))

    except Exception as e:
        flash(f"Subscription creation failed: {e}", "error")
        return redirect(url_for("billing.overview"))


@billing_bp.route("/cancel", methods=["POST"])
@_owner_required
def cancel():
    tenant_id = session["tenant_id"]
    sub = billing.get_subscription(tenant_id)
    rz_sub_id = sub.get("razorpay_sub_id")
    if rz_sub_id:
        try:
            key_id = os.environ.get("RAZORPAY_KEY_ID", "")
            key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "")
            client = billing.RazorpayBilling(key_id, key_secret)
            client.cancel_subscription(rz_sub_id, cancel_at_cycle_end=True)
        except Exception as e:
            flash(f"Could not cancel with Razorpay: {e}", "warning")

    billing.update_subscription(tenant_id, "free", "cancelled")
    audit(tenant_id, request.remote_addr, session.get("username"), "PLAN_CANCELLED", "")
    flash("Subscription cancelled. You'll keep access until the end of the billing period.", "info")
    return redirect(url_for("billing.overview"))


# ── Usage API ─────────────────────────────────────────────────────────────────

@billing_bp.route("/usage")
@_owner_required
def usage():
    return jsonify(billing.get_usage_summary(session["tenant_id"]))


# ── Razorpay Webhook ──────────────────────────────────────────────────────────

@billing_bp.route("/webhook/razorpay", methods=["POST"])
def razorpay_webhook():
    payload = request.get_data()
    sig = request.headers.get("X-Razorpay-Signature", "")
    secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")

    if secret:
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return jsonify({"error": "invalid signature"}), 400

    try:
        event = json.loads(payload)
    except Exception:
        return jsonify({"error": "bad json"}), 400

    event_type = event.get("event", "")
    sub_data = event.get("payload", {}).get("subscription", {}).get("entity", {})
    sub_id = sub_data.get("id", "")
    notes = sub_data.get("notes", {})
    tenant_id = notes.get("tenant_id")

    if not tenant_id:
        return jsonify({"ok": True})

    tenant_id = int(tenant_id)

    if event_type == "subscription.activated":
        plan = _plan_from_razorpay_id(sub_data.get("plan_id", ""))
        period_end = sub_data.get("current_end", 0)
        billing.update_subscription(tenant_id, plan, "active",
                                     razorpay_sub_id=sub_id,
                                     period_end=period_end)
        _log_billing_event(tenant_id, event_type, event)

    elif event_type in ("subscription.cancelled", "subscription.expired"):
        billing.update_subscription(tenant_id, "free", "cancelled", razorpay_sub_id=sub_id)
        _log_billing_event(tenant_id, event_type, event)

    elif event_type == "subscription.charged":
        period_end = sub_data.get("current_end", 0)
        sub = billing.get_subscription(tenant_id)
        billing.update_subscription(tenant_id, sub["plan"], "active",
                                     razorpay_sub_id=sub_id,
                                     period_end=period_end)
        _log_billing_event(tenant_id, event_type, event)

    return jsonify({"ok": True})


def _plan_from_razorpay_id(plan_id: str) -> str:
    for k, v in billing.PLANS.items():
        if v.get("razorpay_plan_id") == plan_id:
            return k
        if os.environ.get(f"RAZORPAY_PLAN_{k.upper()}") == plan_id:
            return k
    return "starter"


def _log_billing_event(tenant_id: int, event_type: str, payload: dict):
    conn = db._connect()
    try:
        conn.execute(
            "INSERT INTO billing_events (tenant_id, event_type, payload, ts) VALUES (?, ?, ?, ?)",
            (tenant_id, event_type, json.dumps(payload), int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()
