"""Payment gateway integrations: Razorpay, Stripe, PayU."""
import hashlib
import hmac
import json
import time
from typing import Optional

import requests


class RazorpayClient:
    BASE = "https://api.razorpay.com/v1"

    def __init__(self, key_id: str, key_secret: str):
        self.auth = (key_id, key_secret)
        self.key_id = key_id

    def _get(self, path: str, params: dict = None) -> dict:
        r = requests.get(f"{self.BASE}{path}", auth=self.auth, params=params, timeout=15)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, data: dict) -> dict:
        r = requests.post(
            f"{self.BASE}{path}",
            auth=self.auth,
            json=data,
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

    def create_payment_link(
        self,
        amount_paise: int,
        currency: str = "INR",
        description: str = "",
        customer: dict = None,
        callback_url: str = "",
        expire_by: int = 0,
        reference_id: str = "",
    ) -> dict:
        payload = {
            "amount": amount_paise,
            "currency": currency,
            "description": description,
        }
        if customer:
            payload["customer"] = customer
        if callback_url:
            payload["callback_url"] = callback_url
            payload["callback_method"] = "get"
        if expire_by:
            payload["expire_by"] = expire_by
        if reference_id:
            payload["reference_id"] = reference_id
        return self._post("/payment_links", payload)

    def create_invoice_link(self, client: dict, amount: float, description: str = "") -> str:
        """Create a Razorpay payment link and return the short URL."""
        customer = {
            "name": client.get("name", ""),
            "email": client.get("email", ""),
            "contact": client.get("phone", ""),
        }
        expire_by = int(time.time()) + (7 * 24 * 3600)  # 7 days
        data = self.create_payment_link(
            amount_paise=int(amount * 100),
            description=description or f"Payment from {client.get('name', '')}",
            customer=customer,
            expire_by=expire_by,
        )
        return data.get("short_url", data.get("id", ""))

    def verify_payment_signature(self, order_id: str, payment_id: str, signature: str, key_secret: str) -> bool:
        msg = f"{order_id}|{payment_id}"
        expected = hmac.new(
            key_secret.encode(),
            msg.encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def create_order(self, amount_paise: int, currency: str = "INR", receipt: str = "") -> dict:
        return self._post("/orders", {
            "amount": amount_paise,
            "currency": currency,
            "receipt": receipt,
        })

    def get_payment(self, payment_id: str) -> dict:
        return self._get(f"/payments/{payment_id}")

    def list_payments(self, count: int = 20) -> list:
        data = self._get("/payments", {"count": count})
        return data.get("items", [])


class StripeClient:
    BASE = "https://api.stripe.com/v1"

    def __init__(self, secret_key: str):
        self.headers = {
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

    def _post(self, path: str, data: dict) -> dict:
        r = requests.post(f"{self.BASE}{path}", headers=self.headers, data=data, timeout=15)
        r.raise_for_status()
        return r.json()

    def _get(self, path: str, params: dict = None) -> dict:
        r = requests.get(f"{self.BASE}{path}", headers=self.headers, params=params, timeout=15)
        r.raise_for_status()
        return r.json()

    def create_customer(self, email: str, name: str = "", phone: str = "") -> dict:
        return self._post("/customers", {"email": email, "name": name, "phone": phone})

    def create_payment_link(self, price_data: dict, quantity: int = 1) -> dict:
        # Create a price first, then a payment link
        price = self._post("/prices", {
            "currency": price_data.get("currency", "inr"),
            "unit_amount": price_data.get("unit_amount", 0),
            "product_data[name]": price_data.get("name", "Invoice"),
        })
        link = self._post("/payment_links", {
            "line_items[0][price]": price["id"],
            "line_items[0][quantity]": quantity,
        })
        return link

    def create_invoice(self, customer_id: str, items: list) -> dict:
        invoice = self._post("/invoices", {
            "customer": customer_id,
            "collection_method": "send_invoice",
            "days_until_due": 7,
        })
        for item in items:
            self._post("/invoiceitems", {
                "customer": customer_id,
                "invoice": invoice["id"],
                "amount": int(item.get("amount", 0) * 100),
                "currency": item.get("currency", "inr"),
                "description": item.get("description", ""),
            })
        return self._post(f"/invoices/{invoice['id']}/finalize", {})

    def send_invoice(self, invoice_id: str) -> dict:
        return self._post(f"/invoices/{invoice_id}/send", {})
