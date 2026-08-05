import datetime as dt
import html
import json
import os
import re
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
)
from standard_report_contract import (
    build_standard_report,
    provider_runs_from_records,
    write_standard_companions,
)


HERE = Path(__file__).resolve().parent


def show_single_point_mode_dialog(parent, standard_command, advanced_command):
    win = tk.Toplevel(parent)
    win.title("Choose Single-Point Review Depth")
    win.configure(bg="#0f1724")
    win.resizable(False, False)
    win.transient(parent)
    win.grab_set()

    shell = tk.Frame(win, bg="#0f1724", padx=24, pady=22)
    shell.pack(fill=tk.BOTH, expand=True)
    tk.Label(shell, text="Choose Single-Point Review Depth", bg="#0f1724", fg="#f4cf61",
             font=("Segoe UI", 18, "bold")).pack(anchor="w")
    tk.Label(
        shell,
        text="The established review remains available. Advanced 2R runs as a separate 36-call workflow.",
        bg="#0f1724", fg="#aebed2", font=("Segoe UI", 10),
    ).pack(anchor="w", pady=(5, 18))

    cards = tk.Frame(shell, bg="#0f1724")
    cards.pack(fill=tk.X)

    def add_card(title, subtitle, details, color, command, left):
        frame = tk.Frame(cards, bg="#182437", padx=18, pady=16, highlightthickness=1,
                         highlightbackground="#33445b", width=350, height=280)
        frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8) if left else (8, 0))
        frame.pack_propagate(False)
        tk.Label(frame, text=title, bg="#182437", fg=color,
                 font=("Segoe UI", 14, "bold"), anchor="w").pack(fill=tk.X)
        tk.Label(frame, text=subtitle, bg="#182437", fg="#f1f5f9",
                 font=("Segoe UI", 10, "bold"), wraplength=310,
                 justify=tk.LEFT).pack(anchor="w", pady=(8, 10))
        for line in details:
            tk.Label(frame, text=f"- {line}", bg="#182437", fg="#b9c7d8",
                     font=("Segoe UI", 9), wraplength=310,
                     justify=tk.LEFT).pack(anchor="w", pady=2)
        tk.Frame(frame, bg="#182437").pack(fill=tk.BOTH, expand=True)

        def choose():
            win.destroy()
            command()

        tk.Button(frame, text=f"Open {title}", command=choose, bg=color, fg="#08111d",
                  relief=tk.FLAT, activebackground=color, activeforeground="#08111d",
                  padx=14, pady=9, font=("Segoe UI", 10, "bold"),
                  cursor="hand2").pack(fill=tk.X)

    add_card(
        "Standard Single-Point Review",
        "One structured review against the full matter.",
        ["Fast attack, defence, and counter-response.",
         "Preserves the existing standard workflow."],
        "#52c7bd", standard_command, True,
    )
    add_card(
        "Advanced Single-Point 2R",
        "18 independent attacks, followed by 18 independent full-case responses.",
        ["Every dimension rereads the complete matter in both rounds.",
         "Round 2 receives every Round-1 attack, not an isolated excerpt.",
         "Natural advocacy first; software organizes the reports afterward."],
        "#f4cf61", advanced_command, False,
    )
    tk.Button(shell, text="Cancel", command=win.destroy, bg="#26364b", fg="#dbe5ef",
              relief=tk.FLAT, padx=18, pady=7).pack(anchor="e", pady=(16, 0))
    win.update_idletasks()
    width, height = win.winfo_reqwidth(), win.winfo_reqheight()
    x = parent.winfo_rootx() + max(20, (parent.winfo_width() - width) // 2)
    y = parent.winfo_rooty() + max(20, (parent.winfo_height() - height) // 2)
    win.geometry(f"{width}x{height}+{x}+{y}")


def _safe_name(value):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "report")).strip("_") or "report"


