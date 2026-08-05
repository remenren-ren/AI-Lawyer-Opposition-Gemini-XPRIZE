"""Headless bridge into the existing StrikeOver online lawyer core.

The competition reception window calls this module instead of opening the
Tkinter dual-line interface. The recording can still open that unchanged GUI to
show reviewers how the same dimensions and model routes work internally.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from Nido_StrikeOver_Online_EN import (
    ALL_DIMENSIONS,
    DIMENSION_LABELS_EN,
    LLMClient,
    is_non_material_weakness_display_record,
)


HERE = Path(__file__).resolve().parent
PROVIDER_CONFIG = HERE / "api_profiles.local.json"


class LawyerSoftwareBridge:
    def __init__(self, provider_config: Path = PROVIDER_CONFIG):
        self.provider_config = Path(provider_config)

    def verified_routes(self) -> List[Dict[str, str]]:
        try:
            payload = json.loads(self.provider_config.read_text(encoding="utf-8-sig"))
        except Exception:
            return []
        routes = []
        for row in payload.get("providers") or []:
            key = str(row.get("key") or "").strip()
            if key and bool(row.get("verified")) and bool(row.get("enabled", True)):
                routes.append({"name": str(row.get("name") or "").strip().lower(), "key": key})
        routes.sort(key=lambda item: (item["name"] != "gemini", item["name"] != "deepseek"))
        return routes

    def available(self) -> bool:
        return bool(self.verified_routes())

    def call_json(
        self,
        prompt: str,
        system_instruction: str,
        excluded_providers=None,
    ) -> Dict[str, Any]:
        """Run a reception JSON task through the lawyer software's failover routes."""
        excluded = {str(name or "").strip().lower() for name in (excluded_providers or [])}
        routes = [route for route in self.verified_routes() if route["name"] not in excluded]
        errors = []
        combined_prompt = f"SYSTEM ROLE:\n{system_instruction}\n\nTASK:\n{prompt}"
        for index, route in enumerate(routes):
            client = LLMClient(route["name"], route["key"], personality_idx=index)
            result = client.chat_json(combined_prompt, temperature=0.2, max_tokens=4000)
            if isinstance(result, dict) and not result.get("_error"):
                result["provider_mode"] = f"lawyer-core-failover:{route['name']}"
                return result
            errors.append(
                f"{route['name']}: "
                f"{result.get('_error', 'invalid response') if isinstance(result, dict) else 'invalid response'}"
            )
        raise RuntimeError("; ".join(errors)[:800] or "No unused verified provider route is available.")

    def organise_case(self, record: Dict[str, Any]) -> Dict[str, Any]:
        routes = self.verified_routes()
        if not routes:
            raise RuntimeError("No verified provider is configured in the lawyer software.")
        prompt = f"""You are the case-material classification function used by the StrikeOver online lawyer software.

Read the complete client conversation and available evidence carefully. Extract and organise the complete matter.
Do not conduct opposition, scan for weaknesses, evaluate merits, recommend strategy, predict outcomes, or give legal advice.
Distinguish supplied facts, allegations, documents, and inference. If the other side's position is not supplied, label any possible position as inference.

CLIENT CONVERSATION:
{json.dumps(record.get('intake_messages') or [], ensure_ascii=False)}

EVIDENCE EXTRACTS:
{json.dumps(record.get('evidence_context') or [], ensure_ascii=False)[:60000]}

Return strict JSON only with the same case structure accepted by the lawyer interface:
{{"case_name":"short case name","jurisdiction":"court or jurisdiction","background":"complete neutral factual background","pos_args":["positive/client-side argument"],"pos_ev":["positive/client-side evidence"],"neg_args":["negative/other-side argument"],"neg_ev":["negative/other-side evidence"],"scope_notice":"case-material organisation only; lawyer verification required"}}"""
        errors = []
        for index, route in enumerate(routes):
            client = LLMClient(route["name"], route["key"], personality_idx=index)
            result = client.chat_json(prompt, temperature=0.3, max_tokens=4000)
            if isinstance(result, dict) and not result.get("_error"):
                result["engine_source"] = "StrikeOver Online shared lawyer core"
                result["provider"] = route["name"]
                return result
            errors.append(f"{route['name']}: {result.get('_error', 'invalid response') if isinstance(result, dict) else 'invalid response'}")
        raise RuntimeError("; ".join(errors)[:600] or "All lawyer-software providers failed.")

    @staticmethod
    def _matter_context(record: Dict[str, Any]) -> str:
        report = record.get("free_report") or {}
        def lines(value):
            if isinstance(value, list):
                return "\n".join(str(item) for item in value)
            return str(value or "")
        return (
            f"CASE NAME: {report.get('case_name', '')}\nJURISDICTION: {report.get('jurisdiction', '')}\n\n"
            f"FULL CASE:\n{report.get('background', '')}\n\n"
            f"POSITIVE ARGUMENTS:\n{lines(report.get('pos_args'))}\n\n"
            f"POSITIVE EVIDENCE:\n{lines(report.get('pos_ev'))}\n\n"
            f"NEGATIVE ARGUMENTS:\n{lines(report.get('neg_args'))}\n\n"
            f"NEGATIVE EVIDENCE:\n{lines(report.get('neg_ev'))}"
        )

    @staticmethod
    def _dimension_prompt(batch: List[str], context: str) -> str:
        return f'''Read the complete legal matter and both side frames directly before analysing it. Do not use sentence-by-sentence extraction, pre-built templates, or internal software labels.

Act as one independent legal weakness reviewer for each listed dimension. Diagnose the matter only from that dimension's professional perspective. For every dimension, identify zero or more genuinely material weaknesses across the whole matter. Return no finding when that dimension reveals no useful weakness. Do not force equal counts.

Every value must be English. Each finding must state the weakness and explain why it exists by reference to the supplied case facts. Diagnose only. Do not provide lawyer questions, attack scripts, strategy, recommendations, cures, response language, preparation steps, or everyday examples. Do not invent facts, dates, amounts, documents, clauses, approvals, authorities, or quotations.

DIMENSIONS FOR THIS BATCH:
{json.dumps(batch, ensure_ascii=False)}

COMPLETE MATTER AND SIDE FRAMES:
{context}

Return strict JSON only:
{{"dimensions":[{{"dimension":"one listed English dimension","findings":[{{"conclusion":"short plain-language surface-card conclusion","analysis":"natural connected explanation of the weakness, its factual basis, significance, and limits from this dimension's perspective","relevant_facts":"specific supplied facts","affected_side":"positive, negative, or both","confidence":"high, medium, or low"}}]}}]}}'''

    def review_18_dimensions(self, record: Dict[str, Any]) -> Dict[str, Any]:
        routes = self.verified_routes()
        if not routes:
            raise RuntimeError("No verified provider is configured in the lawyer software.")
        dimensions = [DIMENSION_LABELS_EN.get(name, name) for name, _description in ALL_DIMENSIONS]
        context = self._matter_context(record)
        collected = {name: [] for name in dimensions}
        provider_errors = []
        for index, route in enumerate(routes):
            client = LLMClient(route["name"], route["key"], personality_idx=index)
            pending = [list(dimensions)]
            while pending:
                batch = pending.pop(0)
                result = client.chat_json(self._dimension_prompt(batch, context), temperature=0.3, max_tokens=6500)
                rows = result.get("dimensions") if isinstance(result, dict) and not result.get("_error") else None
                if not isinstance(rows, list) or not rows:
                    error = result.get("_error", "invalid structured response") if isinstance(result, dict) else "invalid structured response"
                    if len(batch) > 1 and "429" not in str(error):
                        midpoint = (len(batch) + 1) // 2
                        pending = [batch[:midpoint], batch[midpoint:]] + pending
                        continue
                    provider_errors.append(f"{route['name']}: {error}")
                    break
                for dimension_row in rows:
                    if not isinstance(dimension_row, dict):
                        continue
                    returned_name = str(dimension_row.get("dimension") or "").strip()
                    matched = next((name for name in dimensions if name.casefold() == returned_name.casefold()), None)
                    if not matched:
                        continue
                    for finding in dimension_row.get("findings") or []:
                        if not isinstance(finding, dict):
                            continue
                        item = dict(finding)
                        item["dimension"] = matched
                        item["provider"] = route["name"]
                        if str(item.get("conclusion") or "").strip() and not is_non_material_weakness_display_record(item):
                            collected[matched].append(item)
        if not any(collected.values()) and provider_errors:
            raise RuntimeError("; ".join(provider_errors)[:800])
        rows = [{"dimension": name, "findings": collected[name]} for name in dimensions]
        return {
            "dimensions": rows,
            "analysis_limits": provider_errors,
            "engine_source": "StrikeOver Online shared 18-dimension lawyer core",
            "providers_used": [route["name"] for route in routes],
        }
