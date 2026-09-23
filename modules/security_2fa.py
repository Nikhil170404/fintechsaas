"""TOTP-based two-factor authentication (RFC 6238)."""
import hashlib
import hmac
import io
import secrets
import sqlite3
import time
from pathlib import Path

import pyotp
import qrcode

from modules.db import _connect


# ── DB helpers ────────────────────────────────────────────────────────────────

def _ensure_tables():
    conn = _connect()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS totp_secrets (
            user_id     INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            secret      TEXT NOT NULL,
            enabled     INTEGER NOT NULL DEFAULT 0,
            backup_hash TEXT,
            created_at  INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS totp_backup_codes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            code_hash   TEXT NOT NULL,
            used        INTEGER NOT NULL DEFAULT 0,
            created_at  INTEGER NOT NULL
        );
        """)
        conn.commit()
    finally:
        conn.close()


_ensure_tables()


# ── Core 2FA functions ────────────────────────────────────────────────────────

def generate_secret(user_id: int, email: str, issuer: str = "FinTech Desk") -> dict:
    """Create a new TOTP secret for a user (not yet enabled)."""
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=email, issuer_name=issuer)

    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO totp_secrets (user_id, secret, enabled, created_at) VALUES (?, ?, 0, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET secret = excluded.secret, enabled = 0",
            (user_id, secret, int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()

    # Build QR code PNG → data URI
    qr = qrcode.make(uri)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    import base64
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return {"secret": secret, "uri": uri, "qr_data_uri": f"data:image/png;base64,{qr_b64}"}


def verify_and_enable(user_id: int, code: str) -> bool:
    """Verify an OTP code and mark 2FA as enabled if correct."""
    conn = _connect()
    try:
        row = conn.execute("SELECT secret FROM totp_secrets WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            return False
        totp = pyotp.TOTP(row["secret"])
        if not totp.verify(code, valid_window=1):
            return False
        # Generate backup codes
        codes = [secrets.token_hex(4).upper() for _ in range(8)]
        code_hashes = [hashlib.sha256(c.encode()).hexdigest() for c in codes]
        conn.execute("DELETE FROM totp_backup_codes WHERE user_id = ?", (user_id,))
        conn.executemany(
            "INSERT INTO totp_backup_codes (user_id, code_hash, created_at) VALUES (?, ?, ?)",
            [(user_id, h, int(time.time())) for h in code_hashes],
        )
        conn.execute("UPDATE totp_secrets SET enabled = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        return codes  # Return plaintext codes once — user must save them
    finally:
        conn.close()


def is_enabled(user_id: int) -> bool:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT enabled FROM totp_secrets WHERE user_id = ?", (user_id,)
        ).fetchone()
        return bool(row and row["enabled"])
    finally:
        conn.close()


def verify_code(user_id: int, code: str) -> bool:
    """Verify TOTP code or a backup code. Returns True if valid."""
    code = code.strip().replace("-", "").replace(" ", "").upper()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT secret FROM totp_secrets WHERE user_id = ? AND enabled = 1", (user_id,)
        ).fetchone()
        if not row:
            return True  # 2FA not enabled — pass through
        # Try TOTP first
        totp = pyotp.TOTP(row["secret"])
        if totp.verify(code, valid_window=1):
            return True
        # Try backup codes
        h = hashlib.sha256(code.encode()).hexdigest()
        backup = conn.execute(
            "SELECT id FROM totp_backup_codes WHERE user_id = ? AND code_hash = ? AND used = 0",
            (user_id, h),
        ).fetchone()
        if backup:
            conn.execute(
                "UPDATE totp_backup_codes SET used = 1 WHERE id = ?", (backup["id"],)
            )
            conn.commit()
            return True
        return False
    finally:
        conn.close()


def disable(user_id: int, code: str) -> bool:
    """Disable 2FA after verifying current code."""
    if not verify_code(user_id, code):
        return False
    conn = _connect()
    try:
        conn.execute("UPDATE totp_secrets SET enabled = 0 WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM totp_backup_codes WHERE user_id = ?", (user_id,))
        conn.commit()
        return True
    finally:
        conn.close()
