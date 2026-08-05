import base64
import hashlib
import html
import hmac
import io
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi import Cookie, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from reception_billing import (
    authorise_human_time,
    authorise_source,
    finish_human_timer,
    public_billing_config,
    public_status as billing_status,
    settle_report,
    start_human_timer,
)
try:
    from .client_report_pdf import build_client_weakness_pdf, build_independent_review_pdf
except ImportError:
    from client_report_pdf import build_client_weakness_pdf, build_independent_review_pdf
try:
    from .professional_report import (
        build_professional_docx,
        build_professional_pdf,
        normalise_output_requirements,
        normalise_professional_report,
    )
except ImportError:
    from professional_report import (
        build_professional_docx,
        build_professional_pdf,
        normalise_output_requirements,
        normalise_professional_report,
    )

try:
    from google import genai
except Exception:
    genai = None
try:
    from google.cloud import firestore, tasks_v2
    from google.protobuf import duration_pb2
except Exception:
    firestore = None
    tasks_v2 = None
    duration_pb2 = None
try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None
try:
    from docx import Document
except Exception:
    Document = None


router = APIRouter()
_SESSIONS: Dict[str, Dict[str, Any]] = {}
_CLIENT_ACCOUNTS: Dict[str, Dict[str, str]] = {}
_USAGE_ANALYTICS: Dict[str, Any] = {"started_at": int(time.time()), "counts": {}}
_ANALYTICS_EVENT_KEYS = set()
_STATE_LOCK = threading.RLock()
PRIVACY_FIRST_MODE = os.getenv("NIDO_PRIVACY_FIRST_MODE", "true").strip().lower() not in {
    "0", "false", "no", "off",
}
_STATE_PATH = Path(os.getenv(
    "NIDO_RECEPTION_STATE_PATH",
    str(Path(__file__).resolve().parents[1] / "reception_sessions.local.json"),
))
PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
_FIRESTORE = firestore.Client(project=PROJECT) if firestore is not None and PROJECT else None
_SESSION_COLLECTION = os.getenv("NIDO_RECEPTION_SESSION_COLLECTION", "reception_sessions")
_ACCOUNT_COLLECTION = os.getenv("NIDO_RECEPTION_ACCOUNT_COLLECTION", "reception_accounts")
_ANALYTICS_COLLECTION = os.getenv("NIDO_ANALYTICS_COLLECTION", "usage_analytics")
_ANALYTICS_EVENT_COLLECTION = os.getenv("NIDO_ANALYTICS_EVENT_COLLECTION", "usage_analytics_events")
_ANALYTICS_SUMMARY_DOCUMENT = "public_summary"


def _account_doc_id(email: str) -> str:
    return hashlib.sha256(str(email or "").strip().lower().encode("utf-8")).hexdigest()


def _load_persistent_state() -> None:
    if _FIRESTORE is not None:
        try:
            if not PRIVACY_FIRST_MODE:
                for snapshot in _FIRESTORE.collection(_SESSION_COLLECTION).stream():
                    value = snapshot.to_dict() or {}
                    if isinstance(value, dict):
                        _SESSIONS[snapshot.id] = value
            for snapshot in _FIRESTORE.collection(_ACCOUNT_COLLECTION).stream():
                value = snapshot.to_dict() or {}
                email = str(value.get("email") or "").strip().lower()
                if email:
                    _CLIENT_ACCOUNTS[email] = value
            analytics_snapshot = _FIRESTORE.collection(_ANALYTICS_COLLECTION).document(
                _ANALYTICS_SUMMARY_DOCUMENT
            ).get()
            if analytics_snapshot.exists:
                analytics_value = analytics_snapshot.to_dict() or {}
                if isinstance(analytics_value, dict):
                    _USAGE_ANALYTICS.update(analytics_value)
            return
        except Exception:
            pass
    if not _STATE_PATH.exists():
        return
    try:
        payload = json.loads(_STATE_PATH.read_text(encoding="utf-8-sig"))
        sessions = payload.get("sessions") or {}
        accounts = payload.get("client_accounts") or {}
        analytics = payload.get("usage_analytics") or {}
        analytics_event_keys = payload.get("analytics_event_keys") or []
        if not PRIVACY_FIRST_MODE and isinstance(sessions, dict):
            _SESSIONS.update(sessions)
        if isinstance(accounts, dict):
            _CLIENT_ACCOUNTS.update(accounts)
        if isinstance(analytics, dict):
            _USAGE_ANALYTICS.update(analytics)
        if isinstance(analytics_event_keys, list):
            _ANALYTICS_EVENT_KEYS.update(str(item) for item in analytics_event_keys)
    except Exception:
        return


def _persist_state() -> None:
    with _STATE_LOCK:
        if _FIRESTORE is not None:
            if not PRIVACY_FIRST_MODE:
                for intake_id, record in _SESSIONS.items():
                    _FIRESTORE.collection(_SESSION_COLLECTION).document(intake_id).set(record)
            for email, account in _CLIENT_ACCOUNTS.items():
                _FIRESTORE.collection(_ACCOUNT_COLLECTION).document(_account_doc_id(email)).set(account)
            return
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = _STATE_PATH.with_suffix(_STATE_PATH.suffix + ".tmp")
        payload = {
            "saved_at": int(time.time()),
            "sessions": {} if PRIVACY_FIRST_MODE else _SESSIONS,
            "client_accounts": _CLIENT_ACCOUNTS,
            "usage_analytics": _USAGE_ANALYTICS,
            "analytics_event_keys": sorted(_ANALYTICS_EVENT_KEYS),
        }
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(_STATE_PATH)


def _persist_session(intake_id: str, record: Dict[str, Any]) -> None:
    """Keep a matter available to the workflow without persisting it in privacy-first mode."""
    with _STATE_LOCK:
        _SESSIONS[intake_id] = record
        if PRIVACY_FIRST_MODE:
            return
        if _FIRESTORE is not None:
            _FIRESTORE.collection(_SESSION_COLLECTION).document(intake_id).set(record)
            return
        _persist_state()


def _persist_account(email: str, account: Dict[str, Any]) -> None:
    with _STATE_LOCK:
        _CLIENT_ACCOUNTS[email] = account
        if _FIRESTORE is not None:
            _FIRESTORE.collection(_ACCOUNT_COLLECTION).document(_account_doc_id(email)).set(account)
            return
        _persist_state()


_load_persistent_state()
DEMO_MODE = os.getenv("NIDO_RECEPTION_DEMO_MODE", "false").lower() == "true"
PROMOTION_FREE = os.getenv("NIDO_PUBLIC_PROMOTION_FREE", "true").strip().lower() not in {
    "0", "false", "no", "off",
}
DEMO_CLIENT_NAME = os.getenv("NIDO_DEMO_CLIENT_NAME", "Demo Client")
DEMO_CLIENT_EMAIL = os.getenv("NIDO_DEMO_CLIENT_EMAIL", "demo.client@gmail.com").strip().lower()
DEMO_CLIENT_PASSWORD = os.getenv("NIDO_DEMO_CLIENT_PASSWORD", "DemoClient2026!")
LOCATION = os.getenv("NIDO_VERTEX_LOCATION", "australia-southeast1")
MODEL = os.getenv("NIDO_VERTEX_MODEL", "gemini-2.5-flash")
PROVIDER_URL = os.getenv("NIDO_INTAKE_PROVIDER_URL", "").strip()
PROVIDER_KEY = os.getenv("NIDO_INTAKE_PROVIDER_KEY", "").strip()
PROVIDER_MODEL = os.getenv("NIDO_INTAKE_PROVIDER_MODEL", "").strip()
PROVIDER_KIND = os.getenv("NIDO_INTAKE_PROVIDER_KIND", "").strip().lower()
LAW_FIRM_NAME = os.getenv("NIDO_LAW_FIRM_NAME", "Participating Law Firm")
FIREBASE_WEB_API_KEY = os.getenv("NIDO_FIREBASE_WEB_API_KEY", "").strip()
FIREBASE_AUTH_DOMAIN = os.getenv("NIDO_FIREBASE_AUTH_DOMAIN", "").strip()
FIREBASE_APP_ID = os.getenv("NIDO_FIREBASE_APP_ID", "").strip()
CLIENT_AUTH_SECRET = os.getenv("NIDO_SESSION_SECRET", "change-this-session-secret").encode("utf-8")
TASK_QUEUE = os.getenv("NIDO_TASKS_QUEUE", "deep-scan-jobs").strip()
TASK_LOCATION = os.getenv("NIDO_TASKS_LOCATION", LOCATION).strip()
TASK_SERVICE_URL = os.getenv("NIDO_TASK_SERVICE_URL", "").rstrip("/")
TASK_SERVICE_ACCOUNT = os.getenv("NIDO_TASK_SERVICE_ACCOUNT", "").strip()
TASK_SECRET = os.getenv("NIDO_TASK_SECRET", "").strip()
_LAWYER_BRIDGE = None
_LAWYER_BRIDGE_CHECKED = False

REVIEW_DIMENSIONS = [
    "Fact Challenge", "Legal Application", "Precedent Resistance", "Logic Gap",
    "Procedural Defect", "Causation and Damage", "Quantum Dispute", "Burden of Proof",
    "Legal Text Interpretation", "Comparative Fault", "Public Policy", "Reverse Reasoning",
    "Cross-Domain Weapon", "Counterfactual Test", "Proportionality Test",
    "Narrative Deconstruction", "Systemic Risk Amplification", "Silent Evidence",
]


class UsageVisitRequest(BaseModel):
    visitor_id: str = Field(min_length=16, max_length=160)


class UsageFunnelRequest(BaseModel):
    visitor_id: str = Field(min_length=16, max_length=160)
    event: str = Field(min_length=3, max_length=80)
    intake_id: str = Field(default="", max_length=160)
    access_token: str = Field(default="", max_length=240)


def _record_is_demo(record: Optional[Dict[str, Any]]) -> bool:
    if not record:
        return False
    email = str(
        record.get("client_account")
        or (record.get("client") or {}).get("email")
        or ""
    ).strip().lower()
    return bool(email and email == DEMO_CLIENT_EMAIL)


def _usage_event_key(event: str, subject: str) -> str:
    material = f"{event}|{subject}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _track_usage_event(
    event: str,
    subject: str,
    record: Optional[Dict[str, Any]] = None,
) -> bool:
    """Count a deduplicated product event without storing case content or identity."""
    event = re.sub(r"[^a-z0-9_]+", "_", str(event or "").strip().lower()).strip("_")
    subject = str(subject or "").strip()
    if not event or not subject or _record_is_demo(record):
        return False
    key = _usage_event_key(event, subject)
    with _STATE_LOCK:
        if _FIRESTORE is not None:
            event_ref = _FIRESTORE.collection(_ANALYTICS_EVENT_COLLECTION).document(key)
            try:
                event_ref.create({
                    "event": event,
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "anonymous_key": key,
                })
            except Exception:
                return False
            summary_ref = _FIRESTORE.collection(_ANALYTICS_COLLECTION).document(
                _ANALYTICS_SUMMARY_DOCUMENT
            )
            summary_ref.set({
                "started_at": _USAGE_ANALYTICS.get("started_at") or int(time.time()),
                "updated_at": firestore.SERVER_TIMESTAMP,
            }, merge=True)
            summary_ref.update({
                f"counts.{event}": firestore.Increment(1),
                "updated_at": firestore.SERVER_TIMESTAMP,
            })
            counts = _USAGE_ANALYTICS.setdefault("counts", {})
            counts[event] = int(counts.get(event) or 0) + 1
            return True
        if key in _ANALYTICS_EVENT_KEYS:
            return False
        _ANALYTICS_EVENT_KEYS.add(key)
        counts = _USAGE_ANALYTICS.setdefault("counts", {})
        counts[event] = int(counts.get(event) or 0) + 1
        _persist_state()
        return True


