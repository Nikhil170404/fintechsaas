"""Telegram Bot API integration for document delivery and notifications."""
from pathlib import Path
import requests


TELEGRAM_BASE = "https://api.telegram.org"


class TelegramBot:
    def __init__(self, token: str):
        self.token = token
        self._base = f"{TELEGRAM_BASE}/bot{token}"

    def _post(self, method: str, data: dict = None, files: dict = None) -> dict:
        url = f"{self._base}/{method}"
        r = requests.post(url, data=data, files=files, timeout=30)
        r.raise_for_status()
        return r.json()

    def send_message(self, chat_id: str, text: str, parse_mode: str = "HTML") -> dict:
        return self._post("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": parse_mode})

    def send_document(self, chat_id: str, file_path: str, caption: str = "") -> dict:
        path = Path(file_path)
        with open(path, "rb") as f:
            return self._post(
                "sendDocument",
                data={"chat_id": chat_id, "caption": caption},
                files={"document": (path.name, f, "application/pdf")},
            )

    def get_updates(self, offset: int = 0) -> list:
        result = self._post("getUpdates", {"offset": offset, "timeout": 0})
        return result.get("result", [])

    def notify_batch_complete(self, chat_id: str, count: int, job: str) -> dict:
        text = f"<b>✅ Batch Complete</b>\n\nJob: <code>{job}</code>\nDocuments sent: <b>{count}</b>"
        return self.send_message(chat_id, text)

    def notify_error(self, chat_id: str, error: str, job: str = "") -> dict:
        text = f"<b>❌ Error</b>\n\nJob: <code>{job}</code>\nError: <code>{error}</code>"
        return self.send_message(chat_id, text)
