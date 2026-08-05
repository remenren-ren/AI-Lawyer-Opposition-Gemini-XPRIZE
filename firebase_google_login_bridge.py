import argparse
import json
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI Lawyer Opposition - Google Sign-In</title>
  <style>
    :root {
      color-scheme: dark;
      font-family: "Segoe UI", Arial, sans-serif;
      background: #0b1220;
      color: #f8fafc;
    }
    * { box-sizing: border-box; }
    body {
      min-height: 100vh;
      margin: 0;
      display: grid;
      place-items: center;
      background: #0b1220;
    }
    main {
      width: min(620px, calc(100vw - 32px));
      border: 1px solid #334155;
      background: #111827;
      padding: 30px;
      box-shadow: 0 24px 70px rgba(0, 0, 0, .38);
    }
    h1 { margin: 0 0 8px; font-size: 26px; letter-spacing: 0; }
    p { color: #cbd5e1; line-height: 1.55; }
    .boundary {
      margin: 22px 0;
      padding: 14px 16px;
      border-left: 4px solid #facc15;
      background: #172033;
      color: #e2e8f0;
    }
    button {
      width: 100%;
      min-height: 48px;
      border: 1px solid #475569;
      background: #f8fafc;
      color: #111827;
      font-size: 16px;
      font-weight: 700;
      cursor: pointer;
    }
    button:disabled { opacity: .55; cursor: wait; }
    #status { min-height: 24px; margin-top: 16px; color: #93c5fd; }
    .small { font-size: 13px; color: #94a3b8; }
  </style>
</head>
<body>
  <main>
    <h1>AI Lawyer Opposition</h1>
    <p>Sign in to restore your saved provider profiles and cloud preferences.</p>
    <div class="boundary">
      Signing in does not connect a model automatically. Restored API providers
      remain inactive until you press Verify inside the selected application.
    </div>
    <button id="google">Sign in with Google</button>
    <div id="status">Ready for secure Google sign-in.</div>
    <p class="small">This window may be closed after the desktop application confirms sign-in.</p>
  </main>
  <script type="module">
    import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.5/firebase-app.js";
    import {
      getAuth,
      GoogleAuthProvider,
      signInWithPopup
    } from "https://www.gstatic.com/firebasejs/10.12.5/firebase-auth.js";

    const firebaseConfig = __FIREBASE_CONFIG__;
    const app = initializeApp(firebaseConfig);
    const auth = getAuth(app);
    const provider = new GoogleAuthProvider();
    provider.setCustomParameters({ prompt: "select_account" });

    const button = document.getElementById("google");
    const status = document.getElementById("status");
    button.addEventListener("click", async () => {
      button.disabled = true;
      status.textContent = "Waiting for Google authorization...";
      try {
        const credential = await signInWithPopup(auth, provider);
        const token = await credential.user.getIdToken(true);
        const response = await fetch("/complete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            idToken: token,
            refreshToken: credential.user.refreshToken || ""
          })
        });
        const result = await response.json();
        if (!response.ok || !result.ok) {
          throw new Error(result.error || "Desktop sign-in handoff failed.");
        }
        status.textContent = "Sign-in complete. Return to the desktop application.";
        button.textContent = "Signed in";
      } catch (error) {
        status.textContent = error?.message || String(error);
        button.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


def validate_firebase_token(api_key, token):
    request = urllib.request.Request(
        f"https://identitytoolkit.googleapis.com/v1/accounts:lookup?key={api_key}",
        data=json.dumps({"idToken": token}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Firebase token validation failed: HTTP {exc.code}: {detail[:300]}") from exc
    users = data.get("users") or []
    if not users:
        raise RuntimeError("Firebase did not return a signed-in user.")
    user = users[0]
    return {
        "ok": True,
        "uid": str(user.get("localId") or ""),
        "email": str(user.get("email") or ""),
        "display_name": str(user.get("displayName") or ""),
        "id_token": token,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()

    config_path = Path(args.config)
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    project_id = str(config.get("project_id") or "").strip()
    api_key = str(config.get("web_api_key") or "").strip()
    auth_domain = str(config.get("auth_domain") or f"{project_id}.firebaseapp.com").strip()
    app_id = str(config.get("app_id") or "").strip()
    if not all([project_id, api_key, auth_domain, app_id]):
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "Firebase Google sign-in requires project_id, web_api_key, auth_domain, and app_id.",
                }
            ),
            flush=True,
        )
        return 2

    firebase_config = {
        "apiKey": api_key,
        "authDomain": auth_domain,
        "projectId": project_id,
        "appId": app_id,
    }
    state = {"result": None}
    completed = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format, *_args):
            return

        def send_json(self, status, payload):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            if self.path != "/":
                self.send_error(404)
                return
            html = HTML_TEMPLATE.replace(
                "__FIREBASE_CONFIG__",
                json.dumps(firebase_config, ensure_ascii=True),
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

        def do_POST(self):
            if self.path != "/complete":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length") or "0")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                token = str(payload.get("idToken") or "").strip()
                refresh_token = str(payload.get("refreshToken") or "").strip()
                if not token:
                    raise RuntimeError("Google sign-in did not return an ID token.")
                result = validate_firebase_token(api_key, token)
                if not result["uid"]:
                    raise RuntimeError("Firebase user ID is missing.")
                result["refresh_token"] = refresh_token
                result["expires_in"] = 3600
                state["result"] = result
                self.send_json(200, {"ok": True})
                completed.set()
            except Exception as exc:
                self.send_json(400, {"ok": False, "error": str(exc)})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.timeout = 0.5
    url = f"http://127.0.0.1:{server.server_port}/"
    webbrowser.open(url)
    deadline = time.time() + max(30, args.timeout)
    while not completed.is_set() and time.time() < deadline:
        server.handle_request()
    server.server_close()

    result = state["result"] or {
        "ok": False,
        "error": "Google sign-in timed out before Firebase returned a verified identity.",
    }
    print(json.dumps(result, ensure_ascii=True), flush=True)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
