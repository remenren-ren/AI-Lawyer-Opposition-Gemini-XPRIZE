import json
import hashlib
import html
import os
import re
import shutil
import threading
import tkinter as tk
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from tkinter import filedialog, messagebox

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:
    DND_FILES = None
    TkinterDnD = None

from pinch_payment_backend import PinchAPIError, PinchSandboxClient, load_config, save_config


class PinchPaymentCentre:
    BG = "#151625"
    PANEL = "#24263a"
    PANEL_ALT = "#1c2435"
    INPUT = "#101827"
    TEXT = "#f8fafc"
    MUTED = "#b7c0d8"
    GOLD = "#ffd84d"
    PINCH = "#ef4b7b"
    TEAL = "#22c7c9"
    GREEN = "#22c55e"
    BLUE = "#2563a8"
    PURPLE = "#7257d9"
    WARNING = "#4b2a19"

    REPORT_STAGES = (
        (
            "intent",
            "1. Intent deposit",
            "Client confirms genuine interest and unlocks the initial case-analysis report.",
            "100.00",
            "Initial Case Analysis Report",
        ),
        (
            "ai_reports",
            "2. AI report package",
            "Paid after the initial analysis is ready; unlocks weakness scans and opposition results.",
            "300.00",
            "Weakness Scan and Opposition Results",
        ),
        (
            "lawyer_review",
            "3. Lawyer review",
            "Activates human lawyer review, correction, professional judgement, and a reviewed report.",
            "750.00",
            "Lawyer-Reviewed Analysis Report",
        ),
        (
            "engagement",
            "4. Formal engagement",
            "Optional final payment if the client instructs the participating law firm to continue.",
            "1500.00",
            "Formal Lawyer Engagement and Matter Handover",
        ),
    )

    def __init__(self):
        self.root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
        self.root.title("AI Lawyer Opposition - Pinch Payment Centre (Sandbox)")
        self.root.geometry("1240x900")
        self.root.minsize(1000, 720)
        self.root.configure(bg=self.BG)
        self.client = None
        self.vars = {}
        self.status_var = tk.StringVar(value="Sandbox only: no real money will be collected.")
        self.flow_summary_var = tk.StringVar(value="Law-firm client  ->  Participating law firm")
        self.plan_var = tk.StringVar(value="intent")
        self.active_stage_key = "intent"
        self.stage_amounts = {item[0]: item[3] for item in self.REPORT_STAGES}
        self.paid_stage_keys = set()
        self.completed_stage_keys = set()
        self.stage_widgets = {}
        self.latest_client_portal = ""
        self.report_status_var = tk.StringVar(value="No report has been registered for this session.")
        self.surcharge_var = tk.BooleanVar(value=False)
        self.secure_link_url = ""
        self.build_ui()
        self.load_local_config()
        self.select_plan("intent")

    def build_ui(self):
        self.build_header()

        body = tk.Frame(self.root, bg=self.BG)
        body.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(body, bg=self.BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(body, orient=tk.VERTICAL, command=canvas.yview)
        self.content = tk.Frame(canvas, bg=self.BG, padx=18, pady=4)
        window_id = canvas.create_window((0, 0), window=self.content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.content.bind(
            "<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.bind(
            "<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width)
        )
        canvas.bind_all(
            "<MouseWheel>", lambda event: canvas.yview_scroll(int(-event.delta / 120), "units")
        )

        self.build_relationship_panel()
        self.build_plan_panel()
        self.build_config_panel()
        self.build_payer_panel()
        self.build_checkout_panel()

        footer = tk.Frame(self.root, bg=self.BG, padx=18, pady=9)
        footer.pack(fill=tk.X)
        tk.Label(
            footer,
            textvariable=self.status_var,
            bg=self.BG,
            fg="#86efac",
            anchor="w",
            font=("Microsoft YaHei UI", 9),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.button(footer, "Pinch API Docs", self.open_docs, self.BLUE).pack(side=tk.RIGHT)

    def build_header(self):
        header = tk.Frame(self.root, bg=self.BG, padx=20, pady=15)
        header.pack(fill=tk.X)
        tk.Label(
            header,
            text="Pinch Payment Centre",
            bg=self.BG,
            fg=self.GOLD,
            font=("Microsoft YaHei UI", 20, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="Report-gated legal-service payments: the client pays the participating law firm at each agreed delivery point.",
            bg=self.BG,
            fg=self.MUTED,
            font=("Microsoft YaHei UI", 10),
        ).pack(anchor="w", pady=(4, 0))

    def section(self, title):
        panel = tk.LabelFrame(
            self.content,
            text=f" {title} ",
            bg=self.PANEL,
            fg=self.GOLD,
            padx=14,
            pady=12,
            font=("Microsoft YaHei UI", 12, "bold"),
        )
        panel.pack(fill=tk.X, pady=(0, 12))
        return panel

    def build_relationship_panel(self):
        panel = self.section("1. Confirm the single funds flow")
        direction = tk.Frame(panel, bg="#10293a", padx=14, pady=12)
        direction.pack(fill=tk.X)
        tk.Label(
            direction,
            text="CLIENT LEGAL-SERVICE PAYMENT",
            bg="#10293a",
            fg="#7dd3fc",
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            direction,
            textvariable=self.flow_summary_var,
            bg="#10293a",
            fg=self.TEXT,
            font=("Microsoft YaHei UI", 12, "bold"),
        ).pack(anchor="w", pady=(3, 0))
        tk.Label(
            direction,
            text=(
                "The software does not collect or resell matter data and does not receive the legal-service fee. "
                "Production settlement requires the selected firm's own Pinch merchant account or an approved managed-merchant route."
            ),
            bg="#10293a",
            fg=self.MUTED,
            wraplength=1120,
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(4, 0))

    def build_plan_panel(self):
        panel = self.section("2. Sequential payment and report-delivery journey")
        tk.Label(
            panel,
            text=(
                "There is nothing to select. Payment unlocks the current report drop zone; issuing that report activates the next payment. "
                "The final payment opens formal engagement."
            ),
            bg=self.PANEL,
            fg=self.MUTED,
            wraplength=1120,
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(0, 8))

        cards = tk.Frame(panel, bg=self.PANEL)
        cards.pack(fill=tk.X)
        for index, (key, title, detail, _default, deliverable) in enumerate(self.REPORT_STAGES):
            card = tk.Frame(cards, bg=self.PANEL_ALT, highlightbackground="#465069", highlightthickness=1, padx=9, pady=8)
            card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 5, 0))
            cards.grid_columnconfigure(index, weight=1, uniform="plan")
            tk.Label(
                card,
                text=title,
                bg=self.PANEL_ALT,
                fg=self.GOLD,
                font=("Microsoft YaHei UI", 9, "bold"),
                wraplength=235,
                justify=tk.LEFT,
            ).pack(anchor="w")
            tk.Label(card, text=detail, bg=self.PANEL_ALT, fg=self.MUTED, wraplength=235, justify=tk.LEFT).pack(anchor="w", pady=(5, 0))
            tk.Label(card, text=f"Unlocks: {deliverable}", bg=self.PANEL_ALT, fg=self.TEAL, wraplength=235, justify=tk.LEFT, font=("Microsoft YaHei UI", 8, "bold")).pack(anchor="w", pady=(6, 0))
            status_label = tk.Label(
                card,
                text="LOCKED",
                bg="#263247",
                fg=self.MUTED,
                padx=7,
                pady=4,
                font=("Microsoft YaHei UI", 8, "bold"),
            )
            status_label.pack(anchor="w", pady=(8, 0))
            self.stage_widgets[key] = {"card": card, "status": status_label}

        controls = tk.Frame(panel, bg=self.PANEL)
        controls.pack(fill=tk.X, pady=(10, 8))
        self.entry(controls, "Matter/reference ID (no case text)", "matter_ref", 28)
        self.entry(controls, "Current milestone amount (AUD)", "plan_amount", 21)
        self.entry(controls, "Customer-facing deliverable", "description", 52)
        self.button(controls, "Update Milestones", self.refresh_schedule, self.BLUE).pack(side=tk.LEFT, padx=(8, 0), pady=(18, 0))

        lower = tk.Frame(panel, bg=self.PANEL)
        lower.pack(fill=tk.X)
        preview_box = tk.Frame(lower, bg=self.INPUT, padx=12, pady=9)
        preview_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        tk.Label(preview_box, text="REPORT DELIVERY AND PAYMENT MILESTONES", bg=self.INPUT, fg=self.TEAL, font=("Microsoft YaHei UI", 9, "bold")).pack(anchor="w")
        self.schedule_text = tk.Text(
            preview_box,
            height=7,
            bg=self.INPUT,
            fg=self.TEXT,
            relief=tk.FLAT,
            wrap=tk.WORD,
            font=("Consolas", 9),
        )
        self.schedule_text.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        self.schedule_text.configure(state=tk.DISABLED)

        boundary = tk.Frame(lower, bg="#382817", padx=12, pady=9, width=410)
        boundary.pack(side=tk.RIGHT, fill=tk.Y)
        tk.Label(boundary, text="PAYMENT-GATED REPORT DROP ZONE", bg="#382817", fg="#fbbf24", font=("Microsoft YaHei UI", 9, "bold")).pack(anchor="w")
        tk.Label(
            boundary,
            text=(
                "The report area remains locked until Pinch confirms the current payment. After the law firm drops the issued report, "
                "a local client-readable copy is created and the next payment becomes due."
            ),
            bg="#382817",
            fg=self.TEXT,
            wraplength=350,
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(5, 6))
        self.report_drop_zone = tk.Label(
            boundary,
            text="LOCKED - CURRENT PAYMENT REQUIRED",
            bg="#2d3345",
            fg="#94a3b8",
            relief=tk.GROOVE,
            bd=2,
            padx=10,
            pady=16,
            cursor="hand2",
            wraplength=350,
            justify=tk.CENTER,
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        self.report_drop_zone.pack(fill=tk.X, pady=(9, 0))
        self.report_drop_zone.bind("<Button-1>", lambda _event: self.register_report_and_request_next_payment())
        if DND_FILES:
            try:
                self.report_drop_zone.drop_target_register(DND_FILES)
                self.report_drop_zone.dnd_bind("<<Drop>>", self.on_report_drop)
            except Exception:
                pass
        action_row = tk.Frame(boundary, bg="#382817")
        action_row.pack(fill=tk.X, pady=(8, 0))
        self.demo_paid_button = self.button(action_row, "Sandbox: Mark Payment Paid", self.demo_mark_current_payment_paid, self.PURPLE)
        self.demo_paid_button.pack(side=tk.LEFT)
        self.open_report_button = self.button(action_row, "Open Client Report", self.open_client_report, self.BLUE)
        self.open_report_button.pack(side=tk.LEFT, padx=(7, 0))
        self.open_report_button.configure(state=tk.DISABLED)
        tk.Label(
            boundary,
            textvariable=self.report_status_var,
            bg="#382817",
            fg="#fde68a",
            wraplength=350,
            justify=tk.LEFT,
            font=("Microsoft YaHei UI", 8),
        ).pack(anchor="w", pady=(7, 0))

    def build_config_panel(self):
        panel = self.section("3. Pinch sandbox connection")
        row = tk.Frame(panel, bg=self.PANEL)
        row.pack(fill=tk.X)
        self.entry(row, "Application ID", "application_id", 31)
        self.entry(row, "Secret Key", "secret_key", 31, show="*")
        self.entry(row, "Publishable Key", "publishable_key", 31)
        self.button(row, "Save + Test", self.test_authentication, self.PINCH).pack(side=tk.LEFT, padx=(8, 0), pady=(18, 0))
        tk.Label(
            panel,
            text="Development credentials stay in pinch_sandbox.local.json on this computer and are excluded from source control.",
            bg=self.PANEL,
            fg=self.MUTED,
        ).pack(anchor="w", pady=(8, 0))

    def build_payer_panel(self):
        panel = self.section("4. Create the sandbox payer")
        tk.Label(
            panel,
            text="Use fictional details only. In production the payer is the participating law firm's client.",
            bg=self.PANEL,
            fg=self.MUTED,
        ).pack(anchor="w", pady=(0, 7))
        row = tk.Frame(panel, bg=self.PANEL)
        row.pack(fill=tk.X)
        self.entry(row, "First name", "first_name", 18)
        self.entry(row, "Last name", "last_name", 18)
        self.entry(row, "Email", "email", 28)
        self.entry(row, "Mobile", "mobile", 18)
        self.button(row, "Create Sandbox Payer", self.create_payer, "#0f766e").pack(side=tk.LEFT, padx=(8, 0), pady=(18, 0))

    def build_checkout_panel(self):
        panel = self.section("5. Secure Pinch-hosted checkout")
        row = tk.Frame(panel, bg=self.PANEL)
        row.pack(fill=tk.X)
        self.entry(row, "Payer ID", "payer_id", 24)
        self.entry(row, "Currently due (AUD)", "amount", 16)
        self.entry(row, "Payment Link ID", "payment_link_id", 24)
        self.entry(row, "Payment ID", "payment_id", 24)

        options = tk.Frame(panel, bg=self.PANEL)
        options.pack(fill=tk.X, pady=(9, 7))
        tk.Checkbutton(
            options,
            text="Pass eligible Pinch processing fees to payer (sandbox demonstration)",
            variable=self.surcharge_var,
            bg=self.PANEL,
            fg=self.TEXT,
            activebackground=self.PANEL,
            activeforeground=self.TEXT,
            selectcolor=self.INPUT,
        ).pack(side=tk.LEFT)

        actions = tk.Frame(panel, bg=self.PANEL)
        actions.pack(fill=tk.X)
        self.button(actions, "Create + Open Secure Payment Link", self.create_and_open_payment_link, self.PINCH).pack(side=tk.LEFT)
        self.button(actions, "Open Existing Link", self.open_payment_link, self.BLUE).pack(side=tk.LEFT, padx=(8, 0))
        self.button(actions, "Refresh Link Status", self.refresh_payment_link, self.BLUE).pack(side=tk.LEFT, padx=(8, 0))
        self.button(actions, "Refresh Payment Status", self.refresh_payment, self.PURPLE).pack(side=tk.LEFT, padx=(8, 0))

        safety = tk.Frame(panel, bg="#3b2430", padx=12, pady=9)
        safety.pack(fill=tk.X, pady=(10, 8))
        tk.Label(
            safety,
            text=(
                "Security: card and bank-account details are entered only on Pinch's hosted sandbox page. "
                "This desktop application receives IDs and status records, not raw payment credentials."
            ),
            bg="#3b2430",
            fg="#fecdd3",
            font=("Microsoft YaHei UI", 9, "bold"),
            wraplength=1120,
            justify=tk.LEFT,
        ).pack(anchor="w")

        tk.Label(panel, text="Sandbox API result", bg=self.PANEL, fg=self.MUTED).pack(anchor="w", pady=(4, 3))
        self.output = tk.Text(
            panel,
            height=11,
            bg="#0d1523",
            fg=self.TEXT,
            insertbackground=self.TEXT,
            relief=tk.FLAT,
            wrap=tk.WORD,
            font=("Consolas", 9),
        )
        self.output.pack(fill=tk.BOTH, expand=True)

    def entry(self, parent, label, key, width, show=None):
        group = tk.Frame(parent, bg=self.PANEL)
        group.pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(group, text=label, bg=self.PANEL, fg=self.MUTED, font=("Microsoft YaHei UI", 9)).pack(anchor="w")
        var = self.vars.setdefault(key, tk.StringVar())
        widget = tk.Entry(
            group,
            textvariable=var,
            width=width,
            show=show or "",
            bg=self.INPUT,
            fg=self.TEXT,
            insertbackground=self.TEXT,
            relief=tk.FLAT,
            bd=5,
        )
        widget.pack()
        return widget

    def button(self, parent, text, command, color):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=color,
            fg="white",
            activebackground=color,
            activeforeground="white",
            relief=tk.RAISED,
            bd=2,
            padx=12,
            pady=6,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9, "bold"),
        )

    def select_plan(self, plan_key):
        previous = self.active_stage_key
        if previous and "plan_amount" in self.vars:
            current_text = self.vars["plan_amount"].get().strip()
            if current_text:
                try:
                    self.stage_amounts[previous] = f"{self.money(current_text):.2f}"
                except Exception:
                    pass
        self.active_stage_key = plan_key
        self.plan_var.set(plan_key)
        option = next(item for item in self.REPORT_STAGES if item[0] == plan_key)
        self.vars.setdefault("plan_amount", tk.StringVar()).set(self.stage_amounts[plan_key])
        self.vars.setdefault("description", tk.StringVar()).set(option[4])
        self.refresh_schedule()

    def stage_status(self, stage_key):
        if stage_key in self.completed_stage_keys:
            return "REPORT DELIVERED", self.GREEN
        if stage_key in self.paid_stage_keys:
            if stage_key == "engagement":
                return "PAID - FORMAL ENGAGEMENT ACTIVE", self.GREEN
            return "PAID - REPORT DROP UNLOCKED", self.TEAL
        if stage_key == self.active_stage_key:
            return "PAYMENT DUE", self.PINCH
        return "LOCKED", "#475569"

    def update_stage_ui(self):
        for key, widgets in self.stage_widgets.items():
            status_text, color = self.stage_status(key)
            active = key == self.active_stage_key
            widgets["status"].configure(text=status_text, bg=color, fg="white")
            widgets["card"].configure(highlightbackground=self.GOLD if active else "#465069", highlightthickness=2 if active else 1)
        current_key = self.active_stage_key
        if current_key == "engagement":
            if current_key in self.paid_stage_keys:
                drop_text = "FORMAL ENGAGEMENT ACTIVE\nNo further report payment stage"
                bg, fg = "#14532d", "#bbf7d0"
            else:
                drop_text = "FINAL PAYMENT DUE\nReport upload is not required for formal engagement"
                bg, fg = "#3b2430", "#fecdd3"
        elif current_key in self.paid_stage_keys:
            deliverable = self.report_stage_details(current_key)[4]
            drop_text = f"DROP OR CLICK TO ADD THE ISSUED REPORT\n{deliverable}"
            bg, fg = "#0f766e", "white"
        else:
            drop_text = "LOCKED - CURRENT PAYMENT REQUIRED\nReport upload opens after payment is confirmed"
            bg, fg = "#2d3345", "#94a3b8"
        self.report_drop_zone.configure(text=drop_text, bg=bg, fg=fg)

    def money(self, value):
        try:
            amount = Decimal(str(value).strip())
        except InvalidOperation as exc:
            raise PinchAPIError("Amount must be a number such as 250.00.") from exc
        if amount <= 0:
            raise PinchAPIError("Amount must be greater than zero.")
        return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def schedule(self):
        current = self.active_stage_key
        current_amount = self.money(self.vars["plan_amount"].get())
        self.stage_amounts[current] = f"{current_amount:.2f}"
        rows = []
        for key, title, _detail, _default, deliverable in self.REPORT_STAGES:
            amount = self.money(self.stage_amounts[key])
            rows.append((key, title, deliverable, amount, key != "intent"))
        return rows

    def refresh_schedule(self):
        try:
            rows = self.schedule()
        except Exception as exc:
            self.show_error(str(exc))
            return
        lines = []
        for key, title, deliverable, amount, requires_firm in rows:
            marker = self.stage_status(key)[0].lower()
            current = "  < CURRENTLY DUE" if key == self.plan_var.get() else ""
            lines.append(f"{title}: AUD {amount:,.2f} | unlocks {deliverable} | {marker}{current}")
        total = sum((amount for _key, _title, _deliverable, amount, _confirm in rows), Decimal("0.00"))
        lines.append(f"\nConfigured journey total: AUD {total:,.2f} (final engagement remains optional)")
        self.schedule_text.configure(state=tk.NORMAL)
        self.schedule_text.delete("1.0", tk.END)
        self.schedule_text.insert("1.0", "\n".join(lines))
        self.schedule_text.configure(state=tk.DISABLED)
        selected_amount = next(amount for key, _title, _deliverable, amount, _confirm in rows if key == self.plan_var.get())
        self.vars["amount"].set(f"{selected_amount:.2f}")
        self.update_stage_ui()

    def report_log_path(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "report_delivery_log.local.jsonl")

    def next_stage_key(self, stage_key):
        keys = [item[0] for item in self.REPORT_STAGES]
        index = keys.index(stage_key)
        return keys[index + 1] if index + 1 < len(keys) else ""

    def report_stage_details(self, stage_key):
        return next(item for item in self.REPORT_STAGES if item[0] == stage_key)

    def previous_stage_key(self, stage_key):
        keys = [item[0] for item in self.REPORT_STAGES]
        index = keys.index(stage_key)
        return keys[index - 1] if index > 0 else ""

    def client_portal_copy(self, report_path, stage_key, deliverable):
        matter_ref = self.vars["matter_ref"].get().strip() or "unreferenced-matter"
        safe_ref = re.sub(r"[^A-Za-z0-9._-]+", "_", matter_ref).strip("._") or "matter"
        portal_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "client_reports.local",
            safe_ref,
            stage_key,
        )
        os.makedirs(portal_dir, exist_ok=True)
        extension = os.path.splitext(report_path)[1].lower()
        client_report_path = os.path.join(portal_dir, f"issued_report{extension}")
        shutil.copy2(report_path, client_report_path)
        portal_path = os.path.join(portal_dir, "index.html")
        page = f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>{html.escape(deliverable)}</title>
