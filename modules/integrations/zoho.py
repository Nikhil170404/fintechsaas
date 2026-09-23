"""Zoho CRM, Books, and Mail integration."""
import json
import time
import requests
from typing import Optional


class ZohoOAuth:
    AUTH_URL = "https://accounts.zoho.com/oauth/v2/auth"
    TOKEN_URL = "https://accounts.zoho.com/oauth/v2/token"
    SCOPES = [
        "ZohoCRM.modules.ALL",
        "ZohoBooks.invoices.ALL",
        "ZohoBooks.contacts.ALL",
        "ZohoMail.accounts.ALL",
        "ZohoMail.messages.ALL",
    ]

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def get_auth_url(self, state: str = "") -> str:
        scope = ",".join(self.SCOPES)
        params = (
            f"response_type=code&client_id={self.client_id}"
            f"&scope={scope}&redirect_uri={self.redirect_uri}"
            f"&access_type=offline&state={state}"
        )
        return f"{self.AUTH_URL}?{params}"

    def exchange_code(self, code: str) -> dict:
        resp = requests.post(self.TOKEN_URL, data={
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "code": code,
        }, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def refresh_token(self, refresh_token: str) -> dict:
        resp = requests.post(self.TOKEN_URL, data={
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
        }, timeout=15)
        resp.raise_for_status()
        return resp.json()


class ZohoCRM:
    BASE = "https://www.zohoapis.com/crm/v3"

    def __init__(self, access_token: str):
        self.headers = {
            "Authorization": f"Zoho-oauthtoken {access_token}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: dict = None) -> dict:
        r = requests.get(f"{self.BASE}{path}", headers=self.headers, params=params, timeout=15)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, data: dict) -> dict:
        r = requests.post(f"{self.BASE}{path}", headers=self.headers, json=data, timeout=15)
        r.raise_for_status()
        return r.json()

    def _put(self, path: str, data: dict) -> dict:
        r = requests.put(f"{self.BASE}{path}", headers=self.headers, json=data, timeout=15)
        r.raise_for_status()
        return r.json()

    def list_contacts(self, page: int = 1, per_page: int = 200) -> list:
        data = self._get("/Contacts", params={"page": page, "per_page": per_page})
        return data.get("data", [])

    def create_contact(self, contact: dict) -> dict:
        data = self._post("/Contacts", {"data": [contact]})
        return data.get("data", [{}])[0]

    def update_contact(self, contact_id: str, contact: dict) -> dict:
        data = self._put(f"/Contacts/{contact_id}", {"data": [contact]})
        return data.get("data", [{}])[0]

    def create_lead(self, lead: dict) -> dict:
        data = self._post("/Leads", {"data": [lead]})
        return data.get("data", [{}])[0]

    def list_accounts(self) -> list:
        data = self._get("/Accounts")
        return data.get("data", [])

    def search_records(self, module: str, criteria: str) -> list:
        data = self._get(f"/{module}/search", params={"criteria": criteria})
        return data.get("data", [])

    def sync_clients_from_crm(self) -> list:
        """Pull all CRM contacts and map to local client format."""
        contacts = self.list_contacts()
        clients = []
        for c in contacts:
            clients.append({
                "name": f"{c.get('First_Name', '')} {c.get('Last_Name', '')}".strip(),
                "email": c.get("Email", ""),
                "phone": c.get("Phone", ""),
                "account_no": c.get("Account_Name", {}).get("name", "") if isinstance(c.get("Account_Name"), dict) else c.get("Account_Name", ""),
                "zoho_id": c.get("id", ""),
            })
        return clients

    def push_client_to_crm(self, client: dict) -> dict:
        """Push a local client record to Zoho CRM as a contact."""
        name_parts = client.get("name", "").split(" ", 1)
        contact = {
            "First_Name": name_parts[0],
            "Last_Name": name_parts[1] if len(name_parts) > 1 else "",
            "Email": client.get("email", ""),
            "Phone": client.get("phone", ""),
            "Account_Name": client.get("account_no", ""),
        }
        return self.create_contact(contact)


class ZohoBooks:
    BASE = "https://www.zohoapis.com/books/v3"

    def __init__(self, access_token: str, organization_id: str):
        self.headers = {
            "Authorization": f"Zoho-oauthtoken {access_token}",
            "Content-Type": "application/json",
        }
        self.org_id = organization_id

    def _params(self, extra: dict = None) -> dict:
        p = {"organization_id": self.org_id}
        if extra:
            p.update(extra)
        return p

    def _get(self, path: str, params: dict = None) -> dict:
        r = requests.get(
            f"{self.BASE}{path}",
            headers=self.headers,
            params=self._params(params),
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, data: dict) -> dict:
        r = requests.post(
            f"{self.BASE}{path}",
            headers=self.headers,
            json=data,
            params=self._params(),
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

    def create_invoice(self, invoice_data: dict) -> dict:
        return self._post("/invoices", invoice_data)

    def send_invoice_email(self, invoice_id: str, to_emails: list, body: str = "") -> dict:
        return self._post(f"/invoices/{invoice_id}/email", {
            "to_mail_ids": to_emails,
            "body": body,
        })

    def list_customers(self) -> list:
        data = self._get("/contacts", {"contact_type": "customer"})
        return data.get("contacts", [])

    def create_customer(self, contact: dict) -> dict:
        return self._post("/contacts", contact)

    def build_invoice_payload(self, client: dict, items: list, currency: str = "INR") -> dict:
        return {
            "customer_name": client.get("name", ""),
            "customer_email": client.get("email", ""),
            "currency_code": currency,
            "line_items": [
                {
                    "name": i.get("description", "Service"),
                    "quantity": i.get("quantity", 1),
                    "rate": i.get("rate", 0),
                    "tax_name": i.get("tax_name", "GST"),
                    "tax_percentage": i.get("tax_pct", 18),
                }
                for i in items
            ],
        }


class ZohoMail:
    BASE = "https://mail.zoho.com/api"

    def __init__(self, access_token: str, account_id: str):
        self.headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
        self.account_id = account_id

    def list_accounts(self) -> list:
        r = requests.get(f"{self.BASE}/accounts", headers=self.headers, timeout=15)
        r.raise_for_status()
        return r.json().get("data", [])

    def send_email(
        self,
        to: list,
        subject: str,
        html_body: str,
        attachments: list = None,
        cc: list = None,
    ) -> dict:
        payload = {
            "fromAddress": "",  # filled by Zoho using account_id
            "toAddress": ",".join(to),
            "subject": subject,
            "mailFormat": "html",
            "content": html_body,
        }
        if cc:
            payload["ccAddress"] = ",".join(cc)

        if attachments:
            # For attachments, a multipart upload is required; simplified here
            payload["attachments"] = attachments

        r = requests.post(
            f"{self.BASE}/accounts/{self.account_id}/messages",
            headers={**self.headers, "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        r.raise_for_status()
        return r.json()
