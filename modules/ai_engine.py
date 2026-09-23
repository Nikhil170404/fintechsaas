"""Local AI engine: Ollama client + RAG over tenant financial data.

Auto-detects Ollama, starts it if installed but not running, pulls required
models on first use. RAG stores embeddings in SQLite (no extra vector DB).
"""
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import requests

OLLAMA_BASE = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_LLM = "llama3.2"
DEFAULT_EMBED = "nomic-embed-text"
REQUIRED_MODELS = [DEFAULT_LLM, DEFAULT_EMBED]
CHUNK_SIZE = 400  # words per chunk


# ── Ollama process management ─────────────────────────────────────────────────

def _ollama_binary() -> Optional[str]:
    paths = [
        shutil.which("ollama"),
        "/usr/local/bin/ollama",
        str(Path.home() / ".ollama" / "ollama"),
        "C:/Program Files/Ollama/ollama.exe",
    ]
    return next((p for p in paths if p and Path(p).exists()), None)


def ensure_ollama_running() -> dict:
    """Return {running, started, binary, install_url}."""
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=2)
        if r.status_code == 200:
            return {"running": True, "started": False, "binary": _ollama_binary()}
    except Exception:
        pass

    binary = _ollama_binary()
    if binary:
        try:
            subprocess.Popen(
                [binary, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            for _ in range(10):
                time.sleep(1)
                try:
                    r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=1)
                    if r.status_code == 200:
                        return {"running": True, "started": True, "binary": binary}
                except Exception:
                    pass
        except Exception:
            pass

    return {
        "running": False,
        "started": False,
        "binary": binary,
        "install_url": "https://ollama.ai/download",
        "install_cmd": {
            "linux": "curl -fsSL https://ollama.ai/install.sh | sh",
            "mac": "brew install ollama",
            "windows": "Download from https://ollama.ai/download",
        },
    }


# ── Ollama HTTP client ────────────────────────────────────────────────────────

class OllamaClient:
    def __init__(self, base_url: str = OLLAMA_BASE):
        self.base = base_url.rstrip("/")

    def is_running(self) -> bool:
        try:
            return requests.get(f"{self.base}/api/tags", timeout=2).status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        try:
            r = requests.get(f"{self.base}/api/tags", timeout=5)
            return [m["name"] for m in r.json().get("models", [])]
        except Exception:
            return []

    def has_model(self, name: str) -> bool:
        return any(name in m for m in self.list_models())

    def pull_model(self, model: str, stream: bool = False) -> dict:
        r = requests.post(
            f"{self.base}/api/pull",
            json={"name": model, "stream": stream},
            timeout=600,
        )
        return r.json()

    def embed(self, text: str, model: str = DEFAULT_EMBED) -> list[float]:
        try:
            r = requests.post(
                f"{self.base}/api/embeddings",
                json={"model": model, "prompt": text[:2000]},
                timeout=30,
            )
            return r.json().get("embedding", [])
        except Exception:
            return []

    def chat(
        self,
        messages: list[dict],
        model: str = DEFAULT_LLM,
        system: str = "",
    ) -> str:
        payload = {"model": model, "messages": messages, "stream": False}
        if system:
            payload["system"] = system
        try:
            r = requests.post(f"{self.base}/api/chat", json=payload, timeout=120)
            return r.json().get("message", {}).get("content", "")
        except Exception as e:
            return f"[AI error: {e}]"


# ── Vector helpers ─────────────────────────────────────────────────────────────

def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    return dot / (mag_a * mag_b) if mag_a and mag_b else 0.0


# ── RAG engine ────────────────────────────────────────────────────────────────

class RAGEngine:
    """Embeds text chunks into SQLite, retrieves by cosine similarity."""

    def __init__(self, tenant_id: int, ollama: OllamaClient):
        self.tenant_id = tenant_id
        self.ollama = ollama
        self._ensure_table()

    def _ensure_table(self):
        from modules.db import get_db
        with get_db() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rag_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id INTEGER NOT NULL,
                    doc_id TEXT NOT NULL,
                    chunk_text TEXT NOT NULL,
                    embedding TEXT NOT NULL,
                    metadata TEXT,
                    created_at INTEGER NOT NULL
                )
            """)
            conn.commit()

    def index_text(self, doc_id: str, text: str, metadata: dict = None) -> int:
        from modules.db import get_db
        with get_db() as conn:
            conn.execute(
                "DELETE FROM rag_chunks WHERE tenant_id = ? AND doc_id = ?",
                (self.tenant_id, doc_id),
            )
            conn.commit()

        words = text.split()
        chunks = [" ".join(words[i:i + CHUNK_SIZE]) for i in range(0, len(words), CHUNK_SIZE)]
        chunks = [c for c in chunks if c.strip()]

        meta_json = json.dumps(metadata or {})
        inserted = 0
        with get_db() as conn:
            for chunk in chunks:
                emb = self.ollama.embed(chunk)
                if emb:
                    conn.execute(
                        "INSERT INTO rag_chunks "
                        "(tenant_id, doc_id, chunk_text, embedding, metadata, created_at) "
                        "VALUES (?,?,?,?,?,?)",
                        (self.tenant_id, doc_id, chunk, json.dumps(emb), meta_json, int(time.time())),
                    )
                    inserted += 1
            conn.commit()
        return inserted

    def index_clients(self, clients: list[dict]) -> int:
        total = 0
        for client in clients:
            acct = client.get("account_no", client.get("id", ""))
            doc_id = f"client_{acct}"
            lines = [f"{k}: {v}" for k, v in client.items() if v and str(v).strip()]
            text = "\n".join(lines)
            meta = {
                "type": "client",
                "account_no": str(acct),
                "name": client.get("name", ""),
            }
            total += self.index_text(doc_id, text, meta)
        return total

    def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        from modules.db import get_db
        query_emb = self.ollama.embed(query)
        if not query_emb:
            return []

        with get_db() as conn:
            rows = conn.execute(
                "SELECT chunk_text, embedding, metadata FROM rag_chunks WHERE tenant_id = ?",
                (self.tenant_id,),
            ).fetchall()

        scored = []
        for row in rows:
            try:
                score = _cosine(query_emb, json.loads(row["embedding"]))
                scored.append({
                    "text": row["chunk_text"],
                    "score": score,
                    "metadata": json.loads(row["metadata"] or "{}"),
                })
            except Exception:
                pass

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def chunk_count(self) -> int:
        from modules.db import get_db
        with get_db() as conn:
            return conn.execute(
                "SELECT COUNT(*) c FROM rag_chunks WHERE tenant_id = ?",
                (self.tenant_id,),
            ).fetchone()["c"]

    def answer(
        self,
        question: str,
        model: str = DEFAULT_LLM,
        history: list | None = None,
    ) -> str:
        chunks = self.retrieve(question, top_k=5)
        context = "\n\n---\n\n".join(c["text"] for c in chunks)

        system = (
            "You are an AI assistant for a FinTech company called FinTech Desk. "
            "Answer questions about client accounts, loans, portfolios, invoices, "
            "and financial data. Be concise and professional. "
            "If information is not in the context, say you don't have that data."
        )
        if context:
            system += f"\n\nContext from financial records:\n{context}"

        messages = list(history or []) + [{"role": "user", "content": question}]
        return self.ollama.chat(messages, model=model, system=system)