<style>body{{font-family:Arial,sans-serif;background:#0f172a;color:#e2e8f0;margin:0;padding:40px}}main{{max-width:760px;margin:auto;background:#1e293b;padding:32px;border-radius:14px}}h1{{color:#facc15}}a{{display:inline-block;background:#2563eb;color:white;text-decoration:none;padding:12px 18px;border-radius:8px;font-weight:bold}}.meta{{color:#94a3b8}}</style></head>
<body><main><div class=\"meta\">Matter reference: {html.escape(matter_ref)}</div><h1>{html.escape(deliverable)}</h1>
<p>This report has been issued by the participating law firm and is available for client review.</p>
<p><a href=\"issued_report{html.escape(extension)}\">Open report</a></p>
<p class=\"meta\">Local competition demonstration. Production access must use the law firm's authenticated client portal.</p>
</main></body></html>"""
        with open(portal_path, "w", encoding="utf-8") as handle:
            handle.write(page)
        return client_report_path, portal_path

    def register_report_artifact(self, report_path, stage_key=None):
        stage_key = stage_key or self.plan_var.get()
        if stage_key == "engagement":
            raise PinchAPIError("Formal engagement is the final payment stage and does not accept another report here.")
        if stage_key not in self.paid_stage_keys:
            raise PinchAPIError("The current Pinch payment must be confirmed before the law firm can upload this report.")
        if not report_path or not os.path.isfile(report_path):
            raise PinchAPIError("Select an existing report file.")
        extension = os.path.splitext(report_path)[1].lower()
        if extension not in {".pdf", ".doc", ".docx", ".html", ".htm", ".txt", ".json"}:
            raise PinchAPIError("Select a PDF, Word, HTML, TXT, or JSON report file.")
        digest = hashlib.sha256()
        with open(report_path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        _key, title, _detail, _default, deliverable = self.report_stage_details(stage_key)
        client_report_path, portal_path = self.client_portal_copy(report_path, stage_key, deliverable)
        event = {
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "matter_reference": self.vars["matter_ref"].get().strip(),
            "completed_milestone": stage_key,
            "milestone_title": title,
            "deliverable": deliverable,
            "local_report_path": os.path.abspath(report_path),
            "client_report_path": client_report_path,
            "client_portal_path": portal_path,
            "file_extension": extension,
            "file_size_bytes": os.path.getsize(report_path),
            "sha256": digest.hexdigest(),
            "next_payment_milestone": self.next_stage_key(stage_key) or None,
            "pinch_report_content_sent": False,
        }
        with open(self.report_log_path(), "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        self.completed_stage_keys.add(stage_key)
        return event

    def register_report_and_request_next_payment(self):
        completed_key = self.plan_var.get()
        if completed_key == "engagement":
            self.show_error("The final engagement stage does not require another report upload.")
            return
        if completed_key not in self.paid_stage_keys:
            self.show_error("Report upload is locked until the current Pinch payment is confirmed.")
            return
        _key, completed_title, _detail, _default, deliverable = self.report_stage_details(completed_key)
        report_path = filedialog.askopenfilename(
            title=f"Select issued report: {deliverable}",
            filetypes=[
                ("Report files", "*.pdf *.doc *.docx *.html *.htm *.txt *.json"),
                ("All files", "*.*"),
            ],
        )
        if not report_path:
            return
        self.process_issued_report(report_path)

    def on_report_drop(self, event):
        try:
            paths = list(self.root.tk.splitlist(event.data))
        except Exception:
            paths = [str(getattr(event, "data", "")).strip().strip("{}")]
        if not paths:
            return
        self.process_issued_report(paths[0])

    def process_issued_report(self, report_path):
        completed_key = self.plan_var.get()
        if completed_key == "engagement":
            self.show_error("The final engagement stage does not accept another report.")
            return
        if completed_key not in self.paid_stage_keys:
            self.show_error("Report upload is locked until the current Pinch payment is confirmed.")
            return
        _key, completed_title, _detail, _default, deliverable = self.report_stage_details(completed_key)
        next_key = self.next_stage_key(completed_key)
        next_text = self.report_stage_details(next_key)[1] if next_key else "Matter journey complete"
        if not messagebox.askyesno(
            "Confirm Report Issued",
            (
                f"Current milestone: {completed_title}\n"
                f"Register as issued: {deliverable}\n"
                f"Next step: {next_text}\n\n"
                "A local client-readable copy, file fingerprint, and delivery record will be stored. "
                "The report content will not be sent to Pinch.\n\n"
                "Confirm delivery and prepare the next payment request?"
            ),
        ):
            return
        try:
            event = self.register_report_artifact(report_path, completed_key)
        except Exception as exc:
            self.show_error(str(exc))
            return
        self.report_status_var.set(
            f"Issued: {deliverable} | local SHA-256 {event['sha256'][:12]}..."
        )
        self.latest_client_portal = event["client_portal_path"]
        self.open_report_button.configure(state=tk.NORMAL)
        if not next_key:
            self.refresh_schedule()
            self.show_result("Final service milestone registered. No further payment is due in this journey.", event)
            return
        self.select_plan(next_key)
        self.vars["payment_link_id"].set("")
        self.vars["payment_id"].set("")
        self.secure_link_url = ""
        self.refresh_schedule()
        if not self.vars["payer_id"].get().strip():
            self.show_result(
                "Report registered and the next payment milestone is ready. Create or enter the payer before opening checkout.",
                event,
            )
            return
        self.create_and_open_payment_link()

    def open_client_report(self):
        if not self.latest_client_portal or not os.path.isfile(self.latest_client_portal):
            self.show_error("No client-readable report has been issued in this session.")
            return
        os.startfile(self.latest_client_portal)

    def demo_mark_current_payment_paid(self):
        stage_key = self.active_stage_key
        title = self.report_stage_details(stage_key)[1]
        if stage_key in self.paid_stage_keys:
            self.status_var.set(f"{title} is already marked paid in this sandbox session.")
            return
        if not messagebox.askyesno(
            "Sandbox Payment Simulation",
            f"Mark {title} as paid for the competition demonstration?\n\nThis changes local demo state only and does not move real money.",
        ):
            return
        self.mark_current_payment_paid({"sandbox_demo": True, "status": "paid"})

    def mark_current_payment_paid(self, payload=None):
        stage_key = self.active_stage_key
        self.paid_stage_keys.add(stage_key)
        title = self.report_stage_details(stage_key)[1]
        if stage_key == "engagement":
            status = "Final payment confirmed. Formal lawyer engagement is now active."
        else:
            status = f"{title} confirmed paid. The law firm's report drop zone is now unlocked."
        self.report_status_var.set(status)
        self.refresh_schedule()
        if payload is not None:
            self.show_result(status, payload)

    def payment_is_successful(self, payload):
        success_values = {"paid", "success", "successful", "completed", "complete", "settled", "approved", "processed"}
        success_keys = {"paid", "successful", "succeeded", "completed", "ispaid", "issuccessful"}

        def walk(value, parent_key=""):
            if isinstance(value, dict):
                for key, item in value.items():
                    lowered = str(key).replace("_", "").replace("-", "").lower()
                    if lowered in success_keys and item is True:
                        return True
                    if ("status" in lowered or "state" in lowered) and str(item).strip().lower() in success_values:
                        return True
                    if walk(item, lowered):
                        return True
            elif isinstance(value, list):
                return any(walk(item, parent_key) for item in value)
            return False

        return walk(payload)

    def load_local_config(self):
        try:
            config = load_config()
        except Exception as exc:
            self.status_var.set(f"Local Pinch config could not be read: {exc}")
            return
        for key in ("application_id", "secret_key", "publishable_key"):
            self.vars[key].set(config.get(key, ""))
        self.vars["matter_ref"].set("DEMO-MATTER-001")
        self.vars["first_name"].set("Test")
        self.vars["last_name"].set("Client")
        self.vars["email"].set("test@example.com")

    def get_client(self):
        app_id = self.vars["application_id"].get().strip()
        secret = self.vars["secret_key"].get().strip()
        if not app_id or not secret:
            raise PinchAPIError("Enter the Pinch sandbox Application ID and Secret first.")
        save_config(app_id, secret, self.vars["publishable_key"].get())
        self.client = PinchSandboxClient(app_id, secret)
        return self.client

    def run_async(self, label, operation, success):
        self.status_var.set(label)

        def work():
            try:
                result = operation()
                self.root.after(0, lambda: success(result))
            except Exception as exc:
                self.root.after(0, lambda text=str(exc): self.show_error(text))

        threading.Thread(target=work, daemon=True).start()

    def test_authentication(self):
        try:
            client = self.get_client()
        except Exception as exc:
            self.show_error(str(exc))
            return
        self.run_async(
            "Authenticating with Pinch sandbox...",
            client.authenticate,
            lambda _result: self.show_result(
                "Pinch sandbox authentication succeeded.",
                {"environment": "test", "authenticated": True},
            ),
        )

    def create_payer(self):
        first = self.vars["first_name"].get().strip()
        last = self.vars["last_name"].get().strip()
        email = self.vars["email"].get().strip()
        if not first or not last or "@" not in email:
            self.show_error("First name, last name, and a valid email are required.")
            return
        if not messagebox.askyesno(
            "Create Sandbox Payer",
            "Send this fictional payer name and email to the Pinch sandbox?\n\nDo not use a real identity for the competition demo.",
        ):
            return
        try:
            client = self.get_client()
        except Exception as exc:
            self.show_error(str(exc))
            return
        metadata = json.dumps({"demo": True, "role": "law-firm-client"})
        self.run_async(
            "Creating sandbox payer...",
            lambda: client.create_payer(first, last, email, self.vars["mobile"].get(), metadata),
            self.payer_created,
        )

    def payer_created(self, result):
        payer_id = str(result.get("id") or result.get("Id") or "")
        if payer_id:
            self.vars["payer_id"].set(payer_id)
        self.show_result("Sandbox payer created. Select the currently due report milestone and open secure checkout.", result)

    def amount_cents(self):
        amount = self.money(self.vars["amount"].get())
        return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def payment_metadata(self):
        return json.dumps(
            {
                "product": "AI Lawyer Opposition",
                "environment": "competition-sandbox",
                "funds_flow": "client-to-participating-law-firm",
                "report_milestone": self.plan_var.get(),
                "matter_reference": self.vars["matter_ref"].get().strip(),
            },
            separators=(",", ":"),
        )

    def require_stage_confirmation(self):
        key = self.plan_var.get()
        if key != self.active_stage_key:
            raise PinchAPIError("Only the automatically active payment stage can create a checkout.")
        if key in self.paid_stage_keys:
            raise PinchAPIError("The current payment stage is already marked paid.")
        previous = self.previous_stage_key(key)
        if previous and previous not in self.completed_stage_keys:
            raise PinchAPIError("The preceding report must be issued before the next payment request can be created.")

    def create_and_open_payment_link(self):
        payer_id = self.vars["payer_id"].get().strip()
        if not payer_id:
            self.show_error("Create or enter a sandbox Payer ID first.")
            return
        try:
            self.refresh_schedule()
            self.require_stage_confirmation()
            cents = self.amount_cents()
            client = self.get_client()
        except Exception as exc:
            self.show_error(str(exc))
            return

        description = self.vars["description"].get().strip()
        flow_text = self.flow_summary_var.get()
        stage_title = next(item[1] for item in self.REPORT_STAGES if item[0] == self.plan_var.get())
        if not messagebox.askyesno(
            "Create Secure Sandbox Checkout",
            (
                f"Funds flow: {flow_text}\n"
                f"Milestone: {stage_title}\n"
                f"Currently due: AUD {cents / 100:.2f}\n"
                f"Unlocks: {description}\n\n"
                "Create a Pinch TEST payment link and open Pinch's hosted checkout?\n"
                "No real money will move."
            ),
        ):
            return

        surcharge = ["credit-card", "bank-account"] if self.surcharge_var.get() else []
        return_url = "https://example.com/pinch-sandbox-return"
        self.run_async(
            "Creating secure Pinch sandbox payment link...",
            lambda: client.create_payment_link(
                payer_id,
                cents,
                description,
                return_url,
                ["credit-card", "bank-account"],
                surcharge,
                self.payment_metadata(),
            ),
            self.payment_link_created,
        )

    def payment_link_created(self, result):
        link_id = str(result.get("id") or result.get("Id") or result.get("paymentLinkId") or "")
        url = str(result.get("url") or result.get("Url") or result.get("paymentLinkUrl") or "")
        if link_id:
            self.vars["payment_link_id"].set(link_id)
        self.secure_link_url = url
        self.extract_payment_id(result)
        self.show_result("Secure Pinch sandbox payment link created.", result)
        if url:
            os.startfile(url)
        else:
            messagebox.showwarning("Pinch Sandbox", "The link was created but no checkout URL was returned. Use Refresh Link Status.")

    def open_payment_link(self):
        if not self.secure_link_url:
            self.show_error("No payment-link URL is loaded. Create or refresh a payment link first.")
            return
        os.startfile(self.secure_link_url)

    def refresh_payment_link(self):
        link_id = self.vars["payment_link_id"].get().strip()
        if not link_id:
            self.show_error("Enter a Payment Link ID first.")
            return
        try:
            client = self.get_client()
        except Exception as exc:
            self.show_error(str(exc))
            return
        self.run_async(
            "Refreshing Pinch sandbox payment-link status...",
            lambda: client.get_payment_link(link_id),
            self.payment_link_refreshed,
        )

    def payment_link_refreshed(self, result):
        url = str(result.get("url") or result.get("Url") or self.secure_link_url)
        self.secure_link_url = url
        self.extract_payment_id(result)
        if self.payment_is_successful(result):
            self.mark_current_payment_paid(result)
        else:
            self.show_result("Payment-link status refreshed. Payment is not yet confirmed as paid.", result)

    def extract_payment_id(self, payload):
        candidates = [
            payload.get("paymentId"),
            payload.get("PaymentId"),
            payload.get("payment", {}).get("id") if isinstance(payload.get("payment"), dict) else None,
        ]
        payment_id = next((str(value) for value in candidates if value), "")
        if payment_id:
            self.vars["payment_id"].set(payment_id)

    def refresh_payment(self):
        payment_id = self.vars["payment_id"].get().strip()
        if not payment_id:
            self.show_error("Complete the hosted sandbox checkout or enter a Payment ID first.")
            return
        try:
            client = self.get_client()
        except Exception as exc:
            self.show_error(str(exc))
            return
        self.run_async(
            "Refreshing sandbox payment status...",
            lambda: client.get_payment(payment_id),
            self.payment_status_refreshed,
        )

    def payment_status_refreshed(self, result):
        if self.payment_is_successful(result):
            self.mark_current_payment_paid(result)
        else:
            self.show_result("Payment status refreshed. Report upload remains locked until payment is confirmed.", result)

    def show_result(self, status, payload):
        self.status_var.set(status)
        self.output.delete("1.0", tk.END)
        self.output.insert("1.0", json.dumps(payload, ensure_ascii=False, indent=2))

    def show_error(self, text):
        self.status_var.set("Pinch sandbox action needs attention.")
        messagebox.showerror("Pinch Payment Centre", str(text)[:700])

    def open_docs(self):
        os.startfile("https://docs.getpinch.com.au/docs/payment-links")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    PinchPaymentCentre().run()