def _usage_summary() -> Dict[str, Any]:
    if _FIRESTORE is not None:
        try:
            snapshot = _FIRESTORE.collection(_ANALYTICS_COLLECTION).document(
                _ANALYTICS_SUMMARY_DOCUMENT
            ).get()
            if snapshot.exists:
                value = snapshot.to_dict() or {}
                if isinstance(value, dict):
                    _USAGE_ANALYTICS.update(value)
        except Exception:
            pass
    counts = dict(_USAGE_ANALYTICS.get("counts") or {})
    return {
        "ok": True,
        "tracking_since": _USAGE_ANALYTICS.get("started_at"),
        "unique_visitors": int(counts.get("unique_visitors") or 0),
        "matters_organised": int(counts.get("matters_organised") or 0),
        "deeper_cta_shown": int(counts.get("deeper_cta_shown") or 0),
        "deeper_cta_clicked": int(counts.get("deeper_cta_clicked") or 0),
        "second_stage_auth_started": int(counts.get("second_stage_auth_started") or 0),
        "second_stage_auth_completed": int(counts.get("second_stage_auth_completed") or 0),
        "review_authorisations_completed": int(counts.get("review_authorisations_completed") or 0),
        "advanced_reviews_started": int(counts.get("advanced_reviews_started") or 0),
        "advanced_reviews_completed": int(counts.get("advanced_reviews_completed") or 0),
        "pdf_downloads": int(counts.get("pdf_downloads") or 0),
        "professional_pdf_downloads": int(counts.get("professional_pdf_downloads") or 0),
        "professional_docx_downloads": int(counts.get("professional_docx_downloads") or 0),
        "lawyer_handoffs": int(counts.get("lawyer_handoffs") or 0),
    }


def _shared_lawyer_bridge():
    global _LAWYER_BRIDGE, _LAWYER_BRIDGE_CHECKED
    if _LAWYER_BRIDGE_CHECKED:
        return _LAWYER_BRIDGE
    _LAWYER_BRIDGE_CHECKED = True
    try:
        from lawyer_software_bridge import LawyerSoftwareBridge
        bridge = LawyerSoftwareBridge()
        if bridge.available():
            _LAWYER_BRIDGE = bridge
    except Exception:
        _LAWYER_BRIDGE = None
    return _LAWYER_BRIDGE


class EvidenceFile(BaseModel):
    name: str
    content_type: str = "application/octet-stream"
    content_base64: str


class IntakeRequest(BaseModel):
    client_name: str = ""
    email: str
    jurisdiction: str = ""
    deadline: str = ""
    desired_outcome: str = ""
    case_description: str
    evidence_inventory: str = ""
    consent_external_ai: bool = False
    files: List[EvidenceFile] = Field(default_factory=list)
    output_requirements: Dict[str, Any] = Field(default_factory=dict)


class SessionRequest(BaseModel):
    intake_id: str
    access_token: str


class AIProcessingSessionRequest(SessionRequest):
    consent_external_ai: Optional[bool] = None


class AIConsentRequest(SessionRequest):
    consent_external_ai: bool = False


class HandoffRequest(SessionRequest):
    consent_human_transfer: bool = False
    preferred_contact: str = "email"
    note_for_lawyer: str = ""


class BillingAuthorisationRequest(SessionRequest):
    payment_token: str = ""
    consent_report_charge: bool = False


class HumanBillingAuthorisationRequest(SessionRequest):
    consent_hourly_billing: bool = False


class ClientMessageRequest(SessionRequest):
    message: str


class ChatIntakeRequest(BaseModel):
    intake_id: str = ""
    access_token: str = ""
    message: str = ""
    files: List[EvidenceFile] = Field(default_factory=list)
    force_report: bool = False
    consent_external_ai: Optional[bool] = None
    output_requirements: Dict[str, Any] = Field(default_factory=dict)


class ClientAccountRequest(SessionRequest):
    email: str
    password: str
    name: str = ""


class FormalDecisionRequest(SessionRequest):
    proceed: bool


class AccountAccessRequest(BaseModel):
    email: str = ""
    password: str = ""
    name: str = ""
    intake_id: str = ""
    access_token: str = ""
    firebase_id_token: str = ""


def _clean_json(text: str) -> Dict[str, Any]:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start >= 0 and end > start:
        cleaned = cleaned[start : end + 1]
    try:
        value = json.loads(cleaned)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="The AI returned an unreadable report. Please retry.") from exc
    if not isinstance(value, dict):
        raise HTTPException(status_code=502, detail="The AI report was not an object.")
    return value


