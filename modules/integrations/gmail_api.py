"""Gmail API / Google Workspace integration via OAuth 2.0."""
import base64
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from pathlib import Path
from typing import Optional

import requests


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
]


class GoogleOAuth:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def get_auth_url(self, state: str = "") -> str:
        scope = " ".join(SCOPES)
        return (
            f"{GOOGLE_AUTH_URL}?response_type=code"
            f"&client_id={self.client_id}"
            f"&redirect_uri={self.redirect_uri}"
            f"&scope={requests.utils.quote(scope)}"
            f"&access_type=offline&prompt=consent&state={state}"
        )

    def exchange_code(self, code: str) -> dict:
        r = requests.post(GOOGLE_TOKEN_URL, data={
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "code": code,
        }, timeout=15)
        r.raise_for_status()
        return r.json()

    def refresh_token(self, refresh_token: str) -> dict:
        r = requests.post(GOOGLE_TOKEN_URL, data={
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
        }, timeout=15)
        r.raise_for_status()
        return r.json()


class GmailSender:
    def __init__(self, access_token: str):
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def send_email(
        self,
        sender: str,
        to: list,
        subject: str,
        html_body: str,
        attachments: list = None,
        cc: list = None,
    ) -> dict:
        msg = MIMEMultipart("mixed")
        msg["From"] = sender
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = ", ".join(cc)

        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(html_body, "html"))
        msg.attach(alt)

        if attachments:
            for att in attachments:
                path = Path(att["path"])
                with open(path, "rb") as f:
                    part = MIMEApplication(f.read(), Name=path.name)
                part["Content-Disposition"] = f'attachment; filename="{path.name}"'
                msg.attach(part)

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        r = requests.post(
            f"{GMAIL_BASE}/users/me/messages/send",
            headers=self.headers,
            json={"raw": raw},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def get_profile(self) -> dict:
        r = requests.get(
            f"{GMAIL_BASE}/users/me/profile",
            headers=self.headers,
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    def list_messages(self, query: str = "", max_results: int = 20) -> list:
        r = requests.get(
            f"{GMAIL_BASE}/users/me/messages",
            headers=self.headers,
            params={"q": query, "maxResults": max_results},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("messages", [])
