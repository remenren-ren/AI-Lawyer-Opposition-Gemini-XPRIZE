import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from tkinter import Tk, messagebox


HERE = Path(__file__).resolve().parent
PORT = 8770
BASE_URL = f"http://127.0.0.1:{PORT}"


def health_ok():
    try:
        with urllib.request.urlopen(f"{BASE_URL}/health", timeout=1.5) as response:
            return response.status == 200
    except Exception:
        return False


def provider_environment():
    env = os.environ.copy()
    env["NIDO_RECEPTION_DEMO_MODE"] = "true"
    firm_config = HERE / "law_firm_reception.local.json"
    if firm_config.exists():
        try:
            firm_name = str(json.loads(firm_config.read_text(encoding="utf-8-sig")).get("law_firm_name") or "").strip()
            if firm_name:
                env["NIDO_LAW_FIRM_NAME"] = firm_name[:120]
        except Exception:
            pass
    vendor = str(HERE / "cloud_service" / ".vendor")
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = vendor + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
    profile_path = HERE / "api_profiles.local.json"
    if not profile_path.exists():
        return env
    try:
        profiles = json.loads(profile_path.read_text(encoding="utf-8-sig")).get("providers", [])
    except Exception:
        return env
    verified = [item for item in profiles if item.get("verified") and str(item.get("key") or "").strip()]
    preferred = next((item for item in verified if str(item.get("name", "")).lower() == "gemini"), None)
    preferred = preferred or next((item for item in verified if str(item.get("name", "")).lower() == "deepseek"), None)
    if not preferred:
        return env
    name = str(preferred.get("name") or "").lower()
    env["NIDO_INTAKE_PROVIDER_KIND"] = name
    env["NIDO_INTAKE_PROVIDER_KEY"] = str(preferred.get("key") or "")
    env["NIDO_INTAKE_PROVIDER_URL"] = str(preferred.get("base_url") or "")
    env["NIDO_INTAKE_PROVIDER_MODEL"] = str(preferred.get("model") or "")
    return env


def show_error(text):
    root = Tk()
    root.withdraw()
    messagebox.showerror("AI Law Firm Reception", text)
    root.destroy()


def main():
    if not health_ok():
        bundled_python = Path(r"C:\Program Files\Python310\python.exe")
        python_exe = bundled_python if bundled_python.exists() else Path(sys.executable)
        if python_exe.name.lower() == "pythonw.exe":
            console_python = python_exe.with_name("python.exe")
            if console_python.exists():
                python_exe = console_python
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(
            [str(python_exe), "-m", "uvicorn", "cloud_service.app:app", "--host", "127.0.0.1", "--port", str(PORT)],
            cwd=str(HERE),
            env=provider_environment(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        for _ in range(40):
            if health_ok():
                break
            time.sleep(0.25)
    if not health_ok():
        show_error("The Gemini reception service did not start. Check the Cloud service dependencies and port 8770.")
        return 1
    webbrowser.open(f"{BASE_URL}/client")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
