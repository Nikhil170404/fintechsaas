"""WhatsApp Business API integration (Meta Cloud API)."""
import json
from pathlib import Path
from typing import Optional

import requests


WHATSAPP_BASE = "https://graph.facebook.com/v18.0"


class WhatsAppBusiness:
    def __init__(self, phone_number_id: str, access_token: str):
        self.phone_number_id = phone_number_id
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    @property
    def _base_url(self) -> str:
        return f"{WHATSAPP_BASE}/{self.phone_number_id}/messages"

    def send_text(self, to: str, body: str) -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": body},
        }
        r = requests.post(self._base_url, headers=self.headers, json=payload, timeout=15)
        r.raise_for_status()
        return r.json()

    def send_document(self, to: str, document_url: str, filename: str, caption: str = "") -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "document",
            "document": {
                "link": document_url,
                "caption": caption,
                "filename": filename,
            },
        }
        r = requests.post(self._base_url, headers=self.headers, json=payload, timeout=30)
        r.raise_for_status()
        return r.json()

    def send_template(self, to: str, template_name: str, language: str = "en_US", components: list = None) -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
                "components": components or [],
            },
        }
        r = requests.post(self._base_url, headers=self.headers, json=payload, timeout=15)
        r.raise_for_status()
        return r.json()

    def upload_media(self, file_path: str, mime_type: str = "application/pdf") -> str:
        """Upload a file to WhatsApp media storage, returns media_id."""
        path = Path(file_path)
        upload_url = f"{WHATSAPP_BASE}/{self.phone_number_id}/media"
        with open(path, "rb") as f:
            r = requests.post(
                upload_url,
                headers={"Authorization": self.headers["Authorization"]},
                data={"messaging_product": "whatsapp"},
                files={"file": (path.name, f, mime_type)},
                timeout=60,
            )
        r.raise_for_status()
        return r.json().get("id", "")

    def send_document_by_id(self, to: str, media_id: str, filename: str, caption: str = "") -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "document",
            "document": {
                "id": media_id,
                "caption": caption,
                "filename": filename,
            },
        }
        r = requests.post(self._base_url, headers=self.headers, json=payload, timeout=30)
        r.raise_for_status()
        return r.json()

    def send_statement_to_client(self, client: dict, pdf_path: str, body_text: str = "") -> dict:
        """Upload PDF and send as document to a client's WhatsApp number."""
        phone = str(client.get("phone", "")).strip().replace(" ", "").replace("-", "")
        if not phone:
            raise ValueError(f"No phone for client {client.get('name', '')}")
        # Normalize Indian numbers
        if phone.startswith("0"):
            phone = "91" + phone[1:]
        elif not phone.startswith("+") and not phone.startswith("91"):
            phone = "91" + phone

        media_id = self.upload_media(pdf_path)
        fname = Path(pdf_path).name
        caption = body_text or f"Please find your account statement: {fname}"
        return self.send_document_by_id(phone, media_id, fname, caption)
