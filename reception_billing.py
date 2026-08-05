"""Event-based Pinch billing for the reception-first competition edition.

Raw card or bank details never enter this module. The browser uses Pinch
CaptureJS and sends only a short-lived token. The server retains Pinch IDs and
the client's recorded billing consent.
"""

import math
import os
import time
from typing import Any, Dict

from pinch_payment_backend import PinchAPIError, PinchSandboxClient, load_config


REPORT_FEE_CENTS = int(os.getenv("NIDO_REPORT_FEE_CENTS", "500"))
HOURLY_RATE_CENTS = int(os.getenv("NIDO_HOURLY_RATE_CENTS", "35000"))
BILLING_INCREMENT_MINUTES = max(1, int(os.getenv("NIDO_BILLING_INCREMENT_MINUTES", "6")))
HUMAN_MAX_CENTS = int(os.getenv("NIDO_HUMAN_MAX_CENTS", "200000"))


def public_billing_config() -> Dict[str, Any]:
    config = load_config()
    return {
        "environment": "test",
        "publishable_key": str(config.get("publishable_key") or ""),
        "report_fee_cents": REPORT_FEE_CENTS,
        "hourly_rate_cents": HOURLY_RATE_CENTS,
        "billing_increment_minutes": BILLING_INCREMENT_MINUTES,
        "human_max_cents": HUMAN_MAX_CENTS,
    }


def _client() -> PinchSandboxClient:
    config = load_config()
    return PinchSandboxClient(config.get("application_id"), config.get("secret_key"))


def _billing(record: Dict[str, Any]) -> Dict[str, Any]:
    return record.setdefault("billing", {"environment": "test", "events": []})


def _event(billing: Dict[str, Any], event_type: str, **details) -> Dict[str, Any]:
    item = {"type": event_type, "timestamp": int(time.time()), **details}
    billing.setdefault("events", []).append(item)
    return item


def _extract_id(payload: Dict[str, Any], *names: str) -> str:
    for name in names:
        value = payload.get(name)
        if value:
            return str(value)
    return ""


def authorise_source(
    record: Dict[str, Any],
    payment_token: str,
    consent_report_charge: bool,
    demo_mode: bool,
) -> Dict[str, Any]:
    if not consent_report_charge:
        raise ValueError("Client consent to the disclosed report charge is required.")
    billing = _billing(record)
    if demo_mode and not str(payment_token or "").strip():
        billing.update({
            "payer_id": "pyr_demo_authorised",
            "source_id": "src_demo_authorised",
            "source_mode": "competition-sandbox-simulation",
        })
    else:
        client_data = record.get("client") or {}
        full_name = str(client_data.get("client_name") or "Sandbox Client").strip().split()
        first_name = full_name[0] if full_name else "Sandbox"
        last_name = " ".join(full_name[1:]) or "Client"
        email = str(client_data.get("email") or record.get("client_account") or "sandbox@example.com")
        api = _client()
        payer = api.create_payer(first_name, last_name, email, metadata="AI law firm reception")
        payer_id = _extract_id(payer, "id", "Id")
        source = api.create_payment_source(payer_id, payment_token, "credit-card")
        source_id = _extract_id(source, "id", "Id", "sourceId")
        if not payer_id or not source_id:
            raise PinchAPIError("Pinch did not return the payer and source identifiers.")
        billing.update({"payer_id": payer_id, "source_id": source_id, "source_mode": "pinch-capturejs"})
    billing["report_authorisation"] = {
        "authorised": True,
        "amount_cents": REPORT_FEE_CENTS,
        "authorised_at": int(time.time()),
        "trigger": "successful_18_dimension_report_delivery",
    }
    _event(billing, "report-charge-authorised", amount_cents=REPORT_FEE_CENTS)
    return public_status(record)


def authorise_human_time(record: Dict[str, Any], consent: bool) -> Dict[str, Any]:
    billing = _billing(record)
    if not consent:
        raise ValueError("Client consent to the disclosed hourly terms is required.")
    if not billing.get("source_id"):
        raise ValueError("Authorise a Pinch payment source before requesting human service.")
    billing["human_authorisation"] = {
        "authorised": True,
        "hourly_rate_cents": HOURLY_RATE_CENTS,
        "increment_minutes": BILLING_INCREMENT_MINUTES,
        "maximum_cents": HUMAN_MAX_CENTS,
        "authorised_at": int(time.time()),
        "trigger": "human_session_end",
    }
    _event(
        billing,
        "human-time-authorised",
        hourly_rate_cents=HOURLY_RATE_CENTS,
        increment_minutes=BILLING_INCREMENT_MINUTES,
        maximum_cents=HUMAN_MAX_CENTS,
    )
    return public_status(record)


