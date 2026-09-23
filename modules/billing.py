"""SaaS billing — subscription plans, usage limits, Razorpay integration."""
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Optional

import requests

from modules.db import _connect


# ── Plan definitions ──────────────────────────────────────────────────────────

PLANS = {
    "free": {
        "name": "Free",
        "price_inr": 0,
        "razorpay_plan_id": None,
        "limits": {
            "clients": 10,
            "statements_per_month": 50,
            "users": 2,
            "integrations": 2,
            "storage_mb": 200,
            "api_calls_per_day": 100,
        },
        "features": ["Account statements", "Basic email send", "2 integrations"],
    },
    "starter": {
        "name": "Starter",
        "price_inr": 1999,
        "razorpay_plan_id": None,   # set via RAZORPAY_PLAN_STARTER env var
        "limits": {
            "clients": 50,
            "statements_per_month": 500,
            "users": 5,
            "integrations": 5,
            "storage_mb": 2048,
            "api_calls_per_day": 1000,
        },
        "features": ["All Free features", "GST invoices", "Loan schedules", "Portfolio reports",
                     "WhatsApp delivery", "Zoho CRM sync", "5 integrations"],
    },
    "pro": {
        "name": "Pro",
        "price_inr": 4999,
        "razorpay_plan_id": None,
        "limits": {
            "clients": 500,
            "statements_per_month": -1,   # unlimited
            "users": 15,
            "integrations": -1,
            "storage_mb": 20480,
            "api_calls_per_day": -1,
        },
        "features": ["All Starter features", "Unlimited statements", "All integrations",
                     "Desktop app", "Bulk WhatsApp/SMS", "Priority support"],
    },
    "enterprise": {
        "name": "Enterprise",
        "price_inr": 9999,
        "razorpay_plan_id": None,
        "limits": {
            "clients": -1,
            "statements_per_month": -1,
            "users": -1,
            "integrations": -1,
            "storage_mb": -1,
            "api_calls_per_day": -1,
        },
        "features": ["All Pro features", "White-label branding", "Custom domain",
                     "Dedicated support", "SLA guarantee", "On-premise option"],
    },
}


# ── DB setup ──────────────────────────────────────────────────────────────────

