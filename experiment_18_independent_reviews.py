import datetime as dt
import json
import re
import time
from pathlib import Path

from Nido_StrikeOver_Online_EN import ALL_DIMENSIONS, DIMENSION_DESC_EN, DIMENSION_LABELS_EN, LLMClient
from standard_report_contract import build_standard_report, provider_runs_from_records, write_standard_companions


HERE = Path(__file__).resolve().parent
CASE_PATH = Path(r"D:\Users\user\Desktop\张欢案件.txt")
CONFIG_PATH = HERE / "api_profiles.local.json"


def safe_name(value):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_") or "dimension"


def provider_routes():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    routes = []
    for row in config.get("providers", []):
        name = str(row.get("name") or "").strip().lower()
        key = str(row.get("key") or "").strip()
        if name and key and row.get("enabled", True):
            routes.append((name, key))
    routes.sort(key=lambda pair: (pair[0] != "deepseek", pair[0] != "gemini"))
    return routes


def prompt_for(case_text, dimension, description):
    """Build the first-pass prompt: natural legal analysis, not a card schema."""
    return f'''You are senior litigation counsel independently reviewing the complete matter only through the dimension "{dimension}".

Read the ORIGINAL COMPLETE CASE below from beginning to end. Do not use any prior dimension report, pre-extracted argument list, evidence labels such as P1/P2/D1/D2, sentence-level decomposition, or internal software frame.

Think through the entire case exclusively from this dimension. Write the kind of candid internal analysis that an experienced lawyer would give another lawyer after reading the whole file. Follow the facts and the strongest lines of reasoning wherever they lead. Consider both sides, interactions with the rest of the case, useful attacks, possible answers, evidentiary limits, and uncertainties when they genuinely matter.

Dimension description: {description}

Rules:
- English only.
- Write natural connected prose. Do not return JSON.
- Do not fill a template, checklist, card schema, or a fixed series of headings.
- Do not mechanically repeat the dimension name or manufacture symmetry between the two sides.
- Do not invent facts, dates, amounts, documents, clauses, testimony, approvals, statutes, cases, or authorities.
- Distinguish supplied facts from assumptions and missing material.
- Do not create a weakness merely to fill space. It is acceptable to conclude that this dimension adds little.
- Explain concrete case-specific weaknesses in ordinary professional language when you find them.

ORIGINAL COMPLETE CASE:
{case_text}
'''


def extraction_prompt(free_analysis, dimension):
    """Extract only surface-card metadata without rewriting the free analysis."""
    return f'''Read the completed internal legal analysis below. Do not re-analyse the case and do not rewrite the report.

Extract only the genuinely material weakness conclusions already supported by the analysis. These values are used only as labels and short previews for surface cards; the original internal analysis will remain the full card.

Rules:
- English only.
- Do not add a finding that is not present in the internal analysis.
- Keep positive-side and negative-side weaknesses correctly separated.
- "affected_side" means the side whose position is weakened, not the side making the attack.
- "conclusion" must state the substantive case-specific problem directly, without prefixes such as "This card means", "Target", or "Weakness".
- "surface_summary" should be one or two natural sentences explaining the conclusion in the context already stated by the report.
- Do not expose software labels, internal frames, or JSON terminology in the card wording.
- Do not force a fixed number of findings. Return an empty list if the report contains no material weakness.

Review dimension: {dimension}

COMPLETED INTERNAL ANALYSIS:
{free_analysis}

Return strict JSON only:
{{
  "important_weaknesses": [
    {{
      "affected_side": "positive or negative",
      "conclusion": "direct surface-card conclusion",
      "surface_summary": "short natural preview derived from the analysis"
    }}
  ],
  "no_finding_explanation": "brief reason only when no material finding exists"
}}'''


def markdown_report(number, result, provider):
    dimension = result.get("dimension", "Unknown Dimension")
    lines = [
        f"# {number:02d}. {dimension}",
        "",
        f"Provider: {provider}",
        "",
        "## Independent Internal Analysis",
        str(result.get("full_dimension_report") or ""),
        "",
        "## Extracted Surface-Card Index",
    ]
    weaknesses = result.get("important_weaknesses") or []
    if not weaknesses:
        lines.extend(["No material weakness selected.", "", str(result.get("no_finding_explanation") or "")])
    for index, item in enumerate(weaknesses, 1):
        lines.extend([
            "",
            f"### {index}. {item.get('conclusion', 'Weakness')}",
            f"Affected side: {item.get('affected_side', '')}",
            "",
            str(item.get("surface_summary") or ""),
        ])
    return "\n".join(lines).strip() + "\n"


