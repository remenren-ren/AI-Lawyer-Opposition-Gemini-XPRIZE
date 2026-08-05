import base64
import base64
import ctypes
import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent
SESSION_FILE = HERE / "cloud_session.local.json"
ADMIN_CONFIG_FILE = HERE / "admin_cloud_config.local.json"
INTEGRATION_CONFIG_FILE = HERE / "google_cloud_integrations.local.json"
EVENT_QUEUE_FILE = HERE / "online_user_data" / "cloud_events.pending.jsonl"


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except Exception:
        return {} if default is None else default


def _write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def _dpapi_protect(text):
    raw = str(text or "").encode("utf-8")
    if not raw:
        return ""
    source = ctypes.create_string_buffer(raw)
    source_blob = DATA_BLOB(len(raw), ctypes.cast(source, ctypes.POINTER(ctypes.c_byte)))
    target_blob = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source_blob),
        "AI Lawyer Opposition cloud session",
        None,
        None,
        None,
        0,
        ctypes.byref(target_blob),
    ):
        raise ctypes.WinError()
    try:
        encrypted = ctypes.string_at(target_blob.pbData, target_blob.cbData)
        return base64.b64encode(encrypted).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(target_blob.pbData)


def _dpapi_unprotect(value):
    if not value:
        return ""
    encrypted = base64.b64decode(value)
    source = ctypes.create_string_buffer(encrypted)
    source_blob = DATA_BLOB(len(encrypted), ctypes.cast(source, ctypes.POINTER(ctypes.c_byte)))
    target_blob = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(target_blob),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target_blob.pbData, target_blob.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(target_blob.pbData)


def _request_json(url, method="GET", payload=None, headers=None, timeout=25):
    body = None
    request_headers = {"Accept": "application/json"}
    request_headers.update(headers or {})
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:500]}") from exc


def _firestore_value(value):
    if value is None:
        return {"nullValue": None}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, list):
        return {"arrayValue": {"values": [_firestore_value(item) for item in value]}}
    if isinstance(value, dict):
        return {"mapValue": {"fields": {str(k): _firestore_value(v) for k, v in value.items()}}}
    return {"stringValue": str(value)}