def _ensure_tables():
    conn = _connect()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id           INTEGER NOT NULL UNIQUE REFERENCES tenants(id) ON DELETE CASCADE,
            plan                TEXT NOT NULL DEFAULT 'free',
            status              TEXT NOT NULL DEFAULT 'active',
            razorpay_sub_id     TEXT,
            razorpay_customer_id TEXT,
            current_period_end  INTEGER,
            trial_ends_at       INTEGER,
            created_at          INTEGER NOT NULL,
            updated_at          INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS usage_tracking (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id   INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            month       TEXT NOT NULL,
            action      TEXT NOT NULL,
            count       INTEGER NOT NULL DEFAULT 0,
            UNIQUE(tenant_id, month, action)
        );

        CREATE TABLE IF NOT EXISTS billing_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id   INTEGER NOT NULL,
            event_type  TEXT NOT NULL,
            payload     TEXT,
            ts          INTEGER NOT NULL
        );
        """)
        conn.commit()
    finally:
        conn.close()


_ensure_tables()


# ── Subscription helpers ──────────────────────────────────────────────────────

def get_subscription(tenant_id: int) -> dict:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM subscriptions WHERE tenant_id = ?", (tenant_id,)
        ).fetchone()
        if row:
            return dict(row)
        # Auto-create free plan on first lookup
        now = int(time.time())
        trial_end = now + 14 * 86400  # 14-day free trial of Pro
        conn.execute(
            "INSERT INTO subscriptions (tenant_id, plan, status, trial_ends_at, created_at, updated_at) "
            "VALUES (?, 'free', 'trial', ?, ?, ?)",
            (tenant_id, trial_end, now, now),
        )
        conn.commit()
        return {"tenant_id": tenant_id, "plan": "free", "status": "trial",
                "trial_ends_at": trial_end, "created_at": now}
    finally:
        conn.close()


def effective_plan(tenant_id: int) -> str:
    """Returns the plan whose limits actually apply right now."""
    sub = get_subscription(tenant_id)
    if sub["status"] == "trial" and sub.get("trial_ends_at", 0) > int(time.time()):
        return "pro"   # full Pro during trial
    return sub["plan"]


def get_limits(tenant_id: int) -> dict:
    return PLANS[effective_plan(tenant_id)]["limits"]


def check_limit(tenant_id: int, resource: str) -> tuple[bool, int, int]:
    """Returns (allowed, current_usage, limit). limit=-1 means unlimited."""
    limits = get_limits(tenant_id)
    limit = limits.get(resource, -1)
    if limit == -1:
        return True, 0, -1

    if resource in ("statements_per_month",):
        month = time.strftime("%Y-%m")
        current = _get_usage(tenant_id, month, resource)
        return current < limit, current, limit

    if resource == "clients":
        from modules.db import get_clients_blob
        clients = get_clients_blob(tenant_id) or []
        return len(clients) < limit, len(clients), limit

    if resource == "users":
        from modules.db import list_users_for_tenant
        users = list_users_for_tenant(tenant_id)
        return len(users) < limit, len(users), limit

    return True, 0, limit


def _get_usage(tenant_id: int, month: str, action: str) -> int:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT count FROM usage_tracking WHERE tenant_id = ? AND month = ? AND action = ?",
            (tenant_id, month, action),
        ).fetchone()
        return row["count"] if row else 0
    finally:
        conn.close()


def increment_usage(tenant_id: int, action: str, amount: int = 1):
    month = time.strftime("%Y-%m")
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO usage_tracking (tenant_id, month, action, count) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(tenant_id, month, action) DO UPDATE SET count = count + ?",
            (tenant_id, month, action, amount, amount),
        )
        conn.commit()
    finally:
        conn.close()


def get_usage_summary(tenant_id: int) -> dict:
    month = time.strftime("%Y-%m")
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT action, count FROM usage_tracking WHERE tenant_id = ? AND month = ?",
            (tenant_id, month),
        ).fetchall()
        usage = {r["action"]: r["count"] for r in rows}
    finally:
        conn.close()

    limits = get_limits(tenant_id)
    plan = effective_plan(tenant_id)
    result = {"plan": plan, "month": month, "usage": {}}
    for key, limit in limits.items():
        used = usage.get(key, 0)
        result["usage"][key] = {
            "used": used,
            "limit": limit,
            "unlimited": limit == -1,
            "pct": 0 if limit <= 0 else min(100, int(used / limit * 100)),
        }
    return result


def update_subscription(tenant_id: int, plan: str, status: str,
                         razorpay_sub_id: str = None, razorpay_customer_id: str = None,
                         period_end: int = None):
    conn = _connect()
    now = int(time.time())
    try:
        conn.execute(
            "INSERT INTO subscriptions (tenant_id, plan, status, razorpay_sub_id, razorpay_customer_id, "
            "current_period_end, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(tenant_id) DO UPDATE SET plan=excluded.plan, status=excluded.status, "
            "razorpay_sub_id=excluded.razorpay_sub_id, razorpay_customer_id=excluded.razorpay_customer_id, "
            "current_period_end=excluded.current_period_end, updated_at=excluded.updated_at",
            (tenant_id, plan, status, razorpay_sub_id, razorpay_customer_id, period_end, now, now),
        )
        conn.commit()
    finally:
        conn.close()


# ── Razorpay Subscriptions ────────────────────────────────────────────────────

class RazorpayBilling:
    BASE = "https://api.razorpay.com/v1"

    def __init__(self, key_id: str, key_secret: str):
        self.auth = (key_id, key_secret)

    def _post(self, path: str, data: dict) -> dict:
        r = requests.post(f"{self.BASE}{path}", json=data, auth=self.auth, timeout=15)
        r.raise_for_status()
        return r.json()

    def _get(self, path: str) -> dict:
        r = requests.get(f"{self.BASE}{path}", auth=self.auth, timeout=15)
        r.raise_for_status()
        return r.json()

    def create_customer(self, name: str, email: str, contact: str = "") -> dict:
        return self._post("/customers", {"name": name, "email": email, "contact": contact})

    def create_subscription(self, plan_id: str, customer_id: str,
                             total_count: int = 12, notes: dict = None) -> dict:
        payload = {
            "plan_id": plan_id,
            "customer_id": customer_id,
            "total_count": total_count,
            "quantity": 1,
            "notify_info": {"notify_phone": 0, "notify_email": 1},
        }
        if notes:
            payload["notes"] = notes
        return self._post("/subscriptions", payload)

    def cancel_subscription(self, sub_id: str, cancel_at_cycle_end: bool = True) -> dict:
        return self._post(f"/subscriptions/{sub_id}/cancel",
                          {"cancel_at_cycle_end": 1 if cancel_at_cycle_end else 0})

    def get_subscription(self, sub_id: str) -> dict:
        return self._get(f"/subscriptions/{sub_id}")

    def verify_webhook(self, payload: bytes, signature: str, secret: str) -> bool:
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def create_plan(self, name: str, amount_paise: int, interval: int = 1,
                    period: str = "monthly") -> dict:
        """Create a Razorpay plan (run once during setup)."""
        return self._post("/plans", {
            "period": period,
            "interval": interval,
            "item": {"name": name, "amount": amount_paise, "currency": "INR"},
        })
