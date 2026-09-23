import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path("data") / "app.db"

# Thread-local connection pool: one long-lived connection per thread
_local = threading.local()


def _connect() -> sqlite3.Connection:
    """Return this thread's cached connection, creating it if needed."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA cache_size=-8000")   # 8 MB page cache per connection
        conn.execute("PRAGMA synchronous=NORMAL")  # faster writes, still crash-safe
        conn.execute("PRAGMA temp_store=MEMORY")
        _local.conn = conn
    return conn


@contextmanager
def get_db():
    """Yield the thread-local connection (no open/close overhead)."""
    yield _connect()


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

        CREATE TABLE IF NOT EXISTS api_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            token TEXT NOT NULL UNIQUE,
            created_at INTEGER NOT NULL,
            expires_at INTEGER,
            last_used INTEGER
        );

        CREATE INDEX IF NOT EXISTS idx_users_email    ON users(email);
        CREATE INDEX IF NOT EXISTS idx_users_tenant   ON users(tenant_id, is_active);
        CREATE INDEX IF NOT EXISTS idx_audit_tenant   ON audit_log(tenant_id, ts DESC);
        CREATE INDEX IF NOT EXISTS idx_resets_token   ON password_resets(token);
        CREATE INDEX IF NOT EXISTS idx_tokens_token   ON api_tokens(token);
        CREATE INDEX IF NOT EXISTS idx_rag_tenant     ON rag_chunks(tenant_id);
        """)
        conn.commit()


def get_tenant(tenant_id: int):
    return _connect().execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,)).fetchone()


def tenant_count() -> int:
    return _connect().execute("SELECT COUNT(*) c FROM tenants").fetchone()["c"]


def create_tenant(name: str, slug: str) -> int:
    conn = _connect()
    cur = conn.execute(
        "INSERT INTO tenants (name, slug, created_at) VALUES (?, ?, ?)",
        (name, slug, int(time.time())),
    )
    conn.commit()
    return cur.lastrowid


def slug_exists(slug: str) -> bool:
    return _connect().execute("SELECT 1 FROM tenants WHERE slug = ?", (slug,)).fetchone() is not None


def create_user(tenant_id: int, username: str, email: str, password_hash: str, role: str = "staff") -> int:
    conn = _connect()
    cur = conn.execute(
        "INSERT INTO users (tenant_id, username, email, password_hash, role, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (tenant_id, username, email, password_hash, role, int(time.time())),
    )
    conn.commit()
    return cur.lastrowid


def get_user_by_username(username: str):
    return _connect().execute(
        "SELECT * FROM users WHERE username = ? AND is_active = 1", (username,)
    ).fetchone()


def get_user_by_email(email: str):
    return _connect().execute(
        "SELECT * FROM users WHERE email = ? AND is_active = 1", (email,)
    ).fetchone()


def get_user_by_id(user_id: int):
    return _connect().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def username_or_email_taken(username: str, email: str) -> bool:
    return _connect().execute(
        "SELECT 1 FROM users WHERE username = ? OR email = ?", (username, email)
    ).fetchone() is not None


def list_users_for_tenant(tenant_id: int):
    return _connect().execute(
        "SELECT * FROM users WHERE tenant_id = ? ORDER BY created_at", (tenant_id,)
    ).fetchall()


def count_owners(tenant_id: int) -> int:
    return _connect().execute(
        "SELECT COUNT(*) c FROM users WHERE tenant_id = ? AND role = 'owner' AND is_active = 1",
        (tenant_id,),
    ).fetchone()["c"]


def deactivate_user(tenant_id: int, user_id: int):
    conn = _connect()
    conn.execute("UPDATE users SET is_active = 0 WHERE id = ? AND tenant_id = ?", (user_id, tenant_id))
    conn.commit()


def update_password(user_id: int, password_hash: str):
    conn = _connect()
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
    conn.commit()


def update_username(user_id: int, username: str):
    conn = _connect()
    conn.execute("UPDATE users SET username = ? WHERE id = ?", (username, user_id))
    conn.commit()


def create_password_reset(user_id: int, token: str, expires_at: int):
    conn = _connect()
    conn.execute(
        "INSERT INTO password_resets (user_id, token, expires_at) VALUES (?, ?, ?)",
        (user_id, token, expires_at),
    )
    conn.commit()


def get_valid_reset(token: str):
    row = _connect().execute(
        "SELECT * FROM password_resets WHERE token = ? AND used = 0", (token,)
    ).fetchone()
    return row if (row and row["expires_at"] >= int(time.time())) else None


def mark_reset_used(token: str):
    conn = _connect()
    conn.execute("UPDATE password_resets SET used = 1 WHERE token = ?", (token,))
    conn.commit()


def add_audit(tenant_id, ip: str, who: str, action: str, detail: str = ""):
    conn = _connect()
    conn.execute(
        "INSERT INTO audit_log (tenant_id, ts, ip, who, action, detail) VALUES (?, ?, ?, ?, ?, ?)",
        (tenant_id, int(time.time()), ip, who, action, detail),
    )
    conn.commit()


def get_audit(tenant_id: int, limit: int = 100):
    rows = _connect().execute(
        "SELECT * FROM audit_log WHERE tenant_id = ? ORDER BY id DESC LIMIT ?",
        (tenant_id, limit),
    ).fetchall()
    return list(reversed(rows))


# ── Generic per-tenant JSON blob storage (settings / clients / mapping / activity / profiles) ──

def _get_blob(table: str, tenant_id: int):
    conn = _connect()
    row = conn.execute(f"SELECT json FROM {table} WHERE tenant_id = ?", (tenant_id,)).fetchone()
    return json.loads(row["json"]) if row else None


def _set_blob(table: str, tenant_id: int, data):
    payload = json.dumps(data, ensure_ascii=False)
    conn = _connect()
    conn.execute(
        f"INSERT INTO {table} (tenant_id, json) VALUES (?, ?) "
        f"ON CONFLICT(tenant_id) DO UPDATE SET json = excluded.json",
        (tenant_id, payload),
    )
    conn.commit()


def get_settings_blob(tenant_id: int):
    from modules.cache import get as _cget, set as _cset
    key = f"settings:{tenant_id}"
    cached = _cget(key)
    if cached is not None:
        return cached
    val = _get_blob("settings", tenant_id)
    if val is not None:
        _cset(key, val)
    return val


def set_settings_blob(tenant_id: int, data: dict):
    from modules.cache import set as _cset, invalidate as _cinval
    _set_blob("settings", tenant_id, data)
    _cinval(f"settings:{tenant_id}")
    _cset(f"settings:{tenant_id}", data)


def get_settings(tenant_id: int):
    conn = _connect()
    return conn.execute("SELECT json FROM settings WHERE tenant_id = ?", (tenant_id,)).fetchone()


def get_clients_blob(tenant_id: int):
    from modules.cache import get as _cget, set as _cset
    key = f"clients:{tenant_id}"
    cached = _cget(key)
    if cached is not None:
        return cached
    val = _get_blob("clients", tenant_id)
    if val is not None:
        _cset(key, val)
    return val


def set_clients_blob(tenant_id: int, data: list):
    from modules.cache import set as _cset, invalidate as _cinval
    _set_blob("clients", tenant_id, data)
    _cinval(f"clients:{tenant_id}")
    _cset(f"clients:{tenant_id}", data)


def get_clients(tenant_id: int):
    return _connect().execute("SELECT json FROM clients WHERE tenant_id = ?", (tenant_id,)).fetchone()


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
