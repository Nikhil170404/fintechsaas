"""Twilio SMS / WhatsApp integration."""
import requests
from requests.auth import HTTPBasicAuth


TWILIO_BASE = "https://api.twilio.com/2010-04-01"


class TwilioClient:
    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        self.account_sid = account_sid
        self.auth = HTTPBasicAuth(account_sid, auth_token)
        self.from_number = from_number

    def _post(self, path: str, data: dict) -> dict:
        r = requests.post(
            f"{TWILIO_BASE}/Accounts/{self.account_sid}{path}",
            auth=self.auth,
            data=data,
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

    def send_sms(self, to: str, body: str) -> dict:
        return self._post("/Messages.json", {
            "From": self.from_number,
            "To": to,
            "Body": body,
        })

    def send_whatsapp(self, to: str, body: str) -> dict:
        return self._post("/Messages.json", {
            "From": f"whatsapp:{self.from_number}",
            "To": f"whatsapp:{to}",
            "Body": body,
        })

    def send_whatsapp_media(self, to: str, body: str, media_url: str) -> dict:
        return self._post("/Messages.json", {
            "From": f"whatsapp:{self.from_number}",
            "To": f"whatsapp:{to}",
            "Body": body,
            "MediaUrl": media_url,
        })

    def bulk_sms(self, recipients: list, body: str) -> list:
        results = []
        for to in recipients:
            try:
                result = self.send_sms(to, body)
                results.append({"to": to, "status": "sent", "sid": result.get("sid")})
            except Exception as e:
                results.append({"to": to, "status": "failed", "error": str(e)})
        return results
