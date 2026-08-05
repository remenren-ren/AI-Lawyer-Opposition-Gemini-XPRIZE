import os
import base64
import hashlib
import html
import hmac
import json
import logging
import secrets
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs

from fastapi import Cookie, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

try:
    from google.cloud import firestore, logging as cloud_logging, secretmanager, storage
except Exception:
    firestore = None
    cloud_logging = None
    secretmanager = None
    storage = None
try:
    from google import genai
except Exception:
    genai = None
try:
    from .client_reception import add_lawyer_message, accept_handoff_record, handoff_by_id, handoff_queue_records, set_final_lawyer_report, router as client_reception_router
except Exception:
    from client_reception import add_lawyer_message, accept_handoff_record, handoff_by_id, handoff_queue_records, set_final_lawyer_report, router as client_reception_router


SERVICE_NAME = os.getenv("NIDO_SERVICE_NAME", "nido-gemini-online")
DEPLOYMENT_MODE = os.getenv("NIDO_DEPLOYMENT_MODE", "competition")
ALLOW_FULL_TEXT = os.getenv("NIDO_ALLOW_FULL_TEXT", "false").lower() == "true"
PRIVACY_FIRST_MODE = os.getenv("NIDO_PRIVACY_FIRST_MODE", "true").strip().lower() not in {
    "0", "false", "no", "off",
}
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
FIREBASE_WEB_API_KEY = os.getenv("NIDO_FIREBASE_WEB_API_KEY", "").strip()
FIRESTORE_STATE_DOCUMENT = os.getenv("NIDO_FIRESTORE_STATE_DOCUMENT", "system/service-state")
CLOUD_STORAGE_BUCKET = os.getenv("NIDO_CLOUD_STORAGE_BUCKET", "").strip()
LOG_NAME = os.getenv("NIDO_LOG_NAME", "ai-lawyer-opposition")
VERTEX_LOCATION = os.getenv("NIDO_VERTEX_LOCATION", "australia-southeast1")
VERTEX_MODEL = os.getenv("NIDO_VERTEX_MODEL", "gemini-2.5-flash")
USER_STORE_PATH = Path(os.getenv("NIDO_USER_STORE", "online_user_store.local.json"))
DEMO_LOGIN_ENABLED = os.getenv("NIDO_DEMO_LOGIN_ENABLED", "false").lower() == "true"
DEMO_USERNAME = os.getenv("NIDO_DEMO_USERNAME", "").strip()
DEMO_PASSWORD = os.getenv("NIDO_DEMO_PASSWORD", "").strip()


def _secret_value(env_name: str, secret_name_env: str, default: str) -> str:
    direct = os.getenv(env_name, "").strip()
    if direct:
        return direct
    secret_name = os.getenv(secret_name_env, "").strip()
    if not secret_name or secretmanager is None or not GOOGLE_CLOUD_PROJECT:
        return default
    client = secretmanager.SecretManagerServiceClient()
    resource = f"projects/{GOOGLE_CLOUD_PROJECT}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(request={"name": resource})
    return response.payload.data.decode("utf-8")


SESSION_SECRET = _secret_value(
    "NIDO_SESSION_SECRET", "NIDO_SESSION_SECRET_NAME", secrets.token_urlsafe(48)
)
VAULT_SECRET = _secret_value(
    "NIDO_VAULT_SECRET", "NIDO_VAULT_SECRET_NAME", secrets.token_urlsafe(48)
)

_firestore_client = firestore.Client(project=GOOGLE_CLOUD_PROJECT) if firestore and GOOGLE_CLOUD_PROJECT else None
_storage_client = storage.Client(project=GOOGLE_CLOUD_PROJECT) if storage and GOOGLE_CLOUD_PROJECT else None
_cloud_logger = None
if cloud_logging and GOOGLE_CLOUD_PROJECT:
    try:
        _logging_client = cloud_logging.Client(project=GOOGLE_CLOUD_PROJECT)
        _logging_client.setup_logging()
        _cloud_logger = _logging_client.logger(LOG_NAME)
    except Exception:
        _cloud_logger = None
logger = logging.getLogger(LOG_NAME)

app = FastAPI(
    title="Nido Gemini Online Final Review API",
    version="0.1.0",
    description="Cloud Run ready final-review endpoint for Nido Gemini Professional EN.",
)
app.include_router(client_reception_router)


class WeaknessItem(BaseModel):
    point: str = ""
    severity: str = "medium"
    reason: str = ""
    fix: str = ""


class FinalReviewRequest(BaseModel):
    matter_id: str = Field(default="unknown")
    jurisdiction: str = ""
    source: str = "offline-client-authorized"
    positive_summary: str = ""
    negative_summary: str = ""
    positive_weaknesses: List[WeaknessItem] = Field(default_factory=list)
    negative_weaknesses: List[WeaknessItem] = Field(default_factory=list)
    provider_roles: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    full_text: Optional[str] = None


class MatterStoreRequest(BaseModel):
    matter_id: str = Field(default="unknown")
    title: str = ""
    jurisdiction: str = ""
    storage_mode: str = Field(default="structured_or_redacted")
    consent_full_text_storage: bool = False
    structured_summary: str = ""
    full_text: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EventRequest(BaseModel):
    event: str
    timestamp: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ReportUploadRequest(BaseModel):
    filename: str
    matter_name: str = ""
    sha256: str
    content_base64: str
    content_type: str = "application/octet-stream"


