import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path


HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "pinch_sandbox.local.json"
AUTH_URL = "https://auth.getpinch.com.au/connect/token"
TEST_BASE_URL = "https://api.getpinch.com.au/test"
PINCH_VERSION = "2020.1"


class PinchAPIError(RuntimeError):
    pass


def load_config():
    environment_config = {
        "environment": "test",
        "application_id": os.getenv("PINCH_APPLICATION_ID", "").strip(),
        "secret_key": os.getenv("PINCH_SECRET_KEY", "").strip(),
        "publishable_key": os.getenv("PINCH_PUBLISHABLE_KEY", "").strip(),
    }
    if environment_config["application_id"] or environment_config["secret_key"]:
        return environment_config
    if not CONFIG_PATH.exists():
        return {
            "environment": "test",
            "application_id": "",
            "secret_key": "",
            "publishable_key": "",
        }
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    data["environment"] = "test"
    return data


def save_config(application_id, secret_key, publishable_key=""):
    data = {
        "environment": "test",
        "application_id": str(application_id or "").strip(),
        "secret_key": str(secret_key or "").strip(),
        "publishable_key": str(publishable_key or "").strip(),
        "note": "Local Pinch sandbox credentials. Never commit or share this file.",
    }
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


class PinchSandboxClient:
    def __init__(self, application_id, secret_key, timeout=30):
        self.application_id = str(application_id or "").strip()
        self.secret_key = str(secret_key or "").strip()
        self.timeout = int(timeout)
        self.access_token = ""

    def authenticate(self):
        if not self.application_id or not self.secret_key:
            raise PinchAPIError("Pinch sandbox Application ID and Secret are required.")
        basic = base64.b64encode(
            f"{self.application_id}:{self.secret_key}".encode("utf-8")
        ).decode("ascii")
        body = urllib.parse.urlencode(
            {"grant_type": "client_credentials", "scope": "api1"}
        ).encode("ascii")
        request = urllib.request.Request(
            AUTH_URL,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
        )
        payload = self._open_json(request)
        token = str(payload.get("access_token") or "").strip()
        if not token:
            raise PinchAPIError("Pinch authentication succeeded without an access token.")
        self.access_token = token
        return payload

    def create_payer(self, first_name, last_name, email, mobile="", metadata=None):
        payload = {
            "firstName": str(first_name or "").strip(),
            "lastName": str(last_name or "").strip(),
            "email": str(email or "").strip(),
        }
        if str(mobile or "").strip():
            payload["mobile"] = str(mobile).strip()
        if metadata:
            payload["metadata"] = metadata
        return self._api_json("POST", "/payers", payload)

    def get_payer(self, payer_id):
        payer_id = urllib.parse.quote(str(payer_id or "").strip(), safe="")
        if not payer_id:
            raise PinchAPIError("A Pinch Payer ID is required.")
        return self._api_json("GET", f"/payers/{payer_id}")

    def create_payment_source(self, payer_id, token, source_type="credit-card"):
        """Attach a CaptureJS token to a payer without receiving raw card data."""
        payer_id = urllib.parse.quote(str(payer_id or "").strip(), safe="")
        token = str(token or "").strip()
        source_type = str(source_type or "credit-card").strip()
        if not payer_id or not token:
            raise PinchAPIError("A Pinch Payer ID and CaptureJS token are required.")
        if source_type not in {"credit-card", "bank-account"}:
            raise PinchAPIError("Unsupported Pinch payment source type.")
        return self._api_json(
            "POST",
            f"/payers/{payer_id}/sources",
            {"sourceType": source_type, "token": token},
        )

    def create_scheduled_payment(
        self,
        payer_id,
        amount_cents,
        description,
        source_id="",
        transaction_date="",
        nonce="",
    ):
        """Submit an authorised collection against a saved Pinch source."""
        payload = {
            "payerId": str(payer_id or "").strip(),
            "amount": int(amount_cents),
            "transactionDate": str(transaction_date or date.today().isoformat()),
            "description": str(description or "").strip(),
        }
        if str(source_id or "").strip():
            payload["sourceId"] = str(source_id).strip()
        if str(nonce or "").strip():
            payload["nonce"] = str(nonce).strip()
        if not payload["payerId"] or payload["amount"] <= 0 or not payload["description"]:
            raise PinchAPIError("Payer, positive amount, and description are required.")
        return self._api_json("POST", "/payments", payload)

    def create_realtime_payment(
        self,
        payer_id,
        amount_cents,
        description,
        credit_card_token,
        nonce="",
    ):
        payload = {
            "payerId": str(payer_id or "").strip(),
            "amount": int(amount_cents),
            "description": str(description or "").strip(),
            "creditCardToken": str(credit_card_token or "").strip(),
        }
        if str(nonce or "").strip():
            payload["nonce"] = str(nonce).strip()
        return self._api_json("POST", "/payments/realtime", payload)

    def create_payment_link(
        self,
        payer_id,
        amount_cents,
        description,
        return_url,
        allowed_payment_methods=None,
        surcharge_payment_methods=None,
        metadata="",
    ):
        """Create a Pinch-hosted sandbox checkout link.

        Card or bank details are entered on Pinch's hosted page and never pass
        through the desktop application.
        """
        allowed = list(allowed_payment_methods or ["credit-card", "bank-account"])
        payload = {
            "amount": int(amount_cents),
            "payerId": str(payer_id or "").strip(),
            "description": str(description or "").strip(),
            "currency": "AUD",
            "allowedPaymentMethods": allowed,
            "surchargePaymentMethods": list(surcharge_payment_methods or []),
            "returnUrl": str(return_url or "").strip(),
            "metadata": str(metadata or "").strip(),
        }
        if not payload["payerId"]:
            raise PinchAPIError("A Pinch Payer ID is required to create a payment link.")
        if payload["amount"] <= 100:
            raise PinchAPIError("Pinch payment-link amount must be greater than AUD 1.00.")
        if not payload["description"]:
            raise PinchAPIError("A payment description is required.")
        if not payload["returnUrl"]:
            raise PinchAPIError("A return URL is required.")
        return self._api_json("POST", "/payment-links", payload)

    def get_payment_link(self, payment_link_id):
        payment_link_id = urllib.parse.quote(str(payment_link_id or "").strip(), safe="")
        return self._api_json("GET", f"/payment-links/{payment_link_id}")

    def get_payment(self, payment_id):
        payment_id = urllib.parse.quote(str(payment_id or "").strip(), safe="")
        return self._api_json("GET", f"/payments/{payment_id}")

    def _api_json(self, method, path, payload=None):
        if not self.access_token:
            self.authenticate()
        body = None
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "pinch-version": PINCH_VERSION,
            "Accept": "application/json",
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{TEST_BASE_URL}{path}", data=body, method=method, headers=headers
        )
        return self._open_json(request)

    def _open_json(self, request):
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(raw)
                detail = detail.get("error_description") or detail.get("message") or detail
            except Exception:
                detail = raw
            raise PinchAPIError(f"Pinch HTTP {exc.code}: {str(detail)[:500]}") from exc
        except urllib.error.URLError as exc:
            raise PinchAPIError(f"Pinch connection failed: {exc.reason}") from exc
        if not raw.strip():
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PinchAPIError("Pinch returned a non-JSON response.") from exc
