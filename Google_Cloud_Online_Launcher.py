import os
import subprocess
import sys
import tkinter as tk
import json
import threading
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

from google_cloud_backend import get_backend


HERE = Path(__file__).resolve().parent
ONLINE_APP = HERE / "Nido_StrikeOver_Online_EN.py"
PROVIDER_CONFIG = HERE / "api_profiles.local.json"
ADMIN_CLOUD_CONFIG = HERE / "admin_cloud_config.local.json"
SESSION_FILE = HERE / "cloud_session.local.json"
CLOUD_INTEGRATION_CONFIG = HERE / "google_cloud_integrations.local.json"
CLOUD_SERVICE_DIR = HERE / "cloud_service"
CLOUD_DEPLOY_SCRIPT = CLOUD_SERVICE_DIR / "DEPLOY_CLOUD_RUN.cmd"
FIREBASE_GOOGLE_LOGIN_BRIDGE = HERE / "firebase_google_login_bridge.py"


class StrikeOverLauncherEN:
    C = {
        "bg": "#171827",
        "panel": "#24263a",
        "text": "#f8fafc",
        "muted": "#b7c0d8",
        "gold": "#ffd84d",
        "offline": "#0f766e",
        "online": "#7c3aed",
        "button": "#1f3b5f",
    }

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AI Lawyer Opposition - Google Cloud Online")
        self.root.geometry("920x720")
        self.root.minsize(820, 640)
        self.root.configure(bg=self.C["bg"])
        self.cloud_backend = get_backend()
        # A new launcher session always requires an explicit account choice.
        # Provider keys remain stored, but the online app will not reveal them
        # until Google or reviewer-account authentication creates a new gate.
        self.clear_cloud_session()
        self.root.protocol("WM_DELETE_WINDOW", self.close_launcher)
        self.status_var = tk.StringVar(value="Ready: sign in to restore cloud provider settings, or use the local reviewer demo.")
        self.root.withdraw()
        self.build_ui()
        self.root.deiconify()
        self.root.update_idletasks()
        self.show_startup_disclaimer()

    def build_ui(self):
        title = tk.Frame(self.root, bg=self.C["bg"], padx=18, pady=16)
        title.pack(fill=tk.X)
        tk.Label(
            title,
            text="AI Lawyer Opposition - Google Cloud Online",
            bg=self.C["bg"],
            fg=self.C["gold"],
            font=("Microsoft YaHei UI", 18, "bold"),
        ).pack(side=tk.LEFT)
        tk.Label(
            title,
            text="Cloud account, model orchestration, case review, and report delivery",
            bg=self.C["bg"],
            fg=self.C["muted"],
            font=("Microsoft YaHei UI", 11),
        ).pack(side=tk.LEFT, padx=14, pady=(6, 0))

        self.build_cloud_panel()

        cards = tk.Frame(self.root, bg=self.C["bg"], padx=18)
        cards.pack(fill=tk.BOTH, expand=True)
        cards.grid_columnconfigure(0, weight=1)
        cards.grid_rowconfigure(0, weight=1)

        self.build_version_card(
            cards,
            0,
            "Google Cloud Online Version",
            "Full model-assisted opposition, weakness review, single-point rebuttal, and complete report delivery",
            self.C["online"],
            [
                "The established online interface and adversarial workflow remain unchanged.",
                "Firebase Authentication identifies the user; Firestore restores the user's provider profile.",
                "Cloud services progressively replace local-only online storage, logging, secrets, and report delivery.",
            ],
            "Open Google Cloud Online Version",
            lambda: self.launch_app(ONLINE_APP, "Google Cloud Online Version"),
        )

        bottom = tk.Frame(self.root, bg=self.C["bg"], padx=18, pady=10)
        bottom.pack(fill=tk.X)
        tk.Label(bottom, textvariable=self.status_var, bg=self.C["bg"], fg=self.C["muted"], anchor="w").pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        self.make_button(bottom, "Open Folder", self.open_folder, self.C["button"], padx=12, pady=5).pack(side=tk.RIGHT)
        self.make_button(
            bottom,
            "Google Cloud",
            self.open_cloud_integration_center,
            "#b7791f",
            padx=12,
            pady=5,
        ).pack(side=tk.RIGHT, padx=(0, 8))

    def build_cloud_panel(self):
        panel = tk.Frame(self.root, bg=self.C["panel"], padx=14, pady=12)
        panel.pack(fill=tk.X, padx=18, pady=(0, 12))
        tk.Label(
            panel,
            text="Google Cloud Account",
            bg=self.C["panel"],
            fg=self.C["text"],
            font=("Microsoft YaHei UI", 13, "bold"),
        ).pack(anchor="w")
        tk.Label(
            panel,
            text="Firebase Authentication identifies the user and Firestore restores saved provider settings. Restored providers still require Verify inside the online application.",
            bg=self.C["panel"],
            fg=self.C["muted"],
            font=("Microsoft YaHei UI", 10),
        ).pack(anchor="w", pady=(2, 8))

        row = tk.Frame(panel, bg=self.C["panel"])
        row.pack(fill=tk.X)
        self.v_cloud_email = tk.StringVar(value="")
        self.v_cloud_password = tk.StringVar(value="")

        self.cloud_account_entry = self._entry(row, "Account", self.v_cloud_email, 28)
        self.cloud_password_entry = self._entry(row, "Password", self.v_cloud_password, 24, show="*")

        actions = tk.Frame(panel, bg=self.C["panel"])
        actions.pack(fill=tk.X, pady=(8, 0))
        self.cloud_status_var = tk.StringVar(value="Sign-in restores settings only; it does not connect models or upload a matter.")
        self.cloud_status_label = tk.Label(
            actions,
            textvariable=self.cloud_status_var,
            bg=self.C["panel"],
            fg=self.C["gold"],
            font=("Microsoft YaHei UI", 10),
            anchor="w",
        )
        self.cloud_status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.cloud_signin_button = self.make_button(actions, "Sign in", self.sign_in, "#2563eb", padx=12, pady=5)
        self.cloud_signin_button.pack(side=tk.RIGHT, padx=3)
        self.cloud_google_button = self.make_button(
            actions,
            "Sign in with Google",
            self.sign_in_with_google,
            "#f8fafc",
            fg="#111827",
            padx=12,
            pady=5,
        )
        self.cloud_google_button.pack(side=tk.RIGHT, padx=3)

    def _entry(self, parent, label, var, width, show=None):
        group = tk.Frame(parent, bg=self.C["panel"])
        group.pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(group, text=label, bg=self.C["panel"], fg=self.C["muted"], font=("Microsoft YaHei UI", 9)).pack(anchor="w")
        e = tk.Entry(
            group,
            textvariable=var,
            width=width,
            show=show or "",
            bg="#171827",
            fg=self.C["text"],
            disabledbackground="#303244",
            disabledforeground="#9ca3af",
            insertbackground=self.C["text"],
            relief=tk.FLAT,
            bd=5,
            font=("Microsoft YaHei UI", 10),
        )
        e.pack(fill=tk.X)
        return e

    def set_cloud_status(self, text, color=None):
        self.cloud_status_var.set(text)
        self.cloud_status_label.configure(fg=color or self.C["gold"])

    def set_cloud_signed_in(self, message):
        self.set_cloud_status(message, "#86efac")
        self.cloud_account_entry.configure(state=tk.DISABLED)
        self.cloud_password_entry.configure(state=tk.DISABLED)
        self.cloud_signin_button.configure(text="Signed in", state=tk.DISABLED, bg="#4b5563")
        self.cloud_google_button.configure(state=tk.DISABLED, bg="#4b5563", fg="#d1d5db")

    def set_cloud_sign_in_failed(self, message):
        self.set_cloud_status(message, "#f87171")
        self.cloud_account_entry.configure(state=tk.NORMAL)
        self.cloud_password_entry.configure(state=tk.NORMAL)
        self.cloud_signin_button.configure(text="Sign in", state=tk.NORMAL, bg="#2563eb")
        self.cloud_google_button.configure(
            text="Sign in with Google",
            state=tk.NORMAL,
            bg="#f8fafc",
            fg="#111827",
        )

    def clear_cloud_session(self):
        try:
            if SESSION_FILE.exists():
                SESSION_FILE.unlink()
        except Exception:
            pass

    def close_launcher(self):
        self.clear_cloud_session()
        self.root.destroy()

    def write_cloud_session(self, account, source):
        data = {
            "signed_in": True,
            "account": str(account or "").strip(),
            "source": source,
            "created_at": datetime.now().isoformat(),
            "note": "Session gate only. Provider rows still require Verify inside the online application.",
        }
        SESSION_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_admin_cloud_config(self):
        if not ADMIN_CLOUD_CONFIG.exists():
            return None
        try:
            return json.loads(ADMIN_CLOUD_CONFIG.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            raise RuntimeError(f"Admin cloud config is invalid: {exc}") from exc

    def load_cloud_integration_config(self):
        if not CLOUD_INTEGRATION_CONFIG.exists():
            return {}
        try:
            return json.loads(CLOUD_INTEGRATION_CONFIG.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(f"Google Cloud integration config is invalid: {exc}") from exc

    def save_cloud_integration_config(self, data):
        CLOUD_INTEGRATION_CONFIG.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def gemini_profile_status(self):
        try:
            data = json.loads(PROVIDER_CONFIG.read_text(encoding="utf-8-sig"))
        except Exception:
            return False, "Provider profile file is unavailable."
        for row in data.get("providers", []) or []:
            if str(row.get("name") or "").strip().lower() == "gemini":
                if str(row.get("base_url") or "").strip() and str(row.get("model") or "").strip():
                    return True, "Configured locally; final connection still requires Verify inside the selected version."
        return False, "Gemini provider profile is not configured."

    def cloud_service_rows(self):
        config = self.load_cloud_integration_config()
        admin = self.load_admin_cloud_config() or {}
        gemini_ok, gemini_note = self.gemini_profile_status()
        cloud_run = config.get("cloud_run") or {}
        storage = config.get("cloud_storage") or {}
        logging = config.get("cloud_logging") or {}
        secret_manager = config.get("secret_manager") or {}
        vertex = config.get("vertex_ai") or {}
        run_url = str(cloud_run.get("service_url") or "").strip()
        run_active = bool(
            cloud_run.get("enabled")
            and run_url
            and "YOUR_CLOUD_RUN_SERVICE" not in run_url
        )
        firestore_active = bool(
            str(admin.get("project_id") or "").strip()
            and str(admin.get("web_api_key") or "").strip()
        )
        firebase_active = bool(
            firestore_active
            and str(admin.get("auth_domain") or "").strip()
            and str(admin.get("app_id") or "").strip()
        )
        return [
            ("Gemini API", gemini_ok, gemini_note),
            (
                "Firebase Authentication",
                firebase_active,
                "Google and email/password account authentication are configured."
                if firebase_active
                else "Google sign-in is installed; connect a Firebase web app to activate it.",
            ),
            (
                "Cloud Firestore",
                firestore_active,
                "Authenticated provider-profile restore is available."
                if firestore_active
                else "Restore code is installed but no Firebase project is configured.",
            ),
            (
                "Cloud Run",
                run_active,
                f"Configured endpoint: {run_url}"
                if run_active
                else "Deployable service is included; enter the deployed run.app URL after deployment.",
            ),
            (
                "Cloud Storage",
                bool(storage.get("enabled") and str(storage.get("bucket") or "").strip()),
                f"Authorized export bucket: {storage.get('bucket')}"
                if storage.get("enabled") and str(storage.get("bucket") or "").strip()
                else "Prepared for authorized reports and backups; no bucket is configured.",
            ),
            (
                "Cloud Logging",
                bool(logging.get("enabled") and run_active),
                "Enabled for the deployed Cloud Run service."
                if logging.get("enabled") and run_active
                else "Prepared in the deployment profile; activates after Cloud Run deployment.",
            ),
            (
                "Secret Manager",
                bool(secret_manager.get("enabled") and run_active),
                "Configured for server-side secrets."
                if secret_manager.get("enabled") and run_active
                else "Prepared for server secrets; local provider keys remain local until deployment.",
            ),
            (
                "Vertex AI",
                bool(vertex.get("enabled") and run_active),
                f"Managed review model: {vertex.get('model') or 'gemini-2.5-flash'}"
                if vertex.get("enabled") and run_active
                else "Managed Gemini review route is installed and activates with the Cloud Run deployment.",
            ),
        ]

    def open_cloud_integration_center(self):
        try:
            config = self.load_cloud_integration_config()
        except Exception as exc:
            messagebox.showerror("Google Cloud", str(exc))
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Google Cloud Integration Center")
        dialog.geometry("920x650")
        dialog.minsize(820, 580)
        dialog.configure(bg="#111827")
        dialog.transient(self.root)

        header = tk.Frame(dialog, bg="#111827", padx=22, pady=18)
        header.pack(fill=tk.X)
        tk.Label(
            header,
            text="Google Cloud Integration Center",
            bg="#111827",
            fg=self.C["gold"],
            font=("Microsoft YaHei UI", 18, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="This panel reports real configuration state. Prepared code is not shown as active until credentials or a deployed endpoint exist.",
            bg="#111827",
            fg="#cbd5e1",
            font=("Microsoft YaHei UI", 10),
            wraplength=850,
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(5, 0))

        endpoint_box = tk.Frame(dialog, bg="#1f2937", padx=16, pady=12)
        endpoint_box.pack(fill=tk.X, padx=22, pady=(0, 12))
        tk.Label(
            endpoint_box,
            text="Cloud Run service URL",
            bg="#1f2937",
            fg="#e5e7eb",
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(anchor="w")
        run_url_var = tk.StringVar(value=str((config.get("cloud_run") or {}).get("service_url") or ""))
        run_entry = tk.Entry(
            endpoint_box,
            textvariable=run_url_var,
            bg="#111827",
            fg="#f8fafc",
            insertbackground="#f8fafc",
            relief=tk.FLAT,
            bd=7,
            font=("Consolas", 10),
        )
        run_entry.pack(fill=tk.X, pady=(6, 0))

        status_shell = tk.Frame(dialog, bg="#111827")
        status_shell.pack(fill=tk.BOTH, expand=True, padx=22)
        status_canvas = tk.Canvas(status_shell, bg="#111827", highlightthickness=0)
        status_scroll = tk.Scrollbar(status_shell, orient=tk.VERTICAL, command=status_canvas.yview)
        status_inner = tk.Frame(status_canvas, bg="#111827")
        status_inner.bind(
            "<Configure>",
            lambda _event: status_canvas.configure(scrollregion=status_canvas.bbox("all")),
        )
        status_window = status_canvas.create_window((0, 0), window=status_inner, anchor="nw")
        status_canvas.bind(
            "<Configure>",
            lambda event: status_canvas.itemconfigure(status_window, width=event.width),
        )
        status_canvas.configure(yscrollcommand=status_scroll.set)
        status_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        status_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        def render_rows():
            for child in status_inner.winfo_children():
                child.destroy()
            for name, active, note in self.cloud_service_rows():
                row = tk.Frame(
                    status_inner,
                    bg="#1f2937",
                    padx=14,
                    pady=12,
                    highlightthickness=1,
                    highlightbackground="#374151",
                )
                row.pack(fill=tk.X, pady=(0, 7))
                tk.Label(
                    row,
                    text="ACTIVE" if active else "NOT ACTIVE",
                    bg="#065f46" if active else "#4b5563",
                    fg="#ffffff",
                    width=12,
                    pady=5,
                    font=("Microsoft YaHei UI", 9, "bold"),
                ).pack(side=tk.LEFT, padx=(0, 12))
                text = tk.Frame(row, bg="#1f2937")
                text.pack(side=tk.LEFT, fill=tk.X, expand=True)
                tk.Label(
                    text,
                    text=name,
                    bg="#1f2937",
                    fg="#f8fafc",
                    font=("Microsoft YaHei UI", 11, "bold"),
                ).pack(anchor="w")
                tk.Label(
                    text,
                    text=note,
                    bg="#1f2937",
                    fg="#cbd5e1",
                    font=("Microsoft YaHei UI", 9),
                    wraplength=680,
                    justify=tk.LEFT,
                ).pack(anchor="w", pady=(2, 0))

        def save_url():
            latest = self.load_cloud_integration_config()
            latest.setdefault("cloud_run", {})
            url = run_url_var.get().strip()
            latest["cloud_run"]["service_url"] = url
            latest["cloud_run"]["enabled"] = bool(url and "YOUR_CLOUD_RUN_SERVICE" not in url)
            self.save_cloud_integration_config(latest)
            render_rows()
            self.status_var.set("Google Cloud configuration updated.")

        def test_cloud_run():
            import requests

            save_url()
            url = run_url_var.get().strip().rstrip("/")
            if not url or "YOUR_CLOUD_RUN_SERVICE" in url:
                messagebox.showinfo("Cloud Run", "Enter a deployed Cloud Run service URL first.")
                return

            def work():
                try:
                    response = requests.get(f"{url}/health", timeout=15)
                    if response.status_code >= 400:
                        raise RuntimeError(f"HTTP {response.status_code}")
                    self.root.after(
                        0,
                        lambda: messagebox.showinfo("Cloud Run", "Cloud Run health check succeeded."),
                    )
                except Exception as exc:
                    error_text = str(exc)
                    self.root.after(
                        0,
                        lambda text=error_text: messagebox.showerror("Cloud Run", f"Health check failed:\n{text}"),
                    )

            threading.Thread(target=work, daemon=True).start()

        def deploy_cloud_run():
            if not CLOUD_DEPLOY_SCRIPT.exists():
                messagebox.showerror(
                    "Cloud Run",
                    f"Deployment script was not found:\n{CLOUD_DEPLOY_SCRIPT}",
                )
                return
            subprocess.Popen(
                ["cmd.exe", "/k", str(CLOUD_DEPLOY_SCRIPT)],
                cwd=str(CLOUD_SERVICE_DIR),
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
            )
            messagebox.showinfo(
                "Cloud Run Deployment",
                "The Google Cloud deployment console has opened.\n\n"
                "Complete Google sign-in if requested, select or enter a billing-enabled "
                "Google Cloud project, and keep the console open until it prints the "
                "deployed run.app URL.",
            )

        actions = tk.Frame(dialog, bg="#111827", padx=22, pady=16)
        actions.pack(fill=tk.X)
        self.make_button(actions, "Save URL", save_url, "#0f766e", padx=14, pady=7).pack(side=tk.LEFT)
        self.make_button(actions, "Test Cloud Run", test_cloud_run, "#2563eb", padx=14, pady=7).pack(side=tk.LEFT, padx=8)
        self.make_button(
            actions,
            "Deploy Cloud Run",
            deploy_cloud_run,
            "#b7791f",
            padx=14,
            pady=7,
        ).pack(side=tk.LEFT)
        self.make_button(
            actions,
            "Open Cloud Service",
            lambda: os.startfile(str(CLOUD_SERVICE_DIR)),
            "#374151",
            padx=14,
            pady=7,
        ).pack(side=tk.LEFT)
        self.make_button(actions, "Refresh", render_rows, "#374151", padx=14, pady=7).pack(side=tk.RIGHT)

        render_rows()

    def account_to_email(self, account, config):
        account = str(account or "").strip()
        if "@" in account:
            return account
        mapped = (config.get("account_email_map") or {}).get(account)
        if mapped:
            return str(mapped).strip()
        if account.lower() == "demo":
            return "demo@ai-lawyer-opposition.demo"
        return account

    def sign_in(self):
        account = self.v_cloud_email.get().strip()
        password = self.v_cloud_password.get().strip()
        if not all([account, password]):
            self.set_cloud_sign_in_failed("Input error: account and password are required.")
            messagebox.showerror("Sign In", "Account and password are required.")
            return
        try:
            config = self.load_admin_cloud_config()
        except Exception as exc:
            self.set_cloud_sign_in_failed("Sign-in failed: cloud configuration is invalid.")
            messagebox.showerror("Sign In", str(exc)[:260])
            return
        if not config:
            if account.lower() == "demo" and password == "demo":
                self.write_cloud_session(account, "local-demo")
                self.set_cloud_signed_in("Demo sign-in accepted locally. Open the online application and verify provider rows before model use.")
                self.status_var.set("Demo account accepted. Provider keys are managed inside each version.")
                return
            self.set_cloud_sign_in_failed("Input error: demo review login is demo / demo when cloud restore is not configured.")
            messagebox.showerror("Sign In", "Cloud restore is not configured. Use demo / demo for local competition review.")
            return
        self.set_cloud_status("Signing in...", "#93c5fd")
        self.cloud_signin_button.configure(text="Signing in...", state=tk.DISABLED, bg="#4b5563")
        self.status_var.set("Signing in and restoring provider settings...")

        def work():
            try:
                restored = self.restore_provider_config_from_cloud(account, password, config)

                def done():
                    self.write_cloud_session(account, "firebase-firestore")
                    if restored:
                        PROVIDER_CONFIG.write_text(json.dumps(restored, ensure_ascii=False, indent=2), encoding="utf-8")
                        self.set_cloud_signed_in("Provider settings restored. Open the online application and click Verify before use.")
                        self.status_var.set("Provider settings restored as inactive rows; Verify is still required.")
                    else:
                        self.set_cloud_signed_in("Sign-in OK. No provider settings were stored for this account.")
                        self.status_var.set("Sign-in OK. Configure providers inside the online application.")

                self.root.after(0, done)
            except Exception as exc:
                self.root.after(0, lambda: (self.set_cloud_sign_in_failed("Sign-in failed: check account, password, or cloud service."), messagebox.showerror("Sign In Failed", str(exc)[:260])))

        threading.Thread(target=work, daemon=True).start()

    def sign_in_with_google(self):
        try:
            config = self.load_admin_cloud_config()
        except Exception as exc:
            self.set_cloud_sign_in_failed("Google sign-in is unavailable: cloud configuration is invalid.")
            messagebox.showerror("Google Sign-In", str(exc)[:300])
            return
        required = {
            "project_id": str((config or {}).get("project_id") or "").strip(),
            "web_api_key": str((config or {}).get("web_api_key") or "").strip(),
            "auth_domain": str((config or {}).get("auth_domain") or "").strip(),
            "app_id": str((config or {}).get("app_id") or "").strip(),
        }
        if not config or not all(required.values()):
            messagebox.showinfo(
                "Firebase Google Sign-In",
                "The Google sign-in interface is installed but not active yet.\n\n"
                "Activation requires a Firebase web application configuration with:\n"
                "- project_id\n"
                "- web_api_key\n"
                "- auth_domain\n"
                "- app_id\n\n"
                "The competition demo can continue to use demo / demo until the "
                "Firebase project is connected.",
            )
            return
        if not FIREBASE_GOOGLE_LOGIN_BRIDGE.exists():
            messagebox.showerror(
                "Google Sign-In",
                f"Google sign-in bridge not found:\n{FIREBASE_GOOGLE_LOGIN_BRIDGE}",
            )
            return

        self.set_cloud_status("Opening secure Google sign-in...", "#93c5fd")
        self.cloud_account_entry.configure(state=tk.DISABLED)
        self.cloud_password_entry.configure(state=tk.DISABLED)
        self.cloud_signin_button.configure(state=tk.DISABLED, bg="#4b5563")
        self.cloud_google_button.configure(text="Waiting for Google...", state=tk.DISABLED, bg="#4b5563", fg="#d1d5db")
        self.status_var.set("Waiting for Firebase Authentication and Firestore provider restore...")

        def work():
            try:
                python_exe = Path(sys.executable)
                if python_exe.name.lower() == "pythonw.exe":
                    console_python = python_exe.with_name("python.exe")
                    if console_python.exists():
                        python_exe = console_python
                completed = subprocess.run(
                    [
                        str(python_exe),
                        str(FIREBASE_GOOGLE_LOGIN_BRIDGE),
                        "--config",
                        str(ADMIN_CLOUD_CONFIG),
                    ],
                    cwd=str(HERE),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=270,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                output_lines = [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]
                if not output_lines:
                    raise RuntimeError((completed.stderr or "Google sign-in returned no result.")[:500])
                result = json.loads(output_lines[-1])
                if not result.get("ok"):
                    raise RuntimeError(str(result.get("error") or "Google sign-in failed."))
                user_id = str(result.get("uid") or "").strip()
                token = str(result.get("id_token") or "").strip()
                refresh_token = str(result.get("refresh_token") or "").strip()
                email = str(result.get("email") or "").strip()
                if not user_id or not token:
                    raise RuntimeError("Firebase did not return a usable user identity.")
                restored = self.restore_provider_config_from_token(user_id, token, config)

                def done():
                    self.cloud_backend.store_firebase_session(
                        user_id,
                        email or user_id,
                        token,
                        refresh_token,
                        result.get("expires_in") or 3600,
                    )
                    self.cloud_backend.run_async(
                        self.cloud_backend.record_event,
                        "firebase_google_sign_in",
                        {"source": "launcher"},
                    )
                    if restored:
                        PROVIDER_CONFIG.write_text(
                            json.dumps(restored, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                        self.set_cloud_signed_in(
                            f"Google sign-in complete for {email or user_id}. Provider settings restored; Verify is still required."
                        )
                        self.status_var.set("Firebase identity verified and Firestore provider settings restored.")
                    else:
                        self.set_cloud_signed_in(
                            f"Google sign-in complete for {email or user_id}. No saved provider settings were found."
                        )
                        self.status_var.set("Firebase identity verified. Configure providers inside the online application.")

                self.root.after(0, done)
            except Exception as exc:
                error_text = str(exc)
                self.root.after(
                    0,
                    lambda text=error_text: (
                        self.set_cloud_sign_in_failed("Google sign-in failed or was cancelled."),
                        messagebox.showerror("Google Sign-In Failed", text[:500]),
                    ),
                )

        threading.Thread(target=work, daemon=True).start()

    def restore_provider_config_from_cloud(self, account, password, config):
        import requests

        project_id = str(config.get("project_id") or "").strip()
        web_api_key = str(config.get("web_api_key") or "").strip()
        if not project_id or not web_api_key:
            raise RuntimeError("Admin cloud config must include project_id and web_api_key.")
        email = self.account_to_email(account, config)
        auth_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={web_api_key}"
        auth = requests.post(
            auth_url,
            json={"email": email, "password": password, "returnSecureToken": True},
            timeout=20,
        )
        if auth.status_code >= 400:
            raise RuntimeError(f"Authentication failed: HTTP {auth.status_code}")
        auth_data = auth.json()
        user_id = auth_data.get("localId")
        token = auth_data.get("idToken")
        if not user_id or not token:
            raise RuntimeError("Authentication response did not include user identity.")
        return self.restore_provider_config_from_token(user_id, token, config)

    def restore_provider_config_from_token(self, user_id, token, config):
        import requests

        project_id = str(config.get("project_id") or "").strip()
        if not project_id:
            raise RuntimeError("Admin cloud config must include project_id.")
        doc_template = str(config.get("provider_document") or "users/{uid}/providerProfiles/default")
        doc_path = doc_template.format(uid=user_id, account=user_id)
        doc_url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents/{doc_path}"
        doc = requests.get(doc_url, headers={"Authorization": f"Bearer {token}"}, timeout=20)
        if doc.status_code == 404:
            return None
        if doc.status_code >= 400:
            raise RuntimeError(f"Provider restore failed: HTTP {doc.status_code}")
        fields = doc.json().get("fields", {})
        raw = fields.get("configJson", {}).get("stringValue", "")
        if not raw:
            return None
        return self.mark_provider_config_requires_verify(json.loads(raw))

    def mark_provider_config_requires_verify(self, data):
        restored = dict(data or {})
        restored["restored_requires_verify"] = True
        restored["restored_at"] = datetime.now().isoformat()
        rows = []
        for item in restored.get("providers", []) or []:
            row = dict(item or {})
            row["verified"] = False
            row["restored_requires_verify"] = True
            rows.append(row)
        restored["providers"] = rows
        return restored

    def build_version_card(self, parent, column, title, subtitle, color, bullets, button_text, command):
        card = tk.Frame(parent, bg=self.C["panel"], padx=18, pady=18)
        card.grid(row=0, column=column, sticky="nsew", padx=(0, 9) if column == 0 else (9, 0), pady=(0, 8))
        tk.Label(card, text=title, bg=color, fg="white", font=("Microsoft YaHei UI", 18, "bold"), pady=10).pack(fill=tk.X)
        tk.Label(
            card,
            text=subtitle,
            bg=self.C["panel"],
            fg=self.C["gold"],
            font=("Microsoft YaHei UI", 12, "bold"),
            wraplength=400,
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(16, 10))
        for bullet in bullets:
            tk.Label(
                card,
                text=f"- {bullet}",
                bg=self.C["panel"],
                fg=self.C["text"],
                font=("Microsoft YaHei UI", 10),
                wraplength=410,
                justify=tk.LEFT,
            ).pack(anchor="w", pady=4)
        tk.Frame(card, bg=self.C["panel"]).pack(fill=tk.BOTH, expand=True)
        self.make_button(card, button_text, command, color, padx=20, pady=14, font=("Microsoft YaHei UI", 14, "bold")).pack(
            fill=tk.X, pady=(12, 0)
        )

    def make_button(self, parent, text, command, color, fg="white", padx=10, pady=4, font=None):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=color,
            fg=fg,
            activebackground=self.lighten(color),
            activeforeground=fg,
            relief=tk.RAISED,
            bd=3,
            overrelief=tk.SUNKEN,
            padx=padx,
            pady=pady,
            cursor="hand2",
            font=font or ("Microsoft YaHei UI", 10, "bold"),
            highlightthickness=1,
            highlightbackground="#0f172a",
        )

    def lighten(self, color):
        color = str(color or "#333333").lstrip("#")
        if len(color) != 6:
            return "#444444"
        r = min(255, int(color[0:2], 16) + 24)
        g = min(255, int(color[2:4], 16) + 24)
        b = min(255, int(color[4:6], 16) + 24)
        return f"#{r:02x}{g:02x}{b:02x}"

    def launch_app(self, script_path, label):
        if not script_path.exists():
            messagebox.showerror("Launch Failed", f"Program not found:\n{script_path}")
            return
        try:
            subprocess.Popen([self.find_pythonw(prefer_dnd=(script_path == ONLINE_APP)), str(script_path)], cwd=str(HERE))
            self.status_var.set(f"Launched {label}.")
        except Exception as exc:
            messagebox.showerror("Launch Failed", str(exc))

    def find_pythonw(self, prefer_dnd=False):
        if prefer_dnd:
            dnd_python = Path(r"C:\Program Files\Python310\pythonw.exe")
            if dnd_python.exists():
                return str(dnd_python)
        for candidate in [
            Path(r"C:\ProgramData\anaconda3\pythonw.exe"),
            Path(sys.executable).with_name("pythonw.exe"),
        ]:
            if candidate.exists():
                return str(candidate)
        return sys.executable or "python"

    def open_folder(self):
        try:
            os.startfile(str(HERE))
        except Exception as exc:
            messagebox.showerror("Open Failed", str(exc))

    def show_startup_disclaimer(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Professional Use Notice")
        dialog.configure(bg="#111827")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.lift()
        dialog.focus_force()

        shell = tk.Frame(dialog, bg="#111827", padx=24, pady=22)
        shell.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            shell,
            text="Professional Use Notice",
            bg="#111827",
            fg=self.C["gold"],
            font=("Microsoft YaHei UI", 17, "bold"),
        ).pack(anchor="w")
        tk.Label(
            shell,
            text="AI Lawyer Opposition is a legal-preparation assistant. It supports review, argument drafting, and weakness scanning; it does not replace professional judgment.",
            bg="#111827",
            fg="#cbd5e1",
            wraplength=620,
            justify=tk.LEFT,
            font=("Microsoft YaHei UI", 10),
        ).pack(anchor="w", pady=(6, 18))

        body = tk.Frame(shell, bg="#1f2937", padx=16, pady=14, highlightthickness=1, highlightbackground="#374151")
        body.pack(fill=tk.X)
        notices = [
            ("Role of the software", "Outputs are reference materials for lawyers, legal teams, or informed users preparing questions and arguments."),
            ("Required review", "Case analysis, legal authorities, citations, tactics, translations, and final wording must be checked by a qualified person before use."),
            ("Confidential matters", "The Online Version may send case content to configured model providers after API verification. Enable redaction or use a separately distributed private/offline edition when confidentiality is critical."),
        ]
        for title, text in notices:
            item = tk.Frame(body, bg="#1f2937")
            item.pack(fill=tk.X, pady=(0, 10))
            tk.Label(
                item,
                text=title,
                bg="#1f2937",
                fg="#f8fafc",
                font=("Microsoft YaHei UI", 10, "bold"),
            ).pack(anchor="w")
            tk.Label(
                item,
                text=text,
                bg="#1f2937",
                fg="#cbd5e1",
                wraplength=600,
                justify=tk.LEFT,
                font=("Microsoft YaHei UI", 9),
            ).pack(anchor="w", pady=(2, 0))

        actions = tk.Frame(shell, bg="#111827")
        actions.pack(fill=tk.X, pady=(18, 0))
        tk.Button(
            actions,
            text="I understand",
            command=dialog.destroy,
            bg="#2563eb",
            fg="#ffffff",
            activebackground="#3b82f6",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            padx=22,
            pady=8,
            cursor="hand2",
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(side=tk.RIGHT)

        dialog.update_idletasks()
        width = dialog.winfo_reqwidth()
        height = dialog.winfo_reqheight()
        x = self.root.winfo_screenwidth() // 2 - width // 2
        y = self.root.winfo_screenheight() // 2 - height // 2
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        self.root.wait_window(dialog)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    StrikeOverLauncherEN().run()
