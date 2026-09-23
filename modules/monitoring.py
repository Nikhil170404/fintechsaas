"""Error monitoring (Sentry), health checks, and backup utilities."""
import os
import shutil
import sqlite3
import subprocess
import time
from datetime import datetime
from pathlib import Path


# ── Sentry ────────────────────────────────────────────────────────────────────

def init_sentry():
    dsn = os.environ.get("SENTRY_DSN", "")
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        sentry_sdk.init(
            dsn=dsn,
            integrations=[FlaskIntegration()],
            traces_sample_rate=0.1,
            environment=os.environ.get("FLASK_ENV", "production"),
            release=os.environ.get("APP_VERSION", "1.0.0"),
        )
    except ImportError:
        pass   # sentry-sdk not installed — silent skip


# ── Health check ──────────────────────────────────────────────────────────────

def health_status() -> dict:
    from modules.db import _connect
    checks = {}

    # DB reachable
    try:
        conn = _connect()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    # Disk space
    try:
        stat = shutil.disk_usage(".")
        free_gb = stat.free / 1e9
        checks["disk_free_gb"] = round(free_gb, 2)
        checks["disk"] = "ok" if free_gb > 0.5 else "warning: low disk"
    except Exception:
        checks["disk"] = "unknown"

    # Data dir writable
    try:
        test = Path("data") / ".healthcheck"
        test.write_text("ok")
        test.unlink()
        checks["data_dir"] = "ok"
    except Exception as e:
        checks["data_dir"] = f"error: {e}"

    overall = "ok" if all(v == "ok" for v in checks.values() if isinstance(v, str)) else "degraded"
    return {
        "status": overall,
        "ts": int(time.time()),
        "version": os.environ.get("APP_VERSION", "1.0.0"),
        "checks": checks,
    }


# ── Backup ────────────────────────────────────────────────────────────────────

BACKUP_DIR = Path("data") / "backups"


def backup_database(label: str = "") -> Path:
    """Hot SQLite backup using the backup API. Returns the backup file path."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{label}" if label else ""
    dest = BACKUP_DIR / f"app_{ts}{suffix}.db"

    src = sqlite3.connect("data/app.db")
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()

    # Keep only the 30 most recent backups
    backups = sorted(BACKUP_DIR.glob("app_*.db"))
    for old in backups[:-30]:
        old.unlink(missing_ok=True)

    return dest


def backup_tenant_files(tenant_id: int) -> Path:
    """Zip a tenant's uploaded/output files."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"tenant_{tenant_id}_{ts}.zip"
    src = Path("data") / "tenants" / str(tenant_id)
    if not src.exists():
        return None
    shutil.make_archive(str(dest.with_suffix("")), "zip", str(src))
    return dest


def list_backups() -> list:
    if not BACKUP_DIR.exists():
        return []
    files = sorted(BACKUP_DIR.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
    return [{"name": f.name, "size_mb": round(f.stat().st_size / 1e6, 2),
             "ts": int(f.stat().st_mtime)} for f in files]


# ── Uptime tracking ───────────────────────────────────────────────────────────

_start_time = time.time()


def uptime_seconds() -> float:
    return time.time() - _start_time