def _stamp_model_metadata(
    result: Dict[str, Any],
    provider_display_name: str,
    model_name: str,
    engine_source: str,
) -> Dict[str, Any]:
    value = dict(result or {})
    provider = str(provider_display_name or "Not recorded").strip()
    if "gemini" in provider.lower() or "gemini" in str(model_name or "").lower():
        provider = "Google Gemini"
    value["analysis_metadata"] = {
        "provider_display_name": provider,
        "model_name": str(model_name or "Not recorded").strip(),
        "engine_source": str(engine_source or "Not recorded").strip(),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    value["provider"] = provider
    value["engine_source"] = str(engine_source or "Not recorded").strip()
    return value


def _provider_call(prompt: str, system_instruction: str) -> Dict[str, Any]:
    failed_primary = set()
    try:
        if PROJECT and genai is not None:
            client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config={"system_instruction": system_instruction, "response_mime_type": "application/json"},
            )
            return _stamp_model_metadata(
                _clean_json(str(getattr(response, "text", "") or "")),
                "Google Gemini",
                MODEL,
                "Vertex AI",
            )
        if PROVIDER_KIND == "gemini" and PROVIDER_KEY:
            model = PROVIDER_MODEL or "gemini-2.5-flash"
            base = PROVIDER_URL or "https://generativelanguage.googleapis.com/v1beta"
            url = f"{base.rstrip('/')}/models/{model}:generateContent?key={PROVIDER_KEY}"
            payload = {
                "system_instruction": {"parts": [{"text": system_instruction}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"},
            }
            request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST", headers={"Content-Type": "application/json"})
            raw = _open_json(request)
            text = (((raw.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}])[0].get("text", "")
            return _stamp_model_metadata(_clean_json(text), "Google Gemini", model, "Gemini API")
        if PROVIDER_URL and PROVIDER_KEY:
            url = PROVIDER_URL.rstrip("/")
            if not url.endswith("/chat/completions"):
                url += "/chat/completions"
            payload = {
                "model": PROVIDER_MODEL or "deepseek-chat",
                "messages": [{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}],
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            }
            request = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                method="POST",
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {PROVIDER_KEY}"},
            )
            raw = _open_json(request)
            text = (((raw.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
            return _stamp_model_metadata(
                _clean_json(text),
                PROVIDER_KIND or "Configured provider",
                PROVIDER_MODEL or "deepseek-chat",
                "OpenAI-compatible API",
            )
    except Exception:
        if PROVIDER_KIND:
            failed_primary.add(PROVIDER_KIND)

    bridge = _shared_lawyer_bridge()
    if bridge is not None:
        try:
            result = bridge.call_json(prompt, system_instruction, excluded_providers=failed_primary)
            provider = str(result.get("provider") or result.get("provider_mode") or "Lawyer software provider")
            model = str((result.get("analysis_metadata") or {}).get("model_name") or provider)
            return _stamp_model_metadata(result, provider, model, "Lawyer software bridge")
        except Exception:
            pass
    if "intake interviewer" in system_instruction.lower():
        return _stamp_model_metadata(_local_chat_fallback(), "Local structured preview", "rule-based fallback", "Local")
    if "18-dimension" in system_instruction.lower():
        return _stamp_model_metadata(_local_deep_fallback(), "Local structured preview", "rule-based fallback", "Local")
    return _stamp_model_metadata(_local_intake_fallback(prompt), "Local structured preview", "rule-based fallback", "Local")


def _strict_json_model_call(prompt: str, system_instruction: str) -> Dict[str, Any]:
    """Call a real configured model and never substitute a synthetic legal result."""
    errors: List[str] = []
    if PROJECT and genai is not None:
        try:
            client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config={
                    "system_instruction": system_instruction,
                    "response_mime_type": "application/json",
                    "temperature": 0.2,
                    "max_output_tokens": 8192,
                },
            )
            return _stamp_model_metadata(
                _clean_json(str(getattr(response, "text", "") or "")),
                "Google Gemini",
                MODEL,
                "Vertex AI",
            )
        except Exception as exc:
            errors.append(f"Vertex Gemini: {exc}")
    if PROVIDER_KIND == "gemini" and PROVIDER_KEY:
        try:
            model = PROVIDER_MODEL or "gemini-2.5-flash"
            base = PROVIDER_URL or "https://generativelanguage.googleapis.com/v1beta"
            url = f"{base.rstrip('/')}/models/{model}:generateContent?key={PROVIDER_KEY}"
            body = {
                "system_instruction": {"parts": [{"text": system_instruction}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "temperature": 0.2,
                    "maxOutputTokens": 8192,
                },
            }
            request = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            raw = _open_json(request)
            text = (((raw.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}])[0].get("text", "")
            return _stamp_model_metadata(_clean_json(text), "Google Gemini", model, "Gemini API")
        except Exception as exc:
            errors.append(f"Gemini API: {exc}")
    if PROVIDER_URL and PROVIDER_KEY and PROVIDER_KIND != "gemini":
        try:
            url = PROVIDER_URL.rstrip("/")
            if not url.endswith("/chat/completions"):
                url += "/chat/completions"
            body = {
                "model": PROVIDER_MODEL or "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            }
            request = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                method="POST",
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {PROVIDER_KEY}"},
            )
            raw = _open_json(request)
            text = (((raw.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
            return _stamp_model_metadata(
                _clean_json(text),
                PROVIDER_KIND or "Configured provider",
                PROVIDER_MODEL or "deepseek-chat",
                "OpenAI-compatible API",
            )
        except Exception as exc:
            errors.append(f"Configured provider: {exc}")
    bridge = _shared_lawyer_bridge()
    if bridge is not None:
        try:
            result = bridge.call_json(prompt, system_instruction)
            provider = str(result.get("provider") or result.get("provider_mode") or "Lawyer software provider")
            model = str((result.get("analysis_metadata") or {}).get("model_name") or provider)
            return _stamp_model_metadata(result, provider, model, "Lawyer software bridge")
        except Exception as exc:
            errors.append(f"Lawyer bridge: {exc}")
    detail = "; ".join(errors)[-800:] or "No verified model provider is configured."
    raise HTTPException(status_code=502, detail=f"Independent deep review model call failed. {detail}")


def _independent_review_packet(record: Dict[str, Any]) -> str:
    packet = {
        "client_intake": record.get("client") or {},
        "organised_case_report": record.get("free_report") or {},
        "evidence_text": record.get("evidence_context") or [],
        "rapid_18_angle_review": record.get("deep_report") or {},
    }
    return json.dumps(packet, ensure_ascii=False)[:110000]


def _run_independent_review(intake_id: str, record: Dict[str, Any]) -> Dict[str, Any]:
    """Run 18 isolated whole-case reads, one real model call per dimension."""
    completed = {
        str(item.get("dimension") or "").strip().casefold(): item
        for item in (record.get("independent_review_reports") or [])
        if isinstance(item, dict)
    }
    packet = _independent_review_packet(record)
    reports: List[Dict[str, Any]] = []
    system = (
        "You are one independent whole-case legal weakness reviewer. Read the complete supplied matter yourself. "
        "Diagnose only: identify vulnerabilities, their supplied factual basis, significance and limits. Do not give "
        "legal advice, strategy, attack scripts, questions to ask, remedies, preparation steps or invented authorities. "
        "Return valid JSON only."
    )
    for index, dimension in enumerate(REVIEW_DIMENSIONS, 1):
        existing = completed.get(dimension.casefold())
        if existing:
            reports.append(existing)
            continue
        prompt = f"""INDEPENDENT REVIEW {index} OF {len(REVIEW_DIMENSIONS)}
REVIEW DIMENSION: {dimension}

Read the entire matter packet below independently through this dimension. Produce a complete, self-contained report,
not a template and not a one-line card. If this dimension reveals no material weakness, say so plainly rather than
forcing a finding. Treat the client's position as positive and the other side's position as negative.

MATTER PACKET:
{packet}

Return strict JSON with this shape:
{{
  "dimension": "{dimension}",
  "report_title": "specific plain-language title",
  "full_analysis": "connected self-contained analysis of the whole matter through this dimension, between 500 and 900 words",
  "findings": [{{
    "conclusion": "short specific weakness title",
    "analysis": "vulnerability, supplied factual basis, significance and limits",
    "relevant_facts": "only facts supplied in the matter",
    "affected_side": "positive, negative, or both",
    "confidence": "high, medium, or low"
  }}],
  "limits": ["material limitation of this dimension"]
}}"""
        result = None
        last_error: Optional[Exception] = None
        for attempt in range(2):
            try:
                retry_note = "" if attempt == 0 else (
                    "\nIMPORTANT RETRY: The earlier response was not valid complete JSON. Keep full_analysis under 900 words, "
                    "return no more than 6 findings, close every JSON string and object, and output JSON only."
                )
                result = _strict_json_model_call(prompt + retry_note, system)
                break
            except Exception as exc:
                last_error = exc
        if result is None:
            raise last_error or HTTPException(status_code=502, detail=f"{dimension} review failed.")
        findings = []
        for finding in result.get("findings") or []:
            if not isinstance(finding, dict) or not str(finding.get("conclusion") or "").strip():
                continue
            affected = str(finding.get("affected_side") or "both").strip().lower()
            if affected not in {"positive", "negative", "both"}:
                affected = "both"
            findings.append({
                "conclusion": str(finding.get("conclusion") or "").strip(),
                "analysis": str(finding.get("analysis") or "").strip(),
                "relevant_facts": str(finding.get("relevant_facts") or "").strip(),
                "affected_side": affected,
                "confidence": str(finding.get("confidence") or "medium").strip().lower(),
            })
        item = {
            "dimension": dimension,
            "report_title": str(result.get("report_title") or dimension).strip(),
            "full_analysis": str(result.get("full_analysis") or "No material weakness was identified from the supplied material.").strip()[:16000],
            "findings": findings,
            "limits": [str(value).strip() for value in (result.get("limits") or []) if str(value).strip()][:8],
            "analysis_metadata": result.get("analysis_metadata") or {},
        }
        reports.append(item)
        record["independent_review_reports"] = reports
        record["independent_review_progress"] = round(index * 100 / len(REVIEW_DIMENSIONS))
        _persist_session(intake_id, record)
    positive: List[Dict[str, Any]] = []
    negative: List[Dict[str, Any]] = []
    for report in reports:
        for finding in report.get("findings") or []:
            item = {"dimension": report.get("dimension"), **finding}
            affected = finding.get("affected_side")
            if affected in {"positive", "both"}:
                positive.append(item)
            if affected in {"negative", "both"}:
                negative.append(item)
    model_runs = []
    seen_models = set()
    for item in reports:
        metadata = item.get("analysis_metadata") or {}
        key = (
            str(metadata.get("provider_display_name") or ""),
            str(metadata.get("model_name") or ""),
            str(metadata.get("engine_source") or ""),
        )
        if any(key) and key not in seen_models:
            seen_models.add(key)
            model_runs.append(metadata)
    return {
        "review_mode": "18 independent whole-case reviews",
        "list_price_aud": 88,
        "promotion_price_aud": 0,
        "complete_reports": reports,
        "positive_side_weaknesses": positive,
        "negative_side_weaknesses": negative,
        "provider": MODEL if PROJECT else (PROVIDER_MODEL or PROVIDER_KIND or "verified provider"),
        "analysis_metadata": model_runs[0] if model_runs else {},
        "models_used": model_runs,
        "completed_dimensions": len(reports),
    }


def _open_json(request: urllib.request.Request) -> Dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise HTTPException(status_code=502, detail=f"AI provider error {exc.code}: {detail[:240]}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider unavailable: {str(exc)[:240]}") from exc


def _extract_files(files: List[EvidenceFile]) -> List[Dict[str, Any]]:
    if len(files) > 8:
        raise HTTPException(status_code=413, detail="A maximum of 8 evidence files is allowed for free intake.")
    extracted = []
    total = 0
    for item in files:
        try:
            content = base64.b64decode(item.content_base64, validate=True)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Evidence file is not valid base64: {item.name}") from exc
        total += len(content)
        if len(content) > 8 * 1024 * 1024 or total > 24 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Evidence upload exceeds the free-intake size boundary.")
        suffix = os.path.splitext(item.name)[1].lower()
        text = ""
        try:
            if suffix in {".txt", ".md", ".csv", ".json"}:
                text = content.decode("utf-8", errors="replace")
            elif suffix == ".pdf" and PdfReader is not None:
                reader = PdfReader(io.BytesIO(content))
                text = "\n".join((page.extract_text() or "") for page in reader.pages[:80])
            elif suffix == ".docx" and Document is not None:
                document = Document(io.BytesIO(content))
                text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        except Exception:
            text = ""
        extracted.append({"name": os.path.basename(item.name), "type": item.content_type, "bytes": len(content), "text": text[:24000]})
    return extracted


def _local_intake_fallback(prompt: str) -> Dict[str, Any]:
    return {
        "case_name": "Client matter - local structured preview",
        "jurisdiction": "To be confirmed from the client intake",
        "background": "The intake and evidence index were received locally. Connect Vertex AI or a verified provider for semantic analysis.",
        "pos_args": ["The client's complete position requires semantic analysis and lawyer verification."],
        "pos_ev": ["The client's evidence inventory and selected file names were received."],
        "neg_args": ["No opposing position is inferred in local preview mode."],
        "neg_ev": ["No opposing evidence can be assessed without semantic analysis."],
        "scope_notice": "Local structured preview only; this is not legal advice.",
        "provider_mode": "local-structured-preview",
    }


def _local_deep_fallback() -> Dict[str, Any]:
    return {
        "dimensions": [{"dimension": name, "findings": []} for name in REVIEW_DIMENSIONS],
        "analysis_limits": [
            "The 18-dimension workflow was prepared locally, but semantic weakness findings require Vertex AI or a verified provider."
        ],
        "provider_mode": "local-structured-preview",
    }


def _local_chat_fallback() -> Dict[str, Any]:
    return {
        "ready_for_report": False,
        "assistant_message": "Please describe the help you need, the material you already have, the output you want, and any important deadline. If this concerns a dispute, also include the key people, dates and each side's position where known.",
        "missing_details": ["requested service", "available material", "desired output", "deadline or urgency"],
        "provider_mode": "local-structured-preview",
    }


def _password_record(password: str, salt_hex: str = "") -> Dict[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 180000)
    return {"salt": salt.hex(), "hash": digest.hex()}


def _password_matches(password: str, record: Dict[str, str]) -> bool:
    try:
        candidate = _password_record(password, record["salt"])["hash"]
        return hmac.compare_digest(candidate, record["hash"])
    except Exception:
        return False


def _client_cookie(email: str) -> str:
    expires = int(time.time()) + 30 * 24 * 3600
    value = f"{email.strip().lower()}|{expires}"
    signature = hmac.new(CLIENT_AUTH_SECRET, value.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{value}|{signature}"


def _cookie_email(cookie: str = "") -> str:
    try:
        email, expires_text, signature = str(cookie or "").split("|", 2)
        value = f"{email}|{expires_text}"
        expected = hmac.new(CLIENT_AUTH_SECRET, value.encode("utf-8"), hashlib.sha256).hexdigest()
        if int(expires_text) < int(time.time()) or not hmac.compare_digest(signature, expected):
            return ""
        return email.strip().lower()
    except Exception:
        return ""


def _firebase_identity(id_token: str) -> Dict[str, str]:
    if not FIREBASE_WEB_API_KEY or not str(id_token or "").strip():
        raise HTTPException(status_code=401, detail="Google sign-in is not configured.")
    request = urllib.request.Request(
        f"https://identitytoolkit.googleapis.com/v1/accounts:lookup?key={FIREBASE_WEB_API_KEY}",
        data=json.dumps({"idToken": id_token}).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        payload = _open_json(request)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Google identity could not be verified.") from exc
    user = (payload.get("users") or [{}])[0]
    email = str(user.get("email") or "").strip().lower()
    if not email or not user.get("localId"):
        raise HTTPException(status_code=401, detail="The Google account did not provide a verified email.")
    return {"email": email, "name": str(user.get("displayName") or "").strip(), "uid": str(user.get("localId"))}


def _attach_account(record: Optional[Dict[str, Any]], email: str, name: str = "") -> None:
    if record is None:
        return
    record["client_authenticated"] = True
    record["client_account"] = email
    record.setdefault("client", {}).update({"email": email, "client_name": name or (record.get("client") or {}).get("client_name", "")})


def _account_matters(email: str) -> List[Dict[str, Any]]:
    rows = []
    source: List[Any]
    if _FIRESTORE is not None and not PRIVACY_FIRST_MODE:
        try:
            source = []
            for snapshot in _FIRESTORE.collection(_SESSION_COLLECTION).stream():
                record = snapshot.to_dict() or {}
                _SESSIONS[snapshot.id] = record
                source.append((snapshot.id, record))
        except Exception:
            source = list(_SESSIONS.items())
    else:
        source = list(_SESSIONS.items())
    for intake_id, record in source:
        if str(record.get("client_account") or "").strip().lower() != email:
            continue
        free_report = record.get("free_report") or {}
        handoff = record.get("handoff") or {}
        if handoff.get("formal_service_requested") is True:
            workflow_stage = "formal_service_requested"
        elif handoff.get("final_lawyer_report"):
            workflow_stage = "lawyer_report_delivered"
        elif handoff.get("status") == "accepted_by_law_firm":
            workflow_stage = "human_consultation_running"
        elif handoff:
            workflow_stage = "awaiting_law_firm_acceptance"
        elif record.get("deep_report"):
            workflow_stage = "weakness_report_ready"
        elif record.get("deep_scan_status") in {"queued", "running"}:
            workflow_stage = "weakness_review_running"
        elif free_report:
            workflow_stage = "initial_report_ready"
        else:
            workflow_stage = "case_intake"
        handoff_public = None
        if handoff:
            handoff_public = {
                "handoff_id": handoff.get("handoff_id"),
                "status": handoff.get("status"),
                "created_at": handoff.get("created_at"),
                "accepted_at": handoff.get("accepted_at"),
                "accepted_by": handoff.get("accepted_by"),
                "billing_boundary": handoff.get("billing_boundary"),
                "messages": handoff.get("messages") or [],
                "final_lawyer_report": handoff.get("final_lawyer_report"),
                "formal_service_requested": handoff.get("formal_service_requested"),
            }
        rows.append({
            "intake_id": intake_id,
            "access_token": record.get("access_token", ""),
            "case_name": free_report.get("case_name") or "Client matter",
            "created_at": int(record.get("created_at") or 0),
            "scan_status": record.get("deep_scan_status") or ("complete" if record.get("deep_report") else "not_started"),
            "workflow_stage": workflow_stage,
            "free_report": free_report,
            "deep_report": record.get("deep_report"),
            "handoff": handoff_public,
            "billing": billing_status(record),
        })
    return sorted(rows, key=lambda item: item["created_at"], reverse=True)


def _ensure_demo_client_account() -> None:
    """Keep a predictable local competition account available after restart."""
    if not DEMO_MODE or not DEMO_CLIENT_EMAIL:
        return
    if DEMO_CLIENT_EMAIL not in _CLIENT_ACCOUNTS:
        _CLIENT_ACCOUNTS[DEMO_CLIENT_EMAIL] = {
            "email": DEMO_CLIENT_EMAIL,
            "name": DEMO_CLIENT_NAME,
            "demo_account": True,
            **_password_record(DEMO_CLIENT_PASSWORD),
        }


def _case_report_for_record(record: Dict[str, Any]) -> Dict[str, Any]:
    bridge = _shared_lawyer_bridge()
    if bridge is not None:
        report = bridge.organise_case(record)
        provider = str(report.get("provider") or report.get("provider_mode") or "Lawyer software provider")
        model = str((report.get("analysis_metadata") or {}).get("model_name") or provider)
        report = _stamp_model_metadata(report, provider, model, "Lawyer software bridge")
        return normalise_professional_report(report, record.get("output_requirements"))
    client = record.get("client") or {}
    output_requirements = normalise_output_requirements(record.get("output_requirements"))
    prompt = f"""Organise the complete supplied request and any case material as a professional, source-aware lawyer review pack. Return strict JSON only:
{{
  "request_type": "legal matter, document service, evidence organisation, intake, compliance support, or other",
  "case_name": "short matter or service-request name",
  "jurisdiction": "court or jurisdiction, or not applicable for a technical support request",
  "executive_summary": "concise neutral summary for a reviewing professional",
  "background": "complete neutral background of the matter or requested service",
  "involved_people": [{{"name":"person or organisation","role":"neutral role","position":"stated position if supplied"}}],
  "key_dates": [{{"date":"supplied date or date to be confirmed","event":"event","source":"source file or client statement"}}],
  "chronology": [{{"date":"date or sequence marker","event":"neutral event","source":"source location","status":"confirmed, alleged, disputed, or missing"}}],
  "pos_args": ["client-side position, or requested deliverables for a support service"],
  "pos_ev": ["client evidence, or source material supplied for a support service"],
  "neg_args": ["other-side position, or constraints and unresolved requirements for a support service"],
  "neg_ev": ["other-side evidence, or missing source material relevant to a support service"],
  "issues_for_review": ["issue requiring qualified lawyer or professional review, without deciding it"],
  "evidence_index": [{{"item":"E-01","document":"document or evidence","date":"date if supplied","source":"file/page or client statement","relevance":"fact it may support","status":"available, missing, disputed, or unverified"}}],
  "missing_information": ["specific missing fact, document, date, formatting rule, or instruction"],
  "requested_deliverables": ["requested output or service result"],
  "lawyer_review_tasks": ["specific verification or decision reserved for the reviewing lawyer"],
  "scope_and_limits": ["material limit arising from the supplied record"],
  "scope_notice": "information organisation or technical support only; lawyer verification required where legal judgment is involved"
}}
First identify whether the person is describing a legal matter or requesting a technical/administrative service such
as document organisation, formatting, chronology creation or evidence indexing. Do not force a support request into
a dispute structure, and do not ask for an opposing party when none is relevant. This is classification and
organisation only. Do not scan weaknesses, evaluate merits, conduct opposition, recommend strategy, predict outcomes,
 or give legal advice. Distinguish facts, allegations, documents, requested deliverables, constraints and inference.
Use only supplied facts. Do not invent dates, people, evidence, authorities, filing rules or source locations. If a source
page is unavailable, say that it must be confirmed. Preserve compatibility fields pos_args, pos_ev, neg_args and neg_ev.

SELECTED OUTPUT REQUIREMENTS:
{json.dumps(output_requirements, ensure_ascii=False)}

CLIENT CONVERSATION:
{json.dumps(record.get('intake_messages') or [], ensure_ascii=False)}

EVIDENCE EXTRACTS:
{json.dumps(record.get('evidence_context') or [], ensure_ascii=False)[:60000]}

CLIENT DETAILS:
{json.dumps(client, ensure_ascii=False)}"""
    report = _provider_call(prompt, "You are a law-firm request and case-material classification engine. Produce a source-aware professional review pack, route technical or administrative support requests without inventing a dispute, and reserve legal judgment for a qualified lawyer. For legal matters, organise the complete background, parties, chronology, both sides' positions, evidence index, missing material and review tasks. No weakness analysis, opposition or legal advice. Return valid JSON only.")
    return normalise_professional_report(report, output_requirements)


def _session(payload: SessionRequest) -> Dict[str, Any]:
    record = _SESSIONS.get(payload.intake_id)
    if _FIRESTORE is not None and not PRIVACY_FIRST_MODE:
        try:
            snapshot = _FIRESTORE.collection(_SESSION_COLLECTION).document(payload.intake_id).get()
            if snapshot.exists:
                record = snapshot.to_dict() or {}
                _SESSIONS[payload.intake_id] = record
        except Exception:
            pass
    if not record or not secrets.compare_digest(str(record.get("access_token", "")), payload.access_token):
        raise HTTPException(status_code=404, detail="Intake session was not found.")
    return record


def handoff_queue_records() -> List[Dict[str, Any]]:
    rows = []
    for intake_id, record in _SESSIONS.items():
        handoff = record.get("handoff")
        if handoff:
            rows.append({"intake_id": intake_id, **handoff})
    return sorted(rows, key=lambda item: int(item.get("created_at", 0)), reverse=True)


def accept_handoff_record(handoff_id: str, lawyer_username: str) -> Dict[str, Any]:
    for intake_id, record in _SESSIONS.items():
        handoff = record.get("handoff")
        if handoff and secrets.compare_digest(str(handoff.get("handoff_id", "")), str(handoff_id or "")):
            start_human_timer(record)
            handoff["status"] = "accepted_by_law_firm"
            handoff["accepted_by"] = lawyer_username
            handoff["accepted_at"] = int(time.time())
            handoff["billing_boundary"] = "Human lawyer review may now begin under the firm's confirmed hourly engagement terms."
            _persist_session(intake_id, record)
            return handoff
    raise KeyError(handoff_id)


def handoff_by_id(handoff_id: str) -> Dict[str, Any]:
    for record in _SESSIONS.values():
        handoff = record.get("handoff")
        if handoff and secrets.compare_digest(str(handoff.get("handoff_id", "")), str(handoff_id or "")):
            return handoff
    raise KeyError(handoff_id)


def add_lawyer_message(handoff_id: str, lawyer_username: str, message: str) -> Dict[str, Any]:
    handoff = handoff_by_id(handoff_id)
    intake_id, owner_record = next(
        (intake_id, record) for intake_id, record in _SESSIONS.items() if record.get("handoff") is handoff
    )
    text = str(message or "").strip()
    if not text:
        raise ValueError("Message is empty.")
    item = {"role": "lawyer", "sender": lawyer_username, "message": text[:4000], "timestamp": int(time.time())}
    handoff.setdefault("messages", []).append(item)
    _persist_session(intake_id, owner_record)
    return item


def set_final_lawyer_report(handoff_id: str, lawyer_username: str, report_text: str) -> Dict[str, Any]:
    handoff = handoff_by_id(handoff_id)
    intake_id, owner_record = next(
        (intake_id, record) for intake_id, record in _SESSIONS.items() if record.get("handoff") is handoff
    )
    text = str(report_text or "").strip()
    if len(text) < 40:
        raise ValueError("The final report must contain at least 40 characters.")
    report = {"author": lawyer_username, "delivered_at": int(time.time()), "text": text[:50000]}
    handoff["final_lawyer_report"] = report
    handoff["status"] = "final_report_delivered"
    try:
        report["billing"] = finish_human_timer(owner_record, DEMO_MODE)
    except Exception as exc:
        owner_record.setdefault("billing", {})["human_billing_error"] = str(exc)[:500]
        report["billing"] = {"status": "needs_attention", "error": str(exc)[:240]}
    _persist_session(intake_id, owner_record)
    return report


@router.get("/client", response_class=HTMLResponse)
def client_portal() -> HTMLResponse:
    page_path = Path(__file__).with_name("client_reception_page.html")
    page = page_path.read_text(encoding="utf-8") if page_path.exists() else CLIENT_HTML
    page = page.replace("__DEMO_MODE__", "true" if DEMO_MODE else "false")
    page = page.replace("__LAW_FIRM_NAME__", html.escape(LAW_FIRM_NAME))
    billing = public_billing_config()
    page = page.replace("__PINCH_PUBLISHABLE_KEY__", json.dumps(billing["publishable_key"])[1:-1])
    page = page.replace("__REPORT_FEE_CENTS__", str(billing["report_fee_cents"]))
    page = page.replace("__HOURLY_RATE_CENTS__", str(billing["hourly_rate_cents"]))
    page = page.replace("__BILLING_INCREMENT_MINUTES__", str(billing["billing_increment_minutes"]))
    page = page.replace("__HUMAN_MAX_CENTS__", str(billing["human_max_cents"]))
    page = page.replace("__DEMO_CLIENT_NAME__", json.dumps(DEMO_CLIENT_NAME)[1:-1] if DEMO_MODE else "")
    page = page.replace("__DEMO_CLIENT_EMAIL__", json.dumps(DEMO_CLIENT_EMAIL)[1:-1] if DEMO_MODE else "")
    page = page.replace("__DEMO_CLIENT_PASSWORD__", json.dumps(DEMO_CLIENT_PASSWORD)[1:-1] if DEMO_MODE else "")
    page = page.replace("__FIREBASE_API_KEY__", json.dumps(FIREBASE_WEB_API_KEY)[1:-1])
    page = page.replace("__FIREBASE_AUTH_DOMAIN__", json.dumps(FIREBASE_AUTH_DOMAIN)[1:-1])
    page = page.replace("__FIREBASE_PROJECT_ID__", json.dumps(PROJECT)[1:-1])
    page = page.replace("__FIREBASE_APP_ID__", json.dumps(FIREBASE_APP_ID)[1:-1])
    page = page.replace("__PRIVACY_FIRST_MODE__", "true" if PRIVACY_FIRST_MODE else "false")
    page = page.replace("__ACCOUNT_BUTTON_LABEL__", "Sign in" if PRIVACY_FIRST_MODE else "Sign in / saved matters")
    return HTMLResponse(page, headers={
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    })


@router.post("/client/api/ai-consent")
def update_ai_consent(payload: AIConsentRequest) -> Dict[str, Any]:
    record = _session(payload)
    consent = bool(payload.consent_external_ai)
    record["consent_external_ai"] = consent
    record.setdefault("consent_events", []).append({
        "status": "authorised" if consent else "withdrawn",
        "timestamp": int(time.time()),
    })
    _persist_state()
    return {"ok": True, "consent_external_ai": consent, "ai_processing_allowed": consent}


@router.post("/client/api/usage/visit")
def record_usage_visit(payload: UsageVisitRequest) -> Dict[str, Any]:
    _track_usage_event("unique_visitors", payload.visitor_id)
    return _usage_summary()


@router.get("/client/api/usage")
def public_usage_summary() -> Dict[str, Any]:
    return _usage_summary()


@router.post("/client/api/usage/funnel")
def record_usage_funnel(payload: UsageFunnelRequest) -> Dict[str, Any]:
    allowed = {
        "deeper_cta_shown",
        "deeper_cta_clicked",
        "second_stage_auth_started",
        "second_stage_auth_completed",
        "review_authorisations_completed",
        "advanced_reviews_started",
    }
    event = re.sub(r"[^a-z0-9_]+", "_", payload.event.strip().lower()).strip("_")
    if event not in allowed:
        raise HTTPException(status_code=400, detail="Unknown anonymous funnel event.")
    subject = payload.intake_id.strip() or payload.visitor_id.strip()
    record: Optional[Dict[str, Any]] = None
    if payload.intake_id.strip() and payload.access_token.strip():
        try:
            record = _session(SessionRequest(
                intake_id=payload.intake_id.strip(),
                access_token=payload.access_token.strip(),
            ))
        except HTTPException:
            record = None
    _track_usage_event(event, subject, record)
    return {"ok": True}


@router.post("/client/api/intake-chat")
def intake_chat(payload: ChatIntakeRequest) -> Dict[str, Any]:
    if payload.consent_external_ai is None:
        raise HTTPException(status_code=409, detail="This reception page is out of date. Refresh the page before continuing.")
    incoming_output_requirements = normalise_output_requirements(payload.output_requirements)
    if payload.intake_id:
        record = _session(SessionRequest(intake_id=payload.intake_id, access_token=payload.access_token))
        intake_id, token = payload.intake_id, payload.access_token
        if payload.output_requirements:
            record["output_requirements"] = incoming_output_requirements
    else:
        if not payload.consent_external_ai:
            raise HTTPException(status_code=400, detail="Online AI processing authorisation is required before continuing.")
        intake_id, token = "int_" + secrets.token_urlsafe(9), secrets.token_urlsafe(24)
        record = {
            "access_token": token,
            "created_at": int(time.time()),
            "client": {},
            "intake_messages": [],
            "messages": [],
            "evidence_files": [],
            "evidence_context": [],
            "deep_scan_paid": False,
            "client_authenticated": False,
            "consent_external_ai": True,
            "consent_events": [{"status": "authorised", "timestamp": int(time.time())}],
            "output_requirements": incoming_output_requirements,
        }
        _SESSIONS[intake_id] = record
        _track_usage_event("intakes_started", intake_id, record)
    if not payload.consent_external_ai:
        if record.get("consent_external_ai") is not False:
            record["consent_external_ai"] = False
            record.setdefault("consent_events", []).append({"status": "withdrawn", "timestamp": int(time.time())})
            _persist_state()
        raise HTTPException(status_code=400, detail="Online AI processing authorisation is required before continuing.")
    if record.get("consent_external_ai") is not True:
        record["consent_external_ai"] = True
        record.setdefault("consent_events", []).append({"status": "authorised", "timestamp": int(time.time())})
    message = payload.message.strip()
    if not message and not payload.files and not payload.force_report:
        raise HTTPException(status_code=400, detail="Describe what you need help with or attach material before continuing.")
    if message:
        record.setdefault("intake_messages", []).append({"role": "client", "message": message[:12000]})
    evidence = _extract_files(payload.files)
    if evidence:
        record.setdefault("evidence_files", []).extend({k: v for k, v in item.items() if k != "text"} for item in evidence)
        record.setdefault("evidence_context", []).extend({"name": item["name"], "text": item["text"]} for item in evidence if item.get("text"))
        record.setdefault("intake_messages", []).append({"role": "client", "message": "Attached material: " + ", ".join(item["name"] for item in evidence)})
    if payload.force_report:
        report = _case_report_for_record(record)
        record["free_report"] = report
        _persist_state()
        _track_usage_event("matters_organised", intake_id, record)
        return {"ok": True, "intake_id": intake_id, "access_token": token, "status": "report_ready", "assistant_message": "I have organised the supplied information into the first request report. You may add anything that was missed or, for a legal matter, continue to deeper analysis.", "report": report}
    interview_prompt = f"""Act as a careful AI law-firm reception and intake interviewer. First determine whether the person is:
A. describing a new or existing legal matter; or
B. requesting a technical or administrative service, including document organisation, formatting, chronology creation, evidence indexing or related case support.

For a legal matter, gather the material facts, relevant people or organisations, important dates, the known positions of each side, desired outcome and available evidence. For a technical or administrative service, gather the requested task, source documents or file types, desired output, volume, deadline, confidentiality constraints and any formatting or indexing rules. Do not assume there is a dispute or opposing party when none is relevant.

The selected delivery requirements are below. Ask only for missing requirements that materially affect the requested output. Do not claim that a selected template complies with a court or regulator unless the user supplied a current official template or verified rules.
{json.dumps(record.get('output_requirements') or {}, ensure_ascii=False)}

Read the conversation and evidence list, then decide whether there is enough information to organise a useful first request report. Ask only the next 1 to 4 focused questions that materially improve the record, numbered 1 to 4. Ask for missing documents when relevant. Do not add a navigation or completion instruction because the interface adds a fixed fifth option. Do not analyse weaknesses, conduct opposition, assess merits, recommend strategy, predict outcomes, or give legal advice.
Return strict JSON only:
{{"ready_for_report":true_or_false,"assistant_message":"brief natural conversational response or focused questions","missing_details":["material still missing"]}}

CONVERSATION:
{json.dumps(record.get('intake_messages') or [], ensure_ascii=False)}
EVIDENCE FILES:
{json.dumps(record.get('evidence_files') or [], ensure_ascii=False)}"""
    interview = _provider_call(interview_prompt, "You are a law-firm reception interviewer. Route legal matters and technical or administrative support requests, then gather only the facts, documents and delivery requirements relevant to that request. Do not invent a dispute, analyse legal weaknesses, conduct opposition or give legal advice. Return valid JSON only.")
    assistant_message = str(interview.get("assistant_message") or "Please add the help you need, the material you have, the output you want, and any important deadline.")
    if not bool(interview.get("ready_for_report")):
        message_parts = assistant_message.strip().split("\n\n", 1)
        introduction = message_parts[0].rstrip().rstrip(":.;")
        introduction += (
            ", but if you have no further information to add, select the blue "
            "Submit Complete Report button below."
        )
        remaining_questions = "\n\n" + message_parts[1] if len(message_parts) > 1 else ""
        assistant_message = introduction + remaining_questions + (
            "\n\n5. If you have no further information or documents to add, "
            "select the complete-material report option below."
        )
    record.setdefault("intake_messages", []).append({"role": "assistant", "message": assistant_message})
    if bool(interview.get("ready_for_report")):
        report = _case_report_for_record(record)
        record["free_report"] = report
        _persist_state()
        _track_usage_event("matters_organised", intake_id, record)
        return {"ok": True, "intake_id": intake_id, "access_token": token, "status": "report_ready", "assistant_message": assistant_message, "missing_details": interview.get("missing_details") or [], "report": report}
    _persist_state()
    return {"ok": True, "intake_id": intake_id, "access_token": token, "status": "collecting", "assistant_message": assistant_message, "missing_details": interview.get("missing_details") or []}


@router.post("/client/api/register")
def client_register(payload: ClientAccountRequest) -> JSONResponse:
    record = _session(payload)
    _ensure_demo_client_account()
    email = payload.email.strip().lower()
    if "@" not in email or len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Use a valid email and a password of at least 8 characters.")
    if email in _CLIENT_ACCOUNTS:
        raise HTTPException(status_code=409, detail="This account already exists. Please log in.")
    account = {"email": email, "name": payload.name.strip()[:120], **_password_record(payload.password)}
    _persist_account(email, account)
    record["client_authenticated"] = True
    record["client_account"] = email
    record.setdefault("client", {}).update({"email": email, "client_name": payload.name.strip()[:120]})
    _persist_session(payload.intake_id, record)
    _track_usage_event("registered_accounts", _account_doc_id(email), record)
    return _account_login_response(email, payload.name.strip()[:120])


@router.post("/client/api/login")
def client_login(payload: ClientAccountRequest) -> JSONResponse:
    record = _session(payload)
    _ensure_demo_client_account()
    email = payload.email.strip().lower()
    account = _CLIENT_ACCOUNTS.get(email)
    if not account or not _password_matches(payload.password, account):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    record["client_authenticated"] = True
    record["client_account"] = email
    record.setdefault("client", {}).update({"email": email, "client_name": account.get("name") or payload.name.strip()[:120]})
    _persist_session(payload.intake_id, record)
    return _account_login_response(email, str(account.get("name") or ""))


def _account_login_response(email: str, name: str = "") -> JSONResponse:
    payload = {"ok": True, "authenticated": True, "email": email, "name": name, "matters": _account_matters(email)}
    response = JSONResponse(payload)
    response.set_cookie(
        "nido_client_auth",
        _client_cookie(email),
        max_age=30 * 24 * 3600,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return response


@router.post("/client/api/account/login")
def account_login(payload: AccountAccessRequest) -> JSONResponse:
    _ensure_demo_client_account()
    email = payload.email.strip().lower()
    account = _CLIENT_ACCOUNTS.get(email)
    if account is None and _FIRESTORE is not None:
        try:
            snapshot = _FIRESTORE.collection(_ACCOUNT_COLLECTION).document(_account_doc_id(email)).get()
            if snapshot.exists:
                account = snapshot.to_dict() or {}
                _CLIENT_ACCOUNTS[email] = account
        except Exception:
            pass
    if not account or not _password_matches(payload.password, account):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    record = None
    if payload.intake_id and payload.access_token:
        record = _session(SessionRequest(intake_id=payload.intake_id, access_token=payload.access_token))
        _attach_account(record, email, str(account.get("name") or payload.name))
        _persist_session(payload.intake_id, record)
    return _account_login_response(email, str(account.get("name") or ""))


@router.post("/client/api/account/google-login")
def google_account_login(payload: AccountAccessRequest) -> JSONResponse:
    identity = _firebase_identity(payload.firebase_id_token)
    email, name = identity["email"], identity["name"]
    account_was_new = email not in _CLIENT_ACCOUNTS
    account = _CLIENT_ACCOUNTS.get(email) or {
        "email": email,
        "name": name,
        "google_uid": identity["uid"],
        "providers": ["google.com"],
        "created_at": int(time.time()),
    }
    account.update({"name": name or account.get("name", ""), "google_uid": identity["uid"]})
    providers = set(account.get("providers") or [])
    providers.add("google.com")
    account["providers"] = sorted(providers)
    _persist_account(email, account)
    record = None
    if payload.intake_id and payload.access_token:
        record = _session(SessionRequest(intake_id=payload.intake_id, access_token=payload.access_token))
        _attach_account(record, email, name)
        _persist_session(payload.intake_id, record)
    if account_was_new and email != DEMO_CLIENT_EMAIL:
        _track_usage_event("registered_accounts", _account_doc_id(email), record)
    return _account_login_response(email, name)


@router.get("/client/api/account/matters")
def account_matters(nido_client_auth: str = Cookie(default="")) -> Dict[str, Any]:
    email = _cookie_email(nido_client_auth)
    if not email:
        raise HTTPException(status_code=401, detail="Please sign in to restore saved matters.")
    return {"ok": True, "email": email, "matters": _account_matters(email)}


@router.post("/client/api/account/attach-session")
def attach_signed_in_account(
    payload: SessionRequest,
    nido_client_auth: str = Cookie(default=""),
) -> Dict[str, Any]:
    """Attach the active intake to an account that already has a valid login cookie."""
    email = _cookie_email(nido_client_auth)
    if not email:
        raise HTTPException(status_code=401, detail="Please sign in to continue.")
    record = _session(payload)
    account = _CLIENT_ACCOUNTS.get(email) or {}
    _attach_account(record, email, str(account.get("name") or ""))
    _persist_session(payload.intake_id, record)
    return {"ok": True, "authenticated": True, "email": email}


@router.post("/client/api/account/logout")
def account_logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie("nido_client_auth")
    return response


@router.post("/client/api/free-analysis")
def free_analysis(payload: IntakeRequest) -> Dict[str, Any]:
    if "@" not in payload.email or len(payload.case_description.strip()) < 80:
        raise HTTPException(status_code=400, detail="Enter a valid email and a case description of at least 80 characters.")
    if not payload.consent_external_ai:
        raise HTTPException(status_code=400, detail="Consent is required before the online AI analyses matter material.")
    evidence = _extract_files(payload.files)
    evidence_text = "\n\n".join(f"FILE: {item['name']}\n{item['text']}" for item in evidence if item["text"])
    prompt = f"""You are the hidden main-case analysis engine used by a law-firm AI reception system.
Read the client's complete available matter and return strict JSON only with this exact shape:
{{
  "case_name": "short case name",
  "jurisdiction": "court or jurisdiction",
  "background": "neutral factual background",
  "pos_args": ["client/claimant/applicant core position"],
  "pos_ev": ["evidence supporting the client position"],
  "neg_args": ["other side's stated or reasonably possible position, clearly labelled if only inferred"],
  "neg_ev": ["evidence supporting or potentially supporting the other side"],
  "scope_notice": "case-material organisation only; lawyer verification required"
}}
This stage is classification and organisation only. Reconstruct the complete case material, then place each argument
and item of evidence under the appropriate side. Do not scan for weaknesses, evaluate legal strength, recommend a
strategy, conduct an attack-and-defence round, predict an outcome, or give legal advice. Do not invent facts, laws,
cases, deadlines, evidence, or an absent party's actual defence. Distinguish supplied facts, allegations, documents,
and inference. If the other side's position is not supplied, label any possible position as inference rather than fact.

Jurisdiction: {payload.jurisdiction}
Deadline stated by client: {payload.deadline}
Desired outcome: {payload.desired_outcome}
Client narrative: {payload.case_description}
Evidence inventory: {payload.evidence_inventory}
Extracted evidence text: {evidence_text[:60000]}"""
    report = _provider_call(prompt, "You are the existing case-material classification engine operating behind an AI law-firm receptionist. Organise the complete matter into background, positive-side arguments and evidence, and negative-side arguments and evidence. Do not perform opposition, weakness analysis, merits evaluation, strategy, or outcome prediction. Return valid JSON only.")
    intake_id = "int_" + secrets.token_urlsafe(9)
    token = secrets.token_urlsafe(24)
    _SESSIONS[intake_id] = {
        "access_token": token,
        "created_at": int(time.time()),
        "client": payload.model_dump(exclude={"files"}),
        "evidence_files": [{k: v for k, v in item.items() if k != "text"} for item in evidence],
        "evidence_context": [{"name": item["name"], "text": item["text"]} for item in evidence if item.get("text")],
        "free_report": report,
        "deep_scan_paid": False,
        "messages": [],
    }
    _persist_state()
    record = _SESSIONS[intake_id]
    _track_usage_event("intakes_started", intake_id, record)
    _track_usage_event("matters_organised", intake_id, record)
    return {"ok": True, "intake_id": intake_id, "access_token": token, "report": report, "provider_mode": report.get("provider_mode", "online-ai")}


@router.post("/client/api/demo-confirm-scan-payment")
def demo_confirm_scan_payment(payload: SessionRequest) -> Dict[str, Any]:
    if not DEMO_MODE:
        raise HTTPException(status_code=403, detail="The demo payment control is disabled.")
    record = _session(payload)
    status = authorise_source(record, "", True, True)
    record["deep_scan_paid"] = True
    _persist_state()
    return {"ok": True, "status": "authorised", "billing": status, "next": "detailed-weakness-scan"}


@router.post("/client/api/promotion/activate-rapid-review")
def activate_free_promotion_review(payload: SessionRequest) -> Dict[str, Any]:
    if not PROMOTION_FREE:
        raise HTTPException(status_code=403, detail="The public free-review promotion is not active.")
    record = _session(payload)
    if not record.get("client_authenticated"):
        raise HTTPException(status_code=401, detail="Register or log in before starting the review.")
    record["deep_scan_paid"] = True
    record.setdefault("billing", {})["report_payment"] = {
        "status": "promotion_free",
        "amount_cents": 0,
        "normal_price_cents": 500,
        "created_at": int(time.time()),
    }
    _persist_session(payload.intake_id, record)
    return {"ok": True, "status": "promotion_free", "normal_price_cents": 500, "amount_cents": 0}


@router.post("/client/api/billing/authorise-report")
def authorise_report_billing(payload: BillingAuthorisationRequest) -> Dict[str, Any]:
    record = _session(payload)
    if not record.get("client_authenticated"):
        raise HTTPException(status_code=401, detail="Register or log in before authorising payment.")
    try:
        status = authorise_source(
            record,
            payload.payment_token,
            payload.consent_report_charge,
            DEMO_MODE,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record["deep_scan_paid"] = True
    _persist_session(payload.intake_id, record)
    _track_usage_event("report_authorisations", payload.intake_id, record)
    return {"ok": True, "status": "authorised", "billing": status}


@router.post("/client/api/billing/authorise-human")
def authorise_human_billing(payload: HumanBillingAuthorisationRequest) -> Dict[str, Any]:
    record = _session(payload)
    try:
        status = authorise_human_time(record, payload.consent_hourly_billing)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _persist_session(payload.intake_id, record)
    return {"ok": True, "status": "authorised", "billing": status}


@router.post("/client/api/billing/status")
def client_billing_status(payload: SessionRequest) -> Dict[str, Any]:
    return {"ok": True, "billing": billing_status(_session(payload))}


@router.post("/client/api/deep-scan")
def deep_scan(payload: AIProcessingSessionRequest) -> Dict[str, Any]:
    record = _session(payload)
    if payload.consent_external_ai is None:
        raise HTTPException(status_code=409, detail="This reception page is out of date. Refresh the page before continuing.")
    if not payload.consent_external_ai:
        if record.get("consent_external_ai") is not False:
            record["consent_external_ai"] = False
            record.setdefault("consent_events", []).append({"status": "withdrawn", "timestamp": int(time.time())})
            _persist_state()
        raise HTTPException(status_code=400, detail="Online AI processing authorisation is required before starting the 18-dimension review.")
    if record.get("consent_external_ai") is not True:
        record["consent_external_ai"] = True
        record.setdefault("consent_events", []).append({"status": "authorised", "timestamp": int(time.time())})
        _persist_state()
    if not record.get("client_authenticated"):
        raise HTTPException(status_code=401, detail="Register or log in before starting the 18-dimension review.")
    if not record.get("free_report"):
        raise HTTPException(status_code=409, detail="Complete the case-material organisation report first.")
    if not record.get("deep_scan_paid"):
        raise HTTPException(status_code=402, detail="This firm's configured authorisation step must be completed before the 18-dimension review.")
    prompt = f"""Read the complete prepared matter and the first main-case report directly before analysing it.
Act as one independent legal weakness reviewer for each of the 18 listed dimensions. For every dimension, identify zero
or more genuinely material weaknesses across the whole matter. Return no finding when a dimension reveals no useful
weakness. Do not force equal counts. Diagnose only. Do not provide lawyer questions, attack scripts, strategy,
recommendations, cures, response language, preparation steps, or everyday examples. Do not invent facts, dates,
amounts, documents, clauses, approvals, authorities, or quotations.

DIMENSIONS:
{json.dumps(REVIEW_DIMENSIONS, ensure_ascii=False)}

CLIENT INTAKE:
{json.dumps(record['client'], ensure_ascii=False)}

FIRST MAIN-CASE REPORT:
{json.dumps(record['free_report'], ensure_ascii=False)}

EVIDENCE TEXT AVAILABLE TO THE FIRST ANALYSIS:
{json.dumps(record.get('evidence_context') or [], ensure_ascii=False)[:60000]}

Return strict JSON only:
{{"dimensions":[{{"dimension":"one listed dimension","findings":[{{"conclusion":"short plain-language weakness title","analysis":"connected explanation of vulnerability, factual basis, significance and limits","relevant_facts":"specific supplied facts","affected_side":"positive, negative, or both","confidence":"high, medium, or low"}}]}}],"analysis_limits":["material limitation"]}}"""
    bridge = _shared_lawyer_bridge()
    if bridge is not None:
        report = bridge.review_18_dimensions(record)
        provider = str(report.get("provider") or report.get("provider_mode") or "Lawyer software provider")
        model = str((report.get("analysis_metadata") or {}).get("model_name") or provider)
        report = _stamp_model_metadata(report, provider, model, "Lawyer software bridge")
    else:
        report = _provider_call(
            prompt,
            "You are the existing 18-dimension whole-case weakness review engine operating behind a client reception progress screen. Be neutral, evidence-bound, diagnostic only, and return valid JSON only.",
        )
    returned_dimensions = report.get("dimensions") or []
    indexed_dimensions = {
        str(item.get("dimension") or "").strip().casefold(): item
        for item in returned_dimensions
        if isinstance(item, dict)
    }
    report["dimensions"] = [
        {
            "dimension": name,
            "findings": list((indexed_dimensions.get(name.casefold()) or {}).get("findings") or []),
        }
        for name in REVIEW_DIMENSIONS
    ]
    positive, negative = [], []
    for dimension in report.get("dimensions") or []:
        if not isinstance(dimension, dict):
            continue
        dimension_name = str(dimension.get("dimension") or "Whole-Case Review")
        for finding in dimension.get("findings") or []:
            if not isinstance(finding, dict) or not str(finding.get("conclusion") or "").strip():
                continue
            item = {"dimension": dimension_name, **finding}
            affected = str(finding.get("affected_side") or "both").lower()
            if affected in {"positive", "both"}:
                positive.append(item)
            if affected in {"negative", "both"}:
                negative.append(item)
    report["positive_side_weaknesses"] = positive
    report["negative_side_weaknesses"] = negative
    record["deep_report"] = report
    if PROMOTION_FREE and str(((record.get("billing") or {}).get("report_payment") or {}).get("status") or "") == "promotion_free":
        payment = (record.get("billing") or {}).get("report_payment") or {"status": "promotion_free", "amount_cents": 0}
        billing_error = ""
    else:
        try:
            payment = settle_report(record, DEMO_MODE)
            billing_error = ""
        except Exception as exc:
            payment = {"status": "needs_attention"}
            billing_error = str(exc)[:240]
            record.setdefault("billing", {})["report_billing_error"] = billing_error
    _persist_session(payload.intake_id, record)
    _track_usage_event("advanced_reviews_completed", payload.intake_id, record)
    if str(payment.get("status") or "").lower() not in {"", "needs_attention", "failed", "declined"}:
        _track_usage_event("report_payments_completed", payload.intake_id, record)
    return {"ok": True, "report": report, "billing": billing_status(record), "payment": payment, "billing_error": billing_error}


def _enqueue_deep_scan(intake_id: str, access_token: str) -> str:
    if tasks_v2 is None or not PROJECT or not TASK_SERVICE_URL or not TASK_SECRET:
        raise RuntimeError("The background review queue is not configured.")
    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(PROJECT, TASK_LOCATION, TASK_QUEUE)
    body = json.dumps({"intake_id": intake_id, "access_token": access_token}).encode("utf-8")
    task: Dict[str, Any] = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": f"{TASK_SERVICE_URL}/client/internal/deep-scan",
            "headers": {"Content-Type": "application/json", "X-Nido-Task-Secret": TASK_SECRET},
            "body": body,
        },
    }
    if TASK_SERVICE_ACCOUNT:
        task["http_request"]["oidc_token"] = {
            "service_account_email": TASK_SERVICE_ACCOUNT,
            "audience": TASK_SERVICE_URL,
        }
    if duration_pb2 is not None:
        task["dispatch_deadline"] = duration_pb2.Duration(seconds=900)
    created = client.create_task(parent=parent, task=task)
    return str(created.name)


@router.post("/client/api/deep-scan/start")
def start_deep_scan(payload: AIProcessingSessionRequest) -> Dict[str, Any]:
    record = _session(payload)
    if not payload.consent_external_ai or record.get("consent_external_ai") is not True:
        raise HTTPException(status_code=400, detail="Online AI processing authorisation is required before starting the review.")
    if not record.get("client_authenticated") or not record.get("client_account"):
        raise HTTPException(status_code=401, detail="Register or log in before starting the 18-dimension review.")
    if not record.get("free_report"):
        raise HTTPException(status_code=409, detail="Complete the case-material organisation report first.")
    if not record.get("deep_scan_paid"):
        raise HTTPException(status_code=402, detail="Authorise the disclosed report fee before starting the review.")
    if record.get("deep_report"):
        return {"ok": True, "status": "complete", "report": record["deep_report"], "billing": billing_status(record)}
    if PRIVACY_FIRST_MODE:
        record["deep_scan_status"] = "running"
        record["deep_scan_started_at"] = int(time.time())
        result = deep_scan(payload)
        record["deep_scan_status"] = "complete"
        record["deep_scan_completed_at"] = int(time.time())
        return {"ok": True, "status": "complete", **result}
    status = str(record.get("deep_scan_status") or "")
    if status in {"queued", "running"}:
        return {"ok": True, "status": status}
    record["deep_scan_status"] = "queued"
    record["deep_scan_queued_at"] = int(time.time())
    record.pop("deep_scan_error", None)
    _persist_session(payload.intake_id, record)
    try:
        record["deep_scan_task"] = _enqueue_deep_scan(payload.intake_id, payload.access_token)
        _persist_session(payload.intake_id, record)
    except Exception as exc:
        record["deep_scan_status"] = "failed"
        record["deep_scan_error"] = str(exc)[:300]
        _persist_session(payload.intake_id, record)
        raise HTTPException(status_code=503, detail="The background review could not be queued. Please retry.") from exc
    return {"ok": True, "status": "queued"}


@router.post("/client/api/deep-scan/status")
def deep_scan_status(payload: SessionRequest) -> Dict[str, Any]:
    record = _session(payload)
    status = record.get("deep_scan_status") or ("complete" if record.get("deep_report") else "not_started")
    return {
        "ok": True,
        "status": status,
        "report": record.get("deep_report") if status == "complete" else None,
        "billing": billing_status(record),
        "payment": (record.get("billing") or {}).get("report_payment"),
        "error": record.get("deep_scan_error", "") if status == "failed" else "",
    }


@router.post("/client/internal/deep-scan")
def background_deep_scan(
    payload: SessionRequest,
    x_nido_task_secret: str = Header(default=""),
) -> Dict[str, Any]:
    if not TASK_SECRET or not secrets.compare_digest(str(x_nido_task_secret or ""), TASK_SECRET):
        raise HTTPException(status_code=403, detail="Background task authentication failed.")
    record = _session(payload)
    if record.get("deep_report"):
        record["deep_scan_status"] = "complete"
        _persist_session(payload.intake_id, record)
        return {"ok": True, "status": "complete", "idempotent": True}
    record["deep_scan_status"] = "running"
    record["deep_scan_started_at"] = int(time.time())
    _persist_session(payload.intake_id, record)
    try:
        result = deep_scan(AIProcessingSessionRequest(
            intake_id=payload.intake_id,
            access_token=payload.access_token,
            consent_external_ai=True,
        ))
        record = _session(payload)
        record["deep_scan_status"] = "complete"
        record["deep_scan_completed_at"] = int(time.time())
        _persist_session(payload.intake_id, record)
        return {"ok": True, "status": "complete", "payment": result.get("payment")}
    except Exception as exc:
        record["deep_scan_status"] = "failed"
        record["deep_scan_error"] = str(exc)[:500]
        _persist_session(payload.intake_id, record)
        raise


@router.post("/client/api/professional-report/pdf")
def download_professional_report_pdf(payload: SessionRequest) -> Response:
    record = _session(payload)
    if not record.get("free_report"):
        raise HTTPException(status_code=409, detail="Generate the organised matter report before downloading a professional report.")
    pdf = build_professional_pdf(record, LAW_FIRM_NAME)
    _track_usage_event("professional_pdf_downloads", payload.intake_id, record)
    case_name = str((record.get("free_report") or {}).get("case_name") or "client-matter")
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "-", case_name).strip("-")[:70] or "client-matter"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}-professional-review-pack.pdf"'},
    )


@router.post("/client/api/professional-report/docx")
def download_professional_report_docx(payload: SessionRequest) -> Response:
    record = _session(payload)
    if not record.get("free_report"):
        raise HTTPException(status_code=409, detail="Generate the organised matter report before downloading a professional report.")
    docx = build_professional_docx(record, LAW_FIRM_NAME)
    _track_usage_event("professional_docx_downloads", payload.intake_id, record)
    case_name = str((record.get("free_report") or {}).get("case_name") or "client-matter")
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "-", case_name).strip("-")[:70] or "client-matter"
    return Response(
        content=docx,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}-professional-review-pack.docx"'},
    )


@router.post("/client/api/report/pdf")
def download_client_report_pdf(payload: SessionRequest) -> Response:
    record = _session(payload)
    if not record.get("client_authenticated"):
        raise HTTPException(status_code=401, detail="Log in before downloading the report.")
    if not record.get("deep_report"):
        raise HTTPException(status_code=409, detail="The completed 18-dimension report is not available yet.")
    payment = (record.get("billing") or {}).get("report_payment") or {}
    payment_status = str(payment.get("status") or "").strip().lower()
    if not payment or payment_status in {"failed", "declined", "cancelled", "canceled", "rejected"}:
        raise HTTPException(status_code=402, detail="The report payment has not been completed.")
    pdf = build_client_weakness_pdf(record, LAW_FIRM_NAME)
    _track_usage_event("pdf_downloads", payload.intake_id, record)
    case_name = str((record.get("free_report") or {}).get("case_name") or "client-matter")
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "-", case_name).strip("-")[:70] or "client-matter"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}-18D-weakness-report.pdf"'},
    )


@router.post("/client/api/independent-review")
def independent_deep_review(payload: AIProcessingSessionRequest) -> Dict[str, Any]:
    record = _session(payload)
    if not payload.consent_external_ai or record.get("consent_external_ai") is not True:
        raise HTTPException(status_code=400, detail="Online AI processing authorisation is required before starting the independent deep review.")
    if not record.get("client_authenticated"):
        raise HTTPException(status_code=401, detail="Log in before starting the independent deep review.")
    if not record.get("deep_report"):
        raise HTTPException(status_code=409, detail="Complete the rapid 18-angle review first.")
    if record.get("independent_report"):
        return {"ok": True, "status": "complete", "report": record["independent_report"]}
    if record.get("independent_review_status") == "running":
        return {"ok": True, "status": "running", "progress": record.get("independent_review_progress", 0)}
    record["independent_review_status"] = "running"
    record["independent_review_started_at"] = int(time.time())
    record["independent_review_progress"] = int(record.get("independent_review_progress") or 0)
    record.pop("independent_review_error", None)
    _persist_session(payload.intake_id, record)
    try:
        report = _run_independent_review(payload.intake_id, record)
        record["independent_report"] = report
        record["independent_review_status"] = "complete"
        record["independent_review_progress"] = 100
        record["independent_review_completed_at"] = int(time.time())
        _persist_session(payload.intake_id, record)
        _track_usage_event("independent_deep_reviews_completed", payload.intake_id, record)
        return {"ok": True, "status": "complete", "report": report}
    except Exception as exc:
        record["independent_review_status"] = "failed"
        record["independent_review_error"] = str(exc)[:500]
        _persist_session(payload.intake_id, record)
        raise


@router.post("/client/api/independent-report/pdf")
def download_independent_report_pdf(payload: SessionRequest) -> Response:
    record = _session(payload)
    if not record.get("client_authenticated"):
        raise HTTPException(status_code=401, detail="Log in before downloading the report.")
    if not record.get("independent_report"):
        raise HTTPException(status_code=409, detail="The independent deep-review report is not available yet.")
    pdf = build_independent_review_pdf(record, LAW_FIRM_NAME)
    _track_usage_event("independent_pdf_downloads", payload.intake_id, record)
    case_name = str((record.get("free_report") or {}).get("case_name") or "client-matter")
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "-", case_name).strip("-")[:70] or "client-matter"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}-independent-18D-deep-review.pdf"'},
    )