def _submit(record: Dict[str, Any], purpose: str, amount_cents: int, demo_mode: bool) -> Dict[str, Any]:
    billing = _billing(record)
    existing = billing.get(purpose + "_payment")
    if existing:
        return existing
    nonce = f"alo-{purpose}-{record.get('created_at', 0)}"
    if demo_mode and billing.get("source_mode") == "competition-sandbox-simulation":
        payment = {
            "id": "pmt_demo_" + nonce[-18:],
            "status": "approved",
            "amount_cents": int(amount_cents),
            "sandbox_simulated": True,
            "nonce": nonce,
        }
    else:
        result = _client().create_scheduled_payment(
            billing.get("payer_id"),
            amount_cents,
            "18-dimension report" if purpose == "report" else "Human lawyer consultation",
            source_id=billing.get("source_id"),
            nonce=nonce,
        )
        payment = {
            "id": _extract_id(result, "id", "Id", "paymentId"),
            "status": str(result.get("status") or result.get("Status") or "submitted"),
            "amount_cents": int(amount_cents),
            "sandbox_simulated": False,
            "nonce": nonce,
        }
    billing[purpose + "_payment"] = payment
    _event(billing, purpose + "-charge-submitted", **payment)
    return payment


def settle_report(record: Dict[str, Any], demo_mode: bool) -> Dict[str, Any]:
    auth = _billing(record).get("report_authorisation") or {}
    if not auth.get("authorised"):
        raise ValueError("The report charge has not been authorised.")
    return _submit(record, "report", int(auth["amount_cents"]), demo_mode)


def start_human_timer(record: Dict[str, Any]) -> Dict[str, Any]:
    billing = _billing(record)
    if not (billing.get("human_authorisation") or {}).get("authorised"):
        raise ValueError("The client has not authorised the hourly engagement terms.")
    timer = billing.setdefault("human_timer", {})
    if not timer.get("started_at"):
        timer["started_at"] = int(time.time())
        timer["status"] = "running"
        _event(billing, "human-timer-started", started_at=timer["started_at"])
    return public_status(record)


def finish_human_timer(record: Dict[str, Any], demo_mode: bool) -> Dict[str, Any]:
    billing = _billing(record)
    timer = billing.get("human_timer") or {}
    started = int(timer.get("started_at") or 0)
    if not started:
        raise ValueError("The billable human session has not started.")
    if timer.get("status") == "finished" and billing.get("human_payment"):
        return billing["human_payment"]
    ended = int(time.time())
    elapsed_seconds = max(1, ended - started)
    auth = billing["human_authorisation"]
    increment = int(auth["increment_minutes"])
    billable_minutes = max(increment, int(math.ceil(elapsed_seconds / 60 / increment) * increment))
    raw_amount = int(math.ceil(int(auth["hourly_rate_cents"]) * billable_minutes / 60))
    amount = min(raw_amount, int(auth["maximum_cents"]))
    timer.update({
        "ended_at": ended,
        "status": "finished",
        "elapsed_seconds": elapsed_seconds,
        "billable_minutes": billable_minutes,
        "amount_cents": amount,
    })
    _event(billing, "human-timer-finished", **timer)
    return _submit(record, "human", amount, demo_mode)


def public_status(record: Dict[str, Any]) -> Dict[str, Any]:
    billing = _billing(record)
    return {
        "environment": "Pinch test sandbox",
        "source_authorised": bool(billing.get("source_id")),
        "source_mode": billing.get("source_mode", ""),
        "report_authorisation": billing.get("report_authorisation"),
        "report_payment": billing.get("report_payment"),
        "human_authorisation": billing.get("human_authorisation"),
        "human_timer": billing.get("human_timer"),
        "human_payment": billing.get("human_payment"),
        "events": list(billing.get("events") or []),
    }
