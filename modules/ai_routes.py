"""AI Blueprint — local Ollama + RAG endpoints consumed by the Flutter app."""
from flask import Blueprint, jsonify, request, Response, stream_with_context
import json

from modules.api_routes import api_auth_required

ai_bp = Blueprint("ai", __name__, url_prefix="/api/v1/ai")


def _ollama():
    from modules.ai_engine import OllamaClient
    return OllamaClient()


# ── Status / setup ────────────────────────────────────────────────────────────

@ai_bp.route("/status", methods=["GET"])
@api_auth_required
def status():
    from modules.ai_engine import ensure_ollama_running, DEFAULT_LLM, DEFAULT_EMBED
    info = ensure_ollama_running()
    ollama = _ollama()
    models = ollama.list_models() if info["running"] else []
    return jsonify({
        **info,
        "models": models,
        "has_llm": any(DEFAULT_LLM in m for m in models),
        "has_embed": any(DEFAULT_EMBED in m for m in models),
        "default_llm": DEFAULT_LLM,
        "default_embed": DEFAULT_EMBED,
    })


@ai_bp.route("/models", methods=["GET"])
@api_auth_required
def list_models():
    ollama = _ollama()
    return jsonify({"models": ollama.list_models() if ollama.is_running() else []})


@ai_bp.route("/pull", methods=["POST"])
@api_auth_required
def pull_model():
    data = request.get_json(force=True, silent=True) or {}
    from modules.ai_engine import DEFAULT_LLM
    model = data.get("model", DEFAULT_LLM)
    ollama = _ollama()
    if not ollama.is_running():
        return jsonify({"error": "Ollama is not running. Install it first."}), 503
    result = ollama.pull_model(model)
    return jsonify({"message": f"Model '{model}' pulled successfully", "status": result.get("status", "done")})


# ── RAG indexing ──────────────────────────────────────────────────────────────

@ai_bp.route("/index", methods=["POST"])
@api_auth_required
def index_data():
    tenant_id = request.api_tenant_id
    from modules.ai_engine import OllamaClient, RAGEngine, DEFAULT_EMBED
    from modules.db import get_clients_blob, get_settings_blob

    ollama = OllamaClient()
    if not ollama.is_running():
        return jsonify({"error": "Ollama is not running"}), 503
    if not ollama.has_model(DEFAULT_EMBED):
        try:
            ollama.pull_model(DEFAULT_EMBED)
        except Exception as e:
            return jsonify({"error": f"Could not pull embedding model: {e}"}), 500

    clients = get_clients_blob(tenant_id) or []
    settings = get_settings_blob(tenant_id) or {}

    rag = RAGEngine(tenant_id, ollama)

    # Index clients
    client_chunks = rag.index_clients(clients)

    # Index company settings as context
    if settings:
        lines = [f"{k}: {v}" for k, v in settings.items()
                 if v and "password" not in k.lower() and "secret" not in k.lower()]
        rag.index_text("company_settings", "\n".join(lines), {"type": "settings"})

    return jsonify({
        "message": "Indexing complete",
        "clients_indexed": len(clients),
        "chunks_created": client_chunks,
        "total_chunks": rag.chunk_count(),
    })


@ai_bp.route("/index/status", methods=["GET"])
@api_auth_required
def index_status():
    tenant_id = request.api_tenant_id
    from modules.ai_engine import OllamaClient, RAGEngine
    rag = RAGEngine(tenant_id, OllamaClient())
    return jsonify({"total_chunks": rag.chunk_count()})


# ── Chat ──────────────────────────────────────────────────────────────────────

@ai_bp.route("/chat", methods=["POST"])
@api_auth_required
def chat():
    tenant_id = request.api_tenant_id
    data = request.get_json(force=True, silent=True) or {}
    question = str(data.get("message", "")).strip()
    model = data.get("model", "")
    history = data.get("history", [])

    if not question:
        return jsonify({"error": "message is required"}), 400

    from modules.ai_engine import OllamaClient, RAGEngine, DEFAULT_LLM, ensure_ollama_running
    info = ensure_ollama_running()
    if not info["running"]:
        return jsonify({
            "error": "Ollama is not running.",
            "install_url": info.get("install_url", "https://ollama.ai/download"),
            "install_cmd": info.get("install_cmd", {}),
        }), 503

    ollama = OllamaClient()
    chosen_model = model or DEFAULT_LLM

    # Auto-pull LLM if missing
    if not ollama.has_model(chosen_model):
        try:
            ollama.pull_model(chosen_model)
        except Exception as e:
            return jsonify({"error": f"Could not pull model '{chosen_model}': {e}"}), 500

    rag = RAGEngine(tenant_id, ollama)
    answer = rag.answer(question, model=chosen_model, history=history)
    return jsonify({"answer": answer, "model": chosen_model})
