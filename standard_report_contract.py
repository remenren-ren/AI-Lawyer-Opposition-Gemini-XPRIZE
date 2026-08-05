"""Shared professional report contract for every analysis stage.

This layer preserves the original analysis text while adding a consistent,
machine-readable envelope. It never upgrades AI output to lawyer-approved work.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


SCHEMA_VERSION = "nido-professional-report/1.0"
REVIEW_STATUSES = {
    "ai_generated_unverified",
    "lawyer_review_in_progress",
    "lawyer_confirmed",
    "lawyer_modified",
    "lawyer_rejected",
}

REPORT_TYPE_LABELS = {
    "intake_material_organisation": "Matter Intake and Material Organisation Report",
    "weakness_scan": "Weakness Diagnostic Register",
    "advanced_18d_review": "Independent 18-Dimension Review",
    "contextual_18d_challenge": "Contextual 18-Dimension Challenge",
    "single_point_review": "Single-Issue Analysis Memorandum",
    "single_point_2r": "Single-Issue Attack and Response Matrix",
    "two_round_opposition": "Whole-Matter Attack and Response Matrix",
    "advanced_main_opposition_2r": "Advanced Whole-Matter Opposition Report",
    "advanced_single_point_2r": "Advanced Single-Issue Opposition Report",
    "evidence_index": "Evidence Index and Proof-Gap Register",
    "chronology": "Material Event Chronology",
    "synthetic_analogue": "Synthetic Analogue Analysis Report",
    "tactic_frame_suggestions": "Opponent Tactic Preparation Register",
    "legal_source_pack": "Legal Source Verification Pack",
    "final_lawyer_pack": "Lawyer Working Paper",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> List[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _safe_status(value: Any) -> str:
    status = _text(value) or "ai_generated_unverified"
    return status if status in REVIEW_STATUSES else "ai_generated_unverified"


def make_report_id(report_type: str, matter_name: str, generated_at_utc: str) -> str:
    seed = f"{report_type}|{matter_name}|{generated_at_utc}".encode("utf-8", errors="replace")
    return f"RPT-{hashlib.sha256(seed).hexdigest()[:12].upper()}"


def normalise_provider_run(value: Any) -> Dict[str, str]:
    raw = value if isinstance(value, dict) else {}
    return {
        "provider": _text(raw.get("provider") or raw.get("provider_display_name")) or "Not recorded",
        "model": _text(raw.get("model") or raw.get("model_name")) or "Not recorded",
        "engine_source": _text(raw.get("engine_source") or raw.get("source")) or "Not recorded",
        "run_reference": _text(raw.get("run_reference") or raw.get("dimension") or raw.get("stage")),
    }


def normalise_finding(value: Any, index: int = 1, stage: str = "analysis") -> Dict[str, Any]:
    raw = dict(value) if isinstance(value, dict) else {"finding": value}
    finding_id = _text(raw.get("finding_id") or raw.get("id")) or f"F-{index:03d}"
    evidence = raw.get("evidence_references") or raw.get("evidence") or raw.get("source_references") or []
    if isinstance(evidence, str):
        evidence = [item.strip() for item in re.split(r"[\n;,]", evidence) if item.strip()]
    status = _safe_status(raw.get("review_status") or raw.get("status"))
    return {
        "finding_id": finding_id,
        "analysis_stage": _text(raw.get("analysis_stage")) or stage,
        "dimension": _text(raw.get("dimension")) or "Not assigned",
        "title": _text(raw.get("title") or raw.get("conclusion") or raw.get("weakness")) or f"Finding {index}",
        "finding": _text(raw.get("finding") or raw.get("analysis") or raw.get("weakness") or raw.get("attack")),
        "affected_side": _text(raw.get("affected_side") or raw.get("side")) or "Not assigned",
        "factual_basis": _text(raw.get("factual_basis") or raw.get("relevant_facts") or raw.get("target") or raw.get("targeting")),
        "evidence_references": _list(evidence),
        "significance": _text(raw.get("significance") or raw.get("priority_reason")) or "Materiality requires lawyer assessment",
        "confidence": _text(raw.get("confidence")) or "Not independently scored",
        "provider": _text(raw.get("provider")) or "Not recorded",
        "model": _text(raw.get("model")) or "Not recorded",
        "review_status": status,
        "lawyer_note": _text(raw.get("lawyer_note")),
        "source_reference": _text(raw.get("source_reference") or raw.get("source_label")),
    }


def build_standard_report(
    report_type: str,
    stage: str,
    matter_name: str,
    jurisdiction: str = "Not specified",
    findings: Optional[Iterable[Any]] = None,
    provider_runs: Optional[Iterable[Any]] = None,
    input_scope: Optional[Dict[str, Any]] = None,
    sections: Optional[Dict[str, Any]] = None,
    missing_material: Optional[Iterable[Any]] = None,
    limitations: Optional[Iterable[Any]] = None,
    synthetic: bool = False,
    generated_at_utc: str = "",
) -> Dict[str, Any]:
    if report_type not in REPORT_TYPE_LABELS:
        report_type = "final_lawyer_pack"
    generated = _text(generated_at_utc) or datetime.now(timezone.utc).isoformat(timespec="seconds")
    normalised_findings = [normalise_finding(item, index, stage) for index, item in enumerate(findings or [], 1)]
    runs = []
    seen = set()
    for item in provider_runs or []:
        run = normalise_provider_run(item)
        key = tuple(run.values())
        if key not in seen:
            seen.add(key)
            runs.append(run)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_id": make_report_id(report_type, matter_name, generated),
        "report_type": report_type,
        "report_title": REPORT_TYPE_LABELS[report_type],
        "analysis_stage": _text(stage) or report_type,
        "matter": {
            "name": _text(matter_name) or "Current matter",
            "jurisdiction": _text(jurisdiction) or "Not specified",
            "synthetic_demonstration": bool(synthetic),
        },
        "generated_at_utc": generated,
        "provider_runs": runs or [{
            "provider": "Offline local workflow",
            "model": "No external model recorded",
            "engine_source": "Local application state",
            "run_reference": _text(stage),
        }],
        "input_scope": dict(input_scope or {}),
        "findings": normalised_findings,
        "sections": dict(sections or {}),
        "missing_material": [_text(item) for item in (missing_material or []) if _text(item)],
        "lawyer_verification": {
            "overall_status": "ai_generated_unverified",
            "required_tasks": [
                "Verify all facts and quotations against original source material.",
                "Verify governing law, jurisdiction, current authorities, deadlines and procedural requirements.",
                "Assess materiality, evidence weight, privilege, admissibility and client instructions.",
                "Confirm, modify or reject every material finding before external use.",
            ],
            "lawyer_name": "",
            "reviewed_at": "",
            "final_note": "",
        },
        "limitations": [_text(item) for item in (limitations or []) if _text(item)] or [
            "AI-assisted lawyer reference material only; not legal advice or a final legal opinion.",
            "No fact, evidence item, authority, deadline or filing rule is treated as verified without lawyer review.",
        ],
    }


def render_standard_markdown(report: Dict[str, Any]) -> str:
    value = dict(report or {})
    matter = value.get("matter") or {}
    lines = [
        f"# {value.get('report_title') or 'Professional Analysis Report'}", "",
        f"**Report ID:** {value.get('report_id', '')}",
        f"**Schema:** {value.get('schema_version', SCHEMA_VERSION)}",
        f"**Stage:** {value.get('analysis_stage', '')}",
        f"**Matter:** {matter.get('name', '')}",
        f"**Jurisdiction:** {matter.get('jurisdiction', '')}",
        f"**Synthetic demonstration:** {'YES' if matter.get('synthetic_demonstration') else 'NO'}",
        f"**Generated:** {value.get('generated_at_utc', '')}", "",
        "## Model and Engine Provenance", "",
    ]
    for run in value.get("provider_runs") or []:
        lines.append(
            f"- {run.get('provider', 'Not recorded')} | {run.get('model', 'Not recorded')} | "
            f"{run.get('engine_source', 'Not recorded')} | {run.get('run_reference', '')}"
        )
    lines.extend(["", "## Input Scope", "", "```json", json.dumps(value.get("input_scope") or {}, ensure_ascii=False, indent=2), "```", ""])
    lines.extend(["## Findings Register", ""])
    findings = value.get("findings") or []
    if not findings:
        lines.append("No material finding was recorded. This does not mean the matter has no risk.")
    for item in findings:
        lines.extend([
            f"### {item.get('finding_id')} - {item.get('title')}", "",
            f"- **Dimension:** {item.get('dimension')}",
            f"- **Affected side:** {item.get('affected_side')}",
            f"- **Finding:** {item.get('finding') or 'No narrative supplied'}",
            f"- **Factual basis:** {item.get('factual_basis') or 'Not recorded'}",
            f"- **Evidence references:** {', '.join(item.get('evidence_references') or []) or 'Not recorded'}",
            f"- **Significance:** {item.get('significance')}",
            f"- **Confidence:** {item.get('confidence')}",
            f"- **Provider/model:** {item.get('provider')} / {item.get('model')}",
            f"- **Source reference:** {item.get('source_reference') or 'Not recorded'}",
            f"- **Lawyer review status:** {item.get('review_status')}",
            f"- **Lawyer note:** {item.get('lawyer_note') or 'Not yet reviewed'}", "",
        ])
    for key, content in (value.get("sections") or {}).items():
        lines.extend([f"## {str(key).replace('_', ' ').title()}", ""])
        if isinstance(content, (dict, list)):
            lines.extend(["```json", json.dumps(content, ensure_ascii=False, indent=2), "```", ""])
        else:
            lines.extend([_text(content), ""])
    lines.extend(["## Missing Material", ""])
    lines.extend(f"- {item}" for item in value.get("missing_material") or ["None separately recorded; lawyer must confirm."])
    lawyer = value.get("lawyer_verification") or {}
    lines.extend(["", "## Lawyer Verification", "", f"**Overall status:** {lawyer.get('overall_status', 'ai_generated_unverified')}", ""])
    lines.extend(f"- {item}" for item in lawyer.get("required_tasks") or [])
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in value.get("limitations") or [])
    return "\n".join(lines).rstrip() + "\n"


def write_standard_companions(output_dir: Any, basename: str, report: Dict[str, Any]) -> Dict[str, str]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", _text(basename)).strip("-") or "professional-report"
    json_path = directory / f"{safe}.professional.json"
    md_path = directory / f"{safe}.professional.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    md_path.write_text(render_standard_markdown(report), encoding="utf-8-sig")
    return {"json": str(json_path), "markdown": str(md_path)}


def provider_runs_from_records(records: Iterable[Any], *provider_fields: str) -> List[Dict[str, str]]:
    runs = []
    for record in records or []:
        if not isinstance(record, dict):
            continue
        reference = _text(record.get("dimension") or record.get("review_number") or record.get("number"))
        for field in provider_fields or ("provider",):
            provider = _text(record.get(field))
            if provider:
                runs.append({
                    "provider": provider,
                    "model": _text(record.get(field.replace("provider", "model"))) or "Not recorded",
                    "engine_source": "Recorded model output",
                    "run_reference": f"{reference} / {field}".strip(" /"),
                })
    return runs