class VertexReviewRequest(BaseModel):
    prompt: str
    system_instruction: str = "Act as a legal preparation assistant. Do not present output as legal advice."
    metadata: Dict[str, Any] = Field(default_factory=dict)


def _read_store() -> Dict[str, Any]:
    if _firestore_client is not None:
        snapshot = _firestore_client.document(FIRESTORE_STATE_DOCUMENT).get()
        if snapshot.exists:
            return snapshot.to_dict() or {"users": {}}
        return {"users": {}}
    if not USER_STORE_PATH.exists():
        return {"users": {}}
    with USER_STORE_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_store(store: Dict[str, Any]) -> None:
    if _firestore_client is not None:
        _firestore_client.document(FIRESTORE_STATE_DOCUMENT).set(store)
        return
    USER_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    USER_STORE_PATH.write_text(json.dumps(store, indent=2, sort_keys=True), encoding="utf-8")


def _ensure_demo_user(store: Dict[str, Any]) -> None:
    if not DEMO_LOGIN_ENABLED:
        return
    users = store.setdefault("users", {})
    if DEMO_USERNAME in users:
        return
    users[DEMO_USERNAME] = {
        "password_hash": _hash_password(DEMO_PASSWORD),
        "providers": [
            {
                "name": "gemini",
                "base_url": "https://generativelanguage.googleapis.com/v1beta",
                "model": "gemini-2.5-flash",
                "api_key_enc": _encrypt_secret("demo-key-not-real"),
                "updated_at": int(time.time()),
            },
            {
                "name": "deepseek",
                "base_url": "https://api.deepseek.com/v1",
                "model": "deepseek-chat",
                "api_key_enc": _encrypt_secret("demo-key-not-real"),
                "updated_at": int(time.time()),
            },
            {
                "name": "cloudapi-final",
                "base_url": "https://YOUR_CLOUD_RUN_OR_VERTEX_ENDPOINT/v1",
                "model": "cloud-final-review",
                "api_key_enc": _encrypt_secret("demo-key-not-real"),
                "updated_at": int(time.time()),
            },
        ],
        "matters": [
            {
                "matter_id": "demo-contract-001",
                "title": "Demo custom-equipment delay dispute",
                "jurisdiction": "NSW",
                "storage_mode": "structured_or_redacted",
                "structured_summary": "Buyer alleges late custom equipment delivery; supplier relies on specification changes, approval delay, and mitigation.",
                "metadata": {"demo": True, "intake_provider": "Gemini", "opposition_provider": "DeepSeek"},
                "has_full_text": False,
                "updated_at": int(time.time()),
            }
        ],
        "created_at": int(time.time()),
        "demo_account": True,
    }


def _hash_password(password: str, salt: Optional[str] = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000)
    return f"{salt}${base64.urlsafe_b64encode(digest).decode('ascii')}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, expected = stored.split("$", 1)
    except ValueError:
        return False
    return hmac.compare_digest(_hash_password(password, salt), f"{salt}${expected}")


def _vault_key() -> bytes:
    return hashlib.sha256(VAULT_SECRET.encode("utf-8")).digest()


