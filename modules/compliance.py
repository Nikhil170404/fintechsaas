"""DPDP (Digital Personal Data Protection) Act 2023 & GDPR compliance helpers."""
import hashlib
import json
import time

from modules.db import _connect


# ── Tables ────────────────────────────────────────────────────────────────────

def _ensure_tables():
    conn = _connect()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS consent_records (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id   INTEGER,
            user_id     INTEGER,
            purpose     TEXT NOT NULL,
            granted     INTEGER NOT NULL DEFAULT 1,
            ip          TEXT,
            ts          INTEGER NOT NULL,
            version     TEXT NOT NULL DEFAULT '1.0'
        );

        CREATE TABLE IF NOT EXISTS data_retention_rules (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id   INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            data_type   TEXT NOT NULL,
            retain_days INTEGER NOT NULL DEFAULT 730,
            created_at  INTEGER NOT NULL,
            UNIQUE(tenant_id, data_type)
        );

        CREATE TABLE IF NOT EXISTS deletion_requests (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id   INTEGER NOT NULL,
            user_id     INTEGER,
            requester_email TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'pending',
            requested_at INTEGER NOT NULL,
            completed_at INTEGER
        );
        """)
        conn.commit()
    finally:
        conn.close()


_ensure_tables()


# ── Consent ───────────────────────────────────────────────────────────────────

CONSENT_PURPOSES = {
    "data_processing":   "Processing your financial data to generate reports and statements",
    "email_marketing":   "Sending product updates, tips, and promotional emails",
    "analytics":         "Anonymised usage analytics to improve the product",
    "third_party_share": "Sharing data with integrated third-party services (Zoho, Gmail, etc.)",
}


def record_consent(tenant_id, user_id, purposes: list[str], granted: bool,
                   ip: str = "", version: str = "1.0"):
    conn = _connect()
    try:
        ts = int(time.time())
        conn.executemany(
            "INSERT INTO consent_records (tenant_id, user_id, purpose, granted, ip, ts, version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(tenant_id, user_id, p, 1 if granted else 0, ip, ts, version) for p in purposes],
        )
        conn.commit()
    finally:
        conn.close()


def get_consents(user_id: int) -> dict:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT purpose, granted, ts FROM consent_records WHERE user_id = ? "
            "ORDER BY ts DESC",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()
    # Keep latest per purpose
    seen, result = set(), {}
    for r in rows:
        if r["purpose"] not in seen:
            seen.add(r["purpose"])
            result[r["purpose"]] = {"granted": bool(r["granted"]), "ts": r["ts"]}
    return result


def has_required_consent(user_id: int) -> bool:
    consents = get_consents(user_id)
    return consents.get("data_processing", {}).get("granted", False)


# ── Data erasure (Right to be Forgotten) ─────────────────────────────────────

def request_deletion(tenant_id: int, requester_email: str, user_id: int = None) -> int:
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO deletion_requests (tenant_id, user_id, requester_email, requested_at) "
            "VALUES (?, ?, ?, ?)",
            (tenant_id, user_id, requester_email, int(time.time())),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def execute_deletion(request_id: int) -> dict:
    """Anonymise/delete personal data for a deletion request."""
    conn = _connect()
    try:
        req = conn.execute(
            "SELECT * FROM deletion_requests WHERE id = ?", (request_id,)
        ).fetchone()
        if not req or req["status"] != "pending":
            return {"ok": False, "reason": "Request not found or already processed"}

        tenant_id = req["tenant_id"]
        deleted = []

        # Anonymise client PII (name→hashed, email→removed, phone→removed)
        from modules.db import get_clients_blob, set_clients_blob
        clients = get_clients_blob(tenant_id) or []
        for c in clients:
            c["email"] = ""
            c["phone"] = ""
            c["address"] = "[deleted]"
        set_clients_blob(tenant_id, clients)
        deleted.append("client_pii")

        # Mark request complete
        conn.execute(
            "UPDATE deletion_requests SET status = 'completed', completed_at = ? WHERE id = ?",
            (int(time.time()), request_id),
        )
        conn.commit()
        return {"ok": True, "deleted": deleted, "request_id": request_id}
    finally:
        conn.close()


# ── Privacy policy version tracking ──────────────────────────────────────────

CURRENT_POLICY_VERSION = "2.0"
CURRENT_POLICY_DATE = "2024-01-01"


def anonymise_email(email: str) -> str:
    """One-way anonymisation for logging."""
    return hashlib.sha256(email.encode()).hexdigest()[:16] + "@anon"