def _key_passage(text):
    paragraphs = [re.sub(r"\s+", " ", part).strip(" #*-\t")
                  for part in re.split(r"\n\s*\n", str(text or ""))]
    for paragraph in paragraphs:
        if len(paragraph) >= 80:
            return paragraph[:700]
    return (paragraphs[0] if paragraphs else "No material passage returned.")[:700]


def build_single_point_report(output_dir, case_name, point, owner, records):
    sections = []
    for record in records:
        dimension = html.escape(record["dimension"])
        attack = html.escape(record.get("attack") or "Not completed")
        response = html.escape(record.get("response") or "Not completed")
        attack_key = html.escape(_key_passage(record.get("attack")))
        response_key = html.escape(_key_passage(record.get("response")))
        sections.append(f"""
        <section id="d{record['number']:02d}">
          <h2>{record['number']:02d}. {dimension}</h2>
          <div class="keys"><div><b>Round 1 key passage</b><p>{attack_key}</p></div>
          <div><b>Round 2 key passage</b><p>{response_key}</p></div></div>
          <div class="rounds"><article><h3>Round 1 - Opposing Counsel Attack</h3><pre>{attack}</pre></article>
          <article><h3>Round 2 - Point-Owner Response</h3><pre>{response}</pre></article></div>
        </section>""")
    nav = "".join(
        f'<a href="#d{record["number"]:02d}">{record["number"]:02d} {html.escape(record["dimension"])}</a>'
        for record in records
    )
    document = f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(case_name)} - Advanced Single-Point 2R</title>
    <style>
    body{{margin:0;background:#0c1421;color:#eef4fb;font:15px Segoe UI,Arial,sans-serif}}header{{padding:28px 34px;background:#172235;border-bottom:3px solid #f4cf61}}
    h1{{margin:0;color:#f4cf61}}header p{{max-width:1100px;color:#c5d1df}}nav{{position:sticky;top:0;background:#101b2b;padding:12px 24px;z-index:2;white-space:nowrap;overflow:auto}}nav a{{color:#49d2c5;margin-right:18px;text-decoration:none}}
    main{{max-width:1500px;margin:auto;padding:22px}}section{{border:1px solid #304158;background:#111c2c;margin:0 0 22px;padding:18px}}h2{{color:#f4cf61}}
    .keys,.rounds{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}.keys div{{background:#172235;border-left:4px solid #49d2c5;padding:12px}}article{{background:#0c1421;border:1px solid #304158;padding:14px}}article:nth-child(2){{border-top:3px solid #7fb3ff}}h3{{color:#e8edf5}}pre{{white-space:pre-wrap;font:14px/1.55 Segoe UI,Arial,sans-serif}}
    .notice{{color:#a9b9cb}}@media(max-width:900px){{.keys,.rounds{{grid-template-columns:1fr}}}}
    </style></head><body><header><h1>Advanced Single-Point 2R Review</h1>
    <p><b>Matter:</b> {html.escape(case_name)}<br><b>Point owner:</b> {html.escape(owner)}<br><b>Selected point:</b> {html.escape(point)}</p>
    <p class="notice">Round 1 contains 18 independent full-matter attacks. Round 2 contains 18 independent rereadings of the full matter and the complete Round-1 attack dossier. This is lawyer-preparation reference material, not a final legal conclusion.</p></header>
    <nav>{nav}</nav><main>{''.join(sections)}</main></body></html>"""
    path = Path(output_dir) / "00_COMPLETE_SINGLE_POINT_2R.html"
    path.write_text(document, encoding="utf-8")
    return path


class AdvancedSinglePoint2R:
    C = {"bg": "#0c1421", "panel": "#172235", "line": "#304158", "text": "#eef4fb",
         "muted": "#a9b9cb", "gold": "#f4cf61", "teal": "#49d2c5", "red": "#d75870"}

    def __init__(self, parent, matter_context, provider_routes, case_name="Matter", privacy_label=""):
        self.parent = parent
        self.matter_context = str(matter_context or "").strip()
        self.provider_routes = list(provider_routes or [])
        self.case_name = str(case_name or "Matter").strip() or "Matter"
        self.privacy_label = privacy_label or "Confirm external processing authorization before starting."
        self.cancel_event = threading.Event()
        self.running = False
        self.output_dir = None
        self.report_path = None
        self.status_vars = []
        self.records = []
        self._parent_widget_states = []
        self._parent_locked = False
        self._drop_target_record = None
        self.win = tk.Toplevel(parent)
        self.win.title("Advanced Single-Point 2R Review")
        self.win.geometry("1120x840")
        self.win.minsize(960, 700)
        self.win.configure(bg=self.C["bg"])
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.build_ui()
        self._register_weakness_drop_target()

    def build_ui(self):
        header = tk.Frame(self.win, bg=self.C["bg"], padx=22, pady=16)
        header.pack(fill=tk.X)
        tk.Label(header, text="Advanced Single-Point 2R", bg=self.C["bg"], fg=self.C["gold"],
                 font=("Segoe UI", 19, "bold")).pack(anchor="w")
        tk.Label(header, text="18 full-matter attacks, then 18 full-matter responses informed by every attack",
                 bg=self.C["bg"], fg=self.C["muted"], font=("Segoe UI", 10)).pack(anchor="w", pady=(4, 0))

        entry = tk.Frame(self.win, bg=self.C["panel"], padx=14, pady=12)
        entry.pack(fill=tk.X, padx=22, pady=(0, 10))
        top = tk.Frame(entry, bg=self.C["panel"])
        top.pack(fill=tk.X)
        tk.Label(top, text="Point belongs to", bg=self.C["panel"], fg=self.C["text"]).pack(side=tk.LEFT)
        self.owner_var = tk.StringVar(value="Positive side")
        ttk.Combobox(top, textvariable=self.owner_var, values=["Positive side", "Negative side"],
                     state="readonly", width=18).pack(side=tk.LEFT, padx=(8, 18))
        providers = ", ".join(str(item.get("name") or "custom") for item in self.provider_routes) or "None"
        tk.Label(top, text=f"Verified provider order: {providers}", bg=self.C["panel"],
                 fg=self.C["muted"]).pack(side=tk.RIGHT)
        tk.Label(entry, text="Selected point, evidence item, assertion, or question - weakness cards may be dropped here", bg=self.C["panel"],
                 fg=self.C["text"], font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 4))
        self.point_text = scrolledtext.ScrolledText(entry, height=5, bg="#0b1523", fg=self.C["text"],
                                                    insertbackground="white", wrap=tk.WORD,
                                                    font=("Segoe UI", 10), relief=tk.FLAT)
        self.point_text.pack(fill=tk.X)

        body = tk.Frame(self.win, bg=self.C["panel"], padx=10, pady=10)
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

        for number, (dimension_cn, _desc) in enumerate(ALL_DIMENSIONS, 1):
            dimension = DIMENSION_LABELS_EN.get(dimension_cn, dimension_cn)
            row = tk.Frame(inner, bg="#111c2c", padx=12, pady=9, highlightthickness=1,
                           highlightbackground="#28394f")
            row.pack(fill=tk.X, pady=3)
            tk.Label(row, text=f"{number:02d}", width=3, bg="#111c2c", fg=self.C["gold"],
                     font=("Consolas", 11, "bold")).pack(side=tk.LEFT)
            tk.Label(row, text=dimension, bg="#111c2c", fg=self.C["text"],
                     font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=8)
            var = tk.StringVar(value="Ready")
            self.status_vars.append(var)
            tk.Label(row, textvariable=var, width=42, bg="#111c2c", fg=self.C["muted"],
                     anchor="e", font=("Segoe UI", 9)).pack(side=tk.RIGHT)

        footer = tk.Frame(self.win, bg=self.C["bg"], padx=22, pady=14)
        footer.pack(fill=tk.X)
        self.progress = ttk.Progressbar(footer, mode="determinate", maximum=36, length=310)
        self.summary_var = tk.StringVar(value="Ready")
        tk.Label(footer, textvariable=self.summary_var, bg=self.C["bg"], fg=self.C["teal"],
                 width=30, anchor="w").pack(side=tk.LEFT, padx=12)
        self.open_btn = tk.Button(footer, text="Open Combined Report", command=self.open_report,
                                  bg="#2b3442", fg="#7f8b99", disabledforeground="#7f8b99",
                                  relief=tk.FLAT, padx=14, pady=9, state=tk.DISABLED)
        self.open_btn.pack(side=tk.RIGHT, padx=(8, 0))
        self.start_btn = tk.Button(footer, text="Start Advanced Single-Point 2R", command=self.start,
                                   bg="#f2c94c", fg="#101621", relief=tk.FLAT, padx=16, pady=9,
                                   activebackground="#ffda67", activeforeground="#101621",
                                   font=("Segoe UI", 10, "bold"), cursor="hand2")
        self.start_btn.pack(side=tk.RIGHT, padx=(8, 0))

    def _register_weakness_drop_target(self):
        targets = getattr(self.parent, "_nido_weakness_drop_targets", None)
        if targets is None:
            targets = []
            self.parent._nido_weakness_drop_targets = targets
        self._drop_target_record = {"window": self.win, "accept": self.accept_weakness_drop}
        targets.append(self._drop_target_record)

    def _unregister_weakness_drop_target(self):
        targets = getattr(self.parent, "_nido_weakness_drop_targets", [])
        if self._drop_target_record in targets:
            targets.remove(self._drop_target_record)
        self._drop_target_record = None

    def accept_weakness_drop(self, item, affected_side):
        if self.running or not isinstance(item, dict):
            return False
        conclusion = str(item.get("conclusion") or "Weakness identified").strip()
        analysis = str(item.get("surface_summary") or item.get("analysis") or "").strip()
        dimension = str(item.get("dimension") or "").strip()
        provider = str(item.get("provider") or "").strip()
        parts = [conclusion]
        if analysis and analysis.lower() != conclusion.lower():
            parts.append(analysis)
        if dimension:
            parts.append(f"Review Dimension: {dimension}")
        if provider:
            parts.append(f"Source Model: {provider}")
        dropped_text = "\n\n".join(parts).strip()
        existing = self.point_text.get("1.0", tk.END).strip()
        if dropped_text.lower() in existing.lower():
            self.win.lift()
            self.point_text.focus_set()
            return False
        self.owner_var.set("Positive side" if str(affected_side).lower() == "positive" else "Negative side")
        if existing:
            self.point_text.insert(tk.END, "\n\n" + dropped_text)
        else:
            self.point_text.insert("1.0", dropped_text)
        self.point_text.see(tk.END)
        self.win.lift()
        self.point_text.focus_set()
        return True

    def _walk_parent_widgets(self, widget):
        for child in widget.winfo_children():
            if child == self.win or isinstance(child, tk.Toplevel):
                continue
            yield child
            yield from self._walk_parent_widgets(child)

    def _lock_parent_ui(self):
        if self._parent_locked:
            return
        muted = "#667085"
        self._parent_widget_states = []
        for widget in self._walk_parent_widgets(self.parent):
            saved = {}
            for option in ("state", "foreground", "disabledforeground", "insertbackground"):
                try:
                    saved[option] = widget.cget(option)
                except (tk.TclError, AttributeError):
                    pass
            if not saved:
                continue
            self._parent_widget_states.append((widget, saved))
            for option in ("foreground", "disabledforeground"):
                if option in saved:
                    try:
                        widget.configure(**{option: muted})
                    except tk.TclError:
                        pass
            if "state" in saved:
                try:
                    widget.configure(state=tk.DISABLED)
                except tk.TclError:
                    pass
        self._parent_locked = True

    def _unlock_parent_ui(self):
        if not self._parent_locked:
            return
        for widget, saved in reversed(self._parent_widget_states):
            try:
                if not widget.winfo_exists():
                    continue
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

    def start(self):
        if self.running:
            self.cancel_event.set()
            self.start_btn.config(text="Stopping...", state=tk.DISABLED)
            self.summary_var.set("Stopping after current call")
            return
        point = self.point_text.get("1.0", tk.END).strip()
        if not point:
            messagebox.showwarning("Missing Point", "Enter one point, evidence item, assertion, or question first.", parent=self.win)
            return
        if not self.matter_context:
            messagebox.showwarning("Missing Matter", "Import or enter the complete matter before starting.", parent=self.win)
            return
        if not self.provider_routes:
            messagebox.showwarning("No Verified Provider", "Verify at least one model provider before starting.", parent=self.win)
            return
        if not messagebox.askyesno(
            "Confirm 36 Independent Model Calls",
            "Round 1 sends the prepared complete matter separately to 18 legal dimensions.\n\n"
            "Round 2 sends the complete matter and all 18 Round-1 attacks separately to the same 18 dimensions.\n\n"
            "The AI writes natural advocacy first; the software organizes it afterward. This may use substantial model quota.\n\n"
            f"Current privacy boundary: {self.privacy_label}\n\nContinue?",
            parent=self.win, icon=messagebox.WARNING,
        ):
            return
        self.cancel_event.clear()
        self.running = True
        self._lock_parent_ui()
        self.progress["value"] = 0
        self.report_path = None
        self.records = []
        for var in self.status_vars:
            var.set("Queued for Round 1")
        self.owner_var_widget_state("disabled")
        self.point_text.config(state=tk.DISABLED)
        self.open_btn.config(state=tk.DISABLED, bg="#2b3442", fg="#7f8b99")
        self.start_btn.config(text="Stop After Current Call", bg="#9f2f3f", fg="white")
        threading.Thread(target=self.run, args=(point, self.owner_var.get()), daemon=True).start()

    def owner_var_widget_state(self, state):
        for child in self.win.winfo_children():
            self._set_combobox_state(child, state)

    def _set_combobox_state(self, widget, state):
        if isinstance(widget, ttk.Combobox):
            widget.config(state="readonly" if state == "normal" else "disabled")
        for child in widget.winfo_children():
            self._set_combobox_state(child, state)

    def _call_dimension(self, prompt, dimension_number, round_number):
        errors = []
        count = len(self.provider_routes)
        start = (dimension_number - 1 + round_number - 1) % count
        routes = self.provider_routes[start:] + self.provider_routes[:start]
        for index, route in enumerate(routes):
            if self.cancel_event.is_set():
                break
            provider = str(route.get("name") or "custom").strip()
            key = str(route.get("key") or "").strip()
            try:
                client = LLMClient(provider, key, personality_idx=dimension_number + round_number + index)
                return client.chat_text(prompt, temperature=0.68, max_tokens=4200), provider, errors
            except Exception as exc:
                errors.append(f"{provider}: {exc}")
                time.sleep(1.2)
        return "", "", errors

    def run(self, point, owner):
        timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_dir = HERE / "runs" / f"advanced_single_point_2r_{timestamp}"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "00_prepared_matter.txt").write_text(self.matter_context, encoding="utf-8-sig")
        (self.output_dir / "00_selected_point.txt").write_text(point, encoding="utf-8-sig")
        attacker = "Negative side" if owner == "Positive side" else "Positive side"
        records = []

        for number, (dimension_cn, _desc_cn) in enumerate(ALL_DIMENSIONS, 1):
            if self.cancel_event.is_set():
                break
            dimension = DIMENSION_LABELS_EN.get(dimension_cn, dimension_cn)
            description = DIMENSION_DESC_EN.get(dimension_cn, "Independent whole-matter legal review.")
            self.ui(number - 1, f"Round 1: {attacker} attack ({number}/18)", self.C["gold"])
            prompt = f"""Act as senior counsel for the {attacker}. Read the entire matter below again from the perspective of {dimension} ({description}).

The selected point belongs to the {owner}. Attack that point for the {attacker}, but do not isolate it from the rest of the case. Use any argument, evidence, omission, chronology, inconsistency, legal element, alternative explanation, or practical litigation move in the complete record that materially affects this point. Explore unusual but defensible angles when the record supports them. Distinguish what the record proves from what is only inferred.

Write a natural, forceful litigation memorandum for a lawyer. Do not return JSON. Do not follow a fixed heading template. Do not mechanically fill fields. Develop the strongest attack this dimension genuinely supports, explain why it matters, and include concrete questions or moves where useful. If this dimension does not support a strong attack, say so briefly and explain the limit instead of inventing one.

SELECTED POINT:
{point}

COMPLETE MATTER:
{self.matter_context}"""
            attack, provider, errors = self._call_dimension(prompt, number, 1)
            filename = f"{number:02d}_{_safe_name(dimension)}_R1_Attack.md"
            if not attack:
                attack = "Round 1 failed.\n\n" + "\n".join(f"- {error}" for error in errors)
                self.ui(number - 1, "Round 1 failed", self.C["red"])
            else:
                self.ui(number - 1, f"Round 1 complete via {provider}", self.C["teal"])
            (self.output_dir / filename).write_text(f"# {dimension} - Round 1 Attack\n\n{attack}\n", encoding="utf-8")
            records.append({"number": number, "dimension": dimension, "attack": attack,
                            "attack_provider": provider, "response": "", "response_provider": ""})
            self.win.after(0, lambda value=number: self.progress.configure(value=value))
            time.sleep(1.2)

        dossier = "\n\n".join(
            f"===== ROUND 1 - {record['number']:02d}. {record['dimension']} =====\n{record['attack']}"
            for record in records
        )
        (self.output_dir / "00_R1_ATTACK_DOSSIER.md").write_text(dossier, encoding="utf-8")

        if not self.cancel_event.is_set() and len(records) == 18:
            for index, record in enumerate(records, 1):
                if self.cancel_event.is_set():
                    break
                dimension = record["dimension"]
                dimension_cn = ALL_DIMENSIONS[index - 1][0]
                description = DIMENSION_DESC_EN.get(dimension_cn, "Independent whole-matter legal review.")
                self.ui(index - 1, f"Round 2: {owner} rereading ({index}/18)", "#7fb3ff")
                prompt = f"""Act as senior counsel for the {owner}. Reread the entire matter below from the perspective of {dimension} ({description}). Then read every Round-1 attack in the complete attack dossier.

Defend, qualify, narrow, reformulate, or if strategically necessary partially concede the selected point. Do not answer only the same-dimension attack: use the entire Round-1 dossier and every relevant fact, argument, and evidence item in the complete matter. Address the strongest attacks rather than easy ones. You may expose contradictions between attacks, rely on other evidence, shift emphasis, or counterattack where professionally justified.

Write a natural advocacy memorandum for a lawyer. Do not return JSON. Do not follow a fixed heading template. Do not mechanically answer a checklist. Explain the best available response and its evidentiary limits. If the current record cannot answer a serious attack, identify exactly what is missing rather than pretending the gap is closed.

SELECTED POINT:
{point}

COMPLETE MATTER:
{self.matter_context}

ALL ROUND-1 ATTACKS:
{dossier}"""
                response, provider, errors = self._call_dimension(prompt, index, 2)
                filename = f"{index:02d}_{_safe_name(dimension)}_R2_Response.md"
                if not response:
                    response = "Round 2 failed.\n\n" + "\n".join(f"- {error}" for error in errors)
                    self.ui(index - 1, "Round 2 failed", self.C["red"])
                else:
                    self.ui(index - 1, f"Both rounds complete via {record['attack_provider']} / {provider}", self.C["teal"])
                (self.output_dir / filename).write_text(f"# {dimension} - Round 2 Response\n\n{response}\n", encoding="utf-8")
                record["response"] = response
                record["response_provider"] = provider
                self.win.after(0, lambda value=18 + index: self.progress.configure(value=value))
                time.sleep(1.2)

        self.records = records
        manifest = [{key: value for key, value in record.items() if key not in ("attack", "response")}
                    for record in records]
        (self.output_dir / "00_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        professional_findings = []
        matrix = []
        for record in records:
            number = int(record.get("number") or 0)
            professional_findings.append({
                "id": f"ASP-{number:03d}",
                "dimension": record.get("dimension"),
                "title": f"{record.get('dimension')} attack on selected point",
                "finding": record.get("attack"),
                "affected_side": owner,
                "factual_basis": point,
                "significance": "Review together with the Round-2 response; materiality requires lawyer assessment",
                "provider": record.get("attack_provider"),
                "model": "Not recorded",
                "source_reference": f"Selected point / Round 1 / dimension {number}",
                "review_status": "ai_generated_unverified",
            })
            matrix.append({
                "issue_id": f"ASP-{number:03d}",
                "dimension": record.get("dimension"),
                "selected_point": point,
                "point_owner": owner,
                "round_1_attack": record.get("attack"),
                "round_1_provider": record.get("attack_provider"),
                "round_2_response": record.get("response"),
                "round_2_provider": record.get("response_provider"),
                "remaining_risk": "Requires lawyer assessment",
                "lawyer_status": "ai_generated_unverified",
            })
        professional_report = build_standard_report(
            "advanced_single_point_2r",
            "advanced_single_point_two_round_opposition",
            self.case_name,
            findings=professional_findings,
            provider_runs=provider_runs_from_records(records, "attack_provider", "response_provider"),
            input_scope={
                "selected_point": point,
                "point_owner": owner,
                "complete_matter_reread_per_call": True,
                "round_1_calls": len(records),
                "round_2_completed": len([record for record in records if record.get("response")]),
                "privacy_boundary": self.privacy_label,
            },
            sections={"attack_response_matrix": matrix},
            limitations=[
                "This workflow stress-tests one selected point and does not replace whole-matter review.",
                "Advocacy output is not a neutral factual or legal conclusion and requires lawyer verification.",
            ],
        )
        write_standard_companions(self.output_dir, "advanced-single-point-2r", professional_report)
        try:
            self.report_path = build_single_point_report(self.output_dir, self.case_name, point, owner, records)
        except Exception as exc:
            self.report_path = None
            self.win.after(0, lambda error=str(exc): messagebox.showerror("Report Failed", error, parent=self.win))
        self.win.after(0, self.finish)

    def ui(self, index, text, _color):
        self.win.after(0, lambda: (self.status_vars[index].set(text), self.summary_var.set(text)))

    def finish(self):
        self.running = False
        self._unlock_parent_ui()
        self.owner_var_widget_state("normal")
        self.point_text.config(state=tk.NORMAL)
        self.start_btn.config(text="Start New Advanced Single-Point 2R", bg="#f2c94c",
                              fg="#101621", state=tk.NORMAL)
        completed = int(self.progress["value"])
        if self.cancel_event.is_set():
            self.summary_var.set(f"Stopped after {completed}/36 calls")
        else:
            self.summary_var.set(f"Complete - {completed}/36 calls")
        if completed >= 36 and self.report_path and self.report_path.exists():
            self.open_btn.config(state=tk.NORMAL, bg="#167d5a", fg="white", cursor="hand2")
        else:
            self.open_btn.config(state=tk.DISABLED, bg="#2b3442", fg="#7f8b99")

    def open_report(self):
        if self.report_path and self.report_path.exists():
            os.startfile(str(self.report_path))

    def close(self):
        if self.running and not messagebox.askyesno(
            "Review In Progress", "Stop after the current model call and close this window?", parent=self.win
        ):
            return
        self.cancel_event.set()
        self._unlock_parent_ui()
        self._unregister_weakness_drop_target()
        self.win.destroy()


def open_advanced_single_point_review(parent, matter_context, provider_routes, case_name="Matter", privacy_label=""):
    return AdvancedSinglePoint2R(parent, matter_context, provider_routes, case_name, privacy_label)