def main():
    raw_case = CASE_PATH.read_bytes()
    try:
        case_text = raw_case.decode("utf-8-sig")
    except UnicodeDecodeError:
        case_text = raw_case.decode("gb18030")
    routes = provider_routes()
    if not routes:
        raise RuntimeError("No configured provider with an API key was found.")

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = HERE / "runs" / f"independent_18_dimension_experiment_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "00_original_case.txt").write_text(case_text, encoding="utf-8-sig")

    index_lines = [
        "# Zhang Huan Case - 18 Independent Whole-Case Dimension Reviews",
        "",
        "Each dimension independently reread the complete original case. No prior report or preprocessed side frame was supplied.",
        "",
    ]
    manifest = []

    for number, (dimension_cn, _description_cn) in enumerate(ALL_DIMENSIONS, 1):
        dimension = DIMENSION_LABELS_EN.get(dimension_cn, dimension_cn)
        description = DIMENSION_DESC_EN.get(dimension_cn, "Independent whole-case legal review.")
        result = None
        used_provider = ""
        errors = []
        for provider_index, (provider, key) in enumerate(routes):
            try:
                client = LLMClient(provider, key, personality_idx=provider_index)
                free_analysis = client.chat_text(prompt_for(case_text, dimension, description), temperature=0.6, max_tokens=6000)
                if not str(free_analysis or "").strip():
                    raise RuntimeError("free-form internal analysis was empty")
                extracted = client.chat_json(extraction_prompt(free_analysis, dimension), temperature=0.15, max_tokens=2200)
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
                    "analysis_mode": "free_form_then_surface_extraction",
                }
                used_provider = provider
                break
            except Exception as exc:
                errors.append(f"{provider}: {exc}")
                time.sleep(1.5)

        filename = f"{number:02d}_{safe_name(dimension)}"
        if result is None:
            failure = {"dimension": dimension, "errors": errors}
            (output_dir / f"{filename}.json").write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
            (output_dir / f"{filename}.md").write_text(
                f"# {number:02d}. {dimension}\n\nReview failed.\n\n" + "\n".join(f"- {error}" for error in errors),
                encoding="utf-8",
            )
            index_lines.append(f"- {number:02d}. {dimension}: FAILED")
            manifest.append(failure)
            continue

        result["dimension"] = dimension
        result["provider"] = used_provider
        result["review_number"] = number
        (output_dir / f"{filename}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (output_dir / f"{filename}.md").write_text(markdown_report(number, result, used_provider), encoding="utf-8")
        weakness_count = len(result.get("important_weaknesses") or [])
        index_lines.append(f"- {number:02d}. [{dimension}]({filename}.md): {weakness_count} important weakness(es), provider {used_provider}")
        manifest.append(result)
        time.sleep(1.5)

    (output_dir / "00_INDEX.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    (output_dir / "00_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    findings = []
    reports = []
    for record in manifest:
        if record.get("errors"):
            continue
        reports.append({"dimension": record.get("dimension"), "provider": record.get("provider"), "full_analysis": record.get("full_dimension_report")})
        for weakness in record.get("important_weaknesses") or []:
            item = dict(weakness) if isinstance(weakness, dict) else {"finding": weakness}
            item.update({
                "dimension": record.get("dimension"), "provider": record.get("provider"),
                "source_reference": f"Independent review {record.get('review_number')}",
                "review_status": "ai_generated_unverified",
            })
            findings.append(item)
    professional_report = build_standard_report(
        "advanced_18d_review", "independent_18_dimension_experiment", CASE_PATH.stem,
        findings=findings, provider_runs=provider_runs_from_records(manifest, "provider"),
        input_scope={"complete_original_case_reread_per_dimension": True, "requested_dimensions": 18},
        sections={"dimension_reports": reports},
    )
    write_standard_companions(output_dir, "independent-18d-experiment", professional_report)
    print(str(output_dir))


if __name__ == "__main__":
    main()