@router.post("/client/api/human-handoff")
def human_handoff(payload: HandoffRequest) -> Dict[str, Any]:
    record = _session(payload)
    if not record.get("deep_report"):
        raise HTTPException(status_code=409, detail="Complete the 18-dimension weakness report before requesting human involvement.")
    if not payload.consent_human_transfer:
        raise HTTPException(status_code=400, detail="Explicit client consent is required before transferring the matter to a human lawyer.")
    handoff_id = "law_" + secrets.token_urlsafe(8)
    package = {
        "handoff_id": handoff_id,
        "created_at": int(time.time()),
        "preferred_contact": payload.preferred_contact,
        "note_for_lawyer": payload.note_for_lawyer[:2000],
        "client": record["client"],
        "evidence_files": record["evidence_files"],
        "evidence_context": record.get("evidence_context") or [],
        "free_report": record["free_report"],
        "deep_report": record.get("deep_report"),
        "independent_report": record.get("independent_report"),
        "billing": record.setdefault("billing", {}),
        "billing_boundary": "Human lawyer contact begins under the participating firm's disclosed hourly charging standard after the firm accepts the handoff and confirms the engagement terms.",
        "status": "awaiting_firm_acceptance",
        "messages": record.get("messages") or [],
    }
    record["handoff"] = package
    _persist_session(payload.intake_id, record)
    _track_usage_event("lawyer_handoffs", payload.intake_id, record)
    return {"ok": True, "handoff": package}


