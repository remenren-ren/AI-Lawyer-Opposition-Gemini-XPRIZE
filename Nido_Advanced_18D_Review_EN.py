import datetime as dt
import json
import os
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

from Nido_StrikeOver_Online_EN import (
    ALL_DIMENSIONS,
    DIMENSION_DESC_EN,
    DIMENSION_LABELS_EN,
    LLMClient,
    is_non_material_weakness_display_record,
)
from build_18_report_delivery import build_report
from experiment_18_independent_reviews import extraction_prompt, markdown_report, prompt_for, safe_name
from google_cloud_backend import get_backend
from standard_report_contract import (
    build_standard_report,
    provider_runs_from_records,
    write_standard_companions,
)


HERE = Path(__file__).resolve().parent


def show_scan_mode_dialog(parent, standard_command, advanced_command, contextual_advanced_command=None):
    win = tk.Toplevel(parent)
    win.title("Choose Weakness Review Depth")
    win.configure(bg="#0f1724")
    win.resizable(False, False)
    win.transient(parent)
    win.grab_set()

    shell = tk.Frame(win, bg="#0f1724", padx=24, pady=22)
    shell.pack(fill=tk.BOTH, expand=True)
    tk.Label(shell, text="Choose Weakness Review Depth", bg="#0f1724", fg="#f4cf61",
             font=("Segoe UI", 18, "bold")).pack(anchor="w")
    tk.Label(shell, text="The existing scan remains unchanged. Advanced review runs as a separate report workflow.",
             bg="#0f1724", fg="#aebed2", font=("Segoe UI", 10)).pack(anchor="w", pady=(5, 18))

    cards = tk.Frame(shell, bg="#0f1724")
    cards.pack(fill=tk.X)

    card_width = 300 if contextual_advanced_command else 330

    def card(title, subtitle, details, color, command):
        frame = tk.Frame(cards, bg="#182437", padx=18, pady=16, highlightthickness=1,
                         highlightbackground="#33445b", width=card_width, height=250)
        frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8) if title.startswith("Standard") else (8, 0))
        frame.pack_propagate(False)
        tk.Label(frame, text=title, bg="#182437", fg=color, font=("Segoe UI", 14, "bold"),
                 anchor="w").pack(fill=tk.X)
        tk.Label(frame, text=subtitle, bg="#182437", fg="#f1f5f9", font=("Segoe UI", 10, "bold"),
                 wraplength=290, justify=tk.LEFT).pack(anchor="w", pady=(8, 10))
        for line in details:
            tk.Label(frame, text=f"- {line}", bg="#182437", fg="#b9c7d8", font=("Segoe UI", 9),
                     wraplength=290, justify=tk.LEFT).pack(anchor="w", pady=2)
        tk.Frame(frame, bg="#182437").pack(fill=tk.BOTH, expand=True)

        def choose():
            win.destroy()
            command()

        tk.Button(frame, text=f"Open {title}", command=choose, bg=color, fg="#08111d", relief=tk.FLAT,
                  activebackground=color, activeforeground="#08111d", padx=14, pady=9,
                  font=("Segoe UI", 10, "bold"), cursor="hand2").pack(fill=tk.X)

    card(
        "Standard Scan",
        "Use the established weakness-card workflow.",
        ["Preserves the current scan logic and privacy prompts.", "Best for routine review and interactive weakness cards."],
        "#52c7bd",
        standard_command,
    )
    card(
        "Advanced 18-Dimension Review",
        "Each dimension independently rereads the complete matter.",
        ["18 separate model calls with isolated output limits.", "Delivers 18 full reports plus a highlighted combined report."],
        "#f4cf61",
        advanced_command,
    )
    if contextual_advanced_command:
        card(
            "Contextual 18D Challenge",
            "Each dimension rereads the complete matter and both sides' current positions.",
            ["18 separate model calls test the arguments and evidence in full-case context.",
             "Delivers 18 full reports plus targeted weakness cards."],
            "#a970ff",
            contextual_advanced_command,
        )

    tk.Button(shell, text="Cancel", command=win.destroy, bg="#26364b", fg="#dbe5ef", relief=tk.FLAT,
              padx=18, pady=7).pack(anchor="e", pady=(16, 0))
    win.update_idletasks()
    width, height = win.winfo_reqwidth(), win.winfo_reqheight()
    x = parent.winfo_rootx() + max(20, (parent.winfo_width() - width) // 2)
    y = parent.winfo_rooty() + max(20, (parent.winfo_height() - height) // 2)
    win.geometry(f"{width}x{height}+{x}+{y}")


class Advanced18DimensionReview:
    C = {"bg": "#0c1421", "panel": "#172235", "line": "#304158", "text": "#eef4fb",
         "muted": "#a9b9cb", "gold": "#f4cf61", "teal": "#49d2c5", "red": "#d75870",
         "purple": "#a970ff"}

    def __init__(self, parent, case_text, provider_routes, case_name="Matter", privacy_label="",
                 add_weakness_callback=None, review_mode="whole_matter"):
        self.parent = parent
        self.case_text = str(case_text or "").strip()
        self.provider_routes = list(provider_routes or [])
        self.case_name = str(case_name or "Matter").strip() or "Matter"
        self.privacy_label = privacy_label or "Review the transmission notice before starting."
        self.add_weakness_callback = add_weakness_callback
        self.review_mode = review_mode if review_mode in {"whole_matter", "contextual_positions"} else "whole_matter"
        self.contextual_positions = self.review_mode == "contextual_positions"
        self.cancel_event = threading.Event()
        self.output_dir = None
        self.report_path = None
        self.cloud_backend = get_backend()
        self.running = False
        self._parent_locked = False
        self._parent_widget_states = []
        self._close_when_finished = False
        self.status_vars = []
        self.review_results = []
        self.cards_window = None
        self.win = tk.Toplevel(parent)
        self.win.title(
            "Contextual 18-Dimension Challenge"
            if self.contextual_positions else "Advanced 18-Dimension Whole-Matter Review"
        )
        self.win.geometry("1040x780")
        self.win.minsize(900, 680)
        self.win.configure(bg=self.C["bg"])
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.build_ui()

    def build_ui(self):
        header = tk.Frame(self.win, bg=self.C["bg"], padx=22, pady=18)
        header.pack(fill=tk.X)
        title = "Contextual 18-Dimension Challenge" if self.contextual_positions else "Advanced 18-Dimension Review"
        subtitle = (
            "Independent full-case testing of both sides' current arguments and evidence"
            if self.contextual_positions
            else "Independent whole-matter rereading, followed by surface-card extraction"
        )
        accent = self.C["purple"] if self.contextual_positions else self.C["gold"]
        tk.Label(header, text=title, bg=self.C["bg"], fg=accent,
                 font=("Segoe UI", 19, "bold")).pack(anchor="w")
        tk.Label(header, text=subtitle,
                 bg=self.C["bg"], fg=self.C["muted"], font=("Segoe UI", 10)).pack(anchor="w", pady=(4, 0))

        notice = tk.Frame(self.win, bg="#182437", padx=16, pady=13, highlightthickness=1,
                          highlightbackground=self.C["line"])
        notice.pack(fill=tk.X, padx=22, pady=(0, 12))
        tk.Label(notice, text="TRANSMISSION AND OUTPUT BOUNDARY", bg="#182437", fg=self.C["gold"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        tk.Label(notice, text=(
            "Each dimension first produces an unrestricted internal legal analysis. A short second pass reads only "
            "that analysis to create surface-card labels; it does not replace or rewrite the internal report. "
            + self.privacy_label
        ), bg="#182437", fg=self.C["text"], wraplength=950, justify=tk.LEFT,
            font=("Segoe UI", 10)).pack(anchor="w", pady=(5, 0))

        info = tk.Frame(self.win, bg=self.C["panel"], padx=16, pady=11)
        info.pack(fill=tk.X, padx=22, pady=(0, 12))
        providers = ", ".join(str(item.get("name") or "custom") for item in self.provider_routes) or "None"
        tk.Label(info, text=f"Matter: {self.case_name}", bg=self.C["panel"], fg=self.C["text"],
                 font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        tk.Label(info, text=f"Verified provider order: {providers}", bg=self.C["panel"], fg=self.C["muted"],
                 font=("Segoe UI", 10)).pack(side=tk.RIGHT)

        body = tk.Frame(self.win, bg=self.C["panel"], padx=12, pady=12)
        body.pack(fill=tk.BOTH, expand=True, padx=22)
        canvas = tk.Canvas(body, bg=self.C["panel"], highlightthickness=0)
        scroll = ttk.Scrollbar(body, orient=tk.VERTICAL, command=canvas.yview)
        inner = tk.Frame(canvas, bg=self.C["panel"])
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))

        for number, (dimension_cn, _description) in enumerate(ALL_DIMENSIONS, 1):
            dimension = DIMENSION_LABELS_EN.get(dimension_cn, dimension_cn)
            row = tk.Frame(inner, bg="#111c2c", padx=12, pady=9, highlightthickness=1,
                           highlightbackground="#28394f")
            row.pack(fill=tk.X, pady=3)
            tk.Label(row, text=f"{number:02d}", width=3, bg="#111c2c", fg=self.C["gold"],
                     font=("Consolas", 11, "bold")).pack(side=tk.LEFT)
            tk.Label(row, text=dimension, bg="#111c2c", fg=self.C["text"],
                     font=("Segoe UI", 10, "bold"), anchor="w").pack(side=tk.LEFT, padx=8)
            var = tk.StringVar(value="Ready")
            self.status_vars.append(var)
            tk.Label(row, textvariable=var, width=28, bg="#111c2c", fg=self.C["muted"],
                     anchor="e", font=("Segoe UI", 9)).pack(side=tk.RIGHT)

        footer = tk.Frame(self.win, bg=self.C["bg"], padx=22, pady=14)
        footer.pack(fill=tk.X)
        actions = tk.Frame(footer, bg=self.C["bg"])
        actions.pack(side=tk.RIGHT)
        self.open_btn = tk.Button(actions, text="Open Combined Report", command=self.open_report,
                                  bg="#2b3442", fg="#7f8b99", relief=tk.FLAT, padx=14, pady=9,
                                  activebackground="#1d9a70", activeforeground="white",
                                  disabledforeground="#7f8b99",
                                  state=tk.DISABLED)
        self.open_btn.pack(side=tk.RIGHT, padx=(8, 0))
        self.cards_btn = tk.Button(actions, text="Open Weakness Cards", command=self.open_weakness_cards,
                                   bg="#2b3442", fg="#7f8b99", relief=tk.FLAT, padx=14, pady=9,
                                   disabledforeground="#7f8b99", state=tk.DISABLED)
        self.cards_btn.pack(side=tk.RIGHT, padx=(8, 0))
        start_color = self.C["purple"] if self.contextual_positions else "#f2c94c"
        start_hover = "#bd93ff" if self.contextual_positions else "#ffda67"
        self.start_btn = tk.Button(actions, text="Start Advanced Review", command=self.start,
                                   bg=start_color, fg="#101621", relief=tk.FLAT, padx=16, pady=9,
                                   activebackground=start_hover, activeforeground="#101621",
                                   font=("Segoe UI", 10, "bold"), cursor="hand2")
        self.start_btn.pack(side=tk.RIGHT, padx=(8, 0))
        self.summary_var = tk.StringVar(value="Ready")
        tk.Label(footer, textvariable=self.summary_var, bg=self.C["bg"], fg=self.C["teal"],
                 width=18, anchor="w").pack(side=tk.RIGHT, padx=10)
        self.progress = ttk.Progressbar(footer, mode="determinate", maximum=18, length=180)
        self.start_btn.bind(
            "<Enter>",
            lambda _event: self.start_btn.config(bg=start_hover)
            if not self.running and str(self.start_btn.cget("state")) == str(tk.NORMAL) else None,
        )

    def _walk_widgets(self, widget):
        for child in widget.winfo_children():
            if child == self.win:
                continue
            yield child
            yield from self._walk_widgets(child)

    def _lock_parent_ui(self):
        if self._parent_locked:
            return
        self._parent_widget_states = []
        muted = "#667085"
        for widget in self._walk_widgets(self.parent):
            saved = {}
            for option in ("state", "foreground", "disabledforeground", "insertbackground"):
                try:
                    saved[option] = widget.cget(option)
                except (tk.TclError, AttributeError):
                    pass
            if not saved:
                continue
            self._parent_widget_states.append((widget, saved))
            try:
                if "disabledforeground" in saved:
                    widget.configure(disabledforeground=muted)
            except tk.TclError:
                pass
            try:
                if "foreground" in saved:
                    widget.configure(foreground=muted)
            except tk.TclError:
                pass
            try:
                if "state" in saved:
                    widget.configure(state=tk.DISABLED)
            except tk.TclError:
                pass
        try:
            self.win.grab_set()
        except tk.TclError:
            pass
        self._parent_locked = True

    def _unlock_parent_ui(self):
        if not self._parent_locked:
            return
        try:
            if self.win.grab_current() == self.win:
                self.win.grab_release()
        except tk.TclError:
            pass
        for widget, saved in reversed(self._parent_widget_states):
            try:
                if widget.winfo_exists():
                    for option in ("foreground", "disabledforeground", "insertbackground"):
                        if option in saved:
                            try:
                                widget.configure(**{option: saved[option]})
                            except tk.TclError:
                                pass
                    if "state" in saved:
                        widget.configure(state=saved["state"])
            except tk.TclError:
                continue
        self._parent_widget_states = []
        self._parent_locked = False
        self.start_btn.bind(
            "<Leave>",
            lambda _event: self.start_btn.config(bg=start_color)
            if not self.running and str(self.start_btn.cget("state")) == str(tk.NORMAL) else None,
        )

    def start(self):
        if self.running:
            self.cancel_event.set()
            self.start_btn.config(text="Stopping...", state=tk.DISABLED)
            self.summary_var.set("Stopping after current call")
            return
        if not self.case_text:
            messagebox.showwarning("Missing Matter", "Import or enter the complete matter before starting advanced review.", parent=self.win)
            return
        if not self.provider_routes:
            messagebox.showwarning("No Verified Provider", "Verify at least one model provider before starting advanced review.", parent=self.win)
            return
        prepared_scope = (
            "the prepared complete matter and both sides' current argument and evidence frames"
            if self.contextual_positions else "the prepared complete matter"
        )
        if not messagebox.askyesno(
            "Confirm 18 Independent Model Calls",
            f"{prepared_scope.capitalize()} will be sent separately for each of the 18 legal dimensions. Each dimension "
            "then uses a short extraction pass to create surface-card labels from its completed report.\n\n"
            "This produces 18 independent free-form reports and may use substantially more model quota than Standard Scan.\n\n"
            f"Current privacy boundary: {self.privacy_label}\n\nContinue?",
            parent=self.win,
            icon=messagebox.WARNING,
        ):
            return
        self.cancel_event.clear()
        self.running = True
        self._close_when_finished = False
        self._lock_parent_ui()
        self.start_btn.config(
            text="Stop After Current Call", bg="#9f2f3f", fg="white",
            activebackground="#b83a4d", activeforeground="white",
        )
        self.open_btn.config(
            state=tk.DISABLED, bg="#2b3442", fg="#7f8b99",
            disabledforeground="#7f8b99",
        )
        self.progress["value"] = 0
        self.review_results = []
        self.cards_btn.config(state=tk.DISABLED, bg="#2b3442", fg="#7f8b99", cursor="arrow")
        for var in self.status_vars:
            var.set("Queued")
        threading.Thread(target=self.run_reviews, daemon=True).start()

    def dimension_prompt(self, dimension, description):
        if not self.contextual_positions:
            return prompt_for(self.case_text, dimension, description)
        return f'''You are senior litigation counsel independently reviewing the complete matter through the dimension "{dimension}".

This is a contextual position challenge. Read the ORIGINAL COMPLETE CASE and both sides' CURRENT ARGUMENT AND EVIDENCE FRAMES from beginning to end. Treat the frames as positions to be tested, not as established facts. Analyse how each side's introduced conditions, assumptions, exceptions, legal propositions, and factual inferences stand up when compared with the complete case.

Follow the strongest case-specific reasoning wherever it leads. Identify concrete weaknesses in the positive or negative position, including a missing factual bridge, unsupported condition, unproven exception, internal contradiction, evidentiary gap, or legal premise that the supplied matter does not yet establish. Explain the factual basis, significance, and limits of each weakness.

Dimension description: {description}

Rules:
- English only.
- Write natural connected prose. Do not return JSON.
- Do not fill a template, checklist, card schema, or fixed series of headings.
- Diagnose only. Do not provide lawyer questions, attack scripts, strategy, recommendations, cures, response language, preparation steps, or everyday examples.
- Do not invent facts, dates, amounts, documents, clauses, testimony, approvals, statutes, cases, or authorities.
- Distinguish supplied case facts from the parties' assertions, assumptions, and missing material.
- Do not manufacture symmetry or create a weakness merely to fill space. It is acceptable to conclude that this dimension adds little.

COMPLETE CASE AND CURRENT SIDE FRAMES:
{self.case_text}
'''

    def run_reviews(self):
        try:
            self._run_reviews()
        except Exception as exc:
            def fail_review():
                if not self.win.winfo_exists():
                    self._unlock_parent_ui()
                    return
                messagebox.showerror("Advanced Review Failed", str(exc), parent=self.win)
                self.finish()
            try:
                self.win.after(0, fail_review)
            except tk.TclError:
                self._unlock_parent_ui()

    def _run_reviews(self):
        timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        run_prefix = "contextual_18_dimension_challenge" if self.contextual_positions else "advanced_18_dimension_review"
        self.output_dir = HERE / "runs" / f"{run_prefix}_{timestamp}"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "00_prepared_case.txt").write_text(self.case_text, encoding="utf-8-sig")
        manifest = []
        if self.contextual_positions:
            index_lines = [f"# {self.case_name} - 18 Contextual Position Challenges", "",
                           "Each dimension independently reread the complete matter and both sides' current argument and evidence frames.", ""]
        else:
            index_lines = [f"# {self.case_name} - 18 Independent Whole-Matter Reviews", "",
                           "Each dimension independently reread the complete prepared matter.", ""]

        for number, (dimension_cn, _description_cn) in enumerate(ALL_DIMENSIONS, 1):
            if self.cancel_event.is_set():
                break
            dimension = DIMENSION_LABELS_EN.get(dimension_cn, dimension_cn)
            description = DIMENSION_DESC_EN.get(dimension_cn, "Independent whole-case legal review.")
            self.ui_dimension(number - 1, f"Reviewing complete matter ({number}/18)", self.C["gold"])
            result, used_provider, errors = None, "", []
            for provider_index, route in enumerate(self.provider_routes):
                if self.cancel_event.is_set():
                    break
                provider = str(route.get("name") or "custom").strip()
                key = str(route.get("key") or "").strip()
                try:
                    client = LLMClient(provider, key, personality_idx=provider_index)
                    free_analysis = client.chat_text(
                        self.dimension_prompt(dimension, description),
                        temperature=0.6,
                        max_tokens=6000,
                    )
                    if not str(free_analysis or "").strip():
                        raise RuntimeError("free-form internal analysis was empty")
                    extracted = client.chat_json(
                        extraction_prompt(free_analysis, dimension),
                        temperature=0.15,
                        max_tokens=2200,
                    )
                    if not isinstance(extracted, dict) or extracted.get("_error"):
                        raise RuntimeError(str(extracted.get("_error") if isinstance(extracted, dict) else "invalid extraction response"))
                    weaknesses = extracted.get("important_weaknesses") or []
                    if not isinstance(weaknesses, list):
                        raise RuntimeError("surface-card extraction did not return a list")
                    result = {
                        "dimension": dimension,
                        "full_dimension_report": free_analysis,
                        "important_weaknesses": weaknesses,
                        "no_finding_explanation": str(extracted.get("no_finding_explanation") or "").strip(),
                        "analysis_mode": (
                            "contextual_positions_free_form_then_surface_extraction"
                            if self.contextual_positions else "free_form_then_surface_extraction"
                        ),
                    }
                    used_provider = provider
                    break
                except Exception as exc:
                    errors.append(f"{provider}: {exc}")
                    time.sleep(1.5)

            filename = f"{number:02d}_{safe_name(dimension)}"
            if result is None:
                failure = {"dimension": dimension, "review_number": number, "errors": errors}
                (self.output_dir / f"{filename}.json").write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
                (self.output_dir / f"{filename}.md").write_text(
                    f"# {number:02d}. {dimension}\n\nReview failed.\n\n" + "\n".join(f"- {e}" for e in errors), encoding="utf-8")
                manifest.append(failure)
                index_lines.append(f"- {number:02d}. {dimension}: FAILED")
                self.ui_dimension(number - 1, "Failed - may retry later", self.C["red"])
            else:
                result.update({"dimension": dimension, "provider": used_provider, "review_number": number})
                (self.output_dir / f"{filename}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                (self.output_dir / f"{filename}.md").write_text(markdown_report(number, result, used_provider), encoding="utf-8")
                count = len(result.get("important_weaknesses") or [])
                manifest.append(result)
                self.review_results.append(result)
                index_lines.append(f"- {number:02d}. [{dimension}]({filename}.md): {count} important finding(s), {used_provider}")
                self.ui_dimension(number - 1, f"Complete - {count} key finding(s)", self.C["teal"])
            self.win.after(0, lambda value=number: self.progress.configure(value=value))
            time.sleep(1.5)

        (self.output_dir / "00_INDEX.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
        (self.output_dir / "00_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        professional_findings = []
        dimension_reports = []
        failures = []
        for record in manifest:
            if record.get("errors"):
                failures.append({"dimension": record.get("dimension"), "errors": record.get("errors")})
                continue
            dimension_reports.append({
                "dimension": record.get("dimension"),
                "provider": record.get("provider"),
                "full_analysis": record.get("full_dimension_report"),
                "no_finding_explanation": record.get("no_finding_explanation"),
            })
            for weakness in record.get("important_weaknesses") or []:
                item = dict(weakness) if isinstance(weakness, dict) else {"finding": weakness}
                item.update({
                    "dimension": record.get("dimension"),
                    "provider": record.get("provider"),
                    "model": "Not recorded",
                    "source_reference": f"Independent review {record.get('review_number')}",
                    "review_status": "ai_generated_unverified",
                })
                professional_findings.append(item)
        report_type = "contextual_18d_challenge" if self.contextual_positions else "advanced_18d_review"
        professional_report = build_standard_report(
            report_type,
            self.review_mode,
            self.case_name,
            findings=professional_findings,
            provider_runs=provider_runs_from_records(manifest, "provider"),
            input_scope={
                "complete_matter_reread_per_dimension": True,
                "requested_dimensions": 18,
                "completed_dimensions": len(dimension_reports),
                "privacy_boundary": self.privacy_label,
            },
            sections={"dimension_reports": dimension_reports, "failed_dimensions": failures},
            limitations=[
                "Each dimension is an independent AI review; repeated findings do not independently corroborate a fact.",
                "Surface-card extraction does not replace the full dimension report or lawyer verification.",
            ],
        )
        write_standard_companions(self.output_dir, "advanced-18d-review", professional_report)
        try:
            self.report_path = build_report(self.output_dir)
        except Exception as exc:
            self.report_path = None
            self.win.after(0, lambda: messagebox.showerror("Combined Report Failed", str(exc), parent=self.win))
        self.win.after(0, self.finish)

    def ui_dimension(self, index, text, color):
        def update():
            self.status_vars[index].set(text)
            # The label is intentionally stable; status text carries progress without layout shifts.
            self.summary_var.set(text)
        self.win.after(0, update)

    def finish(self):
        self.running = False
        self._unlock_parent_ui()
        self.start_btn.config(
            text="Start New Advanced Review", bg="#f2c94c", fg="#101621", state=tk.NORMAL,
            activebackground="#ffda67", activeforeground="#101621",
        )
        completed = int(self.progress["value"])
        if self.cancel_event.is_set():
            for var in self.status_vars:
                if var.get() == "Queued":
                    var.set("Not run")
            self.summary_var.set(f"Stopped after {completed} dimension(s)")
        else:
            self.summary_var.set(f"Complete - {completed} report(s)")
        full_run_complete = not self.cancel_event.is_set() and completed >= 18
        has_weaknesses = any(result.get("important_weaknesses") for result in self.review_results)
        if has_weaknesses:
            self.cards_btn.config(state=tk.NORMAL, bg="#176f68", fg="white", cursor="hand2",
                                  activebackground="#238f85", activeforeground="white")
        else:
            self.cards_btn.config(state=tk.DISABLED, bg="#2b3442", fg="#7f8b99", cursor="arrow")
        if full_run_complete and self.report_path and self.report_path.exists():
            self.open_btn.config(
                state=tk.NORMAL, bg="#167d5a", fg="white",
                activebackground="#1d9a70", activeforeground="white", cursor="hand2",
            )
            self.cloud_backend.run_async(
                self.cloud_backend.upload_report,
                self.report_path,
                self.case_name,
            )
            self.cloud_backend.run_async(
                self.cloud_backend.record_event,
                "advanced_18_dimension_report_completed",
                {"reports": completed, "provider_count": len(self.provider_routes)},
            )
        else:
            self.open_btn.config(
                state=tk.DISABLED, bg="#2b3442", fg="#7f8b99",
                disabledforeground="#7f8b99", cursor="arrow",
            )
        if has_weaknesses and not self.cancel_event.is_set():
            self.open_weakness_cards()
        if self._close_when_finished:
            self.win.destroy()

    def _weakness_cards_by_side(self):
        cards = {"positive": [], "negative": []}
        for result in self.review_results:
            for finding_index, finding in enumerate(result.get("important_weaknesses") or [], 1):
                if not isinstance(finding, dict):
                    continue
                if is_non_material_weakness_display_record(finding):
                    continue
                side = str(finding.get("affected_side") or "").strip().lower()
                if side not in cards:
                    continue
                item = dict(finding)
                item["dimension"] = result.get("dimension", "")
                item["provider"] = result.get("provider", "")
                item["review_number"] = result.get("review_number", "")
                item["full_dimension_report"] = result.get("full_dimension_report", "")
                item["card_id"] = (
                    f"18d:{item['review_number']}:{finding_index}:{side}:"
                    f"{str(item.get('conclusion') or '').strip().lower()}"
                )
                cards[side].append(item)
        return cards

    @staticmethod
    def _full_weakness_text(item):
        report = str(item.get("full_dimension_report") or "").strip()
        if report:
            return report
        return str(item.get("surface_summary") or item.get("conclusion") or "Weakness identified").strip()

    def open_weakness_cards(self):
        cards = self._weakness_cards_by_side()
        if not cards["positive"] and not cards["negative"]:
            messagebox.showinfo("No Material Weaknesses", "The completed reviews did not return material weakness cards.", parent=self.win)
            return
        if self.cards_window and self.cards_window.winfo_exists():
            self.cards_window.lift()
            self.cards_window.focus_force()
            return

        card_win = tk.Toplevel(self.win)
        self.cards_window = card_win
        card_win.title("Advanced 18-Dimension Weakness Cards")
        card_win.geometry("1180x800")
        card_win.minsize(920, 620)
        card_win.configure(bg=self.C["bg"])
        card_win.transient(self.parent)

        header = tk.Frame(card_win, bg=self.C["bg"], padx=16, pady=12)
        header.pack(fill=tk.X)
        tk.Label(header, text="Advanced 18-Dimension Weakness Cards", bg=self.C["bg"], fg=self.C["gold"],
                 font=("Segoe UI", 17, "bold")).pack(side=tk.LEFT)
        status_var = tk.StringVar(
            value="Click a card for the full finding. Use DRAG to move it into the main case or a Single-Point Review window."
        )
        tk.Label(header, textvariable=status_var, bg=self.C["bg"], fg=self.C["muted"],
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=16)

        panes = tk.PanedWindow(card_win, orient=tk.HORIZONTAL, bg=self.C["bg"], sashwidth=6)
        panes.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 14))
        drag_state = {"item": None, "side": None, "card": None, "ghost": None, "external": False}

        def make_column(side, title, bar, accent):
            shell = tk.Frame(panes, bg=self.C["panel"], padx=8, pady=8)
            panes.add(shell, minsize=440)
            tk.Label(shell, text=title, bg=bar, fg=accent, font=("Segoe UI", 13, "bold"), pady=9).pack(fill=tk.X)
            canvas = tk.Canvas(shell, bg="#0f1928", highlightthickness=0)
            scroll = ttk.Scrollbar(shell, orient=tk.VERTICAL, command=canvas.yview)
            inner = tk.Frame(canvas, bg="#0f1928")
            window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
            canvas.configure(yscrollcommand=scroll.set)
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=(8, 0))
            scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=(8, 0))
            inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))
            inner._scroll_canvas = canvas
            inner._side = side
            inner._accent = accent
            return inner

        pos_inner = make_column("positive", "Positive Side Weaknesses", "#0d5d61", "#47ddd3")
        neg_inner = make_column("negative", "Negative Side Weaknesses", "#762642", "#ff9dbb")

        def close_ghost():
            ghost = drag_state.get("ghost")
            drag_state["ghost"] = None
            if ghost:
                try:
                    ghost.destroy()
                except tk.TclError:
                    pass

        def show_ghost(item):
            close_ghost()
            ghost = tk.Toplevel(self.parent)
            ghost.overrideredirect(True)
            ghost.attributes("-topmost", True)
            ghost.configure(bg="#1f6feb")
            text = str(item.get("conclusion") or "Weakness identified").strip()
            if len(text) > 90:
                text = text[:87].rstrip() + "..."
            tk.Label(ghost, text=f"Drop entire weakness: {text}", bg="#1f6feb", fg="white",
                     font=("Segoe UI", 9, "bold"), padx=10, pady=6).pack()
            drag_state["ghost"] = ghost

        def open_detail(item, side):
            detail = tk.Toplevel(card_win)
            detail.title("Positive-Side Weakness" if side == "positive" else "Negative-Side Weakness")
            detail.geometry("900x680")
            detail.minsize(720, 520)
            detail.configure(bg=self.C["bg"])
            detail.transient(card_win)
            detail.grab_set()
            accent = "#47ddd3" if side == "positive" else "#ff9dbb"
            tk.Label(detail, text=str(item.get("conclusion") or "Weakness identified"), bg=self.C["panel"],
                     fg=accent, wraplength=840, justify=tk.LEFT, anchor="w", padx=18, pady=14,
                     font=("Segoe UI", 15, "bold")).pack(fill=tk.X)
            body = scrolledtext.ScrolledText(detail, bg="#0f1928", fg=self.C["text"], relief=tk.FLAT,
                                             wrap=tk.WORD, padx=18, pady=16, font=("Segoe UI", 11))
            body.pack(fill=tk.BOTH, expand=True, padx=14, pady=12)
            body.insert(tk.END, self._full_weakness_text(item))
            body.config(state=tk.DISABLED)
            controls = tk.Frame(detail, bg=self.C["bg"], padx=14, pady=(0, 12))
            controls.pack(fill=tk.X)
            tk.Button(controls, text="Close", command=detail.destroy, bg="#334155", fg="white",
                      activebackground="#475569", activeforeground="white", relief=tk.FLAT,
                      padx=20, pady=7, cursor="hand2", font=("Segoe UI", 9, "bold")).pack(side=tk.RIGHT)
            detail.update_idletasks()
            x = card_win.winfo_rootx() + max(0, (card_win.winfo_width() - detail.winfo_width()) // 2)
            y = card_win.winfo_rooty() + max(0, (card_win.winfo_height() - detail.winfo_height()) // 2)
            detail.geometry(f"+{x}+{y}")
            detail.lift()
            detail.focus_force()

        def reorder(card, parent):
            pointer_y = self.parent.winfo_pointery()
            siblings = [child for child in parent.winfo_children() if hasattr(child, "_weakness_item")]
            target = next((child for child in siblings if child is not card and
                           pointer_y < child.winfo_rooty() + child.winfo_height() / 2), None)
            if target is not None:
                card.pack_configure(before=target)
            elif siblings and siblings[-1] is not card:
                card.pack_configure(after=siblings[-1])
            parent.update_idletasks()

        def finish_drag():
            item, side, card = drag_state.get("item"), drag_state.get("side"), drag_state.get("card")
            external = drag_state.get("external")
            close_ghost()
            if card:
                card.pack_configure(fill=tk.X, padx=5, pady=5)
                card.configure(highlightthickness=1, highlightbackground="#334155")
            drag_state.update({"item": None, "side": None, "card": None, "external": False})
            if not item or not external:
                status_var.set("Weakness card order updated")
                return
            try:
                widget = self.parent.winfo_containing(self.parent.winfo_pointerx(), self.parent.winfo_pointery())
                target_window = widget.winfo_toplevel() if widget is not None else None
                drop_targets = list(getattr(self.parent, "_nido_weakness_drop_targets", []))
                for target in drop_targets:
                    window = target.get("window") if isinstance(target, dict) else None
                    accept = target.get("accept") if isinstance(target, dict) else None
                    try:
                        available = window is not None and window.winfo_exists()
                    except tk.TclError:
                        available = False
                    if not available:
                        try:
                            self.parent._nido_weakness_drop_targets.remove(target)
                        except (AttributeError, ValueError):
                            pass
                        continue
                    if target_window == window and callable(accept):
                        added = bool(accept(item, side))
                        status_var.set(
                            "Entire weakness added to Single-Point Review"
                            if added else "Single-Point Review did not accept the weakness"
                        )
                        return
                if widget is not None and target_window == self.parent:
                    if self.add_weakness_callback:
                        added = self.add_weakness_callback(item, side)
                        status_var.set("Entire weakness added to the main case" if added else "Weakness was not added")
                    else:
                        status_var.set("Main-case insertion is unavailable in this build")
                else:
                    status_var.set("Drop the card inside the main case or a Single-Point Review window")
            except tk.TclError:
                status_var.set("Weakness drop cancelled")

        def render(parent, items, side):
            accent = parent._accent
            for item in items:
                card = tk.Frame(parent, bg="#111c2c", padx=12, pady=10, highlightthickness=1,
                                highlightbackground="#334155")
                card.pack(fill=tk.X, padx=5, pady=5)
                card._weakness_item = item
                top = tk.Frame(card, bg="#111c2c")
                top.pack(fill=tk.X)
                title = tk.Label(top, text=str(item.get("conclusion") or "Weakness identified"), bg="#111c2c",
                                 fg=accent, wraplength=405, justify=tk.LEFT, anchor="w",
                                 font=("Segoe UI", 11, "bold"))
                title.pack(side=tk.LEFT, fill=tk.X, expand=True)
                handle = tk.Label(top, text="DRAG", bg="#1f6feb", fg="white", cursor="fleur",
                                  font=("Segoe UI", 8, "bold"), padx=10, pady=5)
                handle.pack(side=tk.RIGHT, padx=(8, 0))
                reason = tk.Label(card, text=str(item.get("surface_summary") or ""), bg="#111c2c", fg="#dbe7f5",
                                  wraplength=490, justify=tk.LEFT, anchor="w")
                reason.pack(fill=tk.X, pady=(7, 4))
                meta = tk.Label(card, text=f"{item.get('dimension', '')}  |  {item.get('provider', '')}",
                                bg="#111c2c", fg=self.C["muted"], anchor="w")
                meta.pack(fill=tk.X)
                for widget in (card, top, title, reason, meta):
                    widget.configure(cursor="hand2")
                    widget.bind("<Button-1>", lambda _e, record=item, record_side=side:
                                open_detail(record, record_side))

                def press(_event, record=item, record_side=side, widget=card, drag_handle=handle):
                    drag_state.update({"item": record, "side": record_side, "card": widget, "external": False})
                    widget.pack_configure(fill=tk.X, padx=58, pady=2)
                    widget.configure(highlightthickness=2, highlightbackground="#22c55e")
                    drag_handle.configure(text="MOVING", bg="#22c55e", fg="#052e16")
                    status_var.set("Moving card - drag it into the main case or a Single-Point Review window")
                    return "break"

                def motion(_event, widget=card, container=parent, drag_handle=handle):
                    canvas = container._scroll_canvas
                    px, py = self.parent.winfo_pointerx(), self.parent.winfo_pointery()
                    left, top_y = canvas.winfo_rootx(), canvas.winfo_rooty()
                    right, bottom = left + canvas.winfo_width(), top_y + canvas.winfo_height()
                    outside = px < left - 12 or px > right + 12 or py < top_y - 12 or py > bottom + 12
                    if outside:
                        if not drag_state.get("external"):
                            drag_state["external"] = True
                            widget.pack_configure(fill=tk.X, padx=16, pady=10)
                            drag_handle.configure(text="DRAGGING", bg="#22c55e", fg="#052e16")
                            show_ghost(drag_state["item"])
                        ghost = drag_state.get("ghost")
                        if ghost:
                            ghost.geometry(f"+{px + 14}+{py + 12}")
                    else:
                        if py < top_y + 34:
                            canvas.yview_scroll(-1, "units")
                        elif py > bottom - 34:
                            canvas.yview_scroll(1, "units")
                        reorder(widget, container)
                    return "break"

                def release(_event, drag_handle=handle):
                    drag_handle.configure(text="DRAG", bg="#1f6feb", fg="white")
                    finish_drag()
                    return "break"

                handle.bind("<ButtonPress-1>", press)
                handle.bind("<B1-Motion>", motion)
                handle.bind("<ButtonRelease-1>", release)

        render(pos_inner, cards["positive"], "positive")
        render(neg_inner, cards["negative"], "negative")

    def open_report(self):
        if self.report_path and self.report_path.exists():
            os.startfile(str(self.report_path))

    def close(self):
        if self.running:
            if not messagebox.askyesno("Review In Progress", "Stop after the current model call and close this window?", parent=self.win):
                return
            self.cancel_event.set()
            self._close_when_finished = True
            self.start_btn.config(text="Stopping...", state=tk.DISABLED)
            self.summary_var.set("Stopping after current call")
            return
        self._unlock_parent_ui()
        self.win.destroy()


def open_advanced_review(parent, case_text, provider_routes, case_name="Matter", privacy_label="",
                         add_weakness_callback=None, review_mode="whole_matter"):
    return Advanced18DimensionReview(
        parent, case_text, provider_routes, case_name, privacy_label, add_weakness_callback, review_mode
    )