def _from_firestore_value(value):
    if "nullValue" in value:
        return None
    if "booleanValue" in value:
        return value["booleanValue"]
    if "integerValue" in value:
        return int(value["integerValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "timestampValue" in value:
        return value["timestampValue"]
    if "stringValue" in value:
        return value["stringValue"]
    if "arrayValue" in value:
        return [_from_firestore_value(item) for item in value["arrayValue"].get("values", [])]
    if "mapValue" in value:
        return {k: _from_firestore_value(v) for k, v in value["mapValue"].get("fields", {}).items()}
    return None


class GoogleCloudBackend:
    def __init__(self, session_file=SESSION_FILE):
        self.session_file = Path(session_file)
        self.admin = _read_json(ADMIN_CONFIG_FILE, {})
        self.integration = _read_json(INTEGRATION_CONFIG_FILE, {})
        EVENT_QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)

    @property
    def project_id(self):
        return str(self.admin.get("project_id") or self.integration.get("project_id") or "").strip()

    @property
    def cloud_run_url(self):
        cloud_run = self.integration.get("cloud_run") or {}
        url = str(cloud_run.get("service_url") or "").strip().rstrip("/")
        if not cloud_run.get("enabled") or not url or "YOUR_CLOUD_RUN_SERVICE" in url:
            return ""
        return url

    def store_firebase_session(self, uid, email, id_token, refresh_token="", expires_in=3600):
        data = {
            "signed_in": True,
            "account": str(email or uid or "").strip(),
            "uid": str(uid or "").strip(),
            "source": "firebase-google-firestore",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": int(time.time()) + max(60, int(expires_in or 3600)) - 60,
            "id_token_protected": _dpapi_protect(id_token),
            "refresh_token_protected": _dpapi_protect(refresh_token),
            "note": "Tokens are encrypted for the current Windows user. Providers still require Verify.",
        }
        _write_json(self.session_file, data)
        return data

    def load_session(self, refresh=True):
        data = _read_json(self.session_file, {})
        if not data.get("signed_in"):
            return data
        try:
            data["id_token"] = _dpapi_unprotect(data.get("id_token_protected", ""))
            data["refresh_token"] = _dpapi_unprotect(data.get("refresh_token_protected", ""))
        except Exception:
            data["id_token"] = ""
            data["refresh_token"] = ""
        if refresh and data.get("refresh_token") and int(data.get("expires_at") or 0) <= int(time.time()):
            data = self.refresh_firebase_session(data)
        return data

    def refresh_firebase_session(self, session=None):
        session = session or self.load_session(refresh=False)
        api_key = str(self.admin.get("web_api_key") or "").strip()
        refresh_token = str(session.get("refresh_token") or "").strip()
        if not api_key or not refresh_token:
            return session
        encoded = urllib.parse.urlencode(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}
        ).encode("ascii")
        request = urllib.request.Request(
            f"https://securetoken.googleapis.com/v1/token?key={urllib.parse.quote(api_key)}",
            data=encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                result = json.loads(response.read().decode("utf-8"))
        except Exception:
            return session
        self.store_firebase_session(
            result.get("user_id") or session.get("uid"),
            session.get("account"),
            result.get("id_token", ""),
            result.get("refresh_token") or refresh_token,
            result.get("expires_in") or 3600,
        )
        return self.load_session(refresh=False)

    def _firestore_document_url(self, path):
        if not self.project_id:
            return ""
        clean_path = str(path or "").strip("/")
        return (
            f"https://firestore.googleapis.com/v1/projects/{urllib.parse.quote(self.project_id)}"
            f"/databases/(default)/documents/{clean_path}"
        )

    def _authenticated_headers(self):
        session = self.load_session(refresh=True)
        token = str(session.get("id_token") or "").strip()
        return (session, {"Authorization": f"Bearer {token}"}) if token else (session, {})

    def firestore_get(self, path):
        url = self._firestore_document_url(path)
        session, headers = self._authenticated_headers()
        if not url or not headers:
            return None
        try:
            document = _request_json(url, headers=headers)
        except RuntimeError as exc:
            if "HTTP 403" in str(exc) or "HTTP 404" in str(exc):
                return None
            raise
        return {k: _from_firestore_value(v) for k, v in document.get("fields", {}).items()}

    def firestore_set(self, path, data):
        url = self._firestore_document_url(path)
        session, headers = self._authenticated_headers()
        if not url or not headers:
            return False
        payload = {"fields": {str(k): _firestore_value(v) for k, v in data.items()}}
        _request_json(url, method="PATCH", payload=payload, headers=headers)
        return True

    def provider_document_path(self, uid):
        template = str(
            self.admin.get("provider_document")
            or (self.integration.get("firestore") or {}).get("provider_document")
            or "users/{uid}/providerProfiles/default"
        )
        return template.replace("{uid}", uid)

    def sync_provider_profile(self, profile):
        session = self.load_session()
        uid = str(session.get("uid") or "").strip()
        if not uid:
            return False
        clean = dict(profile or {})
        for row in clean.get("providers", []) or []:
            row["verified"] = False
            row["restored_requires_verify"] = True
        payload = {
            "configJson": json.dumps(clean, ensure_ascii=False),
            "schema": "api_profiles_v1",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        return self.firestore_set(self.provider_document_path(uid), payload)

    def restore_provider_profile(self):
        session = self.load_session()
        uid = str(session.get("uid") or "").strip()
        if not uid:
            return None
        document = self.firestore_get(self.provider_document_path(uid))
        if not document:
            return None
        raw = document.get("configJson")
        if not raw:
            return None
        restored = json.loads(raw)
        restored["restored_requires_verify"] = True
        for row in restored.get("providers", []) or []:
            row["verified"] = False
            row["restored_requires_verify"] = True
        return restored

    def save_case_index(self, case_data, local_path=""):
        session = self.load_session()
        uid = str(session.get("uid") or "").strip()
        if not uid:
            return False
        title = str((case_data or {}).get("name") or "Untitled matter").strip()
        digest_source = f"{title}|{(case_data or {}).get('jurisdiction', '')}|{local_path}"
        case_id = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:24]
        payload = {
            "case_id": case_id,
            "title": title,
            "jurisdiction": str((case_data or {}).get("jurisdiction") or ""),
            "local_file": str(local_path or ""),
            "storage_mode": "local_content_cloud_index",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        collection = str((self.integration.get("firestore") or {}).get("case_collection") or "cases")
        return self.firestore_set(f"users/{uid}/{collection}/{case_id}", payload)

    def record_event(self, event, metadata=None):
        safe_metadata = {}
        for key, value in dict(metadata or {}).items():
            key_text = str(key)
            if any(term in key_text.lower() for term in ("text", "content", "background", "argument", "evidence", "api_key", "token")):
                continue
            safe_metadata[key_text] = value
        row = {
            "event": str(event or "unknown"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": safe_metadata,
        }
        with EVENT_QUEUE_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        if self.cloud_run_url:
            try:
                self._cloud_run_post("/events", row)
                return True
            except Exception:
                return False
        return True

    def upload_report(self, path, matter_name=""):
        path = Path(path)
        if not path.exists() or not self.cloud_run_url:
            return False
        payload = {
            "filename": path.name,
            "matter_name": str(matter_name or ""),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "content_base64": base64.b64encode(path.read_bytes()).decode("ascii"),
            "content_type": "text/html" if path.suffix.lower() == ".html" else "text/markdown",
        }
        self._cloud_run_post("/reports", payload, timeout=60)
        return True

    def _cloud_run_post(self, route, payload, timeout=25):
        session, headers = self._authenticated_headers()
        if not self.cloud_run_url:
            raise RuntimeError("Cloud Run is not configured.")
        return _request_json(
            self.cloud_run_url + route,
            method="POST",
            payload=payload,
            headers=headers,
            timeout=timeout,
        )

    def run_async(self, func, *args, **kwargs):
        def work():
            try:
                func(*args, **kwargs)
            except Exception:
                return
        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        return thread


_BACKEND = None


def get_backend():
    global _BACKEND
    if _BACKEND is None:
        _BACKEND = GoogleCloudBackend()
    return _BACKEND
