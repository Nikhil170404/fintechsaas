import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path("data") / "app.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = _connect()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS tenants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'staff',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token TEXT NOT NULL UNIQUE,
            expires_at INTEGER NOT NULL,
            used INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER,
            ts INTEGER NOT NULL,
            ip TEXT,
            who TEXT,
            action TEXT NOT NULL,
            detail TEXT
        );

        CREATE TABLE IF NOT EXISTS settings (
            tenant_id INTEGER PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
            json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS clients (
            tenant_id INTEGER PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
            json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS mapping (
            tenant_id INTEGER PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
            json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS activity (
            tenant_id INTEGER PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
            json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS mapping_profiles (
            tenant_id INTEGER PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
            json TEXT NOT NULL
        );
        """)
        conn.commit()
    finally:
        conn.close()


def tenant_count() -> int:
    conn = _connect()
    try:
        return conn.execute("SELECT COUNT(*) c FROM tenants").fetchone()["c"]
    finally:
        conn.close()


def create_tenant(name: str, slug: str) -> int:
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO tenants (name, slug, created_at) VALUES (?, ?, ?)",
            (name, slug, int(time.time())),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def slug_exists(slug: str) -> bool:
    conn = _connect()
    try:
        return conn.execute("SELECT 1 FROM tenants WHERE slug = ?", (slug,)).fetchone() is not None
    finally:
        conn.close()


def create_user(tenant_id: int, username: str, email: str, password_hash: str, role: str = "staff") -> int:
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO users (tenant_id, username, email, password_hash, role, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (tenant_id, username, email, password_hash, role, int(time.time())),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_user_by_username(username: str):
    conn = _connect()
    try:
        return conn.execute(
            "SELECT * FROM users WHERE username = ? AND is_active = 1", (username,)
        ).fetchone()
    finally:
        conn.close()


def get_user_by_email(email: str):
    conn = _connect()
    try:
        return conn.execute(
            "SELECT * FROM users WHERE email = ? AND is_active = 1", (email,)
        ).fetchone()
    finally:
        conn.close()


def get_user_by_id(user_id: int):
    conn = _connect()
    try:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    finally:
        conn.close()


def username_or_email_taken(username: str, email: str) -> bool:
    conn = _connect()
    try:
        return conn.execute(
            "SELECT 1 FROM users WHERE username = ? OR email = ?", (username, email)
        ).fetchone() is not None
    finally:
        conn.close()


def list_users_for_tenant(tenant_id: int):
    conn = _connect()
    try:
        return conn.execute(
            "SELECT * FROM users WHERE tenant_id = ? ORDER BY created_at", (tenant_id,)
        ).fetchall()
    finally:
        conn.close()


def count_owners(tenant_id: int) -> int:
    conn = _connect()
    try:
        return conn.execute(
            "SELECT COUNT(*) c FROM users WHERE tenant_id = ? AND role = 'owner' AND is_active = 1",
            (tenant_id,),
        ).fetchone()["c"]
    finally:
        conn.close()


def deactivate_user(tenant_id: int, user_id: int):
    conn = _connect()
    try:
        conn.execute(
            "UPDATE users SET is_active = 0 WHERE id = ? AND tenant_id = ?", (user_id, tenant_id)
        )
        conn.commit()
    finally:
        conn.close()


def update_password(user_id: int, password_hash: str):
    conn = _connect()
    try:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
        conn.commit()
    finally:
        conn.close()


def update_username(user_id: int, username: str):
    conn = _connect()
    try:
        conn.execute("UPDATE users SET username = ? WHERE id = ?", (username, user_id))
        conn.commit()
    finally:
        conn.close()


def create_password_reset(user_id: int, token: str, expires_at: int):
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO password_resets (user_id, token, expires_at) VALUES (?, ?, ?)",
            (user_id, token, expires_at),
        )
        conn.commit()
    finally:
        conn.close()


def get_valid_reset(token: str):
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM password_resets WHERE token = ? AND used = 0", (token,)
        ).fetchone()
        if row and row["expires_at"] >= int(time.time()):
            return row
        return None
    finally:
        conn.close()


def mark_reset_used(token: str):
    conn = _connect()
    try:
        conn.execute("UPDATE password_resets SET used = 1 WHERE token = ?", (token,))
        conn.commit()
    finally:
        conn.close()


def add_audit(tenant_id, ip: str, who: str, action: str, detail: str = ""):
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO audit_log (tenant_id, ts, ip, who, action, detail) VALUES (?, ?, ?, ?, ?, ?)",
            (tenant_id, int(time.time()), ip, who, action, detail),
        )
        conn.commit()
    finally:
        conn.close()


def get_audit(tenant_id: int, limit: int = 100):
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE tenant_id = ? ORDER BY id DESC LIMIT ?",
            (tenant_id, limit),
        ).fetchall()
        return list(reversed(rows))
    finally:
        conn.close()


# ── Generic per-tenant JSON blob storage (settings / clients / mapping / activity / profiles) ──

def _get_blob(table: str, tenant_id: int):
    conn = _connect()
    try:
        row = conn.execute(f"SELECT json FROM {table} WHERE tenant_id = ?", (tenant_id,)).fetchone()
        return json.loads(row["json"]) if row else None
    finally:
        conn.close()


def _set_blob(table: str, tenant_id: int, data):
    payload = json.dumps(data, ensure_ascii=False)
    conn = _connect()
    try:
        conn.execute(
            f"INSERT INTO {table} (tenant_id, json) VALUES (?, ?) "
            f"ON CONFLICT(tenant_id) DO UPDATE SET json = excluded.json",
            (tenant_id, payload),
        )
        conn.commit()
    finally:
        conn.close()


def get_settings_blob(tenant_id: int):
    return _get_blob("settings", tenant_id)


def set_settings_blob(tenant_id: int, data: dict):
    _set_blob("settings", tenant_id, data)


def get_clients_blob(tenant_id: int):
    return _get_blob("clients", tenant_id)


def set_clients_blob(tenant_id: int, data: list):
    _set_blob("clients", tenant_id, data)


def get_mapping_blob(tenant_id: int):
    return _get_blob("mapping", tenant_id)


def set_mapping_blob(tenant_id: int, data: dict):
    _set_blob("mapping", tenant_id, data)


def get_activity_blob(tenant_id: int):
    return _get_blob("activity", tenant_id)


def set_activity_blob(tenant_id: int, data: dict):
    _set_blob("activity", tenant_id, data)


def get_profiles_blob(tenant_id: int):
    return _get_blob("mapping_profiles", tenant_id)


def set_profiles_blob(tenant_id: int, data: dict):
    _set_blob("mapping_profiles", tenant_id, data)