def _keystream(nonce: bytes, length: int) -> bytes:
    key = _vault_key()
    out = bytearray()
    counter = 0
    while len(out) < length:
        out.extend(hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
        counter += 1
    return bytes(out[:length])


def _encrypt_secret(value: str) -> str:
    raw = value.encode("utf-8")
    nonce = secrets.token_bytes(16)
    stream = _keystream(nonce, len(raw))
    cipher = bytes(a ^ b for a, b in zip(raw, stream))
    tag = hmac.new(_vault_key(), nonce + cipher, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(nonce + tag + cipher).decode("ascii")


def _decrypt_secret(value: str) -> str:
    data = base64.urlsafe_b64decode(value.encode("ascii"))
    nonce, tag, cipher = data[:16], data[16:48], data[48:]
    expected = hmac.new(_vault_key(), nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise HTTPException(status_code=400, detail="Stored secret could not be verified.")
    stream = _keystream(nonce, len(cipher))
    return bytes(a ^ b for a, b in zip(cipher, stream)).decode("utf-8")


def _session_signature(username: str, expires: int) -> str:
    body = f"{username}|{expires}".encode("utf-8")
    return hmac.new(SESSION_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _make_session(username: str) -> str:
    expires = int(time.time()) + 60 * 60 * 24 * 14
    return f"{username}|{expires}|{_session_signature(username, expires)}"


def _current_user(nido_session: Optional[str]) -> Optional[str]:
    if not nido_session:
        return None
    try:
        username, expires_text, signature = nido_session.split("|", 2)
        expires = int(expires_text)
    except ValueError:
        return None
    if expires < int(time.time()):
        return None
    if not hmac.compare_digest(signature, _session_signature(username, expires)):
        return None
    return username


def _require_user(nido_session: Optional[str]) -> str:
    username = _current_user(nido_session)
    if not username:
        raise HTTPException(status_code=401, detail="Login required.")
    return username


def _mask_key(encrypted_value: str) -> str:
    try:
        value = _decrypt_secret(encrypted_value)
    except HTTPException:
        return "stored-key-unreadable"
    if not value:
        return ""
    return f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "stored"


def _html_page(username: Optional[str], message: str = "", demo_result: Optional[Dict[str, Any]] = None) -> str:
    demo_username = html.escape(DEMO_USERNAME, quote=True)
    demo_password = html.escape(DEMO_PASSWORD, quote=True)
    providers = []
    if username:
        store = _read_store()
        user = store.get("users", {}).get(username, {})
        for item in user.get("providers", []):
            providers.append(
                f"<tr><td>{item.get('name','')}</td><td>{item.get('base_url','')}</td>"
                f"<td>{item.get('model','')}</td><td>{_mask_key(item.get('api_key_enc',''))}</td></tr>"
            )
    provider_rows = "\n".join(providers) or "<tr><td colspan='4'>No providers saved.</td></tr>"
    demo_block = f"""
      <section class="demo">
        <h2>Judge Demo Access</h2>
        <p>Use this pre-filled account for competition review. It contains placeholder providers and a sample matter only.</p>
        <form method="post" action="/demo-login">
          <button type="submit">Enter Demo Portal</button>
        </form>
        <p class="hint">Username: {demo_username} &nbsp; Password: {demo_password}</p>
      </section>
    """ if DEMO_LOGIN_ENABLED else ""
    login_block = f"""
      {demo_block}
      <form method="post" action="/login">
        <h2>Sign in</h2>
        <input name="username" placeholder="Email or username" autocomplete="username" value="{demo_username if DEMO_LOGIN_ENABLED else ''}">
        <input name="password" placeholder="Password" type="password" autocomplete="current-password" value="{demo_password if DEMO_LOGIN_ENABLED else ''}">
        <button type="submit">Sign in</button>
      </form>
      <form method="post" action="/register">
        <h2>Create account</h2>
        <input name="username" placeholder="Email or username" autocomplete="username">
        <input name="password" placeholder="Password" type="password" autocomplete="new-password">
        <button type="submit">Create account</button>
      </form>
    """
    dashboard_block = f"""
      <div class="topbar">
        <strong>{username}</strong>
        <form method="post" action="/logout"><button type="submit">Sign out</button></form>
      </div>
      <section class="demo">
        <h2>Demo Case Review</h2>
        <p>This prepared review shows the competition flow without requiring a judge to register, upload private documents, or enter real API keys.</p>
        <ol>
          <li>Gemini-style intake separates the matter into facts, issues, evidence gaps, and candidate arguments.</li>
          <li>DeepSeek-style opposing counsel reviews both sides for attacks, rebuttals, and weakness points.</li>
          <li>Cloud Run consolidates the final vulnerability review for lawyer preparation.</li>
        </ol>
        <form method="post" action="/demo-review">
          <button type="submit">Run Demo Case Review</button>
        </form>
      </section>
      {_demo_review_html(demo_result) if demo_result else ""}
      <section>
        <h2>Provider Vault</h2>
        <form method="post" action="/providers">
          <input name="name" placeholder="Provider name, e.g. gemini / deepseek / private-model">
          <input name="base_url" placeholder="Endpoint URL">
          <input name="model" placeholder="Model name">
          <input name="api_key" placeholder="API key" type="password" autocomplete="off">
          <button type="submit">Save provider</button>
        </form>
        <table>
          <thead><tr><th>Provider</th><th>Endpoint</th><th>Model</th><th>API key</th></tr></thead>
          <tbody>{provider_rows}</tbody>
        </table>
      </section>
      <section>
        <h2>Routing</h2>
        <p>Gemini handles intake and long-context case analysis. DeepSeek handles positive-side and negative-side adversarial counsel. Cloud Run coordinates final review and private endpoint bridging.</p>
      </section>
      <section>
        <h2>Cloud Matter Storage</h2>
        <p>Default cloud storage is structured or redacted. Full matter text can be stored only when this deployment enables full-text storage and the user gives explicit per-matter consent.</p>
      </section>
    """
    body = dashboard_block if username else login_block
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Nido Gemini Online</title>
  <style>
    :root {{ color-scheme: light; font-family: Arial, sans-serif; }}
    body {{ margin: 0; background: #f7f7f4; color: #222; }}
    main {{ max-width: 980px; margin: 0 auto; padding: 32px 18px; }}
    h1 {{ font-size: 32px; margin: 0 0 18px; }}
    h2 {{ font-size: 18px; margin: 0 0 12px; }}
    form, section {{ margin: 0 0 20px; padding: 18px; background: #fff; border: 1px solid #ddd; border-radius: 8px; }}
    input {{ width: 100%; box-sizing: border-box; margin: 0 0 10px; padding: 10px; border: 1px solid #bbb; border-radius: 6px; font-size: 14px; }}
    button {{ padding: 9px 14px; border: 1px solid #111; border-radius: 6px; background: #222; color: #fff; cursor: pointer; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; }}
    th, td {{ border-bottom: 1px solid #ddd; padding: 10px; text-align: left; font-size: 14px; word-break: break-word; }}
    ol, ul {{ margin: 8px 0 0 20px; padding: 0; }}
    li {{ margin: 6px 0; }}
    .topbar {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 18px; }}
    .topbar form {{ margin: 0; padding: 0; border: 0; background: transparent; }}
    .message {{ margin: 0 0 14px; color: #8a3a16; }}
    .hint {{ font-size: 13px; color: #666; }}
    .demo {{ border-color: #222; }}
    .result {{ border-color: #9f7a20; background: #fffdf5; }}
    .metrics {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 12px 0; }}
    .metrics span {{ padding: 8px 10px; border: 1px solid #ddd; border-radius: 6px; background: #fff; }}
  </style>
</head>
<body>
  <main>
    <h1>Nido Gemini Online</h1>
    <p class="message">{message}</p>
    {body}
  </main>
</body>
</html>"""


async def _form_values(request: Request) -> Dict[str, str]:
    body = (await request.body()).decode("utf-8")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[0] for key, values in parsed.items()}


def _score(items: List[WeaknessItem]) -> int:
    weights = {"fatal": 5, "high": 3, "medium": 2, "low": 1}
    return sum(weights.get((item.severity or "").lower(), 2) for item in items)


def _top_actions(items: List[WeaknessItem], side: str) -> List[str]:
    if not items:
        return [f"{side}: no specific weakness was supplied; request a structured weakness list before final review."]
    actions = []
    for item in items[:5]:
        point = item.point.strip() or "Unspecified weakness"
        if item.fix.strip():
            actions.append(f"{side}: {item.fix.strip()}")
        else:
            actions.append(f"{side}: address and evidence-check this point: {point}")
    return actions


def _demo_review_payload() -> FinalReviewRequest:
    return FinalReviewRequest(
        matter_id="demo-contract-001",
        jurisdiction="NSW",
        source="judge-demo",
        positive_summary=(
            "Buyer claims custom equipment was delivered late and seeks delay damages. "
            "Gemini intake separates the dispute into delivery obligation, variation history, approval delay, "
            "loss proof, mitigation, and notice issues."
        ),
        negative_summary=(
            "Supplier argues the delivery date moved because buyer changed specifications, delayed approvals, "
            "and failed to provide timely site access. DeepSeek-style adversarial counsel focuses on causation, "
            "notice, and damages proof."
        ),
        positive_weaknesses=[
            WeaknessItem(
                point="The buyer has not tied each alleged delay day to a specific contractual milestone.",
                severity="high",
                reason="A delay claim becomes vulnerable if the timeline is broad rather than milestone-based.",
                fix="Prepare a dated milestone table linking contract clause, promised date, actual event, and evidence.",
            ),
            WeaknessItem(
                point="Loss evidence is asserted but not quantified against invoices, replacement costs, or lost profit records.",
                severity="medium",
                reason="Damages can fail even when breach is arguable.",
                fix="Separate liability proof from damages proof and attach calculation support.",
            ),
        ],
        negative_weaknesses=[
            WeaknessItem(
                point="Supplier relies on specification changes but has not shown written variation approval for every extension.",
                severity="high",
                reason="Without documented extensions, variation history may not defeat the original deadline.",
                fix="Collect emails, change orders, approval logs, and any conduct showing accepted deadline movement.",
            ),
            WeaknessItem(
                point="Supplier's mitigation argument is underdeveloped because it does not identify what the buyer could reasonably have done.",
                severity="medium",
                reason="A generic mitigation allegation is easy to dismiss.",
                fix="List concrete alternative steps available to the buyer and the evidence that those steps were reasonable.",
            ),
        ],
        provider_roles={
            "gemini": "first-pass intake, long-context issue segmentation, evidence organization",
            "deepseek_positive": "buyer-side adversarial argument drafting",
            "deepseek_negative": "supplier-side adversarial argument drafting",
            "cloud_run": "final structured vulnerability review and cross-side consolidation",
        },
    )


def _demo_review_html(result: Dict[str, Any]) -> str:
    positive_actions = "".join(f"<li>{html.escape(item)}</li>" for item in result.get("positive_actions", []))
    negative_actions = "".join(f"<li>{html.escape(item)}</li>" for item in result.get("negative_actions", []))
    summary = html.escape(result.get("summary", ""))
    return f"""
      <section class="result">
        <h2>Demo Review Result</h2>
        <p>{summary}</p>
        <div class="metrics">
          <span>Positive vulnerability score: <strong>{result.get("positive_vulnerability_score", 0)}</strong></span>
          <span>Negative vulnerability score: <strong>{result.get("negative_vulnerability_score", 0)}</strong></span>
        </div>
        <h3>Recommended Positive-Side Work</h3>
        <ul>{positive_actions}</ul>
        <h3>Recommended Negative-Side Work</h3>
        <ul>{negative_actions}</ul>
      </section>
    """


@app.get("/", response_class=HTMLResponse)
def portal(nido_session: Optional[str] = Cookie(default=None)) -> HTMLResponse:
    store = _read_store()
    before = json.dumps(store, sort_keys=True)
    _ensure_demo_user(store)
    if json.dumps(store, sort_keys=True) != before:
        _write_store(store)
    return HTMLResponse(_html_page(_current_user(nido_session)))


@app.get("/login", response_class=HTMLResponse)
def login_page(nido_session: Optional[str] = Cookie(default=None)) -> HTMLResponse:
    return portal(nido_session)


@app.post("/register")
async def register(request: Request) -> Response:
    form = await _form_values(request)
    username = form.get("username", "").strip().lower()
    password = form.get("password", "")
    if len(username) < 3 or len(password) < 8:
        return HTMLResponse(_html_page(None, "Use a username of at least 3 characters and a password of at least 8 characters."), status_code=400)
    store = _read_store()
    users = store.setdefault("users", {})
    if username in users:
        return HTMLResponse(_html_page(None, "That account already exists."), status_code=400)
    users[username] = {"password_hash": _hash_password(password), "providers": [], "created_at": int(time.time())}
    _write_store(store)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("nido_session", _make_session(username), httponly=True, samesite="lax")
    return response


@app.post("/login")
async def login(request: Request) -> Response:
    form = await _form_values(request)
    username = form.get("username", "").strip().lower()
    password = form.get("password", "")
    store = _read_store()
    user = store.get("users", {}).get(username)
    if not user or not _verify_password(password, user.get("password_hash", "")):
        return HTMLResponse(_html_page(None, "Invalid username or password."), status_code=401)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("nido_session", _make_session(username), httponly=True, samesite="lax")
    return response


@app.post("/demo-login")
async def demo_login() -> Response:
    if not DEMO_LOGIN_ENABLED:
        raise HTTPException(status_code=404, detail="Demo login is disabled.")
    store = _read_store()
    _ensure_demo_user(store)
    _write_store(store)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("nido_session", _make_session(DEMO_USERNAME), httponly=True, samesite="lax")
    return response


@app.post("/demo-review", response_class=HTMLResponse)
def demo_review(nido_session: Optional[str] = Cookie(default=None)) -> HTMLResponse:
    username = _require_user(nido_session)
    result = final_review(_demo_review_payload())
    return HTMLResponse(_html_page(username, "Demo case review completed.", result))


@app.post("/logout")
def logout() -> Response:
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("nido_session")
    return response


@app.get("/lawyer/intake-queue", response_class=HTMLResponse)
def lawyer_intake_queue(nido_session: Optional[str] = Cookie(default=None)) -> HTMLResponse:
    username = _require_user(nido_session)
    rows = handoff_queue_records()
    cards = []
    for item in rows:
        client = item.get("client") or {}
        free_report = item.get("free_report") or {}
        deep_report = item.get("deep_report") or {}
        status = str(item.get("status") or "awaiting_firm_acceptance")
        accept_form = ""
        if status != "accepted_by_law_firm":
            accept_form = (
                f'<form method="post" action="/lawyer/intake-queue/{html.escape(str(item.get("handoff_id") or ""))}/accept">'
                '<button type="submit">Accept human handoff</button></form>'
            )
        cards.append(
            f"""<article><div class="status">{html.escape(status.replace('_', ' ').upper())}</div>
<h2>{html.escape(str(client.get('client_name') or 'Client intake'))}</h2>
<p><b>Email:</b> {html.escape(str(client.get('email') or ''))} &nbsp; <b>Jurisdiction:</b> {html.escape(str(client.get('jurisdiction') or ''))}</p>
<p><b>Desired outcome:</b> {html.escape(str(client.get('desired_outcome') or ''))}</p>
<p><b>Evidence files:</b> {len(item.get('evidence_files') or [])} &nbsp; <b>Handoff ID:</b> {html.escape(str(item.get('handoff_id') or ''))}</p>
<p class="boundary">{html.escape(str(item.get('billing_boundary') or ''))}</p><p><a href="/lawyer/intake/{html.escape(str(item.get('handoff_id') or ''))}">Open matter and client conversation →</a></p>{accept_form}
<details><summary>Prepared matter package</summary><h3>Free intake report</h3><pre>{html.escape(json.dumps(free_report, ensure_ascii=False, indent=2))}</pre>
<h3>Detailed weakness scan</h3><pre>{html.escape(json.dumps(deep_report, ensure_ascii=False, indent=2))}</pre></details></article>"""
        )
    body = "".join(cards) or "<article><h2>No client has requested human review yet.</h2></article>"
    page = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Lawyer Intake Queue</title>
<style>body{{font-family:Arial;background:#07111f;color:#eef4ff;margin:0}}main{{max-width:1050px;margin:auto;padding:28px}}h1{{color:#ffd84d}}article{{background:#111d31;border:1px solid #33445f;border-radius:12px;padding:20px;margin:14px 0}}.status{{color:#22c7c9;font-weight:bold}}.boundary{{background:#173421;padding:10px;border-left:4px solid #22c55e}}button{{background:#7c3aed;color:white;border:0;padding:10px 15px;border-radius:7px;font-weight:bold}}pre{{white-space:pre-wrap;background:#07111f;padding:12px;border-radius:8px;color:#cbd5e1}}a{{color:#7dd3fc}}</style></head>
<body><main><p><a href="/">← Provider portal</a></p><h1>Human Lawyer Intake Queue</h1><p>Signed in as {html.escape(username)}. AI intake is complete before lawyer time begins.</p>{body}</main></body></html>"""
    return HTMLResponse(page)


@app.post("/lawyer/intake-queue/{handoff_id}/accept")
def accept_lawyer_intake(handoff_id: str, nido_session: Optional[str] = Cookie(default=None)) -> Response:
    username = _require_user(nido_session)
    try:
        accept_handoff_record(handoff_id, username)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Handoff was not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RedirectResponse("/lawyer/intake-queue", status_code=303)


@app.get("/lawyer/intake/{handoff_id}", response_class=HTMLResponse)
def lawyer_intake_detail(handoff_id: str, nido_session: Optional[str] = Cookie(default=None)) -> HTMLResponse:
    username = _require_user(nido_session)
    try:
        handoff = handoff_by_id(handoff_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Handoff was not found.") from exc
    client = handoff.get("client") or {}
    messages = handoff.get("messages") or []
    message_html = "".join(
        f'<div class="msg {html.escape(str(item.get("role") or ""))}"><b>{html.escape(str(item.get("sender") or ""))}</b><br>{html.escape(str(item.get("message") or ""))}</div>'
        for item in messages
    ) or '<p class="muted">No messages yet. The prepared matter is already available below.</p>'
    evidence_html = "".join(
        f'<details><summary>{html.escape(str(item.get("name") or "Evidence"))}</summary><pre>{html.escape(str(item.get("text") or "")[:12000])}</pre></details>'
        for item in handoff.get("evidence_context") or []
    ) or '<p class="muted">No extractable evidence text was retained in this demonstration.</p>'
    page = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Prepared Client Matter</title>
<style>body{{font-family:Arial;background:#07111f;color:#eef4ff;margin:0}}main{{max-width:1100px;margin:auto;padding:28px}}h1,h2{{color:#ffd84d}}section{{background:#111d31;border:1px solid #33445f;border-radius:12px;padding:18px;margin:14px 0}}pre{{white-space:pre-wrap;background:#07111f;padding:12px;border-radius:8px;color:#cbd5e1}}textarea{{width:100%;min-height:90px;background:#07111f;color:white;border:1px solid #40506a;border-radius:8px;padding:10px}}button{{background:#7c3aed;color:white;border:0;padding:11px 16px;border-radius:7px;font-weight:bold}}a{{color:#7dd3fc}}.msg{{padding:10px;border-radius:8px;margin:8px 0;background:#17233a}}.msg.client{{border-left:4px solid #22c7c9}}.msg.lawyer{{border-left:4px solid #a78bfa}}.muted{{color:#a9b6cc}}</style></head><body><main>
<p><a href="/lawyer/intake-queue">← Human intake queue</a></p><h1>Prepared Matter: {html.escape(str(client.get('client_name') or handoff_id))}</h1>
<section><h2>Client conversation</h2>{message_html}<form method="post" action="/lawyer/intake/{html.escape(handoff_id)}/message"><textarea name="message" placeholder="Ask a focused follow-up question based on the prepared report..."></textarea><p><button type="submit">Send as {html.escape(username)}</button></p></form></section>
<section><h2>Pinch hourly billing</h2><p class="muted">The client-authorised timer starts when the firm accepts this matter. Delivering the final lawyer report stops the timer and submits the calculated Sandbox collection.</p><pre>{html.escape(json.dumps(handoff.get('billing') or {}, ensure_ascii=False, indent=2))}</pre></section>
<section><h2>Final lawyer report</h2><p class="muted">Deliver the lawyer-reviewed report after the focused consultation. The client will then decide whether to enter formal human service.</p><form method="post" action="/lawyer/intake/{html.escape(handoff_id)}/final-report"><textarea name="report_text" placeholder="Enter the final lawyer-reviewed report..."></textarea><p><button type="submit">Deliver final report</button></p></form><pre>{html.escape(json.dumps(handoff.get('final_lawyer_report') or {}, ensure_ascii=False, indent=2))}</pre></section>
<section><h2>Client narrative and objective</h2><pre>{html.escape(json.dumps(client, ensure_ascii=False, indent=2))}</pre></section>
<section><h2>Case-material organisation report</h2><pre>{html.escape(json.dumps(handoff.get('free_report') or {}, ensure_ascii=False, indent=2))}</pre></section>
<section><h2>18-dimension weakness report</h2><pre>{html.escape(json.dumps(handoff.get('deep_report') or {}, ensure_ascii=False, indent=2))}</pre></section>
<section><h2>Evidence extracts</h2>{evidence_html}</section></main></body></html>"""
    return HTMLResponse(page)


@app.post("/lawyer/intake/{handoff_id}/message")
async def lawyer_send_message(handoff_id: str, request: Request, nido_session: Optional[str] = Cookie(default=None)) -> Response:
    username = _require_user(nido_session)
    values = await _form_values(request)
    try:
        add_lawyer_message(handoff_id, username, values.get("message", ""))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Handoff was not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(f"/lawyer/intake/{handoff_id}", status_code=303)


@app.post("/lawyer/intake/{handoff_id}/final-report")
async def lawyer_final_report(handoff_id: str, request: Request, nido_session: Optional[str] = Cookie(default=None)) -> Response:
    username = _require_user(nido_session)
    values = await _form_values(request)
    try:
        set_final_lawyer_report(handoff_id, username, values.get("report_text", ""))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Handoff was not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(f"/lawyer/intake/{handoff_id}", status_code=303)


@app.post("/providers")
async def save_provider(request: Request, nido_session: Optional[str] = Cookie(default=None)) -> Response:
    username = _require_user(nido_session)
    form = await _form_values(request)
    name = form.get("name", "").strip().lower()
    base_url = form.get("base_url", "").strip()
    model = form.get("model", "").strip()
    api_key = form.get("api_key", "")
    if not name or not base_url or not model or not api_key:
        return HTMLResponse(_html_page(username, "Provider name, endpoint URL, model, and API key are required."), status_code=400)
    store = _read_store()
    user = store.setdefault("users", {}).setdefault(username, {"providers": []})
    providers = [item for item in user.get("providers", []) if item.get("name") != name]
    providers.append(
        {
            "name": name,
            "base_url": base_url,
            "model": model,
            "api_key_enc": _encrypt_secret(api_key),
            "updated_at": int(time.time()),
        }
    )
    user["providers"] = providers
    _write_store(store)
    return RedirectResponse("/", status_code=303)


@app.get("/providers")
def list_providers(nido_session: Optional[str] = Cookie(default=None)) -> Dict[str, Any]:
    username = _require_user(nido_session)
    store = _read_store()
    providers = []
    for item in store.get("users", {}).get(username, {}).get("providers", []):
        providers.append(
            {
                "name": item.get("name", ""),
                "base_url": item.get("base_url", ""),
                "model": item.get("model", ""),
                "api_key_mask": _mask_key(item.get("api_key_enc", "")),
                "updated_at": item.get("updated_at"),
            }
        )
    return {"user": username, "providers": providers}


@app.post("/matters")
def save_matter(payload: MatterStoreRequest, nido_session: Optional[str] = Cookie(default=None)) -> Dict[str, Any]:
    username = _require_user(nido_session)
    if PRIVACY_FIRST_MODE:
        raise HTTPException(
            status_code=403,
            detail="Persistent matter storage is disabled in this privacy-first public deployment.",
        )
    if payload.full_text and not ALLOW_FULL_TEXT:
        raise HTTPException(
            status_code=400,
            detail="Full-text matter storage is disabled for this deployment.",
        )
    if payload.full_text and not payload.consent_full_text_storage:
        raise HTTPException(
            status_code=400,
            detail="Full-text matter storage requires explicit per-matter consent.",
        )

    store = _read_store()
    user = store.setdefault("users", {}).setdefault(username, {"providers": []})
    matters = [item for item in user.get("matters", []) if item.get("matter_id") != payload.matter_id]
    matter_record = {
        "matter_id": payload.matter_id,
        "title": payload.title,
        "jurisdiction": payload.jurisdiction,
        "storage_mode": "full_text_authorized" if payload.full_text else payload.storage_mode,
        "structured_summary": payload.structured_summary,
        "metadata": payload.metadata,
        "has_full_text": bool(payload.full_text),
        "updated_at": int(time.time()),
    }
    if payload.full_text:
        matter_record["full_text_enc"] = _encrypt_secret(payload.full_text)
    matters.append(matter_record)
    user["matters"] = matters
    _write_store(store)
    return {
        "user": username,
        "matter_id": payload.matter_id,
        "saved": True,
        "storage_mode": matter_record["storage_mode"],
        "has_full_text": matter_record["has_full_text"],
    }


@app.get("/matters")
def list_matters(nido_session: Optional[str] = Cookie(default=None)) -> Dict[str, Any]:
    username = _require_user(nido_session)
    store = _read_store()
    matters = []
    for item in store.get("users", {}).get(username, {}).get("matters", []):
        matters.append(
            {
                "matter_id": item.get("matter_id", ""),
                "title": item.get("title", ""),
                "jurisdiction": item.get("jurisdiction", ""),
                "storage_mode": item.get("storage_mode", ""),
                "has_full_text": item.get("has_full_text", False),
                "updated_at": item.get("updated_at"),
            }
        )
    return {"user": username, "matters": matters}


def _firebase_api_user(request: Request) -> str:
    authorization = str(request.headers.get("Authorization") or "")
    if not authorization.startswith("Bearer "):
        if FIREBASE_WEB_API_KEY:
            raise HTTPException(status_code=401, detail="Firebase bearer token required.")
        return "deployment-service"
    token = authorization[7:].strip()
    if not FIREBASE_WEB_API_KEY:
        return "authenticated-client"
    lookup = urllib.request.Request(
        f"https://identitytoolkit.googleapis.com/v1/accounts:lookup?key={FIREBASE_WEB_API_KEY}",
        data=json.dumps({"idToken": token}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(lookup, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=401, detail="Firebase identity could not be verified.") from exc
    users = result.get("users") or []
    if not users:
        raise HTTPException(status_code=401, detail="Firebase identity is missing.")
    return str(users[0].get("localId") or users[0].get("email") or "authenticated-client")


@app.post("/events")
def write_event(payload: EventRequest, request: Request) -> Dict[str, Any]:
    user = _firebase_api_user(request)
    safe_metadata = {
        str(key): value
        for key, value in payload.metadata.items()
        if not any(term in str(key).lower() for term in ("text", "content", "argument", "evidence", "api_key", "token"))
    }
    entry = {
        "event": payload.event,
        "timestamp": payload.timestamp or int(time.time()),
        "user": user,
        "metadata": safe_metadata,
    }
    logger.info("cloud_event %s", json.dumps(entry, ensure_ascii=True))
    if _cloud_logger is not None:
        _cloud_logger.log_struct(entry, severity="INFO")
    return {"ok": True, "logged": True}


@app.post("/reports")
def upload_report(payload: ReportUploadRequest, request: Request) -> Dict[str, Any]:
    user = _firebase_api_user(request)
    if PRIVACY_FIRST_MODE:
        raise HTTPException(
            status_code=403,
            detail="Persistent report upload is disabled in this privacy-first public deployment.",
        )
    if _storage_client is None or not CLOUD_STORAGE_BUCKET:
        raise HTTPException(status_code=503, detail="Cloud Storage bucket is not configured.")
    try:
        content = base64.b64decode(payload.content_base64, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Report payload is not valid base64.") from exc
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Report exceeds the 25 MB upload boundary.")
    actual_hash = hashlib.sha256(content).hexdigest()
    if not hmac.compare_digest(actual_hash, payload.sha256):
        raise HTTPException(status_code=400, detail="Report checksum mismatch.")
    safe_user = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in user)
    safe_name = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in Path(payload.filename).name)
    object_name = f"users/{safe_user}/reports/{int(time.time())}_{safe_name}"
    blob = _storage_client.bucket(CLOUD_STORAGE_BUCKET).blob(object_name)
    blob.metadata = {
        "matter_name": payload.matter_name[:200],
        "sha256": payload.sha256,
        "source": "ai-lawyer-opposition-desktop",
    }
    blob.upload_from_string(content, content_type=payload.content_type)
    write_event(
        EventRequest(event="cloud_report_uploaded", metadata={"object": object_name, "bytes": len(content)}),
        request,
    )
    return {"ok": True, "bucket": CLOUD_STORAGE_BUCKET, "object": object_name, "sha256": actual_hash}


@app.post("/vertex-review")
def vertex_review(payload: VertexReviewRequest, request: Request) -> Dict[str, Any]:
    _firebase_api_user(request)
    if genai is None or not GOOGLE_CLOUD_PROJECT:
        raise HTTPException(status_code=503, detail="Vertex AI is not configured.")
    client = genai.Client(vertexai=True, project=GOOGLE_CLOUD_PROJECT, location=VERTEX_LOCATION)
    response = client.models.generate_content(
        model=VERTEX_MODEL,
        contents=payload.prompt,
        config={"system_instruction": payload.system_instruction},
    )
    text = str(getattr(response, "text", "") or "").strip()
    if not text:
        raise HTTPException(status_code=502, detail="Vertex AI returned no review text.")
    return {"ok": True, "model": VERTEX_MODEL, "location": VERTEX_LOCATION, "text": text}


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "mode": DEPLOYMENT_MODE,
        "allow_full_text": ALLOW_FULL_TEXT,
        "firestore_active": _firestore_client is not None,
        "cloud_storage_active": _storage_client is not None and bool(CLOUD_STORAGE_BUCKET),
        "cloud_logging_active": _cloud_logger is not None,
        "vertex_ai_active": genai is not None and bool(GOOGLE_CLOUD_PROJECT),
        "timestamp": int(time.time()),
    }


@app.get("/capabilities")
def capabilities() -> Dict[str, Any]:
    return {
        "service": SERVICE_NAME,
        "roles": [
            "multi_api_orchestration",
            "final_review",
            "vulnerability_summary",
            "private_model_bridge",
            "structured_payload_review",
            "authorized_cloud_matter_storage",
        ],
        "recommended_routing": {
            "gemini": "case intake, drag-and-drop document understanding, long-context issue extraction, structured case analysis",
            "deepseek": "positive-side and negative-side adversarial counsel",
            "cloud_run": "orchestration and final-review endpoint",
            "private_model_endpoint": "optional customer-owned model provider"
        },
        "recommended_payload": "structured summaries, selected weaknesses, redacted exports",
        "not_default_payload": "full local matter database",
        "full_text_storage": {
            "enabled": ALLOW_FULL_TEXT,
            "policy": "Allowed only with explicit per-matter user consent when deployment full-text storage is enabled.",
        },
        "google_cloud_modules": [
            "Cloud Run",
            "Cloud Logging",
            "Firestore",
            "Cloud Storage",
            "Vertex AI",
            "Firebase",
        ],
        "activation": {
            "firebase_authentication": bool(FIREBASE_WEB_API_KEY),
            "firestore": _firestore_client is not None,
            "cloud_storage": _storage_client is not None and bool(CLOUD_STORAGE_BUCKET),
            "cloud_logging": _cloud_logger is not None,
            "secret_manager": secretmanager is not None and bool(GOOGLE_CLOUD_PROJECT),
            "vertex_ai": genai is not None and bool(GOOGLE_CLOUD_PROJECT),
        },
    }


@app.post("/final-review")
def final_review(payload: FinalReviewRequest) -> Dict[str, Any]:
    if payload.full_text and not ALLOW_FULL_TEXT:
        raise HTTPException(
            status_code=400,
            detail="Full text is disabled for this deployment. Send structured summaries or redacted payloads.",
        )

    pos_score = _score(payload.positive_weaknesses)
    neg_score = _score(payload.negative_weaknesses)

    if pos_score > neg_score:
        balance = "The positive side currently has the heavier vulnerability load."
    elif neg_score > pos_score:
        balance = "The negative side currently has the heavier vulnerability load."
    else:
        balance = "Both sides show a similar vulnerability load based on supplied weaknesses."

    return {
        "matter_id": payload.matter_id,
        "service": SERVICE_NAME,
        "final_review_type": "structured_vulnerability_summary",
        "summary": (
            f"{balance} This is a preparation review only, not legal advice or a decision on the merits."
        ),
        "positive_vulnerability_score": pos_score,
        "negative_vulnerability_score": neg_score,
        "positive_actions": _top_actions(payload.positive_weaknesses, "Positive side"),
        "negative_actions": _top_actions(payload.negative_weaknesses, "Negative side"),
        "provider_role_note": payload.provider_roles,
        "privacy_note": (
            "The endpoint is designed for structured summaries, selected weaknesses, redacted payloads, "
            "or authorized exports. The local matter database should remain local unless the user explicitly authorizes backup or transfer."
        ),
    }