@router.post("/client/api/formal-decision")
def formal_decision(payload: FormalDecisionRequest) -> Dict[str, Any]:
    record = _session(payload)
    handoff = record.get("handoff")
    if not handoff:
        raise HTTPException(status_code=409, detail="Human involvement has not started.")
    if not handoff.get("final_lawyer_report"):
        raise HTTPException(status_code=409, detail="The lawyer's final report has not been delivered yet.")
    handoff["formal_service_requested"] = bool(payload.proceed)
    handoff["status"] = "formal_service_requested" if payload.proceed else "closed_after_final_report"
    _persist_session(payload.intake_id, record)
    return {"ok": True, "proceed": bool(payload.proceed), "status": handoff["status"], "pricing_boundary": "Any formal service follows the participating law firm's disclosed charging standard and engagement terms."}


@router.post("/client/api/messages")
def client_messages(payload: SessionRequest) -> Dict[str, Any]:
    record = _session(payload)
    handoff = record.get("handoff")
    if not handoff:
        raise HTTPException(status_code=409, detail="Human handoff has not been requested.")
    return {"ok": True, "messages": handoff.get("messages") or [], "status": handoff.get("status"), "final_lawyer_report": handoff.get("final_lawyer_report")}


@router.post("/client/api/messages/send")
def send_client_message(payload: ClientMessageRequest) -> Dict[str, Any]:
    record = _session(payload)
    handoff = record.get("handoff")
    if not handoff:
        raise HTTPException(status_code=409, detail="Human handoff has not been requested.")
    text = payload.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message is empty.")
    item = {"role": "client", "sender": record["client"].get("client_name") or "Client", "message": text[:4000], "timestamp": int(time.time())}
    handoff.setdefault("messages", []).append(item)
    _persist_session(payload.intake_id, record)
    return {"ok": True, "message": item}


