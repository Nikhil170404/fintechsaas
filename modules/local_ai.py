"""Small, deliberately constrained client for a locally running Ollama model.

The application never accepts an arbitrary AI URL.  Only a loopback Ollama
endpoint is permitted so financial documents and client details cannot be
silently sent to a third-party service.
"""

from __future__ import annotations

import json
from urllib.error import URLError
from urllib.request import Request, urlopen

OLLAMA_URL = "http://127.0.0.1:11434"
MAX_PROMPT_CHARS = 24_000
TIMEOUT_SECONDS = 45


class LocalAIError(RuntimeError):
    pass


def status() -> dict:
    """Return only local runtime metadata; prompts and client data are never logged."""
    try:
        with urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        models = [model.get("name", "") for model in payload.get("models", [])]
        return {"available": True, "models": models}
    except (URLError, OSError, ValueError):
        return {"available": False, "models": []}


def generate(model: str, prompt: str) -> str:
    """Generate a suggestion locally.  The caller must display it for approval."""
    if not model or len(prompt) > MAX_PROMPT_CHARS:
        raise LocalAIError("The local AI request is invalid or too large.")

    body = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
    request = Request(
        f"{OLLAMA_URL}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, OSError, ValueError) as exc:
        raise LocalAIError("FinDesk could not reach the local AI service.") from exc

    answer = payload.get("response", "").strip()
    if not answer:
        raise LocalAIError("The local AI service did not return a suggestion.")
    return answer
