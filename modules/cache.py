"""Simple thread-safe TTL cache for per-tenant blobs.

Avoids repeated SQLite reads for settings/clients on every API request.
Cache is invalidated on write automatically via the patched set_*_blob helpers.
"""
import threading
import time
from typing import Any, Optional

_lock = threading.Lock()
_store: dict[str, tuple[Any, float]] = {}  # key -> (value, expires_at)

DEFAULT_TTL = 30  # seconds


def get(key: str) -> Optional[Any]:
    with _lock:
        entry = _store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            del _store[key]
            return None
        return value


def set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
    with _lock:
        _store[key] = (value, time.monotonic() + ttl)


def invalidate(key: str) -> None:
    with _lock:
        _store.pop(key, None)


def invalidate_prefix(prefix: str) -> None:
    with _lock:
        for k in list(_store):
            if k.startswith(prefix):
                del _store[k]
