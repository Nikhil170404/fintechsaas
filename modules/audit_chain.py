"""Tamper-proof audit log using SHA-256 hash chaining.

Each entry stores: hash(prev_hash + ts + tenant_id + action + detail)
Verification walks the chain and recomputes each hash.
"""
import hashlib
import json
import time

from modules.db import _connect


GENESIS_HASH = "0" * 64


def _ensure_table():
    conn = _connect()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS audit_chain (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id   INTEGER NOT NULL,
            ts          INTEGER NOT NULL,
            ip          TEXT,
            who         TEXT,
            action      TEXT NOT NULL,
            detail      TEXT,
            prev_hash   TEXT NOT NULL,
            entry_hash  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_audit_chain_tenant ON audit_chain(tenant_id, id);
        """)
        conn.commit()
    finally:
        conn.close()


_ensure_table()


def _compute_hash(prev_hash: str, ts: int, tenant_id, action: str, detail: str) -> str:
    payload = f"{prev_hash}|{ts}|{tenant_id}|{action}|{detail}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _last_hash(tenant_id: int, conn) -> str:
    row = conn.execute(
        "SELECT entry_hash FROM audit_chain WHERE tenant_id = ? ORDER BY id DESC LIMIT 1",
        (tenant_id,),
    ).fetchone()
    return row["entry_hash"] if row else GENESIS_HASH


def add(tenant_id, ip: str, who: str, action: str, detail: str = ""):
    conn = _connect()
    try:
        ts = int(time.time())
        prev = _last_hash(tenant_id, conn)
        h = _compute_hash(prev, ts, tenant_id, action, detail)
        conn.execute(
            "INSERT INTO audit_chain (tenant_id, ts, ip, who, action, detail, prev_hash, entry_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (tenant_id, ts, ip, who, action, detail, prev, h),
        )
        conn.commit()
    finally:
        conn.close()


def get(tenant_id: int, limit: int = 200, offset: int = 0) -> list:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, ts, ip, who, action, detail, entry_hash FROM audit_chain "
            "WHERE tenant_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (tenant_id, limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def verify_chain(tenant_id: int) -> dict:
    """Walk the entire chain for a tenant and verify each hash. O(n)."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM audit_chain WHERE tenant_id = ? ORDER BY id ASC",
            (tenant_id,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"ok": True, "entries": 0, "first_tampered_id": None}

    prev = GENESIS_HASH
    for row in rows:
        expected = _compute_hash(prev, row["ts"], row["tenant_id"], row["action"], row["detail"] or "")
        if expected != row["entry_hash"] or row["prev_hash"] != prev:
            return {"ok": False, "entries": len(rows), "first_tampered_id": row["id"]}
        prev = row["entry_hash"]

    return {"ok": True, "entries": len(rows), "first_tampered_id": None}