CLIENT_HTML = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Law Firm Reception</title><style>
:root{--bg:#07111f;--panel:#111d31;--line:#2b3a55;--text:#eef4ff;--muted:#a9b6cc;--gold:#ffd84d;--teal:#22c7c9;--pink:#ef4b7b;--purple:#7c3aed;--green:#22c55e}*{box-sizing:border-box}body{margin:0;background:linear-gradient(135deg,#07111f,#12142b);color:var(--text);font:15px Arial,sans-serif}.wrap{max-width:1180px;margin:auto;padding:24px}.hero{padding:24px 0}.hero h1{color:var(--gold);font-size:34px;margin:0 0 8px}.hero p{color:var(--muted);max-width:850px}.steps{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:18px 0}.step{background:var(--panel);border:1px solid var(--line);padding:12px;border-radius:10px;font-size:13px}.step b{color:var(--gold);display:block;margin-bottom:5px}.active{border-color:var(--teal);box-shadow:0 0 0 1px var(--teal)}.card{background:rgba(17,29,49,.96);border:1px solid var(--line);border-radius:14px;padding:22px;margin:14px 0}label{display:block;color:var(--muted);margin:10px 0 5px}input,textarea{width:100%;background:#07111f;border:1px solid #40506a;border-radius:7px;color:white;padding:11px}textarea{min-height:130px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.drop{border:2px dashed #53657f;padding:18px;text-align:center;border-radius:10px;color:var(--muted)}button{background:var(--purple);border:0;color:white;padding:12px 18px;border-radius:8px;font-weight:bold;cursor:pointer;margin:8px 8px 0 0}button.primary{background:var(--teal);color:#03252a}button.pay{background:var(--pink)}button:disabled{opacity:.45;cursor:not-allowed}.notice{background:#3b2817;border-left:4px solid var(--gold);padding:12px;margin:12px 0;color:#fde7a8}.report section{background:#0b1627;border:1px solid #283b58;padding:13px;border-radius:9px;margin:9px 0}.report h3{color:var(--teal);margin:0 0 7px}.report li{margin:6px 0}.hidden{display:none}.status{color:#86efac;margin:10px 0;white-space:pre-wrap}.error{color:#fda4af}.handoff{border-color:var(--green)}@media(max-width:800px){.steps{grid-template-columns:1fr}.grid{grid-template-columns:1fr}}
</style></head><body><div class="wrap"><div class="hero"><h1>__LAW_FIRM_NAME__ AI Reception</h1><p>The main-case and 18-dimension tools run behind this reception screen. Clients see progress and reports, not the law firm's internal working interface.</p></div>
<div class="steps" id="steps"><div class="step active"><b>1 · Complete case organisation</b>Background, both sides and evidence</div><div class="step"><b>2 · 18-dimension review</b>Firm-configured access</div><div class="step"><b>3 · Lawyer conversation</b>Prepared dossier and focused questions</div><div class="step"><b>4 · Formal human service</b>Client decides whether to proceed</div></div>
<div class="card" id="intake"><h2>Free confidential intake</h2><div class="notice">Online AI processing requires your consent. Do not use this service for an emergency. Court, limitation, safety, immigration, criminal, or other urgent deadlines require immediate human legal assistance.</div><div class="grid"><div><label>Name</label><input id="name"></div><div><label>Email</label><input id="email" type="email"></div><div><label>Jurisdiction</label><input id="jurisdiction" placeholder="e.g. Victoria, Australia"></div><div><label>Known deadline or hearing date</label><input id="deadline"></div></div><label>What outcome do you want?</label><input id="outcome"><label>Describe what happened</label><textarea id="story" placeholder="Explain the events, dates, people, agreements, losses, and what the other side says..."></textarea><label>What evidence do you have?</label><textarea id="inventory" placeholder="Contracts, messages, invoices, photographs, witnesses, court documents..."></textarea><label class="drop">Drop or select up to 8 evidence files<input id="files" type="file" multiple style="margin-top:10px"></label><label><input id="consent" type="checkbox" style="width:auto"> I authorise the online AI to process the information and selected files for this preliminary intake.</label><button class="primary" id="analyse">Generate free initial report</button><div class="status" id="status"></div></div>
<div class="card hidden" id="freeCard"><h2>Initial case report</h2><div class="report" id="freeReport"></div><button class="pay" id="pay">Continue to 18-dimension weakness review</button><div class="status" id="payStatus"></div></div>
<div class="card hidden" id="deepCard"><h2>Detailed weakness scan</h2><div class="report" id="deepReport"></div><button id="handoffBtn">Transfer prepared matter to a human lawyer</button></div>
<div class="card hidden handoff" id="handoffCard"><h2>Human lawyer handoff</h2><p>The lawyer receives the organised intake, evidence index, free report, and detailed weakness scan. Hourly professional work starts only after the law firm accepts the matter and confirms engagement terms.</p><label>Note for the lawyer</label><textarea id="lawyerNote"></textarea><label><input id="handoffConsent" type="checkbox" style="width:auto"> I consent to transferring this prepared matter to a human lawyer.</label><button class="primary" id="confirmHandoff">Confirm human handoff</button><div class="status" id="handoffStatus"></div></div>
</div><script>
const DEMO=__DEMO_MODE__;let session=null;const $=id=>document.getElementById(id);function esc(v){return String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}function render(obj,el){el.innerHTML='';Object.entries(obj||{}).forEach(([k,v])=>{let s=document.createElement('section');let h=document.createElement('h3');h.textContent=k.replaceAll('_',' ');s.appendChild(h);if(Array.isArray(v)){let ul=document.createElement('ul');v.forEach(x=>{let li=document.createElement('li');li.textContent=typeof x==='object'?JSON.stringify(x):x;ul.appendChild(li)});s.appendChild(ul)}else{let p=document.createElement('div');p.textContent=typeof v==='object'?JSON.stringify(v,null,2):v;s.appendChild(p)}el.appendChild(s)})}async function api(url,body){let r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});let j=await r.json();if(!r.ok)throw new Error(j.detail||'Request failed');return j}async function fileData(){let out=[];for(const f of [...$('files').files]){let b=await f.arrayBuffer();let bytes=new Uint8Array(b),binary='';for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));out.push({name:f.name,content_type:f.type,content_base64:btoa(binary)})}return out}function stage(n){[...$('steps').children].forEach((x,i)=>x.classList.toggle('active',i===n-1))}
$('analyse').onclick=async()=>{try{$('analyse').disabled=true;$('status').className='status';$('status').textContent='AI receptionist is organising the matter...';let j=await api('/client/api/free-analysis',{client_name:$('name').value,email:$('email').value,jurisdiction:$('jurisdiction').value,deadline:$('deadline').value,desired_outcome:$('outcome').value,case_description:$('story').value,evidence_inventory:$('inventory').value,consent_external_ai:$('consent').checked,files:await fileData()});session={intake_id:j.intake_id,access_token:j.access_token};render(j.report,$('freeReport'));$('freeCard').classList.remove('hidden');$('status').textContent='Free report complete.';stage(2);$('freeCard').scrollIntoView({behavior:'smooth'})}catch(e){$('status').className='status error';$('status').textContent=e.message}finally{$('analyse').disabled=false}};
$('pay').onclick=async()=>{try{if(!DEMO){$('payStatus').textContent='Production: open the Pinch fixed-fee checkout, then return here after payment confirmation.';return}$('pay').disabled=true;$('payStatus').textContent='Sandbox payment confirmed. Running detailed scan...';await api('/client/api/demo-confirm-scan-payment',session);stage(3);let j=await api('/client/api/deep-scan',session);render(j.report,$('deepReport'));$('deepCard').classList.remove('hidden');$('payStatus').textContent='Detailed scan complete.';$('deepCard').scrollIntoView({behavior:'smooth'})}catch(e){$('payStatus').className='status error';$('payStatus').textContent=e.message}finally{$('pay').disabled=false}};
$('handoffBtn').onclick=()=>{$('handoffCard').classList.remove('hidden');stage(4);$('handoffCard').scrollIntoView({behavior:'smooth'})};$('confirmHandoff').onclick=async()=>{try{let j=await api('/client/api/human-handoff',{...session,consent_human_transfer:$('handoffConsent').checked,preferred_contact:'email',note_for_lawyer:$('lawyerNote').value});$('handoffStatus').textContent='Handoff package '+j.handoff.handoff_id+' is ready for law-firm acceptance. No hourly work starts until engagement terms are confirmed.';stage(5)}catch(e){$('handoffStatus').className='status error';$('handoffStatus').textContent=e.message}};
</script></body></html>'''

# Keep the base page readable above, then apply the competition client-flow
# skin as a separate layer. This keeps the commercial steps configurable while
# presenting a dedicated law-firm welcome window and hiding internal tools.
CLIENT_HTML = CLIENT_HTML.replace(
    "grid-template-columns:repeat(5,1fr)",
    "grid-template-columns:repeat(4,1fr)",
).replace(
    ".hidden{display:none}",
    ".hidden{display:none!important}.welcome{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:28px}.welcomeBox{max-width:760px;text-align:center;background:rgba(17,29,49,.97);border:1px solid #40506a;border-radius:18px;padding:48px}.welcomeBox h1{color:var(--gold);font-size:38px}.welcomeBox p{color:var(--muted);font-size:17px;line-height:1.6}.progress{height:12px;background:#07111f;border-radius:8px;overflow:hidden;margin:12px 0}.progress div{height:100%;width:0;background:linear-gradient(90deg,var(--purple),var(--teal));transition:width .35s}.messages{background:#07111f;border-radius:9px;padding:10px;max-height:280px;overflow:auto}.message{background:#17233a;border-left:4px solid var(--teal);padding:9px;margin:7px 0}.message.lawyer{border-color:#a78bfa}",
).replace(
    "</style></head><body><div class=\"wrap\">",
    "</style></head><body><div class=\"welcome\" id=\"welcome\"><div class=\"welcomeBox\"><h1>Welcome to __LAW_FIRM_NAME__ AI System</h1><p>Describe the matter once and provide the evidence you already have. The AI reception system will organise the complete matter and return a preliminary report before lawyer time begins.</p><button class=\"primary\" id=\"startReception\">Start secure AI reception</button></div></div><div class=\"wrap hidden\" id=\"appShell\">",
    1,
).replace(
    "<div class=\"hero\"><h1>AI Law Firm Reception</h1><p>Tell the story once. The AI organises the facts and evidence for free. Pay only if you choose a detailed weakness scan, then decide whether to transfer the prepared matter to a human lawyer.</p></div>",
    "<div class=\"hero\"><h1>__LAW_FIRM_NAME__ AI Reception</h1><p>The main-case and 18-dimension tools run behind this reception screen. Clients see progress and reports, not the law firm's internal working interface.</p></div>",
)
CLIENT_HTML = re.sub(
    r'<div class="steps" id="steps">.*?</div></div>\n<div class="card"',
    '<div class="steps" id="steps"><div class="step active"><b>1 - Complete case organisation</b>Background, both sides and evidence</div><div class="step"><b>2 - 18-dimension review</b>Firm-configured token charge if applicable</div><div class="step"><b>3 - Lawyer conversation</b>Prepared dossier and focused questions</div><div class="step"><b>4 - Formal human service</b>Client decides whether to proceed</div></div>\n<div class="card"',
    CLIENT_HTML,
    count=1,
    flags=re.S,
)
CLIENT_HTML = CLIENT_HTML.replace(
    '<button class="primary" id="analyse">Generate free initial report</button><div class="status" id="status"></div>',
    '<button class="primary" id="analyse">Organise complete case material</button><div class="progress hidden" id="mainProgress"><div></div></div><div class="status" id="status"></div>',
).replace(
    '<button class="pay" id="pay">Continue to 18-dimension weakness review</button><div class="status" id="payStatus"></div>',
    '<button class="pay" id="pay">Continue to 18-dimension weakness review</button><div class="progress hidden" id="deepProgress"><div></div></div><div class="status" id="payStatus"></div>',
).replace(
    '<button id="handoffBtn">Transfer prepared matter to a human lawyer</button>',
    '<button id="handoffBtn">Request human lawyer contact</button>',
).replace(
    '<button class="primary" id="confirmHandoff">Confirm human handoff</button><div class="status" id="handoffStatus"></div></div>',
    '<button class="primary" id="confirmHandoff">Confirm human handoff</button><div class="status" id="handoffStatus"></div><div class="hidden" id="clientChat"><h3>Conversation with the law firm</h3><div class="messages" id="messages"></div><textarea id="clientMessage" placeholder="Send additional details or answer the lawyer\'s focused questions..."></textarea><button id="sendMessage">Send message</button><button id="refreshMessages">Refresh conversation</button></div></div>',
).replace(
    "</div><script>",
    "</div></div><script>",
    1,
)
CLIENT_FLOW_SCRIPT = r'''<script>
$('startReception').onclick=()=>{$('welcome').classList.add('hidden');$('appShell').classList.remove('hidden')};
function beginProgress(id,textId,text){let box=$(id),bar=box.firstElementChild,p=8;box.classList.remove('hidden');bar.style.width=p+'%';$(textId).textContent=text;let timer=setInterval(()=>{p=Math.min(92,p+Math.max(1,(92-p)*.08));bar.style.width=p+'%'},450);return()=>{clearInterval(timer);bar.style.width='100%';setTimeout(()=>box.classList.add('hidden'),500)}}
const baseAnalyse=$('analyse').onclick;$('analyse').onclick=async()=>{let done=beginProgress('mainProgress','status','Organising the complete case background, both sides and evidence...');await baseAnalyse();done()};
const basePay=$('pay').onclick;$('pay').onclick=async()=>{let done=beginProgress('deepProgress','payStatus','The hidden review engine is reading the first report across 18 dimensions...');await basePay();done()};
$('handoffBtn').onclick=()=>{$('handoffCard').classList.remove('hidden');stage(3);$('handoffCard').scrollIntoView({behavior:'smooth'})};
async function refreshConversation(){try{let j=await api('/client/api/messages',session);$('messages').innerHTML=(j.messages||[]).map(x=>'<div class="message '+esc(x.role)+'"><b>'+esc(x.sender)+'</b><br>'+esc(x.message)+'</div>').join('')||'<div class="status">No messages yet. The lawyer already has the prepared reports and evidence index.</div>';if(j.status==='accepted_by_law_firm')stage(4)}catch(e){$('handoffStatus').textContent=e.message}}
$('confirmHandoff').onclick=async()=>{try{let j=await api('/client/api/human-handoff',{...session,consent_human_transfer:$('handoffConsent').checked,preferred_contact:'email',note_for_lawyer:$('lawyerNote').value});$('handoffStatus').textContent='Prepared dossier '+j.handoff.handoff_id+' has entered the lawyer queue. The lawyer can now review the complete history before asking focused questions.';$('clientChat').classList.remove('hidden');stage(3);await refreshConversation()}catch(e){$('handoffStatus').className='status error';$('handoffStatus').textContent=e.message}};
$('sendMessage').onclick=async()=>{try{await api('/client/api/messages/send',{...session,message:$('clientMessage').value});$('clientMessage').value='';await refreshConversation()}catch(e){$('handoffStatus').textContent=e.message}};$('refreshMessages').onclick=refreshConversation;
</script>'''
CLIENT_HTML = CLIENT_HTML.replace("</body></html>", CLIENT_FLOW_SCRIPT + "</body></html>")
