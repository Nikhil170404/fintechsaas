"""Microsoft Graph API integration (Outlook / Microsoft 365)."""
import base64
import json
from pathlib import Path
from typing import Optional

import requests

MS_AUTH_BASE = "https://login.microsoftonline.com"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SCOPES = [
    "offline_access",
    "Mail.Send",
    "Mail.Read",
    "User.Read",
    "Contacts.Read",
    "Contacts.ReadWrite",
]


class MicrosoftOAuth:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, tenant: str = "common"):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.tenant = tenant

    @property
    def _token_url(self) -> str:
        return f"{MS_AUTH_BASE}/{self.tenant}/oauth2/v2.0/token"

    @property
    def _auth_url(self) -> str:
        return f"{MS_AUTH_BASE}/{self.tenant}/oauth2/v2.0/authorize"

    def get_auth_url(self, state: str = "") -> str:
        scope = " ".join(SCOPES)
        return (
            f"{self._auth_url}?response_type=code"
            f"&client_id={self.client_id}"
            f"&redirect_uri={requests.utils.quote(self.redirect_uri)}"
            f"&scope={requests.utils.quote(scope)}"
            f"&response_mode=query&state={state}"
        )

    def exchange_code(self, code: str) -> dict:
        r = requests.post(self._token_url, data={
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "code": code,
            "scope": " ".join(SCOPES),
        }, timeout=15)
        r.raise_for_status()
        return r.json()

    def refresh_token(self, refresh_token: str) -> dict:
        r = requests.post(self._token_url, data={
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "refresh_token": refresh_token,
            "scope": " ".join(SCOPES),
        }, timeout=15)
        r.raise_for_status()
        return r.json()


class OutlookSender:
    def __init__(self, access_token: str):
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def send_email(
        self,
        to: list,
        subject: str,
        html_body: str,
        attachments: list = None,
        cc: list = None,
        save_to_sent: bool = True,
    ) -> None:
        msg = {
            "message": {
                "subject": subject,
                "body": {"contentType": "HTML", "content": html_body},
                "toRecipients": [
                    {"emailAddress": {"address": addr}} for addr in to
                ],
            },
            "saveToSentItems": save_to_sent,
        }

        if cc:
            msg["message"]["ccRecipients"] = [
                {"emailAddress": {"address": addr}} for addr in cc
            ]

        if attachments:
            file_attachments = []
            for att in attachments:
                path = Path(att["path"])
                with open(path, "rb") as f:
                    content = base64.b64encode(f.read()).decode("utf-8")
                file_attachments.append({
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": path.name,
                    "contentBytes": content,
                    "contentType": att.get("content_type", "application/pdf"),
                })
            msg["message"]["attachments"] = file_attachments

        r = requests.post(
            f"{GRAPH_BASE}/me/sendMail",
            headers=self.headers,
            json=msg,
            timeout=60,
        )
        r.raise_for_status()

    def get_profile(self) -> dict:
        r = requests.get(f"{GRAPH_BASE}/me", headers=self.headers, timeout=10)
        r.raise_for_status()
        return r.json()

    def list_contacts(self) -> list:
        r = requests.get(f"{GRAPH_BASE}/me/contacts", headers=self.headers, timeout=15)
        r.raise_for_status()
        return r.json().get("value", [])

    def list_messages(self, top: int = 20, filter_str: str = "") -> list:
        params = {"$top": top}
        if filter_str:
            params["$filter"] = filter_str
        r = requests.get(
            f"{GRAPH_BASE}/me/messages",
            headers=self.headers,
            params=params,
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("value", [])


class TeamsNotifier:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send_card(self, title: str, text: str, facts: list = None) -> None:
        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": "0076D7",
            "summary": title,
            "sections": [{
                "activityTitle": title,
                "activityText": text,
                "facts": [{"name": f["name"], "value": f["value"]} for f in (facts or [])],
                "markdown": True,
            }],
        }
        r = requests.post(self.webhook_url, json=card, timeout=15)
        r.raise_for_status()
