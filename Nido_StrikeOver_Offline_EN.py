#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nido StrikeOver Offline 2R Clean
干净离线版 + Nido 本地两轮攻防内核。

设计目的：
- 保留旧版“案件信息 / 正方画框 / 反方画框 / 多 Tab 输出”的工作手感。
- 不修改旧版对照文件。
- 默认本地解析、本地攻防，不上传案件全文。
"""

import datetime as _dt
import copy
import ctypes
import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:
    DND_FILES = "DND_Files"
    TkinterDnD = None

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
VENDOR_DIR = HERE / ".vendor"
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))

try:
    from nido_strikeover_v4_function_lawyer_gui import (
        DIMENSIONS,
        NidoFunctionLawyerEngine,
        extract_case_file_text,
        short_hash,
    )
except Exception as exc:
    raise RuntimeError(
        "缺少 Nido v4 内核文件，请确认 nido_strikeover_v4_function_lawyer_gui.py "
        "和本文件放在同一目录。"
    ) from exc

try:
    from offline_professional_report import (
        REPORT_TYPES as PROFESSIONAL_REPORT_TYPES,
        build_professional_docx,
        build_professional_markdown,
        build_professional_pdf,
        record_as_json,
    )
except Exception as exc:
    raise RuntimeError(
        "Missing offline_professional_report.py. Keep it beside Nido_StrikeOver_Offline_EN.py."
    ) from exc

from standard_report_contract import (
    build_standard_report,
    render_standard_markdown,
    write_standard_companions,
)


APP_TITLE = "Nido StrikeOver Offline EN - Lawyer Opposition Assistant"
API_CONFIG_FILE = HERE / "api_config.local.json"
API_PROFILES_FILE = HERE / "api_profiles.local.json"
SESSION_FILE = HERE / "cloud_session.local.json"
PERSONAL_SOP_CANDIDATES_FILE = HERE / "personal_sop_candidates.json"
PERSONAL_SOP_APPROVED_FILE = HERE / "personal_sop_approved.jsonl"
PERSONAL_SOP_ROOT = HERE / "personal_sop"
PERSONAL_SOP_LANGUAGE_FILE = PERSONAL_SOP_ROOT / "language_rhetoric.jsonl"
PERSONAL_SOP_CASE_FILE = PERSONAL_SOP_ROOT / "case_decomposition.jsonl"
PERSONAL_SOP_SNAPSHOT_DIR = PERSONAL_SOP_ROOT / "snapshots"
PERSONAL_SOP_CALL_LOG_FILE = PERSONAL_SOP_ROOT / "sop_call_log.jsonl"
PERSONAL_SOP_TRAINING_DIR = PERSONAL_SOP_ROOT / "training_runs"

DIMENSION_LABELS_EN = {
    "事实质疑": "Fact Challenge",
    "法律适用": "Legal Application",
    "先例对抗": "Precedent Attack",
    "逻辑漏洞": "Logic Gap",
    "程序瑕疵": "Procedural Defect",
    "损害因果关系": "Damage Causation",
    "量化争议": "Quantum Dispute",
    "举证责任": "Burden of Proof",
    "法律文本解释": "Legal Text Interpretation",
    "过失比较": "Comparative Fault",
    "公共政策": "Public Policy",
    "逆向思维": "Reverse Reasoning",
    "跨法域武器": "Cross-Jurisdiction Weapon",
    "跨Jurisdiction武器": "Cross-Jurisdiction Weapon",
    "反事实推演": "Counterfactual Reasoning",
    "比例原则检验": "Proportionality Test",
    "叙事解构": "Narrative Deconstruction",
    "系统性风险放大": "Systemic Risk Amplification",
    "沉默证据": "Missing Evidence",
}

DIMENSION_DESC_EN = {
    "事实质疑": "tests factual reliability, completeness, and source integrity",
    "法律适用": "tests whether the legal rule applies to this jurisdiction and fact pattern",
    "先例对抗": "distinguishes cited authority and searches for adverse precedent",
    "逻辑漏洞": "finds breaks in reasoning, causation, and inference",
    "程序瑕疵": "checks procedure, standing, jurisdiction, limitation, and admissibility",
    "损害因果关系": "separates breach, causation, contribution, and loss",
    "量化争议": "challenges the calculation and proof of claimed amounts",
    "举证责任": "puts each assertion back onto the party who must prove it",
    "法律文本解释": "tests the wording, scope, and exceptions in legal text",
    "过失比较": "allocates fault and intervening conduct",
    "公共政策": "tests whether the proposed outcome creates wider policy problems",
    "逆向思维": "turns the opponent's theory back against them",
    "跨法域武器": "uses external rules only as a boundary check, not as binding law",
    "跨Jurisdiction武器": "uses external rules only as a boundary check, not as binding law",
    "反事实推演": "tests alternative factual paths and causes",
    "比例原则检验": "tests whether remedy and responsibility are proportionate",
    "叙事解构": "breaks story-like assertions back into evidence and legal elements",
    "系统性风险放大": "shows the systemic risk created by accepting the opponent's route",
    "沉默证据": "uses missing records and silence as a proof weakness",
}

PROVIDER_PRESETS = {
    "gemini": {
        "label": "Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "model": "gemini-2.5-flash",
        "kind": "gemini_native",
    },
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "kind": "openai_compatible",
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o",
        "kind": "openai_compatible",
    },
    "claude": {
        "label": "Claude",
        "base_url": "https://api.anthropic.com/v1",
        "model": "claude-sonnet-4-20250514",
        "kind": "anthropic",
    },
    "groq": {
        "label": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "kind": "openai_compatible",
    },
    "custom": {
        "label": "自定义兼容接口",
        "base_url": "",
        "model": "",
        "kind": "openai_compatible",
    },
}

JURISDICTION_OPTIONS = [
    "Australia / AU - Commonwealth",
    "Australia / AU - NSW",
    "Australia / AU - VIC",
    "Australia / AU - QLD",
    "Australia / AU - WA",
    "Australia / AU - SA",
    "Australia / AU - TAS",
    "Australia / AU - ACT",
    "Australia / AU - NT",
    "United States / US - Federal",
    "United States / US - California / CA",
    "United States / US - New York / NY",
    "United States / US - Texas / TX",
    "United States / US - Florida / FL",
    "United Kingdom / UK",
    "European Union / EU",
    "China / CN",
    "Custom / User Provided",
]

LEGAL_FRAMEWORK_PACKS = {
    "Australia / AU": {
        "case_name": "澳洲Jurisdiction攻防模板 - 通用攻防底稿",
        "case_text": (
            "【Jurisdiction攻防模板：Australia / AU】\n"
            "用途：在尚未导入具体案件前，先加载澳洲Jurisdiction的常见争点、证据路径和攻防准备框架。\n"
            "提示：本模板不是正式法律意见，不替代律师对最新法规、判例、州/领地规则和客户事实的复核。\n\n"
            "常见路径：合同成立与解释、Australian Consumer Law 消费者保证、误导或欺骗行为、"
            "公平交易/平台规则、Burden of Proof、合理通知、补救比例、Damage Causation、证据原始性与连续性。\n"
            "常见材料：合同/订单页面、条款提示、聊天记录、付款记录、物流签收、照片/视频、"
            "第三方鉴定、商家质检、平台规则、监管沟通记录。"
        ),
        "pos_args": (
            "1. 主张方应先锁定合同、消费者保证、误导行为或侵权等具体法律路径。\n"
            "2. 主张方应证明关键事实发生时间、主体对应关系和证据连续性。\n"
            "3. 若涉及消费者争议，应说明商品/服务未达到合理期待及补救请求为何相称。\n"
            "4. 若涉及合同条款，应说明条款是否已合理提示、是否清楚、是否被接受。"
        ),
        "pos_ev": (
            "[P1] 订单/合同/网页条款：证明交易基础与提示内容。\n"
            "[P2] 聊天记录/通知记录：证明通知时间、承诺、拒绝或争议形成。\n"
            "[P3] 照片/视频/鉴定：证明瑕疵、损害或关键事实。\n"
            "[P4] 付款、物流、签收和平台记录：证明时间线和履行状态。"
        ),
        "neg_args": (
            "1. 攻击对方是否把一般消费者保护主张直接跳到最终补救。\n"
            "2. 攻击瑕疵/损害是否在交付或责任节点已经存在。\n"
            "3. 攻击证据是否原始、连续、未剪辑、能排除替代原因。\n"
            "4. 攻击补救是否过度，是否存在维修、折价、部分补偿等替代路径。"
        ),
        "neg_ev": (
            "[D1] 原始条款和提示页面：用于证明明示规则和接受。\n"
            "[D2] 质检/交付/物流记录：用于切断交付前责任。\n"
            "[D3] 对方使用、迟延通知或退货历史：用于比较过失和诚信攻击。\n"
            "[D4] 替代原因材料：用于攻击因果链。"
        ),
    },
    "United Kingdom / UK": {
        "case_name": "英国Jurisdiction攻防模板 - 通用攻防底稿",
        "case_text": (
            "【Jurisdiction攻防模板：United Kingdom / UK】\n"
            "用途：预置英国合同、消费者和证据攻防路径。提示：需由律师复核最新法规、判例和事实。\n\n"
            "常见路径：contract formation、Consumer Rights Act 2015、misrepresentation、unfair terms、"
            "notice/reasonable time、remedies、causation、evidence authenticity。"
        ),
        "pos_args": "1. 锁定合同成立、消费者权利或误述路径。\n2. 证明条款、通知、瑕疵和损害的时间线。\n3. 说明补救方式与违约/瑕疵程度相称。",
        "pos_ev": "[P1] Contract/order/terms。\n[P2] Communication and notice records。\n[P3] Photos/videos/expert evidence。\n[P4] Payment and delivery records。",
        "neg_args": "1. 攻击合同要约/承诺/对价/确定性。\n2. 攻击消费者权利前提和合理通知。\n3. 攻击证据原始性、连续性和替代原因。\n4. 攻击补救比例过度。",
        "neg_ev": "[D1] Terms and notice evidence。\n[D2] Delivery/inspection records。\n[D3] Alternative cause materials。\n[D4] Mitigation and proportionality evidence。",
    },
    "United States / US": {
        "case_name": "美国Jurisdiction攻防模板 - 通用攻防底稿",
        "case_text": (
            "【Jurisdiction攻防模板：United States / US】\n"
            "用途：预置美国合同、消费者、证据与损害攻防路径。提示：美国规则高度州法化，必须选择具体州并复核最新规则。\n\n"
            "常见路径：contract formation、UCC goods dispute、consumer protection、misrepresentation、"
            "notice, warranty, causation, mitigation, damages, evidence authentication。"
        ),
        "pos_args": "1. 锁定州法、合同/UCC/消费者保护路径。\n2. 证明warranty、notice、breach和damages。\n3. 说明补救和损害计算。",
        "pos_ev": "[P1] Contract/order/terms。\n[P2] Notice and communication。\n[P3] Inspection/expert/photos。\n[P4] Payment/delivery/damages records。",
        "neg_args": "1. 攻击州法适用和构成要件。\n2. 攻击notice是否及时、warranty是否适用。\n3. 攻击causation、mitigation和damages计算。\n4. 攻击证据认证和 hearsay/可靠性问题。",
        "neg_ev": "[D1] Terms and disclaimers。\n[D2] Inspection/delivery/use records。\n[D3] Alternative cause and mitigation evidence。\n[D4] Damages calculation challenge。",
    },
    "European Union / EU": {
        "case_name": "欧盟Jurisdiction攻防模板 - 通用攻防底稿",
        "case_text": (
            "【Jurisdiction攻防模板：European Union / EU】\n"
            "用途：预置欧盟消费者、数据、平台和合同争议攻防路径。提示：需继续选择成员国本地法并复核最新规则。\n\n"
            "常见路径：consumer rights、digital services/platform rules、GDPR/data handling、unfair terms、"
            "contract performance、proportional remedies、evidence and burden。"
        ),
        "pos_args": "1. 锁定欧盟层面规则和成员国具体实施规则。\n2. 证明消费者权利、数据处理、平台规则或合同履行问题。\n3. 说明请求补救的必要性和比例。",
        "pos_ev": "[P1] Contract/platform terms。\n[P2] Data/process logs。\n[P3] Notice/communication。\n[P4] Damage/remedy evidence。",
        "neg_args": "1. 攻击欧盟规则与成员国法的连接是否准确。\n2. 攻击数据/消费者/平台主张的构成前提。\n3. 攻击证据来源、比例和替代补救。",
        "neg_ev": "[D1] Local law implementation materials。\n[D2] Compliance logs。\n[D3] Alternative cause/remedy evidence。\n[D4] Consent/notice records。",
    },
    "China / CN": {
        "case_name": "中国Jurisdiction攻防模板 - 通用攻防底稿",
        "case_text": (
            "【Jurisdiction攻防模板：China / CN】\n"
            "用途：预置中国合同、消费者权益、侵权、证据和平台争议攻防路径。提示：需由律师复核最新法律法规、司法解释和地方裁判尺度。\n\n"
            "常见路径：合同成立与履行、格式条款提示、消费者权益保护、产品质量、侵权责任、Burden of Proof、"
            "电子数据真实性、平台规则、损害与因果关系。"
        ),
        "pos_args": "1. 锁定合同、消费者、产品质量或侵权路径。\n2. 证明承诺、履行、瑕疵、通知、损害和因果关系。\n3. 说明电子数据和平台记录的证明力。",
        "pos_ev": "[P1] 合同/订单/条款页面。\n[P2] 聊天记录/通知/平台记录。\n[P3] 照片视频/鉴定/质检。\n[P4] 付款、物流、签收、损害材料。",
        "neg_args": "1. 攻击格式条款、通知、瑕疵发生时间和Burden of Proof。\n2. 攻击电子数据真实性、完整性和关联性。\n3. 攻击因果链、过错比例和补救过度。",
        "neg_ev": "[D1] items款提示和同意记录。\n[D2] 出库/质检/物流签收。\n[D3] 使用介入、迟延通知、替代原因。\n[D4] 损害金额和比例反证。",
    },
    "Custom / User Provided": {
        "case_name": "自定义Jurisdiction攻防模板 - 待用户补充",
        "case_text": (
            "【Jurisdiction攻防模板：Custom / User Provided】\n"
            "用途：当案件所在国家、州、省或专业领域不在预置列表内时，先建立空框架。\n"
            "请用户或律所本地资料库补充：适用法律、关键构成要件、证明责任、程序规则、常用证据和本地禁忌。"
        ),
        "pos_args": "1. 补充本Jurisdiction的主张路径。\n2. 补充本Jurisdiction的构成要件。\n3. 补充本Jurisdiction的证明责任和救济边界。",
        "pos_ev": "[P1] 本Jurisdiction适用法律。\n[P2] 本Jurisdiction判例/监管材料。\n[P3] 事实证据和程序材料。",
        "neg_args": "1. 攻击对方Jurisdiction选择是否正确。\n2. 攻击构成要件、程序门槛和证据证明力。\n3. 攻击补救比例和替代原因。",
        "neg_ev": "[D1] 反面法规/判例。\n[D2] 程序和证据缺口。\n[D3] 替代原因和比例材料。",
    },
}

def _english_framework_pack(jurisdiction, focus):
    return {
        "case_name": f"{jurisdiction} - General Jurisdiction Preparation Frame",
        "case_text": (
            f"[Jurisdiction Preparation Frame: {jurisdiction}]\n"
            "Purpose: establish a jurisdiction-specific starting frame before a particular matter is imported.\n"
            "This is not legal advice and does not replace lawyer review of current legislation, authorities, "
            "procedural rules, and the client's facts.\n\n"
            f"Primary review areas: {focus}.\n"
            "Common materials: contracts, terms, notices, communications, payment records, delivery records, "
            "photographs, video, expert material, platform records, and procedural documents."
        ),
        "pos_args": (
            "1. Identify the precise statutory, contractual, consumer, tort, or procedural basis of the claim.\n"
            "2. Match every required legal element to a dated fact and a reliable source.\n"
            "3. Establish notice, performance, breach, causation, loss, and the requested remedy.\n"
            "4. Confirm that the requested remedy is available and proportionate in this jurisdiction."
        ),
        "pos_ev": (
            "[P1] Current legislation, binding authorities, and applicable contractual terms.\n"
            "[P2] Original communications, notices, payment, delivery, and performance records.\n"
            "[P3] Photographs, video, expert reports, inspection records, and loss calculations."
        ),
        "neg_args": (
            "1. Test whether the correct jurisdiction and current legal rule have been selected.\n"
            "2. Challenge any missing element, late notice, unsupported factual step, or proof gap.\n"
            "3. Test authenticity, completeness, continuity, causation, and alternative explanations.\n"
            "4. Challenge excessive remedies and identify repair, reduction, mitigation, or other alternatives."
        ),
        "neg_ev": (
            "[D1] Contrary legislation, authorities, terms, exclusions, and notice requirements.\n"
            "[D2] Original inspection, delivery, use, performance, and communication records.\n"
            "[D3] Alternative-cause, mitigation, proportionality, and competing loss evidence."
        ),
    }


LEGAL_FRAMEWORK_PACKS = {
    "Australia / AU": _english_framework_pack(
        "Australia / AU",
        "contract formation and variation, Australian Consumer Law, consumer guarantees, misleading conduct, burden of proof, causation, and proportionate remedies",
    ),
    "United Kingdom / UK": _english_framework_pack(
        "United Kingdom / UK",
        "contract formation, Consumer Rights Act 2015, misrepresentation, unfair terms, notice, causation, and remedies",
    ),
    "United States / US": _english_framework_pack(
        "United States / US",
        "the selected state law, contract formation, UCC issues where applicable, warranties, consumer protection, evidence authentication, causation, and damages",
    ),
    "European Union / EU": _english_framework_pack(
        "European Union / EU",
        "EU rules and member-state implementation, consumer rights, digital services, data handling, unfair terms, burden of proof, and proportionate remedies",
    ),
    "China / CN": _english_framework_pack(
        "China / CN",
        "contract formation and performance, standard terms, consumer protection, product quality, tort liability, electronic evidence, causation, and remedies",
    ),
    "Custom / User Provided": _english_framework_pack(
        "Custom / User Provided",
        "user-supplied governing law, legal elements, burden of proof, procedural thresholds, local evidence rules, and available remedies",
    ),
}


OFFICIAL_LEGAL_SOURCE_PACKS = {
    "Australia / AU": [
        {
            "name": "Federal Register of Legislation API",
            "level": "Commonwealth",
            "url": "https://api.prod.legislation.gov.au/swagger/v1/swagger.json",
            "note": "澳洲联邦法律官方 API 定义；用于后续按 Act/Instrument 查询最新版本。",
            "kind": "json",
        },
        {
            "name": "Federal Register of Legislation API base",
            "level": "Commonwealth",
            "url": "https://api.prod.legislation.gov.au/v1/",
            "note": "澳洲联邦法律官方 API base endpoint。",
            "kind": "index",
        },
        {
            "name": "Australian Consumer Law current legislation",
            "level": "Commonwealth / ACL",
            "url": "https://consumer.gov.au/index.php/australian-consumer-law/legislation",
            "note": "Australian Consumer Law 当前法律入口与官方说明。",
            "kind": "html",
        },
        {
            "name": "NSW legislation official site guide",
            "level": "NSW",
            "url": "https://pco.nsw.gov.au/accessing-legislation.html",
            "note": "NSW legislation 官方访问入口说明。",
            "kind": "html",
        },
        {
            "name": "Queensland Legislation API",
            "level": "QLD",
            "url": "https://www.legislation.qld.gov.au/api",
            "note": "Queensland legislation API 服务说明；部分 API 需要注册。",
            "kind": "html",
        },
    ],
}


class CaseSearchEngine:
    def __init__(self):
        self.log = []
        self.cache = {}

    def search(self, query, jurisdiction=""):
        full_query = f"{query} {jurisdiction} case law judgment court".strip()
        key = short_hash(full_query)
        if key in self.cache:
            return self.cache[key]
        self.log = []
        engines = []
        j = jurisdiction.lower()
        if any(x in j for x in ["australia", "nsw", "vic", "qld", "wa", "tas", "act", "nt"]):
            engines.append(("AustLII", self._austlii))
        engines.append(("DuckDuckGo", self._ddg))
        for name, fn in engines:
            try:
                result = fn(full_query)
                if result.get("results"):
                    result.update({"source": name, "verified": True, "query": full_query})
                    self.cache[key] = result
                    self.log.append(f"{name}: found {len(result['results'])}")
                    return result
            except Exception as exc:
                self.log.append(f"{name}: {str(exc)[:90]}")
        result = {"results": [], "source": "no verified result", "verified": False, "query": full_query, "log": self.log}
        self.cache[key] = result
        return result

    def _open_text(self, url, timeout=12):
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 NidoStrikeOver/2R"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        return raw.decode("utf-8", errors="replace")

    def _austlii(self, query):
        url = "https://www.austlii.edu.au/cgi-bin/searchdb.pl?" + urllib.parse.urlencode({
            "method": "auto",
            "query": query,
            "meta": "/au",
            "results": "10",
        })
        html = self._open_text(url)
        results = []
        for m in re.finditer(r'<li[^>]*>\s*<a\s+href="([^"]+)"[^>]*>([^<]{5,})</a>\s*-?\s*([^<]{0,160})', html, re.I):
            href = m.group(1)
            if href.startswith("/"):
                href = "https://www.austlii.edu.au" + href
            title = re.sub(r"\s+", " ", m.group(2)).strip()
            snippet = re.sub(r"\s+", " ", m.group(3)).strip()
            results.append({"title": title, "snippet": snippet, "url": href})
            if len(results) >= 8:
                break
        if not results:
            raise RuntimeError("AustLII returned no parsed results")
        return {"results": results}

    def _ddg(self, query):
        url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode({
            "q": query,
            "format": "json",
            "no_html": "1",
            "skip_disambig": "1",
        })
        data = json.loads(self._open_text(url))
        results = []
        if data.get("Abstract"):
            results.append({
                "title": data.get("Heading", ""),
                "snippet": data.get("Abstract", ""),
                "url": data.get("AbstractURL", ""),
            })
        for item in data.get("RelatedTopics", [])[:8]:
            if isinstance(item, dict) and item.get("Text"):
                results.append({
                    "title": item.get("Text", "")[:90],
                    "snippet": item.get("Text", ""),
                    "url": item.get("FirstURL", ""),
                })
        if not results:
            raise RuntimeError("DuckDuckGo returned no results")
        return {"results": results[:8]}

    @staticmethod
    def format_for_prompt(search_result):
        if not search_result.get("verified") or not search_result.get("results"):
            return "无已验证案例搜索结果；不得编造案例名称，只能用一般法律原则或律师已确认材料。"
        lines = [
            f"真实案例搜索结果来源：{search_result.get('source', '')}",
            "关键约束：只能引用下列结果中明确出现的案例名称。",
        ]
        for idx, item in enumerate(search_result.get("results", [])[:8], 1):
            lines.append(f"[{idx}] {item.get('title', '')}")
            if item.get("snippet"):
                lines.append(f"摘要：{item.get('snippet', '')}")
            if item.get("url"):
                lines.append(f"来源：{item.get('url', '')}")
        return "\n".join(lines)

TACTIC_FRAME_CATALOG = [
    {
        "name": "结果倒推",
        "family": "因果链攻击",
        "trigger_keywords": ["倒推", "因果", "结果", "必然", "造成", "划痕", "损害", "介入因素"],
        "opponent_move": "对方把后出现的结果直接倒推成我方原因。",
        "counter_principle": "切断因果链，要求对方排除物流、使用、第三方行为和时间线介入因素。",
        "counter_moves": ["替代原因列表", "时间线拆解", "Burden of Proof压回", "要求第三方鉴定"],
        "follow_up_questions": [
            "对方如何证明结果发生在交付前而不是交付后？",
            "物流、使用、保管或第三方行为是否已经被排除？",
            "对方的证据只能证明发现时间，还是能证明产生原因？",
        ],
    },
    {
        "name": "法条压迫",
        "family": "Legal Application攻击",
        "trigger_keywords": ["ACL", "Section", "法条", "消费者法", "强制", "法律规定", "条款", "合理时间"],
        "opponent_move": "对方用一个宽泛法条制造压迫感，跳过构成要件和本案事实前提。",
        "counter_principle": "把法条拆成构成要件，逐项要求对方证明前提成立。",
        "counter_moves": ["构成要件拆解", "事实前提核验", "条款有效性抗辩", "补救比例审查"],
        "follow_up_questions": [
            "该法条每一个适用前提在本案中由谁证明？",
            "对方是否把一般保护规则扩大成无条件权利？",
            "法条是否真的排除双方明示约定？",
        ],
    },
    {
        "name": "证据完整性压迫",
        "family": "证据链攻击",
        "trigger_keywords": ["视频", "照片", "聊天记录", "质检记录", "物流", "签收", "封条", "未剪辑", "连续"],
        "opponent_move": "对方提交局部材料，试图让局部材料承担完整证明责任。",
        "counter_principle": "追问原始性、连续性、完整性和缺失证据，逼对方补足证据链。",
        "counter_moves": ["原始文件核验", "连续时间戳", "封条/外包装状态", "Missing Evidence清单"],
        "follow_up_questions": [
            "证据是否覆盖关键时间点，而不是只覆盖对方有利片段？",
            "是否有第三方或原始文件证明未剪辑、未摆拍？",
            "如果对方说法真实，为什么关键辅助材料没有出现？",
        ],
    },
    {
        "name": "时间线模糊",
        "family": "事实基础攻击",
        "trigger_keywords": ["次日", "当天", "收货", "下单", "通知", "起算", "时效", "期限", "流程"],
        "opponent_move": "对方模糊关键时间点，把迟延、使用后发现或程序缺口包装成及时维权。",
        "counter_principle": "把时间线拆成节点，区分下单、签收、开箱、使用、发现、通知和申请。",
        "counter_moves": ["节点表", "迟延解释要求", "程序期限抗辩", "通知充分性审查"],
        "follow_up_questions": [
            "对方每个关键动作发生在什么日期和时间？",
            "迟延期间是否发生使用、保管或其他介入因素？",
            "对方是否按约定流程提交完整申请？",
        ],
    },
    {
        "name": "情绪叙事包装",
        "family": "Narrative Deconstruction",
        "trigger_keywords": ["受害", "无良", "弱者", "维权", "诚信", "情感", "消费者", "叙事"],
        "opponent_move": "对方把证据问题包装成道德叙事，诱导裁判先接受身份框架。",
        "counter_principle": "拆掉标签和情绪词，回到证据、前提、时间线和责任分配。",
        "counter_moves": ["标签剥离", "选择性呈现审查", "身份叙事反问", "证据责任回归"],
        "follow_up_questions": [
            "对方叙事中哪些是证据，哪些只是身份标签？",
            "对方是否隐藏了不利事实或替代原因？",
            "裁判若不接受情绪标签，剩下的证据是否足够？",
        ],
    },
    {
        "name": "比例过度",
        "family": "补救范围攻击",
        "trigger_keywords": ["全额", "律师费", "赔偿", "退款", "补偿", "比例", "相称", "维修", "折价"],
        "opponent_move": "对方从一个有限瑕疵或有限争议跳到最大化补救。",
        "counter_principle": "把损害程度、功能影响、替代补救和成本拆开，压回相称补救。",
        "counter_moves": ["维修/折价替代", "功能影响拆解", "费用明细要求", "最小补救路径"],
        "follow_up_questions": [
            "即使对方部分成立，为什么必须全额补救？",
            "是否存在维修、折价、重新履行等较小补救？",
            "律师费或附加损害是否有独立法律依据和明细？",
        ],
    },
    {
        "name": "Burden of Proof转移",
        "family": "证明责任攻击",
        "trigger_keywords": ["谁主张谁举证", "证明责任", "举证", "证明", "鉴定", "优势证据", "排除"],
        "opponent_move": "对方用质疑代替证明，要求我方证明对方主张不成立。",
        "counter_principle": "把证明责任压回主张方，区分初步反证和最终证明门槛。",
        "counter_moves": ["证明对象列表", "证明门槛", "反证边界", "缺证后果"],
        "follow_up_questions": [
            "对方主张的具体事实是什么，由谁负证明责任？",
            "对方材料是否达到证明门槛，还是只制造怀疑？",
            "我方反证是否已经足以迫使对方进一步举证？",
        ],
    },
    {
        "name": "Systemic Risk Amplification",
        "family": "Public Policy攻击",
        "trigger_keywords": ["行业", "系统性", "公共", "政策", "成本", "滥用", "市场", "规则", "激励"],
        "opponent_move": "对方把个案结论扩大成行业或公共利益压力。",
        "counter_principle": "审查放大链条是否真实、比例是否过度，同时保留有利Public Policy反击。",
        "counter_moves": ["放大链条拆解", "行业证据要求", "反向Public Policy", "个案边界"],
        "follow_up_questions": [
            "对方从个案跳到行业风险，中间有没有数据支撑？",
            "该Public Policy是否反而支持交易确定性和诚信义务？",
            "裁判是否可以用更窄路径解决个案，避免过度扩张？",
        ],
    },
    {
        "name": "跨Jurisdiction施压",
        "family": "策略施压",
        "trigger_keywords": ["监管", "平台规则", "其他Jurisdiction", "刑法", "投诉", "行政", "NSW Fair Trading", "跨Jurisdiction"],
        "opponent_move": "对方引入本案之外的监管、平台或其他Jurisdiction材料制造压力。",
        "counter_principle": "区分诉讼内法律依据和诉讼外策略材料，避免被无关威胁带偏。",
        "counter_moves": ["关联性审查", "适用Jurisdiction确认", "诉讼内外分离", "不当施压反击"],
        "follow_up_questions": [
            "该外部规则是否真的适用于本案争议？",
            "它是法律依据、证据材料，还是单纯谈判压力？",
            "是否存在滥用投诉或不当施压的反向风险？",
        ],
    },
    {
        "name": "本职风险回看",
        "family": "逆向复盘",
        "trigger_keywords": ["最大风险", "如果", "退而", "剩余风险", "反事实", "最危险", "法官若"],
        "opponent_move": "对方或我方复盘中暴露了本案真正的风险开关。",
        "counter_principle": "把风险开关独立列出，准备主防线、备用防线和退守补救。",
        "counter_moves": ["风险开关表", "主备防线", "反事实路径", "退守方案"],
        "follow_up_questions": [
            "如果对方最强证据成立，我方还能守住哪条路径？",
            "哪个前提一旦失守会导致全案转向？",
            "是否需要立即补证、鉴定或调整补救方案？",
        ],
    },
]


class NidoOldSkinApp:
    C = {
        "bg": "#151827",
        "panel": "#24263a",
        "entry": "#101722",
        "text": "#f3f6ff",
        "muted": "#aeb6c9",
        "accent": "#2f81f7",
        "green": "#56d364",
        "red": "#f85149",
        "pink": "#f5a0b8",
        "blue": "#89b4fa",
        "gold": "#f9d65c",
        "teal": "#39c5bb",
        "pos_header": "#12324a",
        "neg_header": "#4a1f35",
        "drop": "#0b2136",
        "drop_active": "#3b3f4c",
    }

    def __init__(self):
        root_cls = TkinterDnD.Tk if TkinterDnD else tk.Tk
        self.root = root_cls()
        self.root.title(APP_TITLE)
        self.root.geometry("1320x860")
        self.root.minsize(1120, 760)
        self.root.configure(bg=self.C["bg"])

        self.engine = NidoFunctionLawyerEngine(DIMENSIONS)
        self.last_state = None
        self.last_weakness_state = None
        self.weakness_candidates = []
        self.last_run_dir = None
        self.current_case_path = ""
        self.running = False
        self.case_analysis_busy = False
        self.case_analysis_widget_states = {}
        self.case_analysis_busy_var = tk.StringVar(value="")
        self.weakness_cancel_event = threading.Event()
        self.weakness_lock_widgets = []
        self.weakness_widget_states = {}
        self.fast_scroll = False
        self.help_mode = False
        self.help_button = None
        self.case_search_results = {}

        self.mode_var = tk.StringVar(value="General matter")
        self.jur_var = tk.StringVar(value="Australia / AU - Commonwealth")
        self.case_search_var = tk.BooleanVar(value=False)
        self.confidential_var = tk.StringVar(value="Local-only confidentiality")
        self.case_name_var = tk.StringVar()
        self.import_analysis_mode_var = tk.StringVar(value="Import mode: waiting for a case")
        self._last_imported_raw_text = ""
        self._last_imported_path = ""
        self._last_imported_encoding = ""
        self.local_only_var = tk.BooleanVar(value=True)
        self.strategy_enhanced_var = tk.BooleanVar(value=False)
        self.cloud_provider_var = tk.StringVar(value="gemini")
        self.cloud_api_key_var = tk.StringVar(value="")
        self.cloud_base_url_var = tk.StringVar(value=PROVIDER_PRESETS["gemini"]["base_url"])
        self.cloud_model_var = tk.StringVar(value=PROVIDER_PRESETS["gemini"]["model"])
        self.cloud_status_var = tk.StringVar(value="External aid disabled")
        self.positive_provider_route_var = tk.StringVar(value="Full verified providers")
        self.negative_provider_route_var = tk.StringVar(value="Full verified providers")
        self.side_provider_allocation = {"positive": [], "negative": []}
        self.side_allocation_summary_var = tk.StringVar(value="Side allocation: Full verified providers for both sides")
        self.cloud_api_rows = []
        self.provider_session_active = self.is_provider_session_active()
        self.law_status_var = tk.StringVar(value="official law pack not updated")
        self.sop_new_count_var = tk.StringVar(value="0")
        self.weakness_select_var = tk.StringVar()
        self.weakness_run_status_var = tk.StringVar(value="Weakness scan ready")
        self.professional_report_type_var = tk.StringVar(value="Lawyer Working Paper")
        self.professional_output_format_var = tk.StringVar(value="Word + PDF")
        self.professional_include_contents_var = tk.BooleanVar(value=True)
        self.professional_include_pages_var = tk.BooleanVar(value=True)
        self.professional_include_sources_var = tk.BooleanVar(value=True)
        self.professional_include_evidence_var = tk.BooleanVar(value=True)
        self.cloud_parse_count = 0
        self.case_search_engine = CaseSearchEngine()
        self.dimension_vars = {name: tk.BooleanVar(value=True) for name, _ in DIMENSIONS}
        self.load_api_config()

        self._build_style()
        self._build_ui()
        self._setup_global_drop()

    def _build_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TNotebook", background=self.C["panel"], borderwidth=0)
        style.configure("TNotebook.Tab", padding=(12, 6), font=("Microsoft YaHei UI", 10))
        style.configure(
            "TCombobox",
            fieldbackground=self.C["entry"],
            background="#2f3b52",
            foreground=self.C["text"],
            arrowcolor=self.C["text"],
            bordercolor="#5b6478",
            lightcolor="#5b6478",
            darkcolor="#111827",
            selectbackground="#1f6feb",
            selectforeground="#ffffff",
        )
        style.map(
            "TCombobox",
            fieldbackground=[
                ("readonly", self.C["entry"]),
                ("disabled", "#202638"),
                ("!disabled", self.C["entry"]),
            ],
            foreground=[
                ("readonly", self.C["text"]),
                ("disabled", "#b7c4da"),
                ("!disabled", self.C["text"]),
            ],
            background=[
                ("readonly", "#2f3b52"),
                ("disabled", "#202638"),
                ("!disabled", "#2f3b52"),
            ],
            arrowcolor=[
                ("disabled", "#b7c4da"),
                ("!disabled", self.C["text"]),
            ],
        )

    def _build_ui(self):
        title = tk.Frame(self.root, bg=self.C["bg"])
        title.pack(fill=tk.X, padx=12, pady=(10, 4))
        tk.Label(
            title,
            text="Nido StrikeOver Offline 2R Clean",
            bg=self.C["bg"],
            fg=self.C["gold"],
            font=("Microsoft YaHei UI", 18, "bold"),
        ).pack(side=tk.LEFT)
        tk.Label(
            title,
            text="Legacy workflow / Nido local opposition core / confidential by default",
            bg=self.C["bg"],
            fg=self.C["muted"],
            font=("Microsoft YaHei UI", 11),
        ).pack(side=tk.LEFT, padx=12)
        self.help_button = tk.Button(
            title,
            text="?",
            command=self.enable_help_mode,
            bg="#2f3b52",
            fg=self.C["gold"],
            activebackground="#3d4a66",
            activeforeground=self.C["gold"],
            relief="flat",
            width=3,
            cursor="question_arrow",
            font=("Microsoft YaHei UI", 12, "bold"),
        )
        self.help_button.pack(side=tk.RIGHT, padx=(8, 0))
        self.set_help(self.help_button, "Help mode: click the question mark, then click any UI area for details.")

        self.canvas = tk.Canvas(self.root, bg=self.C["bg"], highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=self.canvas.yview)
        self.sf = tk.Frame(self.canvas, bg=self.C["bg"])
        self.sf.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.sf_window = self.canvas.create_window((0, 0), window=self.sf, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.bind("<Configure>", self._sync_main_canvas_width)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.sf.bind("<MouseWheel>", self._on_mousewheel)
        self.root.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        self.canvas.bind("<ButtonPress-3>", lambda _e: self.set_fast_scroll(True))
        self.canvas.bind("<ButtonRelease-3>", lambda _e: self.set_fast_scroll(False))
        self.sf.bind("<ButtonPress-3>", lambda _e: self.set_fast_scroll(True))
        self.sf.bind("<ButtonRelease-3>", lambda _e: self.set_fast_scroll(False))
        self.root.bind_all("<ButtonPress-3>", lambda _e: self.set_fast_scroll(True), add="+")
        self.root.bind_all("<ButtonRelease-3>", lambda _e: self.set_fast_scroll(False), add="+")

        self._build_options()
        self._build_case()
        self._build_side_panels()
        self._build_dimensions()
        self._build_controls()
        self._build_lawyer_workflow_controls()
        self._build_output()
        self.root.bind_all("<Button-1>", self._handle_help_click, add="+")

    def _sync_main_canvas_width(self, event):
        try:
            self.canvas.itemconfigure(self.sf_window, width=event.width)
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except Exception:
            pass

    def _on_mousewheel(self, event):
        if event.widget.winfo_toplevel() is not self.root:
            return "break"
        if event.widget.winfo_class() in {"Text", "Entry", "TEntry", "TCombobox", "Listbox"}:
            return "break"
        units = -1 if event.delta > 0 else 1
        if self.fast_scroll:
            units *= 6
        self.canvas.yview_scroll(units, "units")
        return "break"

    def set_help(self, widget, text):
        try:
            widget._nido_help_text = text
        except Exception:
            pass
        return widget

    def enable_help_mode(self):
        self.help_mode = True
        if self.help_button:
            self.help_button.config(bg=self.C["gold"], fg="#111827")
        try:
            self.status_var.set("Status: help mode is on; click a UI area for details")
        except Exception:
            pass

    def disable_help_mode(self):
        self.help_mode = False
        if self.help_button:
            self.help_button.config(bg="#2f3b52", fg=self.C["gold"])

    def _handle_help_click(self, event):
        if not self.help_mode:
            return None
        widget = event.widget
        help_text = None
        cursor = widget
        while cursor is not None:
            help_text = getattr(cursor, "_nido_help_text", None)
            if help_text:
                break
            try:
                if cursor is self.root:
                    break
                cursor = cursor.master
            except Exception:
                break
        self.disable_help_mode()
        if not help_text:
            help_text = "This area has no separate note yet. Blank layout space does not affect analysis."
        messagebox.showinfo("What is this area?", help_text)
        try:
            self.status_var.set("Status: Ready")
        except Exception:
            pass
        return "break"

    def _on_local_widget_mousewheel(self, widget, event):
        units = -1 if event.delta > 0 else 1
        if self.fast_scroll:
            units *= 6
        widget.yview_scroll(units, "units")
        return "break"

    def bind_local_scroll(self, widget):
        widget.bind("<MouseWheel>", lambda event, w=widget: self._on_local_widget_mousewheel(w, event))
        widget.bind("<ButtonPress-3>", lambda _event: self.set_fast_scroll(True))
        widget.bind("<ButtonRelease-3>", lambda _event: self.set_fast_scroll(False))
        widget.bind("<Button-4>", lambda event, w=widget: (w.yview_scroll(-1, "units"), "break")[-1])
        widget.bind("<Button-5>", lambda event, w=widget: (w.yview_scroll(1, "units"), "break")[-1])
        return widget

    def set_fast_scroll(self, value):
        self.fast_scroll = bool(value)
        return "break"

    def _panel(self, padx=10, pady=8):
        frame = tk.Frame(self.sf, bg=self.C["panel"], padx=padx, pady=pady)
        frame.pack(fill=tk.X, padx=10, pady=5)
        return frame

    def _build_options(self):
        p = self._panel()
        self.set_help(p, "Opposition settings: choose matter mode, jurisdiction, confidentiality boundary, and SOP management.")
        tk.Label(
            p,
            text="Step 1 - Opposition Settings",
            bg=self.C["panel"],
            fg=self.C["text"],
            font=("Microsoft YaHei UI", 12, "bold"),
        ).pack(anchor=tk.W)
        row = tk.Frame(p, bg=self.C["panel"])
        row.pack(fill=tk.X, pady=(8, 2))

        tk.Label(row, text="Mode", bg=self.C["panel"], fg=self.C["muted"]).pack(side=tk.LEFT)
        mode_combo = ttk.Combobox(
            row,
            textvariable=self.mode_var,
            values=["General matter", "Patent invalidity", "Contract evidence", "Client demo"],
            width=18,
            state="readonly",
        )
        self.set_help(mode_combo, "Mode: switch the opposition context. Matter type affects Weakness Scan and wording focus.")
        mode_combo.pack(side=tk.LEFT, padx=(6, 18))
        self.weakness_lock_widgets.append(mode_combo)

        tk.Label(row, text="Jurisdiction", bg=self.C["panel"], fg=self.C["muted"]).pack(side=tk.LEFT)
        jur_entry = tk.Entry(row, textvariable=self.jur_var, width=24, bg=self.C["entry"], fg=self.C["text"], relief="flat")
        self.set_help(jur_entry, "Jurisdiction: record the applicable region. Legal conclusions still require lawyer review.")
        jur_entry.pack(side=tk.LEFT, padx=(6, 18))
        self.weakness_lock_widgets.append(jur_entry)

        self.confidentiality_label = tk.Label(row, text="Confidentiality", bg=self.C["panel"], fg=self.C["muted"])
        self.confidentiality_label.pack(side=tk.LEFT)
        self.confidentiality_alert_frame = tk.Frame(
            row, bg=self.C["panel"], highlightthickness=0, highlightbackground="#ff4d67",
        )
        self.confidentiality_alert_frame.pack(side=tk.LEFT, padx=(6, 18))
        self.confidential_combo = ttk.Combobox(
            self.confidentiality_alert_frame,
            textvariable=self.confidential_var,
            values=["Local-only confidentiality", "External aid after redaction", "Authorized cloud expert"],
            width=18,
            state="readonly",
        )
        self.set_help(self.confidential_combo, "Confidentiality: controls whether external assistance is allowed. Local-only is the default.")
        self.confidential_combo.pack()
        self.weakness_lock_widgets.append(self.confidential_combo)
        self.confidential_var.trace_add("write", self.on_confidentiality_mode_changed)
        local_check = tk.Checkbutton(
            row,
            text="Local by default",
            variable=self.local_only_var,
            bg=self.C["panel"],
            fg=self.C["teal"],
            selectcolor=self.C["entry"],
            activebackground=self.C["panel"],
            activeforeground=self.C["teal"],
        )
        self.set_help(local_check, "Local by default: keep case analysis on this machine unless you explicitly authorize external assistance.")
        local_check.pack(side=tk.LEFT)
        self.weakness_lock_widgets.append(local_check)
        strategy_check = tk.Checkbutton(
            row,
            text="Strategy boost",
            variable=self.strategy_enhanced_var,
            bg=self.C["panel"],
            fg=self.C["gold"],
            selectcolor=self.C["entry"],
            activebackground=self.C["panel"],
            activeforeground=self.C["gold"],
        )
        self.set_help(strategy_check, "Strategy boost: expands local attack paths more aggressively. Turn off for a conservative baseline scan.")
        strategy_check.pack(side=tk.LEFT, padx=(14, 0))
        self.weakness_lock_widgets.append(strategy_check)

        self.cloud_frame = tk.Frame(p, bg="#1b2032", padx=10, pady=8)
        self.cloud_frame.pack(fill=tk.X, pady=(8, 0))
        self.set_help(self.cloud_frame, "Model providers: managed inside the offline version. Verifying a row makes it the active API for authorized external assistance.")
        tk.Label(
            self.cloud_frame,
            text="Model Providers",
            bg="#1b2032",
            fg=self.C["gold"],
            font=("Microsoft YaHei UI", 11, "bold"),
        ).pack(anchor="w")

        self.cloud_rows_frame = tk.Frame(self.cloud_frame, bg="#1b2032")
        self.cloud_rows_frame.pack(fill=tk.X, pady=(4, 0))
        self.load_api_profile_rows()

        bottom_cloud = tk.Frame(self.cloud_frame, bg="#1b2032")
        bottom_cloud.pack(fill=tk.X, pady=(8, 0))
        tk.Button(bottom_cloud, text="+ Add", command=self.add_empty_api_profile_row, bg="#1a3a1a", fg="white", relief="flat", padx=12, pady=3).pack(side=tk.LEFT)
        self.cloud_count_lbl = tk.Label(bottom_cloud, text="", bg="#1b2032", fg=self.C["gold"], font=("Microsoft YaHei UI", 11, "bold"))
        self.cloud_count_lbl.pack(side=tk.LEFT, padx=12)
        tk.Button(bottom_cloud, text="Authorize Cloud Parsing", command=self.cloud_parse_current_case, bg="#5a3d1a", fg="white", relief="flat", padx=14, pady=4).pack(side=tk.LEFT, padx=(10, 0))
        tk.Button(bottom_cloud, text="Forget Keys", command=self.clear_saved_api_keys, bg="#5a2430", fg="white", relief="flat", padx=14, pady=4).pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(bottom_cloud, textvariable=self.cloud_status_var, bg="#1b2032", fg=self.C["teal"]).pack(side=tk.LEFT, padx=12)

        route_row = tk.Frame(self.cloud_frame, bg="#1b2032")
        route_row.pack(fill=tk.X, pady=(8, 0))
        tk.Button(
            route_row,
            text="Side Allocation...",
            command=self.open_side_allocation_dialog,
            bg="#243b5a",
            fg="white",
            relief="flat",
            padx=12,
            pady=4,
        ).pack(side=tk.LEFT)
        tk.Label(route_row, textvariable=self.side_allocation_summary_var, bg="#1b2032", fg=self.C["muted"]).pack(side=tk.LEFT, padx=12)
        self._refresh_side_provider_routes()

        tk.Label(
            self.cloud_frame,
            text="Note: fully local confidentiality mode will not call APIs. Side model routes apply only after rows are verified and external assistance is authorized.",
            bg="#1b2032",
            fg=self.C["muted"],
        ).pack(anchor="w", pady=(6, 0))

    def load_api_config(self):
        if not self.is_provider_session_active():
            self.cloud_status_var.set("Sign in from launcher to restore saved provider keys")
            return
        if not API_CONFIG_FILE.exists():
            return
        try:
            data = json.loads(API_CONFIG_FILE.read_text(encoding="utf-8-sig"))
            provider = data.get("provider") or "gemini"
            if provider in PROVIDER_PRESETS:
                self.cloud_provider_var.set(provider)
            self.cloud_api_key_var.set(data.get("api_key") or "")
            self.cloud_base_url_var.set(data.get("base_url") or PROVIDER_PRESETS[self.cloud_provider_var.get()]["base_url"])
            saved_model = data.get("model") or PROVIDER_PRESETS[self.cloud_provider_var.get()]["model"]
            if provider == "gemini" and saved_model == "gemini-2.5-flash-lite":
                saved_model = PROVIDER_PRESETS["gemini"]["model"]
            self.cloud_model_var.set(saved_model)
            self.cloud_status_var.set("External aid key loaded locally")
        except Exception:
            self.cloud_status_var.set("External aid config load failed")

    def is_provider_session_active(self):
        try:
            data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
            return bool(data.get("signed_in"))
        except Exception:
            return False

    def save_api_config(self):
        data = {
            "provider": self.cloud_provider_var.get(),
            "api_key": self.cloud_api_key_var.get().strip(),
            "base_url": self.cloud_base_url_var.get().strip(),
            "model": self.cloud_model_var.get().strip(),
            "note": "Local file. Used only when user selects external assistance.",
        }
        API_CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8-sig")
        if hasattr(self, "cloud_api_rows"):
            self.save_api_profiles()
        self.cloud_status_var.set("API key saved locally")

    def refresh_cloud_panel(self):
        self.local_only_var.set(True)
        self.cloud_status_var.set("API panel is managed inside the offline version; main workflow stays local by default")

    def clear_saved_api_keys(self):
        if not messagebox.askyesno("Forget saved API keys", "Clear saved API keys from this offline app?"):
            return
        for row in getattr(self, "cloud_api_rows", []):
            row["key"].set("")
            row["verified"].set(False)
            row.get("verify_btn") and row["verify_btn"].config(text="Verify", bg="#89b4fa", activebackground="#9cc5ff")
            if row.get("set_locked"):
                row["set_locked"](False)
        self.cloud_api_key_var.set("")
        self.cloud_base_url_var.set("")
        self.cloud_model_var.set("")
        self.save_api_profiles()
        API_CONFIG_FILE.write_text(json.dumps({
            "provider": "",
            "api_key": "",
            "base_url": "",
            "model": "",
            "note": "Saved API keys cleared by user.",
        }, ensure_ascii=False, indent=2), encoding="utf-8-sig")
        self.update_cloud_count_label()
        self.cloud_status_var.set("Saved API keys cleared")
        self._refresh_side_provider_routes()

    def open_health_check_window(self):
        win = tk.Toplevel(self.root)
        win.title("Offline Health Check")
        win.geometry("820x620")
        win.configure(bg=self.C["bg"])
        controls = tk.Frame(win, bg=self.C["bg"])
        controls.pack(fill=tk.X, padx=10, pady=(10, 0))
        text = tk.Text(win, bg=self.C["entry"], fg=self.C["text"], insertbackground=self.C["text"], wrap=tk.WORD)
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        def refresh_text():
            text.config(state=tk.NORMAL)
            text.delete("1.0", tk.END)
            self.insert_health_report(text)
            text.config(state=tk.DISABLED)

        def run_action(action, label):
            try:
                result = action()
                messagebox.showinfo(label, result or "Done.", parent=win)
                refresh_text()
            except Exception as exc:
                messagebox.showerror(label, str(exc), parent=win)

        tk.Button(controls, text="Export Health Report", command=lambda: run_action(self.export_health_report, "Export Health Report"), bg="#243b5a", fg="white", relief="flat", padx=12, pady=5).pack(side=tk.LEFT)
        tk.Button(controls, text="Clean SOP Files", command=lambda: run_action(self.clean_sop_files_from_health_check, "Clean SOP Files"), bg="#1a4a42", fg="white", relief="flat", padx=12, pady=5).pack(side=tk.LEFT, padx=8)
        tk.Button(controls, text="Clean Candidates", command=lambda: run_action(self.clean_pending_sop_candidates_from_health_check, "Clean Candidates"), bg="#1a4a42", fg="white", relief="flat", padx=12, pady=5).pack(side=tk.LEFT)
        tk.Button(controls, text="Create Fixtures", command=lambda: run_action(self.create_regression_fixtures, "Create Fixtures"), bg="#5a3d1a", fg="white", relief="flat", padx=12, pady=5).pack(side=tk.LEFT, padx=8)
        tk.Button(controls, text="Run Fixtures", command=lambda: run_action(self.run_regression_fixtures, "Run Fixtures"), bg="#5a3d1a", fg="white", relief="flat", padx=12, pady=5).pack(side=tk.LEFT)
        refresh_text()

    def insert_health_report(self, text):
        checks = self.run_health_checks()
        for label, ok, detail in checks:
            mark = "PASS" if ok else "CHECK"
            text.insert(tk.END, f"[{mark}] {label}\n", ("ok" if ok else "warn",))
            if detail:
                text.insert(tk.END, f"  {detail}\n")
            text.insert(tk.END, "\n")
        text.tag_config("ok", foreground=self.C["green"])
        text.tag_config("warn", foreground=self.C["gold"])

    def run_health_checks(self):
        def cjk_count(rows):
            return sum(1 for row in rows if re.search(r"[\u4e00-\u9fff]", str(row.get("title", "")) + "\n" + str(row.get("rule", ""))))

        lang_rows = self.load_personal_sop_jsonl(PERSONAL_SOP_LANGUAGE_FILE) if PERSONAL_SOP_LANGUAGE_FILE.exists() else []
        case_rows = self.load_personal_sop_jsonl(PERSONAL_SOP_CASE_FILE) if PERSONAL_SOP_CASE_FILE.exists() else []
        approved_rows = self.load_personal_sop_jsonl(PERSONAL_SOP_APPROVED_FILE) if PERSONAL_SOP_APPROVED_FILE.exists() else []
        bad_official = cjk_count(lang_rows) + cjk_count(case_rows) + cjk_count(approved_rows)
        pending = self.pending_sop_count()
        candidates = self.load_personal_sop_candidates()
        hidden_blocked = sum(1 for item in candidates if item.get("status", "pending") == "pending" and item.get("filter_status") == "blocked")
        saved_key_rows = sum(1 for row in getattr(self, "cloud_api_rows", []) if row.get("key") and row["key"].get().strip())
        verified_rows = sum(1 for row in getattr(self, "cloud_api_rows", []) if row.get("verified") and row["verified"].get())
        dnd_ok = hasattr(getattr(self, "root", None), "drop_target_register")
        sample_state = {
            "selected_dimensions": list(DIMENSION_LABELS_EN.keys()),
            "stance_frame": {"purpose": "display safety sample"},
            "opponent_frame": {"role": "negative attack"},
        }
        display_json = json.dumps(self.display_state_for_json(sample_state), ensure_ascii=False)
        display_has_cjk = bool(re.search(r"[\u4e00-\u9fff]", display_json))
        fixture_dir = HERE / "regression_fixtures"
        fixture_count = len(list(fixture_dir.glob("*.json"))) if fixture_dir.exists() else 0
        return [
            ("Official SOP files are English-clean", bad_official == 0, f"{bad_official} Chinese title/rule row(s); lang={len(lang_rows)}, case={len(case_rows)}, approved={len(approved_rows)}"),
            ("SOP badge counts only pending passed candidates", True, f"visible={pending}, hidden blocked={hidden_blocked}"),
            ("API verified state is session-only", verified_rows == 0, f"saved key rows={saved_key_rows}, currently connected={verified_rows}; close/reopen resets connection"),
            ("Drag and drop support is registered", dnd_ok, "tkinterdnd2 active" if dnd_ok else "tkinterdnd2 not active in this launch"),
            ("Display JSON is English-safe", not display_has_cjk, "state_display_en.json sample has no CJK" if not display_has_cjk else "sample display JSON still contains CJK"),
            ("Regression fixtures are available", fixture_count >= 3, f"{fixture_count} fixture file(s) in regression_fixtures"),
        ]

    def health_report_text(self):
        lines = ["Nido StrikeOver Offline Health Report", f"Generated: {_dt.datetime.now().isoformat(timespec='seconds')}", ""]
        for label, ok, detail in self.run_health_checks():
            lines.append(f"[{'PASS' if ok else 'CHECK'}] {label}")
            if detail:
                lines.append(f"  {detail}")
            lines.append("")
        return "\n".join(lines)

    def export_health_report(self):
        out_dir = HERE / "runs" / "health_reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"health_report_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        path.write_text(self.health_report_text(), encoding="utf-8")
        return f"Health report exported:\n{path}"

    def backup_sop_files(self, reason="health_check"):
        backup = PERSONAL_SOP_ROOT / "cleanup_backups" / f"{reason}_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup.mkdir(parents=True, exist_ok=True)
        for path in (PERSONAL_SOP_LANGUAGE_FILE, PERSONAL_SOP_CASE_FILE, PERSONAL_SOP_APPROVED_FILE, PERSONAL_SOP_CANDIDATES_FILE):
            if path.exists():
                shutil.copy2(path, backup / path.name)
        return backup

    def sop_clean_row_for_maintenance(self, item):
        row = dict(item)
        title = self.ui_en_text(row.get("title", "")).strip()
        rule = self.ui_en_text(row.get("rule", "")).strip()
        if re.search(r"[\u4e00-\u9fff]", title + "\n" + rule):
            return None
        if not rule or len(rule) < 12 or rule.startswith((":","{","evidencesource","Noteworthy")):
            return None
        row["title"] = title or self.compact(rule, 48) or "Reusable SOP Rule"
        row["rule"] = rule
        row["category"] = row.get("category") or self.classify_personal_sop(row)
        row["type"] = row.get("category")
        row["language"] = "en"
        row["maintenance_cleaned_at"] = _dt.datetime.now().isoformat(timespec="seconds")
        if re.search(r"[\u4e00-\u9fff]", json.dumps(row.get("training_virtual_cases", []), ensure_ascii=False)):
            row["training_virtual_cases"] = []
        return row

    def clean_sop_files_from_health_check(self):
        backup = self.backup_sop_files("health_check_sop_clean")
        source = []
        for path in (PERSONAL_SOP_APPROVED_FILE, PERSONAL_SOP_LANGUAGE_FILE, PERSONAL_SOP_CASE_FILE):
            source.extend(self.load_personal_sop_jsonl(path) if path.exists() else [])
        cleaned = []
        seen = set()
        for item in source:
            if item.get("disabled"):
                continue
            row = self.sop_clean_row_for_maintenance(item)
            if not row:
                continue
            key = (row.get("category"), self.personal_sop_rule_key(row.get("rule", "")).lower())
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(row)
        lang = [x for x in cleaned if x.get("category") == "language_rhetoric"]
        case = [x for x in cleaned if x.get("category") != "language_rhetoric"]
        self.rewrite_personal_sop_jsonl(PERSONAL_SOP_LANGUAGE_FILE, lang)
        self.rewrite_personal_sop_jsonl(PERSONAL_SOP_CASE_FILE, case)
        self.rewrite_personal_sop_jsonl(PERSONAL_SOP_APPROVED_FILE, lang + case)
        return f"SOP files rebuilt. Backup:\n{backup}\nLanguage={len(lang)}, Case={len(case)}, Approved={len(lang)+len(case)}"

    def clean_pending_sop_candidates_from_health_check(self):
        backup = self.backup_sop_files("health_check_candidate_clean")
        items = self.load_personal_sop_candidates()
        changed = 0
        for item in items:
            if item.get("filter_status") != "passed":
                continue
            row = self.sop_clean_row_for_maintenance(item)
            if not row:
                continue
            for key in ("title", "rule", "category", "type", "language", "maintenance_cleaned_at"):
                if item.get(key) != row.get(key):
                    item[key] = row.get(key)
                    changed += 1
        self.save_personal_sop_candidates(items)
        self.refresh_sop_badge()
        return f"Candidate display fields cleaned: {changed} field update(s).\nBackup:\n{backup}"

    def create_regression_fixtures(self):
        fixture_dir = HERE / "regression_fixtures"
        fixture_dir.mkdir(parents=True, exist_ok=True)
        fixtures = {
            "01_import_dragdrop_basic.json": {
                "case_name": "Regression Import Matter",
                "jurisdiction": "Australia / NSW",
                "case_text": "A public-place incident with disputed inspection timing, warning visibility, causation, and quantum.",
                "pos_args": "The claimant says the occupier failed to maintain a safe entrance and the warning was inadequate.",
                "pos_ev": "[P1] medical note\n[P2] incident report\n[P3] weather record",
                "neg_args": "The occupier says a cleaning regime, warning sign, and compliant floor were present.",
                "neg_ev": "[D1] cleaning schedule\n[D2] warning sign photo\n[D3] floor inspection certificate",
                "expected": ["case_text", "pos_args", "pos_ev", "neg_args", "neg_ev"],
            },
            "02_sop_review_queue.json": {
                "case_name": "Regression SOP Queue",
                "jurisdiction": "General",
                "case_text": "SOP queue regression fixture. No private names or facts.",
                "pos_args": "A reusable argument must stay abstract.",
                "pos_ev": "[P1] abstract proof source",
                "neg_args": "A bad SOP candidate may contain residue and must be blocked.",
                "neg_ev": "[D1] blocked candidate marker",
                "expected": ["SOP", "pending", "approved"],
            },
            "03_two_round_fullscreen_export.json": {
                "case_name": "Regression Two Round Export",
                "jurisdiction": "General",
                "case_text": "Two-round fixture testing attack details, safe display state, fullscreen, and export boundaries.",
                "pos_args": "Positive position is supported by facts, legal elements, causation, and evidence.",
                "pos_ev": "[P1] document\n[P2] timeline\n[P3] calculation",
                "neg_args": "Negative position attacks missing proof, causation gaps, and quantum assumptions.",
                "neg_ev": "[D1] inspection record\n[D2] alternative cause\n[D3] missing log",
                "expected": ["Attack Details", "Safe Display State"],
            },
        }
        for name, data in fixtures.items():
            (fixture_dir / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return f"Regression fixtures created:\n{fixture_dir}"

    def run_regression_fixtures(self):
        fixture_dir = HERE / "regression_fixtures"
        if not fixture_dir.exists() or not list(fixture_dir.glob("*.json")):
            self.create_regression_fixtures()
        failures = []
        for path in sorted(fixture_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
            except Exception as exc:
                failures.append(f"{path.name}: invalid JSON: {exc}")
                continue
            for key in ("case_name", "jurisdiction", "case_text", "pos_args", "pos_ev", "neg_args", "neg_ev"):
                if key not in data:
                    failures.append(f"{path.name}: missing {key}")
        sample_display = json.dumps(self.display_state_for_json({
            "selected_dimensions": list(DIMENSION_LABELS_EN.keys()),
            "rounds": {"round1_opponent_attack": [], "round2_my_rebuttal": []},
        }), ensure_ascii=False)
        if re.search(r"[\u4e00-\u9fff]", sample_display):
            failures.append("display_state_for_json sample still contains CJK")
        if failures:
            return "Regression fixture checks failed:\n" + "\n".join(failures)
        return f"Regression fixture checks passed: {len(list(fixture_dir.glob('*.json')))} fixture(s)."

    def on_provider_changed(self):
        provider = self.cloud_provider_var.get()
        preset = PROVIDER_PRESETS.get(provider, PROVIDER_PRESETS["deepseek"])
        if provider != "custom":
            self.cloud_base_url_var.set(preset["base_url"])
            self.cloud_model_var.set(preset["model"])
        self.cloud_status_var.set(f"Selected {preset['label']}")

    def default_api_profiles(self):
        rows = []
        for name in ["gemini", "claude", "deepseek", "custom", "groq"]:
            preset = PROVIDER_PRESETS.get(name, PROVIDER_PRESETS["custom"])
            rows.append({
                "name": name,
                "key": "",
                "base_url": preset.get("base_url", ""),
                "model": preset.get("model", ""),
                "verified": False,
            })
        return rows

    def load_api_profiles(self):
        try:
            if API_PROFILES_FILE.exists():
                data = json.loads(API_PROFILES_FILE.read_text(encoding="utf-8-sig"))
                alloc = data.get("side_provider_allocation") or {}
                self.side_provider_allocation = {
                    "positive": list(alloc.get("positive") or []),
                    "negative": list(alloc.get("negative") or []),
                }
                if not self.side_provider_allocation["positive"]:
                    old_pos = data.get("positive_provider_route")
                    if old_pos and old_pos != "Full verified providers":
                        self.side_provider_allocation["positive"] = [x.strip() for x in str(old_pos).split(",") if x.strip()]
                if not self.side_provider_allocation["negative"]:
                    old_neg = data.get("negative_provider_route")
                    if old_neg and old_neg != "Full verified providers":
                        self.side_provider_allocation["negative"] = [x.strip() for x in str(old_neg).split(",") if x.strip()]
                profiles = data.get("providers", [])
                if profiles:
                    for profile in profiles:
                        if profile.get("name") == "gemini" and profile.get("model") == "gemini-2.5-flash-lite":
                            profile["model"] = PROVIDER_PRESETS["gemini"]["model"]
                    if not self.is_provider_session_active():
                        for profile in profiles:
                            profile["key"] = ""
                    for profile in profiles:
                        profile["verified"] = False
                    return profiles
        except Exception:
            pass
        current = {
            "name": self.cloud_provider_var.get(),
            "key": self.cloud_api_key_var.get(),
            "base_url": self.cloud_base_url_var.get(),
            "model": self.cloud_model_var.get(),
            "verified": False,
        }
        profiles = self.default_api_profiles()
        for item in profiles:
            if item["name"] == current["name"]:
                item.update(current)
                break
        return profiles

    def load_api_profile_rows(self):
        for item in list(getattr(self, "cloud_api_rows", [])):
            try:
                item["frame"].destroy()
            except Exception:
                pass
        self.cloud_api_rows = []
        for profile in self.load_api_profiles():
            self.add_api_profile_row(profile)
        self.update_cloud_count_label()
        self._refresh_side_provider_routes()

    def add_empty_api_profile_row(self):
        self.add_api_profile_row({"name": "custom", "key": "", "base_url": "", "model": "", "verified": False})
        self.update_cloud_count_label()

    def add_api_profile_row(self, data):
        row = tk.Frame(self.cloud_rows_frame, bg="#1b2032")
        row.pack(fill=tk.X, pady=2)

        name = tk.StringVar(value=data.get("name") or "gemini")
        key = tk.StringVar(value=data.get("key") or "")
        preset = PROVIDER_PRESETS.get(name.get(), PROVIDER_PRESETS["custom"])
        base_url = tk.StringVar(value=data.get("base_url") or preset.get("base_url", ""))
        model = tk.StringVar(value=data.get("model") or preset.get("model", ""))
        verified = tk.BooleanVar(value=bool(data.get("verified", False)))

        name_entry = tk.Entry(row, textvariable=name, width=18,
            bg=self.C["entry"], fg=self.C["text"], insertbackground=self.C["text"],
            relief="flat", font=("Microsoft YaHei UI", 11), bd=3)
        name_entry.pack(side=tk.LEFT, padx=2)

        key_entry = tk.Entry(row, textvariable=key, width=46, show="*",
            bg=self.C["entry"], fg=self.C["text"], insertbackground=self.C["text"],
            relief="flat", font=("Microsoft YaHei UI", 11), bd=3)
        key_entry.pack(side=tk.LEFT, padx=2)

        preset_var = tk.StringVar(value=name.get())
        name_box = ttk.Combobox(row, textvariable=preset_var, values=list(PROVIDER_PRESETS.keys()), width=14, state="readonly")
        name_box.pack(side=tk.LEFT, padx=2)

        def apply_preset(_event=None):
            preset2 = PROVIDER_PRESETS.get(name.get(), PROVIDER_PRESETS["custom"])
            if name.get() != "custom":
                base_url.set(preset2.get("base_url", ""))
                model.set(preset2.get("model", ""))
            verified.set(False)
            verify_btn.config(text="Verify", bg="#89b4fa", activebackground="#9cc5ff")
            set_row_locked(False)
            self.update_cloud_count_label()
            self._refresh_side_provider_routes()

        def sync_preset_to_name(_event=None):
            name.set(preset_var.get())
            apply_preset()

        def verify_row():
            if verified.get():
                verified.set(False)
                if self.cloud_provider_var.get() == (name.get().strip() or "custom"):
                    self.cloud_api_key_var.set("")
                    self.cloud_base_url_var.set("")
                    self.cloud_model_var.set("")
                verify_btn.config(text="Verify", bg="#89b4fa", activebackground="#9cc5ff")
                set_row_locked(False)
                self.save_api_profiles()
                self.update_cloud_count_label()
                self._refresh_side_provider_routes()
                self.cloud_status_var.set(f"Disconnected {name.get().strip() or base_url.get().strip()}")
                return
            if not key.get().strip():
                messagebox.showwarning("Missing API key", "Please enter an API key first.")
                return
            self.cloud_provider_var.set(name.get().strip() or "custom")
            self.cloud_api_key_var.set(key.get().strip())
            self.cloud_base_url_var.set(base_url.get().strip())
            self.cloud_model_var.set(model.get().strip())
            verified.set(True)
            verify_btn.config(text="Disconnect", bg="#5a2448", activebackground="#7a315f")
            set_row_locked(True)
            self.save_api_config()
            self.update_cloud_count_label()
            self._refresh_side_provider_routes()
            self.cloud_status_var.set(f"Verified {name.get().strip() or base_url.get().strip()}")

        def delete_row():
            self.cloud_api_rows[:] = [x for x in self.cloud_api_rows if x["frame"] is not row]
            row.destroy()
            self.save_api_profiles()
            self.update_cloud_count_label()
            self._refresh_side_provider_routes()

        name_box.bind("<<ComboboxSelected>>", sync_preset_to_name)
        verify_btn = tk.Button(
            row,
            text="Disconnect" if verified.get() else "Verify",
            command=verify_row,
            bg="#5a2448" if verified.get() else "#89b4fa",
            fg="white",
            relief="flat",
            padx=10,
            pady=2,
        )
        verify_btn.pack(side=tk.LEFT, padx=2)
        delete_btn = tk.Button(row, text="×", command=delete_row, bg="#f38ba8", fg="white", relief="flat", padx=8, pady=2)
        delete_btn.pack(side=tk.LEFT, padx=2)

        def set_row_locked(locked):
            locked = bool(locked)
            entry_bg = "#202638" if locked else self.C["entry"]
            entry_fg = "#9aa6bd" if locked else self.C["text"]
            for widget in (name_entry, key_entry):
                try:
                    widget.config(
                        state=tk.DISABLED if locked else tk.NORMAL,
                        disabledbackground=entry_bg,
                        disabledforeground=entry_fg,
                        bg=entry_bg,
                        fg=entry_fg,
                    )
                except Exception:
                    pass
            try:
                name_box.config(state=tk.DISABLED if locked else "readonly")
            except Exception:
                pass
            try:
                delete_btn.config(
                    state=tk.DISABLED if locked else tk.NORMAL,
                    bg="#40475a" if locked else "#f38ba8",
                    fg="#9aa6bd" if locked else "white",
                    activebackground="#40475a" if locked else "#f38ba8",
                )
            except Exception:
                pass
            try:
                row.config(bg="#171c2b" if locked else "#1b2032")
            except Exception:
                pass

        self.cloud_api_rows.append({
            "frame": row,
            "name": name,
            "key": key,
            "base_url": base_url,
            "model": model,
            "verified": verified,
            "verify_btn": verify_btn,
            "set_locked": set_row_locked,
        })
        set_row_locked(verified.get())
        self.update_cloud_count_label()
        self._refresh_side_provider_routes()

    def _verified_provider_route_names(self):
        names = []
        for row in getattr(self, "cloud_api_rows", []):
            try:
                if row["key"].get().strip() and row["verified"].get():
                    name = row["name"].get().strip()
                    if name and name not in names:
                        names.append(name)
            except Exception:
                pass
        return names

    def ensure_active_verified_provider(self):
        if self.cloud_api_key_var.get().strip() and self.cloud_base_url_var.get().strip() and self.cloud_model_var.get().strip():
            return True
        for row in getattr(self, "cloud_api_rows", []):
            try:
                if not (row["verified"].get() and row["key"].get().strip()):
                    continue
                self.cloud_provider_var.set(row["name"].get().strip() or "custom")
                self.cloud_api_key_var.set(row["key"].get().strip())
                self.cloud_base_url_var.set(row["base_url"].get().strip())
                self.cloud_model_var.set(row["model"].get().strip())
                self.cloud_status_var.set(f"Active provider restored: {row['name'].get().strip() or row['base_url'].get().strip()}")
                return True
            except Exception:
                pass
        return False

    def _refresh_side_provider_routes(self):
        names = self._verified_provider_route_names()
        valid = set(names)
        for side in ("positive", "negative"):
            self.side_provider_allocation[side] = [x for x in self.side_provider_allocation.get(side, []) if x in valid]
        self._update_side_allocation_summary()

    def _update_side_allocation_summary(self):
        pos = self.side_provider_allocation.get("positive", [])
        neg = self.side_provider_allocation.get("negative", [])
        pos_text = ", ".join(pos) if pos else "Full"
        neg_text = ", ".join(neg) if neg else "Full"
        self.positive_provider_route_var.set(pos_text if pos else "Full verified providers")
        self.negative_provider_route_var.set(neg_text if neg else "Full verified providers")
        if hasattr(self, "side_allocation_summary_var"):
            self.side_allocation_summary_var.set(f"Side allocation: Positive -> {pos_text}; Negative -> {neg_text}")

    def open_side_allocation_dialog(self):
        names = self._verified_provider_route_names()
        if not names:
            messagebox.showinfo("No Verified Providers", "Please verify at least one API provider before assigning sides.")
            return
        win = tk.Toplevel(self.root)
        win.title("Side Provider Allocation")
        win.configure(bg=self.C["bg"])
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)

        tk.Label(
            win,
            text="Assign verified API providers to each side. Leave a side unchecked to use Full verified providers.",
            bg=self.C["bg"],
            fg=self.C["text"],
            font=("Microsoft YaHei UI", 11, "bold"),
            wraplength=620,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, padx=16, pady=(14, 8))

        table = tk.Frame(win, bg=self.C["panel"], padx=10, pady=8)
        table.pack(fill=tk.X, padx=16, pady=(0, 10))
        tk.Label(table, text="Provider", bg=self.C["panel"], fg=self.C["gold"], width=24, anchor="w").grid(row=0, column=0, sticky="w")
        tk.Label(table, text="Positive", bg=self.C["panel"], fg=self.C["green"], width=12).grid(row=0, column=1)
        tk.Label(table, text="Negative", bg=self.C["panel"], fg=self.C["red"], width=12).grid(row=0, column=2)

        pos_vars = {}
        neg_vars = {}

        def make_toggle(parent, var, label, on_bg):
            btn = tk.Button(parent, relief="flat", width=11, padx=4, pady=2, font=("Microsoft YaHei UI", 9, "bold"))

            def refresh():
                if var.get():
                    btn.config(text=f"✓ {label}", bg=on_bg, fg="#111827", activebackground=on_bg, activeforeground="#111827")
                else:
                    btn.config(text=label, bg="#34364a", fg=self.C["muted"], activebackground="#44475a", activeforeground=self.C["text"])

            def toggle():
                var.set(not var.get())
                refresh()

            btn.config(command=toggle)
            refresh()
            return btn

        for idx, name in enumerate(names, start=1):
            pos_vars[name] = tk.BooleanVar(value=name in self.side_provider_allocation.get("positive", []))
            neg_vars[name] = tk.BooleanVar(value=name in self.side_provider_allocation.get("negative", []))
            tk.Label(table, text=name, bg=self.C["panel"], fg=self.C["text"], width=24, anchor="w").grid(row=idx, column=0, sticky="w", pady=2)
            make_toggle(table, pos_vars[name], "Positive", self.C["green"]).grid(row=idx, column=1, padx=4, pady=2)
            make_toggle(table, neg_vars[name], "Negative", self.C["red"]).grid(row=idx, column=2, padx=4, pady=2)

        buttons = tk.Frame(win, bg=self.C["bg"])
        buttons.pack(fill=tk.X, padx=16, pady=(0, 14))

        def save_and_close():
            self.side_provider_allocation["positive"] = [name for name in names if pos_vars[name].get()]
            self.side_provider_allocation["negative"] = [name for name in names if neg_vars[name].get()]
            self._update_side_allocation_summary()
            self.save_api_profiles()
            win.destroy()

        tk.Button(buttons, text="Cancel", command=win.destroy, bg="#333", fg="white", relief="flat", padx=14, pady=5).pack(side=tk.RIGHT, padx=(8, 0))
        tk.Button(buttons, text="Apply", command=save_and_close, bg=self.C["accent"], fg="#111827", relief="flat", padx=16, pady=5).pack(side=tk.RIGHT)

    def update_cloud_count_label(self):
        if not hasattr(self, "cloud_count_lbl"):
            return
        verified_count = sum(1 for row in getattr(self, "cloud_api_rows", []) if row.get("verified") and row["verified"].get())
        total_frames = verified_count * 18 * 2
        if verified_count:
            self.cloud_count_lbl.config(text=f"⚡ {verified_count} provider(s) x 18 dimension(s) x 2 = {total_frames} frames")
        else:
            self.cloud_count_lbl.config(text="")

    def collect_api_profiles(self):
        profiles = []
        for row in getattr(self, "cloud_api_rows", []):
            profiles.append({
                "name": row["name"].get().strip() or "custom",
                "key": row["key"].get().strip(),
                "base_url": row["base_url"].get().strip(),
                "model": row["model"].get().strip(),
                "enabled": True,
                "verified": False,
                "lawyers": 36,
            })
        return profiles

    def save_api_profiles(self):
        profiles = self.collect_api_profiles()
        API_PROFILES_FILE.write_text(json.dumps({
            "providers": profiles,
            "positive_provider_route": self.positive_provider_route_var.get(),
            "negative_provider_route": self.negative_provider_route_var.get(),
            "side_provider_allocation": self.side_provider_allocation,
        }, ensure_ascii=False, indent=2), encoding="utf-8-sig")

    def _build_law_materials(self):
        return

    def current_law_region(self):
        jur = self.jur_var.get().strip() if hasattr(self, "jur_var") else JURISDICTION_OPTIONS[0]
        return {"label": jur or JURISDICTION_OPTIONS[0], "jurisdiction": jur or JURISDICTION_OPTIONS[0]}

    def on_law_region_changed(self):
        self.refresh_law_status()
        self.status_var.set(f"Status: jurisdiction selected: {self.current_law_region()['label']}")

    def on_case_search_toggle(self):
        if self.case_search_var.get():
            ok = messagebox.askokcancel(
                "Case Search Risk Notice",
                "When case search is enabled, the app may search online for real authority sources for the current jurisdiction.\n\n"
                "Please note:\n"
                "- Search results require lawyer verification.\n"
                "- Do not cite case names unless they clearly appear in the search results.\n"
                "- When unchecked, no online case search is performed.\n\n"
                "Enable case search?",
            )
            if not ok:
                self.case_search_var.set(False)
        self.refresh_law_status()

    def has_verified_external_provider(self):
        return any(
            row.get("verified") and row["verified"].get() and row["key"].get().strip()
            for row in getattr(self, "cloud_api_rows", [])
        )

    def is_private_model_endpoint(self, base_url):
        value = str(base_url or "").strip().lower()
        host = re.sub(r"^[a-z][a-z0-9+.-]*://", "", value).split("/", 1)[0].split(":", 1)[0]
        if host in {"localhost", "127.0.0.1", "::1"}:
            return True
        if host.startswith("10.") or host.startswith("192.168."):
            return True
        match = re.match(r"^172\.(\d{1,2})\.", host)
        if match and 16 <= int(match.group(1)) <= 31:
            return True
        return host.endswith((".local", ".internal", ".lan")) or (host and "." not in host)

    def verified_private_provider_snapshots(self):
        return [
            item for item in self.verified_provider_snapshots()
            if self.is_private_model_endpoint(item.get("base_url"))
        ]

    def ensure_real_case_external_privacy_gate(self, action_label):
        reasons = []
        if self.has_verified_external_provider():
            reasons.append("one or more external model providers are connected")
        if self.case_search_var.get():
            reasons.append("online case-authority search is enabled")
        if not reasons:
            return True
        if self.confidential_var.get() == "External aid after redaction":
            confirmed = messagebox.askyesno(
                "Confirm Redacted External Assistance",
                f"{action_label} may send case material to connected external model providers.\n\n"
                "Confirm that the material for this new operation has been appropriately redacted and is authorized for external processing.\n\n"
                "Continue?",
                icon=messagebox.WARNING,
            )
            if not confirmed:
                self.status_var.set("Status: external operation cancelled; redaction was not reconfirmed")
            return confirmed
        if self.confidential_var.get() == "Authorized cloud expert":
            return messagebox.askyesno(
                "External Assistance Active",
                f"{action_label} is using a real case while external assistance is available.\n\n"
                "Current mode is Authorized cloud expert, so the original case may be sent to authorized external services if those features are used.\n\n"
                "Continue in Authorized cloud expert mode?",
            )

        continue_real_case = messagebox.askyesno(
            "Real Case Privacy Check",
            f"{action_label} is using a real case and detected: {', '.join(reasons)}.\n\n"
            "Synthetic Analogue Scan is already privacy-reduced and does not need this prompt.\n\n"
            "Continue with this real-case operation?",
        )
        if not continue_real_case:
            self.status_var.set("Status: real-case operation cancelled by privacy check")
            return False

        use_redaction = messagebox.askyesno(
            "Redaction Mode",
            "Before continuing, do you want to switch to External aid after redaction mode?\n\n"
            "Yes: use the redaction/external-aid privacy boundary.\n"
            "No: continue local-only; online case search will be disabled for this run.",
        )
        if use_redaction:
            self.confidential_var.set("External aid after redaction")
            self.local_only_var.set(False)
            self.refresh_cloud_panel()
            self.status_var.set("Status: External aid after redaction mode enabled")
            return True
        if self.case_search_var.get():
            self.case_search_var.set(False)
            self.refresh_law_status()
        self.status_var.set("Status: continuing local-only; online case search disabled for privacy")
        return True

    def verify_cloud_api(self):
        if self.confidential_var.get() == "Local-only confidentiality":
            messagebox.showwarning("Local Confidentiality Mode", 'Please switch Confidentiality Mode to "External aid after redaction" or "Authorized cloud expert" first.')
            return
        if not self.cloud_api_key_var.get().strip():
            messagebox.showwarning("Missing API Key", "Please enter an API key first.")
            return
        self.cloud_status_var.set("Testing API...")

        def worker():
            try:
                res = self.call_cloud_json("请只输出 JSON：{\"ok\": true, \"message\": \"connected\"}", max_tokens=120)
                ok = bool(res.get("ok"))
                self.root.after(0, lambda: self.cloud_status_var.set("API test passed" if ok else "API returned, but the format did not fully match"))
                self.root.after(0, self.save_api_config)
            except Exception as exc:
                msg = str(exc)[:500]
                self.root.after(0, lambda: self.cloud_status_var.set("API Test Failed"))
                self.root.after(0, lambda m=msg: messagebox.showerror("API Test Failed", m))

        threading.Thread(target=worker, daemon=True).start()

    def verify_cloud_api_for_training(self):
        if not self.cloud_api_key_var.get().strip():
            messagebox.showwarning("Missing API Key", "Please enter an API key first.")
            return
        self.cloud_status_var.set("Testing SOP training API...")

        def worker():
            try:
                res = self.call_cloud_json("请只输出 JSON：{\"ok\": true, \"scope\": \"sop_training\"}", max_tokens=120)
                ok = bool(res.get("ok"))
                self.root.after(0, lambda: self.cloud_status_var.set("SOP training API test passed" if ok else "API returned, but the format did not fully match"))
                self.root.after(0, self.save_api_config)
            except Exception as exc:
                msg = str(exc)[:500]
                self.root.after(0, lambda: self.cloud_status_var.set("SOP Training API Test Failed"))
                self.root.after(0, lambda m=msg: messagebox.showerror("SOP Training API Test Failed", m))

        threading.Thread(target=worker, daemon=True).start()

    def parse_case_sections(self, text):
        return self.parse_case_structure(text, getattr(self, "current_case_path", "") or "training_input.txt")

    def anonymized_training_skeleton(self):
        return {}

    def make_virtual_training_cases(self, count=300):
        return []

    def rules_from_virtual_case_flow(self, virtual_case):
        return [], {"positive": 0, "negative": 0}

    def merge_training_rules(self, rule_items):
        return []

    def training_rule_title(self, item):
        return "Disabled competition feature"

    def format_merged_training_rule(self, item):
        return ""

    def load_legacy_deepseek_key(self):
        return ""

    def load_legacy_provider_key(self, provider_name):
        return ""

    def ensure_training_api_config(self):
        return False

    def build_old_style_virtual_training_prompt(self, skeleton, virtual_cases, merged_rules):
        return ""

    def fallback_rules_from_training_text(self, text):
        return []

    def training_strategy_enhanced(self):
        var = getattr(self, "strategy_enhanced_var", None)
        try:
            return bool(var.get())
        except Exception:
            return False

    def language_skeleton_training_rules(self, virtual_count):
        return []

    def train_sop_with_virtual_cases(self):
        messagebox.showinfo("Competition Build", "Reusable training storage is disabled in this competition copy.")

    def train_sop_from_main_case(self):
        messagebox.showinfo("Competition Build", "Reusable training storage is disabled in this competition copy.")

    def build_synthetic_case_skeleton(self):
        case_text = self.get_text(self.t_bg)
        pos_args = self.get_text(self.t_pos_args)
        pos_ev = self.get_text(self.t_pos_ev)
        neg_args = self.get_text(self.t_neg_args)
        neg_ev = self.get_text(self.t_neg_ev)
        selected_dims = [self.dim_label(x) for x in self.selected_dimensions()]
        def strip_identifiers(text, limit):
            text = re.sub(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b", "[person]", text)
            text = re.sub(r"\b[\w.\-]+@[\w.\-]+\.\w+\b", "[email]", text)
            text = re.sub(r"\b(?:\+?\d[\d\s().-]{6,}\d)\b", "[number]", text)
            text = re.sub(r"\$\s?\d+(?:,\d{3})*(?:\.\d+)?", "[amount]", text)
            text = re.sub(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", "[date]", text)
            text = re.sub(r"\s+", " ", text.strip())
            return text[:limit] + ("..." if len(text) > limit else "")

        return {
            "case_name": self.case_name_var.get().strip() or "Current matter",
            "jurisdiction": self.jur_var.get().strip() or "Unspecified",
            "matter_type": self.matter_type_var.get().strip() if hasattr(self, "matter_type_var") else "General legal matter",
            "abstract_background": strip_identifiers(case_text, 900),
            "positive_theory": strip_identifiers(pos_args, 700),
            "positive_evidence_categories": strip_identifiers(pos_ev, 500),
            "negative_theory": strip_identifiers(neg_args, 700),
            "negative_evidence_categories": strip_identifiers(neg_ev, 500),
            "enabled_attack_dimensions": selected_dims[:18],
        }

    def generate_synthetic_analogue_case(self):
        case_text = self.get_text(self.t_bg)
        if not case_text:
            messagebox.showwarning("Missing Case Background", "Please import or enter the case background first.")
            return
        skeleton = self.build_synthetic_case_skeleton()
        ok = self.confirm_synthetic_analogue_privacy()
        if not ok:
            return
        self.open_synthetic_analogue_window(self.local_synthetic_analogue_pack(skeleton))
        self.status_var.set("Status: Local-only synthetic analogue case pack ready")

    def local_synthetic_analogue_pack(self, skeleton, error="", case_count=20):
        dims = skeleton.get("enabled_attack_dimensions") or ["Fact Challenge", "Logic Gap", "Burden of Proof"]
        patterns = [
            f"{dim}: test whether each asserted fact has a matching evidence source and whether the opposing side can separate liability from proof."
            for dim in dims[:6]
        ]
        matter_type = skeleton.get("matter_type", "General legal matter")
        jurisdiction = skeleton.get("jurisdiction", "Unspecified")
        scenario_roots = [
            ("Service Scope Shift", "a service arrangement changed in practice after initial agreement"),
            ("Payment Milestone Dispute", "payment was linked to milestones that were not recorded cleanly"),
            ("Authority And Variation Gap", "a third person gave instructions without clear written authority"),
            ("Delivery And Acceptance Gap", "delivery or handover occurred, but acceptance and defect timing are disputed"),
            ("Platform Record Gap", "key records sit in platform messages, screenshots, or versioned pages"),
            ("Expert Report Foundation", "one side relies on a report or assessment without showing source data"),
            ("Notice Timing Dispute", "notice, refusal, or termination timing affects the available remedy"),
            ("Causation Chain Break", "loss is alleged after several intervening events"),
            ("Quantum Calculation Gap", "the claimed amount depends on estimates, invoices, and mitigation choices"),
            ("Cross-Border Rule Boundary", "outside rules or industry standards are used as pressure rather than binding law"),
        ]
        evidence_sets = [
            "messages, invoice summaries, and partial payment records",
            "a signed form, oral instructions, and missing follow-up emails",
            "photographs, delivery logs, and a disputed inspection note",
            "platform screenshots, page versions, and incomplete metadata",
            "bank transfers, estimates, and a spreadsheet prepared after the dispute",
            "third-party notes, witness memory, and one missing original document",
            "contract clauses, amendment drafts, and unclear acceptance conduct",
            "medical or expert observations, timeline notes, and alternative-cause materials",
            "termination notices, service records, and a disputed deadline calculation",
            "industry rules, policy documents, and local-law entry questions",
        ]
        synthetic_cases = []
        count = max(1, int(case_count or 20))
        for idx in range(count):
            root_title, root_fact = scenario_roots[idx % len(scenario_roots)]
            evidence = evidence_sets[(idx * 3) % len(evidence_sets)]
            dim = dims[idx % len(dims)]
            title = f"Analogue {idx + 1:02d} - {root_title}"
            facts = (
                f"This fictional {matter_type} analogue is set in a {jurisdiction} context. "
                f"Party A and Party B dispute responsibility after {root_fact}. "
                f"The available materials include {evidence}. "
                f"The dispute is intentionally fictional and identifier-reduced; it is used to create attack patterns without exposing the original matter."
            )
            positive_position = (
                "Positive side argues that the obligation, breach, reliance, causation, and remedy remain sufficiently supported by the available record."
            )
            negative_position = (
                "Negative side attacks missing records, authority, timing, causal connection, proof burden, and whether the requested outcome follows from the available materials."
            )
            case_patterns = [
                f"{dim}: test whether this analogue's central assertion is supported by a concrete record rather than a conclusion.",
                "Missing Evidence: identify the original record, timestamp, authority trail, or source data that should exist but is not shown.",
                "Logic Gap: test whether the claimed result follows from the proved steps rather than from a narrative shortcut.",
                "Burden of Proof: separate what a side alleges from what its evidence actually proves.",
            ]
            synthetic_cases.append({
                "title": title,
                "fictional_facts": facts,
                "positive_position": positive_position,
                "negative_position": negative_position,
                "attackable_weaknesses": case_patterns,
                "mapping_back_questions": [
                    "Which assertion in this fictional analogue depends on an unstated factual bridge?",
                    "Which document, timestamp, witness source, or original record would be expected if the assertion were true?",
                    "Which proof gap would survive even if the opponent accepts part of the story?",
                ],
            })
        return {
            "skeleton_summary": (
                f"Abstracted matter type: {skeleton.get('matter_type', 'General legal matter')}. "
                f"Jurisdiction context: {skeleton.get('jurisdiction', 'Unspecified')}. "
                "The pack is generated from reduced side theories and evidence categories, not from a reusable training store."
            ),
            "synthetic_cases": synthetic_cases,
            "cross_case_weakness_patterns": patterns,
            "privacy_note": "Local-only synthetic analogue pack. No external model, cloud endpoint, reusable training store, or self-growth rule was used." + (f" Local note: {error}" if error else ""),
        }

    def confirm_synthetic_analogue_privacy(self):
        win = tk.Toplevel(self.root)
        win.title("Synthetic Analogue Privacy Gate")
        win.configure(bg="#111827")
        win.resizable(False, False)
        result = tk.BooleanVar(value=False)

        outer = tk.Frame(win, bg="#111827", padx=24, pady=22)
        outer.pack(fill=tk.BOTH, expand=True)
        tk.Label(
            outer,
            text="Synthetic Analogue Privacy Gate",
            bg="#111827",
            fg=self.C["gold"],
            font=("Microsoft YaHei UI", 15, "bold"),
            anchor="w",
        ).pack(fill=tk.X)
        tk.Label(
            outer,
            text="The real case is converted into an abstract, identifier-reduced skeleton and processed locally. No configured model, cloud endpoint, or external API is used for synthetic analogue generation.",
            bg="#111827",
            fg=self.C["text"],
            font=("Microsoft YaHei UI", 10),
            wraplength=560,
            justify=tk.LEFT,
            anchor="w",
        ).pack(fill=tk.X, pady=(10, 12))

        points = [
            ("Local function generation only", "The synthetic analogue case is generated by this desktop app's local rules, even when model providers are connected."),
            ("The output is fictional", "The generated analogue matters are used to explore weakness patterns, then mapped back to the real case locally."),
            ("No training store is created", "This competition build does not save reusable training files or self-growth rules."),
        ]
        for title, body in points:
            row = tk.Frame(outer, bg="#172033", padx=12, pady=8)
            row.pack(fill=tk.X, pady=4)
            tk.Label(row, text=title, bg="#172033", fg="#89dceb", font=("Microsoft YaHei UI", 10, "bold"), anchor="w").pack(fill=tk.X)
            tk.Label(row, text=body, bg="#172033", fg=self.C["muted"], font=("Microsoft YaHei UI", 9), wraplength=520, justify=tk.LEFT, anchor="w").pack(fill=tk.X, pady=(2, 0))

        tk.Label(
            outer,
            text="Continue with privacy-preserving synthetic analogue generation?",
            bg="#111827",
            fg=self.C["text"],
            font=("Microsoft YaHei UI", 10, "bold"),
            anchor="w",
        ).pack(fill=tk.X, pady=(14, 8))

        buttons = tk.Frame(outer, bg="#111827")
        buttons.pack(fill=tk.X)

        def choose(value):
            result.set(bool(value))
            win.destroy()

        tk.Button(buttons, text="Cancel", command=lambda: choose(False), bg="#2f3548", fg=self.C["text"], relief="flat", padx=18, pady=7).pack(side=tk.RIGHT)
        tk.Button(buttons, text="Continue", command=lambda: choose(True), bg="#1f6feb", fg="white", relief="flat", padx=18, pady=7).pack(side=tk.RIGHT, padx=(0, 10))

        win.transient(self.root)
        win.grab_set()
        win.update_idletasks()
        x = self.root.winfo_rootx() + max(40, (self.root.winfo_width() - win.winfo_width()) // 2)
        y = self.root.winfo_rooty() + max(40, (self.root.winfo_height() - win.winfo_height()) // 3)
        win.geometry(f"+{x}+{y}")
        win.wait_window()
        return bool(result.get())

    def render_synthetic_analogue_report(self, payload):
        lines = [
            "# Synthetic Analogue Case Directory",
            "",
            "The fictional analogue cases were generated locally from an identifier-reduced skeleton. Select between 1 and 5 cases for each verified-model scan.",
            "",
            "Next step: send only the selected fictional cases to a verified model provider for weakness scanning. The original real matter is not sent.",
            "",
            "## Case Directory",
            "",
        ]
        for idx, item in enumerate(payload.get("synthetic_cases") or [], 1):
            lines.append(f"{idx:02d}. {item.get('title', 'Untitled Analogue')}")
        if payload.get("privacy_note"):
            lines.extend(["", "## Privacy Note", str(payload.get("privacy_note")).strip()])
        legacy = "\n".join(lines).strip()
        cases = payload.get("synthetic_cases") or []
        report = build_standard_report(
            "synthetic_analogue",
            "synthetic_analogue_generation",
            "Synthetic analogue case pack",
            self.jur_var.get(),
            findings=[],
            input_scope={
                "synthetic_case_count": len(cases),
                "real_case_sent_to_external_model": False,
                "generation_method": "Local identifier-reduced analogue generation",
            },
            sections={"synthetic_case_directory": legacy},
            synthetic=True,
        )
        return render_standard_markdown(report).strip()

    def render_synthetic_case_detail(self, item, idx=1):
        lines = [
            f"# Synthetic Case {idx:02d}: {item.get('title', 'Untitled Analogue')}",
            "",
            "## Fictional Facts",
            str(item.get("fictional_facts") or "").strip(),
            "",
            "## Positive Position",
            str(item.get("positive_position") or "").strip(),
            "",
            "## Negative Position",
            str(item.get("negative_position") or "").strip(),
            "",
            "## Initial Weakness Directions",
        ]
        for weakness in item.get("attackable_weaknesses") or []:
            lines.append(f"- {weakness}")
        lines.extend(["", "## Review Questions"])
        for question in item.get("mapping_back_questions") or []:
            lines.append(f"- {question}")
        return "\n".join(lines).strip()

    def render_synthetic_analogue_model_context(self, payload):
        lines = [
            "# Synthetic Analogue Case Pack",
            "",
            "Purpose: directly analyse locally generated fictional matters. These are not the user's real case.",
            "",
            "The model receives only the fictional cases listed below. No real-case skeleton, mapping instruction, or pre-generated local weakness list is included.",
            "",
        ]
        for idx, item in enumerate(payload.get("synthetic_cases") or [], 1):
            lines.extend([
                f"## Synthetic Case {idx}: {item.get('title', 'Untitled Analogue')}",
                "",
                "### Fictional Facts",
                str(item.get("fictional_facts") or "").strip(),
                "",
                "### Positive Position",
                str(item.get("positive_position") or "").strip(),
                "",
                "### Negative Position",
                str(item.get("negative_position") or "").strip(),
            ])
            lines.append("")
        if payload.get("privacy_note"):
            lines.extend(["", "## Privacy Note", str(payload.get("privacy_note")).strip()])
        return "\n".join(lines).strip()

    def synthetic_model_weakness_prompt(self, payload):
        report = self.render_synthetic_analogue_model_context(payload)
        dims = ", ".join(self.selected_dimensions())
        return (
            "You are a trial weakness-analysis expert. The following material is a fictional synthetic analogue case pack, not the real client matter.\n"
            "Task: directly identify and explain weaknesses in the supplied fictional cases. Produce separate weakness cards for the fictional positive side and fictional negative side.\n"
            "These are final cards about the fictional cases themselves. Do not map them to the real case and do not mention training, self-growth, or reusable rules.\n"
            "Write each card as clearly and concretely as the facts in the fictional case allow.\n\n"
            f"Enabled attack dimensions: {dims or 'all available dimensions'}\n\n"
            "Scan every fictional case supplied in this batch. Merge truly duplicate weaknesses, but preserve materially different weaknesses and identify their fictional source case or cases.\n"
            "For EACH fictional case, independently review EVERY enabled attack dimension against BOTH fictional sides. Do not stop after finding the first weakness for a side or after producing one card for that case.\n"
            "Treat every dimension-by-side pair as an independent result slot. For each enabled dimension, return zero or one positive-side weakness and zero or one negative-side weakness. Return zero only when that dimension genuinely reveals no supported weakness for that side.\n"
            "There is no overall card-count limit per side. A case reviewed across 18 enabled dimensions may therefore return up to 18 positive-side cards and up to 18 negative-side cards when the fictional facts support distinct weaknesses.\n"
            "Do not force a card for a dimension that reveals no supported weakness, but never collapse materially different dimensions into one generic card merely to shorten the response.\n"
            "Keep the two sides genuinely separate. A positive-side item must describe a weakness in the fictional positive position or its proof. A negative-side item must describe a weakness in the fictional negative position or its proof.\n"
            "Do not copy the same item to both sides unless each side has a genuinely different failure, and explain that side-specific difference.\n"
            "Return every distinct material weakness supported by the fictional case. Merge only genuinely identical findings within the same dimension; do not merge findings merely because they concern the same document, contract, event, or legal topic.\n"
            "Each card must identify the relevant fictional source_case and the target_material within that fictional case.\n\n"
            "Boundary rule:\n"
            "- Every finding is about a fictional case only.\n"
            "- Fictional facts may be quoted when needed to explain the fictional weakness clearly.\n"
            "- Never claim that the finding exists in the user's real matter; the real matter is not provided to you.\n"
            "- source_case must name the fictional directory item that supports the finding.\n\n"
            "Strict constraints:\n"
            "- Output English only.\n"
            "- Return JSON only.\n"
            "- No placeholders, ellipses, template variables, or labels such as Argument 1 / Evidence angle / Contract angle in content fields.\n"
            "- Do not invent real authorities. If a legal rule is not supplied, describe the issue as a rule/element problem without fake citations.\n"
            "- If a weakness is too generic to explain concretely from a fictional case, omit it.\n\n"
            "Surface-card wording rule:\n"
            "- For every weakness, also write one plain declarative headline in surface_card_wording.\n"
            "- It must state the practical problem directly in no more than 24 words.\n"
            "- Do not phrase it as a question and do not begin with Check, Whether, Positive side, Negative side, or This statement.\n"
            "- It may use fictional details when necessary, but must not imply that they belong to the real matter.\n"
            "- Each headline must reflect that item's distinct weakness, not a repeated generic heading.\n\n"
            "Full-card explanation rule:\n"
            "- Read the complete fictional case before writing any card. Do not analyse isolated sentences without their surrounding fictional facts.\n"
            "- plain_explanation must explain in natural language who relies on what, what the material actually shows, and why the claimed conclusion goes further than that material.\n"
            "- core_problem must identify the precise factual, evidentiary, legal, causal, authority, timing, quantum, or remedy gap in this fictional case.\n"
            "- what_it_proves and what_it_does_not_prove must draw a clear boundary between the material's direct meaning and the larger conclusion being claimed.\n"
            "- simple_example must give a short everyday analogy when it materially helps a lawyer understand the distinction.\n"
            "- attack_questions must contain three to six natural, concrete questions that a lawyer could ask about the fictional facts, documents, dates, amounts, conduct, or missing step.\n"
            "- defence_preparation must contain two to five concrete documents, facts, explanations, or steps that could answer the weakness.\n"
            "- source_explanation must explain why the cited fictional facts support this weakness, rather than merely naming a dimension.\n"
            "- Do not pad the card with headings repeated as prose, generic legal warnings, or stock phrases. The explanation may be as long as needed to make the point genuinely understandable.\n"
            "- Keep every JSON object on one physical line and escape quotation marks correctly.\n\n"
            "Return JSON Lines (JSONL), not one large JSON object and not an array.\n"
            "Write exactly one complete JSON object per physical line. Do not use Markdown fences, comments, blank continuation lines, or commas between lines.\n"
            "Each line must contain these keys in this order:\n"
            '"side", "id", "source_case", "dimension", "target_material", "name", "surface_card_wording", "pattern", "why_it_matters", '
            '"plain_explanation", "core_problem", "what_it_proves", "what_it_does_not_prove", "simple_example", '
            '"attack_questions", "defence_preparation", "source_explanation", "one_sentence_summary", "severity".\n'
            'Use "side":"positive" for weaknesses in the fictional positive side and "side":"negative" for weaknesses in the fictional negative side.\n'
            "Balance both sides throughout the response. Alternate positive and negative JSONL lines whenever both sides have supported weaknesses.\n"
            "Never place all positive lines before all negative lines, and never return more than two consecutive lines for one side while the other side still has a supported weakness.\n"
            "Before finishing, verify that both fictional sides are represented unless the supplied fictional material genuinely contains no supportable weakness for one side.\n"
            "Example line shape only:\n"
            '{"side":"positive","id":"SCW-01","source_case":"Analogue 01 - fictional title","dimension":"one enabled attack dimension","target_material":"fictional assertion or evidence being tested","name":"short weakness name","surface_card_wording":"plain practical conclusion","pattern":"specific weakness pattern","why_it_matters":"short reason","plain_explanation":"plain explanation","core_problem":"core problem","what_it_proves":"narrow proof","what_it_does_not_prove":"unsupported larger conclusion","simple_example":"short analogy","attack_questions":["question 1","question 2","question 3"],"defence_preparation":["step 1","step 2"],"source_explanation":"why the fictional facts reveal this weakness","one_sentence_summary":"plain summary","severity":"high"}\n\n'
            "Synthetic analogue case pack:\n"
            f"{report}"
        )

    def synthetic_side_checklists(self, result):
        if not isinstance(result, dict):
            return [], []
        positive = result.get("positive_side_weakness_patterns") or result.get("positive_side_weaknesses") or []
        negative = result.get("negative_side_weakness_patterns") or result.get("negative_side_weaknesses") or []
        if not isinstance(positive, list):
            positive = []
        if not isinstance(negative, list):
            negative = []
        if not positive and not negative:
            legacy = result.get("weakness_checklist") or result.get("summary_checklist") or result.get("checklist") or []
            if isinstance(legacy, list):
                # Compatibility only. New scans always request independent side lists.
                positive = list(legacy)
                negative = list(legacy)
        return positive, negative

    def synthetic_dimension_free_analysis_prompt(self, payload, dimension):
        """First pass: let one dimension write a natural report, not a card schema."""
        report = self.render_synthetic_analogue_model_context(payload)
        description = DIMENSION_DESC_EN.get(dimension, "Independent whole-case legal review.")
        return f'''You are senior litigation counsel independently reviewing one FICTIONAL synthetic matter only through the dimension "{dimension}".

Read the complete fictional matter below from beginning to end. Do not use any prior dimension report, pre-extracted argument list, evidence labels such as P1/P2/D1/D2, sentence-level decomposition, card template, or internal software frame.

Think through the entire fictional matter exclusively from this dimension. Write the kind of candid internal analysis that an experienced lawyer would give another lawyer after reading the whole file. Follow the facts and the strongest lines of reasoning wherever they lead. Consider both fictional sides, interactions with the rest of the matter, useful attacks, possible answers, evidentiary limits, and uncertainties when they genuinely matter.

Dimension description: {description}

Rules:
- English only.
- Write natural connected prose. Do not return JSON.
- Do not fill a template, checklist, card schema, or fixed series of headings.
- Do not mechanically repeat the dimension name or manufacture symmetry between the two sides.
- Do not invent facts, dates, amounts, documents, clauses, testimony, approvals, statutes, cases, or authorities.
- Distinguish supplied fictional facts from assumptions and missing material.
- Do not create a weakness merely to fill space. It is acceptable to conclude that this dimension adds little.
- Explain concrete matter-specific weaknesses in ordinary professional language when you find them.
- This is a fictional analogue only. Never claim that any conclusion applies to the user's real matter, which has not been supplied.

COMPLETE FICTIONAL MATTER:
{report}
'''

    def synthetic_surface_extraction_prompt(self, free_analysis, dimension, source_case):
        """Second pass: extract labels only; the free report remains the card body."""
        return f'''Read the completed internal analysis below. Do not re-analyse the fictional matter and do not rewrite, summarize into a template, or replace the report.

Extract only the genuinely material weakness conclusions already supported by that analysis. These values are used only to place short titles on the outside cards. The original free-form analysis remains the complete card body.

Rules:
- English only.
- Do not add a finding that is not present in the internal analysis.
- Keep positive-side and negative-side weaknesses correctly separated.
- "affected_side" means the fictional side whose position is weakened, not the side making the attack.
- "conclusion" must be a short, direct, matter-specific title extracted from the report.
- Do not begin a title with "This card means", "This card", "Weakness", "Positive side", "Negative side", "Whether", or a dimension label.
- Do not turn the title into a question.
- "surface_summary" may contain one natural preview sentence taken from the reasoning already present in the report.
- Do not expose software labels, internal frames, JSON terminology, or a fixed explanatory template.
- Do not force a fixed number of findings. Return an empty list if the report contains no material weakness.

Fictional source case: {source_case}
Review dimension: {dimension}

COMPLETED FREE-FORM INTERNAL ANALYSIS:
{free_analysis}

Return strict JSON only:
{{
  "important_weaknesses": [
    {{
      "affected_side": "positive or negative",
      "conclusion": "short direct title extracted from the report",
      "surface_summary": "one natural preview sentence derived from the report"
    }}
  ],
  "no_finding_explanation": "brief reason only when no material finding exists"
}}'''

    def locally_recover_synthetic_summary_json(self, text):
        """Recover complete side-card objects from malformed model JSON without another API call."""
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(text or "").strip())
        positive_marker = raw.find('"positive_side_weakness_patterns"')
        negative_marker = raw.find('"negative_side_weakness_patterns"')
        if positive_marker < 0 or negative_marker < 0:
            raise ValueError("The malformed response does not contain both side-list markers.")
        decoder = json.JSONDecoder()
        positive = []
        negative = []
        seen = set()
        for match in re.finditer(r"\{", raw):
            start = match.start()
            try:
                obj, _end = decoder.raw_decode(raw[start:])
            except Exception:
                continue
            if not isinstance(obj, dict) or not obj.get("name"):
                continue
            if not (obj.get("surface_card_wording") or obj.get("pattern") or obj.get("plain_explanation")):
                continue
            key = (str(obj.get("id") or ""), str(obj.get("name") or "").strip().lower())
            if key in seen:
                continue
            seen.add(key)
            if positive_marker < start < negative_marker:
                positive.append(obj)
            elif start > negative_marker:
                negative.append(obj)
        if not positive and not negative:
            raise ValueError(
                f"Local recovery found {len(positive)} positive-side and {len(negative)} negative-side complete card(s)."
            )
        return {
            "summary_title": "Synthetic Similar-Case Weakness Summary",
            "overview": "Recovered locally from complete card objects in a malformed model response.",
            "positive_side_weakness_patterns": positive,
            "negative_side_weakness_patterns": negative,
            "comparison_instructions": [
                "Recovered cards remain subject to the local synthetic-detail privacy filter."
            ],
            "local_json_recovery": {
                "used": True,
                "positive_recovered": len(positive),
                "negative_recovered": len(negative),
                "additional_model_calls": 0,
            },
        }

    def parse_synthetic_summary_response(self, text):
        """Parse JSONL first; retain compatibility with earlier root-object responses."""
        raw = str(text or "").strip()
        positive = []
        negative = []
        rejected_lines = 0
        for line in raw.splitlines():
            clean = line.strip().rstrip(",")
            if not clean or clean.startswith("```"):
                continue
            if not (clean.startswith("{") and clean.endswith("}")):
                rejected_lines += 1
                continue
            try:
                item = json.loads(clean)
            except Exception:
                rejected_lines += 1
                continue
            if not isinstance(item, dict) or not item.get("name"):
                rejected_lines += 1
                continue
            side = str(item.get("side") or "").strip().lower()
            if side == "positive":
                positive.append(item)
            elif side == "negative":
                negative.append(item)
            else:
                rejected_lines += 1
        if positive or negative:
            return {
                "summary_title": "Synthetic Similar-Case Weakness Summary",
                "overview": "Parsed locally from independent JSONL weakness cards.",
                "positive_side_weakness_patterns": positive,
                "negative_side_weakness_patterns": negative,
                "comparison_instructions": ["Each card describes only a fictional case; no finding is mapped back to the real matter."],
                "local_jsonl_parse": {
                    "positive_parsed": len(positive),
                    "negative_parsed": len(negative),
                    "rejected_lines": rejected_lines,
                    "additional_model_calls": 0,
                },
            }
        try:
            root = self.extract_json_object(raw)
            pos, neg = self.synthetic_side_checklists(root)
            if pos or neg:
                return root
        except Exception:
            pass
        return self.locally_recover_synthetic_summary_json(raw)

    def synthetic_privacy_literals(self, payload):
        """Build a local-only deny list from the fictional pack sent to the model."""
        literals = {"party a", "party b", "fictional party a", "fictional party b"}
        cases = payload.get("synthetic_cases") or [] if isinstance(payload, dict) else []
        source_text = json.dumps(cases, ensure_ascii=False)
        for item in cases:
            if not isinstance(item, dict):
                continue
            title = re.sub(r"\s+", " ", str(item.get("title") or "")).strip().lower()
            if title:
                literals.add(title)
            item_text = json.dumps(item, ensure_ascii=False)
            for pattern in (
                r"\b[\w.\-]+@[\w.\-]+\.\w+\b",
                r"https?://[^\s\"']+",
                r"(?:AUD|USD|RMB|CNY|GBP|EUR|\$|£|€)\s?\d[\d,]*(?:\.\d+)?",
                r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
                r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b",
                r"\b(?:\+?\d[\d\s().-]{7,}\d)\b",
            ):
                literals.update(x.lower().strip() for x in re.findall(pattern, item_text, flags=re.I))
            # Generated scenario headings such as "Authority And Variation Gap"
            # are abstract weakness concepts, not private fictional facts. Only
            # mine proper names from a case the user manually added.
            if title.startswith("manual analogue"):
                for name in re.findall(r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){1,3}\b", item_text):
                    low = name.lower().strip()
                    if low not in {
                        "positive side", "negative side", "missing evidence", "logic gap",
                        "burden of proof", "fact challenge", "general legal matter",
                    }:
                        literals.add(low)
        return {x for x in literals if len(x) >= 7 and x in source_text.lower()}

    def locally_filter_synthetic_model_result(self, payload, result):
        """Reject contaminated model items locally; this function never calls an API."""
        if not isinstance(result, dict):
            return {}, {"checked": 0, "rejected": 0, "reasons": []}
        literals = self.synthetic_privacy_literals(payload)
        filtered = dict(result)
        rejected_reasons = []
        checked = 0

        def clean_list(items, side):
            nonlocal checked
            clean = []
            for item in items if isinstance(items, list) else []:
                checked += 1
                text = json.dumps(item, ensure_ascii=False).lower()
                hits = sorted(x for x in literals if x in text)
                if re.search(r"\banalogue\s*\d+\b|\bfictional\s+party\b", text, flags=re.I):
                    hits.append("fictional case identifier")
                if hits:
                    rejected_reasons.append({"side": side, "item": checked, "reason_count": len(set(hits))})
                    continue
                clean.append(item)
            return clean

        positive, negative = self.synthetic_side_checklists(result)
        filtered["positive_side_weakness_patterns"] = clean_list(positive, "positive")
        filtered["negative_side_weakness_patterns"] = clean_list(negative, "negative")
        filtered.pop("weakness_checklist", None)
        filtered.pop("summary_checklist", None)
        filtered.pop("checklist", None)
        audit = {
            "checked": checked,
            "rejected": len(rejected_reasons),
            "accepted": len(filtered["positive_side_weakness_patterns"]) + len(filtered["negative_side_weakness_patterns"]),
            "reasons": rejected_reasons,
            "executed_locally": True,
            "additional_model_calls": 0,
        }
        filtered["local_privacy_filter"] = audit
        return filtered, audit

    def render_synthetic_weakness_summary_report(self, result):
        if not isinstance(result, dict):
            result = {}
        title = self.ui_en_text(result.get("summary_title") or "Synthetic Similar-Case Weakness Summary")
        overview = self.ui_en_text(result.get("overview") or "")
        positive_checklist, negative_checklist = self.synthetic_side_checklists(result)
        instructions = result.get("comparison_instructions") or []
        if isinstance(instructions, str):
            instructions = [instructions]
        lines = [
            f"# {title}",
            "",
            "This is a consolidated checklist from locally generated fictional similar cases. It is not a finding about the real case.",
            "Use it as a comparison report: check the real case independently before adding any weakness to the main matter.",
        ]
        if overview:
            lines.extend(["", "## Overview", overview])
        lines.extend(["", "## Positive-Side Weakness Patterns"])
        if not positive_checklist:
            lines.append("No usable checklist items were returned.")
        for side_title, checklist in (
            ("Positive-Side Weakness Patterns", positive_checklist),
            ("Negative-Side Weakness Patterns", negative_checklist),
        ):
            if side_title.startswith("Negative"):
                lines.extend(["", f"## {side_title}"])
            if not checklist:
                lines.append("No usable checklist items were returned.")
                continue
            for idx, item in enumerate(checklist, 1):
                if not isinstance(item, dict):
                    item = {"pattern": str(item)}
                item_id = self.ui_en_text(item.get("id") or f"SCW-{idx:02d}")
                name = self.ui_en_text(item.get("name") or "Weakness direction")
                surface_wording = self.ui_en_text(item.get("surface_card_wording") or "")
                pattern = self.ui_en_text(item.get("pattern") or item.get("summary") or "")
                why = self.ui_en_text(item.get("why_it_matters") or "")
                side_use = self.ui_en_text(item.get("side_use") or side_title)
                severity = self.ui_en_text(item.get("severity") or "medium")
                checks = item.get("real_case_checks") or item.get("checks") or []
                if isinstance(checks, str):
                    checks = [checks]
                boundary = self.ui_en_text(
                    item.get("do_not_import")
                    or "Do not import fictional names, dates, amounts, locations, documents, or conclusions into the real case."
                )
                lines.extend(["", f"### {item_id} - {name}", f"Severity: {severity}", f"Use: {side_use}"])
                if surface_wording:
                    lines.append(f"Surface card: {surface_wording}")
                if pattern:
                    lines.append(f"Pattern: {pattern}")
                if why:
                    lines.append(f"Why it matters: {why}")
                lines.append("Real-case checks:")
                for check in checks[:8]:
                    clean = self.ui_en_text(check)
                    if clean:
                        lines.append(f"- {clean}")
                lines.append(f"Boundary: {boundary}")
        lines.extend(["", "## How To Use This Report"])
        default_instructions = [
            "Treat each item as a checklist question, not as an imported fact.",
            "Only add a weakness to the real case if the real case materials independently show the same gap.",
            "Do not copy fictional parties, dates, amounts, places, or document names into the real case.",
        ]
        for inst in (instructions or default_instructions):
            clean = self.ui_en_text(inst)
            if clean:
                lines.append(f"- {clean}")
        legacy = "\n".join(lines).strip()
        metadata = result.get("engine_metadata") if isinstance(result.get("engine_metadata"), dict) else {}
        provider = str(metadata.get("provider") or "").strip()
        model = str(metadata.get("model") or "").strip()
        findings = []
        for side, checklist in (("positive", positive_checklist), ("negative", negative_checklist)):
            for idx, item in enumerate(checklist, 1):
                raw = item if isinstance(item, dict) else {"pattern": str(item)}
                finding = self.ui_en_text(
                    raw.get("conclusion")
                    or raw.get("surface_card_wording")
                    or raw.get("one_sentence_summary")
                    or raw.get("pattern")
                    or raw.get("summary")
                    or "Synthetic weakness direction"
                )
                findings.append({
                    "id": raw.get("id") or f"SYN-{side[:1].upper()}-{idx:03d}",
                    "analysis_stage": "synthetic_analogue_model_scan",
                    "dimension": raw.get("dimension") or "Not assigned",
                    "title": raw.get("name") or finding,
                    "finding": finding,
                    "affected_side": side,
                    "factual_basis": raw.get("source_case") or "Fictional synthetic case material only",
                    "significance": raw.get("why_it_matters") or "Comparison prompt only; requires independent real-matter verification",
                    "confidence": raw.get("confidence") or "Not independently scored",
                    "provider": provider or "Not recorded",
                    "model": model or "Not recorded",
                    "source_reference": raw.get("source_case") or "Synthetic case pack",
                    "review_status": "ai_generated_unverified",
                })
        provider_runs = []
        if provider or model:
            provider_runs.append({
                "provider": provider or "Not recorded",
                "model": model or "Not recorded",
                "engine_source": "Synthetic analogue model scan",
                "run_reference": result.get("analysis_mode") or "synthetic scan",
            })
        report = build_standard_report(
            "synthetic_analogue",
            "synthetic_analogue_model_scan",
            "Synthetic fictional-case weakness review",
            self.jur_var.get(),
            findings=findings,
            provider_runs=provider_runs,
            input_scope={
                "positive_side_patterns": len(positive_checklist),
                "negative_side_patterns": len(negative_checklist),
                "real_case_analysed_or_mapped": False,
                "analysis_mode": result.get("analysis_mode") or "Not recorded",
            },
            sections={"legacy_comparison_checklist": legacy},
            missing_material=["Original real-matter evidence must be checked independently before adopting any pattern."],
            synthetic=True,
        )
        return render_standard_markdown(report).strip()

    def open_synthetic_weakness_summary_window(self, result):
        report = self.render_synthetic_weakness_summary_report(result)
        win = tk.Toplevel(self.root)
        win.title("Synthetic Similar-Case Weakness Summary")
        win.geometry("980x740")
        win.configure(bg=self.C["bg"])
        tk.Label(
            win,
            text="Synthetic Similar-Case Weakness Summary",
            bg=self.C["bg"],
            fg=self.C["gold"],
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor=tk.W, padx=12, pady=(12, 4))
        tk.Label(
            win,
            text="Consolidated checklist only. Compare against the real case independently; do not import fictional case facts.",
            bg=self.C["bg"],
            fg=self.C["muted"],
            font=("Segoe UI", 10),
        ).pack(anchor=tk.W, padx=12, pady=(0, 8))
        text = scrolledtext.ScrolledText(
            win,
            wrap=tk.WORD,
            height=34,
            bg=self.C["entry"],
            fg=self.C["text"],
            insertbackground=self.C["text"],
        )
        text.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 10))
        text.insert("1.0", report)
        text.config(state=tk.DISABLED)
        btnbar = tk.Frame(win, bg=self.C["bg"])
        btnbar.pack(fill=tk.X, padx=12, pady=(0, 12))
        tk.Button(
            btnbar,
            text="Copy Report",
            bg="#2f3b52",
            fg=self.C["text"],
            activebackground=self.C["accent"],
            activeforeground="white",
            command=lambda: self.copy_to_clipboard(report),
        ).pack(side=tk.LEFT)
        tk.Button(
            btnbar,
            text="Scan Real Case Locally",
            bg=self.C["green"],
            fg="#111827",
            activebackground=self.C["teal"],
            activeforeground="#111827",
            command=lambda: self.safe_map_synthetic_summary_back_to_case(result),
        ).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(
            btnbar,
            text="Close",
            bg="#2f3b52",
            fg=self.C["text"],
            activebackground=self.C["accent"],
            activeforeground="white",
            command=win.destroy,
        ).pack(side=tk.RIGHT)
        win.lift()
        win.focus_force()

    def safe_map_synthetic_summary_back_to_case(self, result):
        try:
            self.map_synthetic_summary_back_to_case(result)
        except Exception as exc:
            messagebox.showerror("Local Real-Case Scan Failed", str(exc))

    def local_surface_conclusion_from_check(self, text, side, fallback=""):
        """Turn a model checklist question into a concise local surface-card conclusion."""
        raw = self.ui_en_text(text or fallback)
        raw = re.sub(r"\s+", " ", str(raw or "")).strip().rstrip("?.")
        raw = re.sub(r"^(?:check|test|determine|ask)\s+(?:whether|if)\s+", "", raw, flags=re.I)
        raw = re.sub(r"^whether\s+", "", raw, flags=re.I)
        label = "positive side" if side == "positive" else "negative side"
        subject = f"The {label}"

        does = re.match(r"^does\s+(?:the\s+)?(?:real\s+)?(?:positive|negative)\s+side\s+(.+)$", raw, flags=re.I)
        if does:
            body = does.group(1).strip()
            patterns = (
                (r"^rely\s+on\s+(?:a\s+)?summary,?\s+screenshot,?\s+or\s+partial\s+record\s+instead\s+of\s+the\s+original\s+document$",
                 "Only a summary, screenshot, or partial record is available; the original document is missing."),
                (r"^rely\s+solely\s+on\s+pointing\s+out\s+gaps\s+in\s+the\s+(?:positive|negative)\s+side's\s+evidence$",
                 "The objection points out missing evidence but offers no supporting evidence of its own."),
                (r"^challenge\s+the\s+quantum\s+without\s+providing\s+an\s+alternative\s+figure$",
                 "The claimed amount is challenged, but no alternative calculation is provided."),
                (r"^assert\s+lack\s+of\s+authority\s+without\s+producing\s+the\s+relevant\s+authority\s+documents$",
                 "Lack of authority is alleged, but the relevant authority documents are not provided."),
                (r"^challenge\s+the\s+timeline\s+without\s+producing\s+its\s+own\s+service\s+records$",
                 "The timeline is challenged without producing any competing service records."),
                (r"^attack\s+the\s+expert\s+report\s+only\s+on\s+missing\s+source\s+data,?\s+not\s+on\s+methodology$",
                 "The expert report is attacked for missing source data, but its methodology is not challenged."),
                (r"^allege\s+tampering\s+without\s+evidence$",
                 "Tampering is alleged without supporting evidence."),
                (r"^identify\s+gaps\s+without\s+providing\s+an\s+alternative\s+explanation$",
                 "Gaps are identified, but no alternative explanation is offered."),
                (r"^make\s+a\s+general\s+burden\s+argument\s+without\s+specificity$",
                 "The burden-of-proof objection is too general to identify the actual missing proof."),
                (r"^assert\s+inapplicability\s+without\s+producing\s+the\s+governing\s+law\s+or\s+contract$",
                 "Inapplicability is asserted without producing the governing law or contract."),
            )
            for expression, conclusion in patterns:
                if re.match(expression, body, flags=re.I):
                    return conclusion
            if re.match(r"^rely\s+on\s+", body, flags=re.I):
                return self.compact("This point may rely on " + re.sub(r"^rely\s+on\s+", "", body, flags=re.I) + ".", 190)
            if " without " in body.lower():
                left, right = re.split(r"\s+without\s+", body, maxsplit=1, flags=re.I)
                return self.compact(f"The point {left.lower()}, but does not provide {right}.", 190)
            body = re.sub(r"^assume\s+", "assumes ", body, flags=re.I)
            return self.compact(f"Possible weakness: this point {body}.", 190)

        has = re.match(r"^has\s+(?:the\s+)?(?:real\s+)?(?:positive|negative)\s+side\s+(.+)$", raw, flags=re.I)
        if has:
            body = has.group(1).strip()
            if re.match(r"^produced\s+any\s+evidence\s+to\s+support\s+its\s+own\s+version\s+of\s+events$", body, flags=re.I):
                return "No evidence supporting the competing version of events is identified."
            return self.compact(f"The required material may not have been {body}.", 190)

        can = re.match(r"^can\s+(?:the\s+)?(?:real\s+)?(?:positive|negative)\s+side\s+(.+)$", raw, flags=re.I)
        if can:
            return self.compact(f"It is uncertain whether {label} can {can.group(1).strip()}.", 190)

        generic_subject = re.sub(
            r"^(?:the\s+)?(?:real\s+)?(?:positive|negative)\s+side\s+",
            f"{subject} ",
            raw,
            flags=re.I,
        )
        if generic_subject and generic_subject.lower() != raw.lower():
            return self.compact(generic_subject[0].upper() + generic_subject[1:] + ".", 190)
        concise_fallback = self.ui_en_text(fallback) or raw
        return self.compact(concise_fallback.rstrip("?.") + ".", 190)

    def synthetic_summary_candidate(self, side, seq, item, real_point):
        if not isinstance(item, dict):
            item = {"pattern": str(item)}
        item_id = self.ui_en_text(item.get("id") or f"SCW-{seq:02d}")
        name = self.ui_en_text(item.get("name") or "Weakness direction")
        surface_reference = self.ui_en_text(item.get("surface_card_wording") or item.get("surface_wording") or "")
        pattern = self.ui_en_text(item.get("pattern") or item.get("summary") or "")
        why = self.ui_en_text(item.get("why_it_matters") or "")
        checks = item.get("real_case_checks") or item.get("checks") or []
        if isinstance(checks, str):
            checks = [checks]
        checks = [self.ui_en_text(x) for x in checks if str(x).strip()]
        target_side = "Positive side" if side == "positive" else "Negative side"
        point_text = re.sub(r"\s+", " ", str((real_point or {}).get("text", "")).strip())
        if not point_text or self.is_placeholder_case_target(point_text):
            return None
        point_kind = self.ui_en_text((real_point or {}).get("kind", "")) or "argument"
        point_index = (real_point or {}).get("index") or seq
        dim_source = " ".join([name, pattern, why, " ".join(checks)])
        dim = self.synthetic_pattern_dimension(dim_source)
        check_text = "; ".join(checks[:6]) if checks else "Check this real-case point against the synthetic summary pattern."
        primary_check = self.remove_repeated_prefix(name, checks[0] if checks else pattern or name)
        primary_check = self.compact(primary_check, 180) or f"Check whether this {point_kind} is independently supported."
        if surface_reference and not self.bad_ui_text(surface_reference):
            surface_reference = re.sub(r"\s+", " ", surface_reference).strip().rstrip("?.")
            surface_reference = re.sub(
                r"^(?:check|whether|positive side|negative side|this statement)\s*[:\-]?\s*",
                "",
                surface_reference,
                flags=re.I,
            )
            surface_summary = self.compact(surface_reference[:1].upper() + surface_reference[1:] + ".", 190)
        else:
            surface_summary = self.local_surface_conclusion_from_check(primary_check, side, fallback=name)
        mapped_checks = [
            f"For current-case {point_kind} '{self.compact(point_text, 120)}': {check}"
            for check in (checks[:8] or [primary_check])
        ]
        weakness = (
            f"{surface_summary}\n\n"
            f"Checklist pattern: {pattern or name}\n\n"
            f"Real-case checks:\n- " + "\n- ".join(mapped_checks)
        )
        attack_question = "\n".join(mapped_checks) if mapped_checks else f"Which concrete record supports this point: {point_text}?"
        severity = self.summary_item_severity(item, dim, pattern, checks)
        model_questions = item.get("attack_questions") or checks or []
        model_defence = item.get("defence_preparation") or []
        if isinstance(model_questions, str):
            model_questions = [model_questions]
        if isinstance(model_defence, str):
            model_defence = [model_defence]
        model_full_card = {
            "plain_explanation": self.ui_en_text(item.get("plain_explanation") or why or surface_summary),
            "core_problem": self.ui_en_text(item.get("core_problem") or pattern or name),
            "what_it_proves": self.ui_en_text(item.get("what_it_proves") or "The material may support the narrow fact it directly records."),
            "what_it_does_not_prove": self.ui_en_text(item.get("what_it_does_not_prove") or primary_check),
            "simple_example": self.ui_en_text(item.get("simple_example") or ""),
            "attack_questions": [self.ui_en_text(x) for x in model_questions if str(x).strip()],
            "defence_preparation": [self.ui_en_text(x) for x in model_defence if str(x).strip()],
            "source_explanation": self.ui_en_text(
                item.get("source_explanation")
                or "This abstract weakness recurred across the fictional similar-case pack and was then checked locally against the real matter."
            ),
            "one_sentence_summary": self.ui_en_text(item.get("one_sentence_summary") or surface_summary),
        }
        guide = {
            "name": name,
            "surface_card_wording": surface_summary,
            "plain_explanation": model_full_card["plain_explanation"],
            "core_problem": model_full_card["core_problem"],
            "summary": weakness,
            "one_sentence_summary": surface_summary,
            "target_claim_or_element": point_text,
            "mapping_checklist": {
                "summary_source": item_id,
                "pattern": pattern,
                "real_case_checks": mapped_checks,
                "case_specific_missing_evidence": "; ".join(mapped_checks),
                "boundary": "This card was generated locally by comparing a model-created synthetic summary to the real case. Do not import fictional facts.",
            },
            "missing_evidence_or_step": mapped_checks,
            "attack_script": mapped_checks,
            "signal_of_success": "The real-case file cannot independently answer one or more checklist questions.",
            "defense": "Prepare the concrete record, date, authority trail, witness source, or calculation that answers each checklist question.",
            "severity": severity,
            "target": point_text,
            "source": f"Synthetic summary checklist {item_id}",
            "reason": "A verified model summarized only fictional similar cases; this local step compares the summary against the current real case without sending the real case out.",
            "tags": "Synthetic summary, local real-case comparison",
            "attacker": "Negative side" if side == "positive" else "Positive side",
            "defender": target_side,
            "model_full_card": model_full_card,
        }
        return {
            "id": f"SS{side[:1].upper()}{seq:03d}",
            "select_id": f"SS{side[:1].upper()}{seq}",
            "display_id": str(seq),
            "side": side,
            "dimension": dim,
            "score": 65,
            "priority_score": 65,
            "rule": "Synthetic summary local comparison",
            "risk_tags": ["Synthetic summary", "Local mapping-back"],
            "source_label": f"Synthetic summary checklist {item_id}",
            "targeting": f"{target_side} {point_kind} {point_index}: {point_text}",
            "opponent_point_kind": point_kind,
            "opponent_point_index": point_index,
            "opponent_point": point_text,
            "weakness": weakness,
            "weakness_lines": [weakness] + mapped_checks[:5],
            "mapping_pattern": pattern or name,
            "mapping_source": f"Synthetic summary checklist {item_id}",
            "plain_guide": guide,
            "attack_item": {
                "dimension": dim,
                "targeting": f"{target_side} {point_kind} {point_index}: {point_text}",
                "finding": weakness,
                "question": attack_question,
                "attack": weakness,
                "local_weakness_rule": "Synthetic summary local comparison",
            },
            "rebuttal_item": {},
            "priority_reason": f"Local comparison of summary checklist {item_id} against current-case {point_kind}: {self.compact(point_text, 100)}.",
        }

    def summary_item_severity(self, item, dim, pattern, checks):
        raw = self.ui_en_text((item or {}).get("severity") or "").strip().lower()
        text = " ".join([dim, str(pattern or ""), " ".join(str(x) for x in (checks or []))]).lower()
        high_words = ["causation", "burden", "missing evidence", "no evidence", "contract formation", "authority", "fatal", "core", "liability", "proof gap"]
        medium_words = ["credibility", "calculation", "notice", "timeline", "procedure", "quantum", "inconsistency", "source"]
        if raw in {"high", "severe", "critical"} or dim in {"Damage Causation", "Legal Application", "Burden of Proof", "Missing Evidence", "Quantum Dispute"} or any(w in text for w in high_words):
            return "High"
        if raw in {"medium", "med"} or dim in {"Fact Challenge", "Logic Gap", "Procedural Defect"} or any(w in text for w in medium_words):
            return "Medium"
        return "Low"

    def build_synthetic_summary_mapping_scan_state(self, summary):
        if not isinstance(summary, dict):
            summary = {}
        positive_checklist, negative_checklist = self.synthetic_side_checklists(summary)
        positive_points = self.current_real_case_points_for_side("positive")
        negative_points = self.current_real_case_points_for_side("negative")
        positive_items = []
        negative_items = []

        for item in positive_checklist:
            search_text = json.dumps(item, ensure_ascii=False) if isinstance(item, dict) else str(item)
            if positive_points:
                point = self.best_real_point_for_synthetic_pattern(search_text, positive_points)
                candidate = self.synthetic_summary_candidate("positive", len(positive_items) + 1, item, point)
                if candidate:
                    positive_items.append(candidate)
        for item in negative_checklist:
            search_text = json.dumps(item, ensure_ascii=False) if isinstance(item, dict) else str(item)
            if negative_points:
                point = self.best_real_point_for_synthetic_pattern(search_text, negative_points)
                candidate = self.synthetic_summary_candidate("negative", len(negative_items) + 1, item, point)
                if candidate:
                    negative_items.append(candidate)

        for display_idx, item in enumerate(positive_items, 1):
            item["display_id"] = str(display_idx)
            item["select_id"] = f"P{display_idx}"
        for display_idx, item in enumerate(negative_items, 1):
            item["display_id"] = str(display_idx)
            item["select_id"] = f"N{display_idx}"

        selected_dims = sorted({x.get("dimension", "Fact Challenge") for x in positive_items + negative_items})
        synthetic_cases = payload.get("synthetic_cases") or []
        scan_scope = payload.get("scan_scope") or f"all {len(synthetic_cases)} fictional cases"
        base_state = {
            "run_id": _dt.datetime.now().strftime("synthetic_summary_mapping_%Y%m%d_%H%M%S"),
            "case_key": short_hash(json.dumps(summary, ensure_ascii=False)[:2000]),
            "selected_dimensions": selected_dims,
            "opponent_point_counts": {"arguments": 0, "evidence": 0},
            "options": {
                "case_name": self.case_name_var.get().strip(),
                "workflow_mode": "synthetic_summary_local_real_case_scan",
                "confidentiality_mode": self.confidential_var.get(),
                "privacy_note": "A model saw only fictional similar cases. The real-case comparison and weakness-card generation were completed locally.",
            },
            "rounds": {"round1_opponent_attack": [], "round2_my_rebuttal": []},
        }
        return {
            "run_id": base_state["run_id"],
            "case_key": base_state["case_key"],
            "positive_state": dict(base_state, opponent_point_counts={"arguments": len(positive_items), "evidence": 0}),
            "negative_state": dict(base_state, opponent_point_counts={"arguments": len(negative_items), "evidence": 0}),
            "positive_weaknesses": positive_items,
            "negative_weaknesses": negative_items,
            "weakness_candidates": positive_items + negative_items,
            "selected_dimensions": selected_dims,
            "source": "synthetic_summary_local_real_case_scan",
        }

    def map_synthetic_summary_back_to_case(self, summary):
        state = self.build_synthetic_summary_mapping_scan_state(summary)
        if not state.get("weakness_candidates"):
            messagebox.showinfo(
                "No Local Weakness Cards",
                "No weakness card was generated because the summary checklist could not be matched to concrete current-case arguments or evidence.\n\n"
                "Add or import real Positive/Negative arguments or evidence first, then run Scan Real Case Locally again.",
            )
            return
        self.last_weakness_state = state
        self.weakness_candidates = state["weakness_candidates"]
        self.save_weakness_scan_artifacts(state)
        self.open_weakness_scan_window(state)
        self.status_var.set("Status: synthetic summary compared locally against current case")

    def synthetic_model_card_to_candidate(self, card, side, idx):
        if not isinstance(card, dict):
            card = {"one_sentence_summary": str(card)}
        summary = self.ui_en_text(card.get("conclusion") or card.get("surface_card_wording") or card.get("one_sentence_summary") or card.get("summary") or card.get("point") or "")
        surface_preview = self.ui_en_text(card.get("surface_summary") or "")
        full_dimension_report = str(card.get("full_dimension_report") or "").strip()
        source_case = self.ui_en_text(card.get("source_case") or card.get("source_cases") or "Synthetic case pack")
        target_material = self.ui_en_text(card.get("target_material") or card.get("target_claim_or_element") or "")
        target = " - ".join(x for x in [source_case, target_material] if x) or summary or "Synthetic-side claim"
        name = summary or self.ui_en_text(card.get("name") or "Synthetic weakness")
        missing = card.get("missing_evidence_or_step") or card.get("real_case_checks") or []
        if isinstance(missing, str):
            missing = [missing]
        attack_script = card.get("attack_questions") or card.get("attack_script") or []
        if isinstance(attack_script, str):
            attack_script = [attack_script]
        checklist = card.get("mapping_checklist") or {}
        if not isinstance(checklist, dict):
            checklist = {}
        severity = self.ui_en_text(card.get("severity") or "Medium").title()
        requested_dim = self.ui_en_text(card.get("dimension") or "")
        enabled_dimensions = self.selected_dimensions()
        dim = requested_dim if requested_dim in enabled_dimensions else self.synthetic_pattern_dimension(" ".join([name, summary, target]))
        source = "Model scan of local synthetic analogue case"
        defence_items = card.get("defence_preparation") or []
        if isinstance(defence_items, str):
            defence_items = [defence_items]
        model_full_card = {
            "plain_explanation": self.ui_en_text(card.get("plain_explanation") or card.get("why_it_matters") or summary),
            "core_problem": self.ui_en_text(card.get("core_problem") or card.get("pattern") or name),
            "what_it_proves": self.ui_en_text(card.get("what_it_proves") or "The fictional material supports only the narrow fact it directly records."),
            "what_it_does_not_prove": self.ui_en_text(card.get("what_it_does_not_prove") or summary),
            "simple_example": self.ui_en_text(card.get("simple_example") or ""),
            "attack_questions": [self.ui_en_text(x) for x in attack_script if str(x).strip()],
            "defence_preparation": [self.ui_en_text(x) for x in defence_items if str(x).strip()],
            "source_explanation": self.ui_en_text(card.get("source_explanation") or f"Identified directly in {source_case}."),
            "one_sentence_summary": self.ui_en_text(card.get("one_sentence_summary") or summary),
        }
        guide = {
            "name": name,
            "summary": surface_preview or summary,
            "one_sentence_summary": summary,
            "surface_summary": surface_preview,
            "full_dimension_report": full_dimension_report,
            "target_claim_or_element": target,
            "mapping_checklist": checklist,
            "missing_evidence_or_step": [self.ui_en_text(x) for x in missing if str(x).strip()],
            "attack_script": [self.ui_en_text(x) for x in attack_script if str(x).strip()],
            "signal_of_success": self.ui_en_text(card.get("signal_of_success") or "The synthetic opponent cannot produce the requested record or gives an uncertain answer."),
            "defense": self.ui_en_text("; ".join(card.get("defence_preparation") or []) if isinstance(card.get("defence_preparation"), list) else card.get("defence_preparation") or ""),
            "severity": severity,
            "target": target,
            "source": source,
            "reason": "The synthetic analogue was scanned by an authorized model provider after local privacy reduction.",
            "tags": "Synthetic analogue, model weakness scan",
            "attacker": "Negative side" if side == "positive" else "Positive side",
            "defender": "Positive side" if side == "positive" else "Negative side",
            "model_full_card": model_full_card,
        }
        return {
            "id": f"MS{side[:1].upper()}{idx:03d}",
            "select_id": f"MS{side[:1].upper()}{idx}",
            "display_id": str(idx),
            "side": side,
            "dimension": dim,
            "score": 80,
            "priority_score": 80,
            "rule": "Model weakness scan on synthetic analogue",
            "risk_tags": ["Synthetic analogue", "Model weakness scan"],
            "source_label": source,
            "synthetic_source_case": source_case,
            "synthetic_freeform_scan": bool(full_dimension_report),
            "full_dimension_report": full_dimension_report,
            "targeting": target,
            "opponent_point_kind": "synthetic claim",
            "opponent_point_index": idx,
            "opponent_point": target,
            "weakness": full_dimension_report or summary or target,
            "weakness_lines": [x for x in [summary, surface_preview] if x],
            "plain_guide": guide,
            "attack_item": {
                "dimension": dim,
                "targeting": target,
                "finding": summary,
                "question": "\n".join(guide["attack_script"]),
                "attack": summary,
            },
            "rebuttal_item": {},
            "priority_reason": f"Generated directly from model review of {source_case}; it is not a finding about the original real matter.",
        }

    def build_synthetic_model_scan_state(self, payload, result):
        positive_cards, negative_cards = self.synthetic_side_checklists(result)
        positive_items = [
            self.synthetic_model_card_to_candidate(card, "positive", idx)
            for idx, card in enumerate(positive_cards, 1)
        ]
        negative_items = [
            self.synthetic_model_card_to_candidate(card, "negative", idx)
            for idx, card in enumerate(negative_cards, 1)
        ]
        metadata = result.get("engine_metadata") if isinstance(result.get("engine_metadata"), dict) else {}
        for item in positive_items + negative_items:
            if metadata.get("provider"):
                item["provider"] = metadata.get("provider")
            if metadata.get("model"):
                item["model"] = metadata.get("model")
        selected_dims = sorted({x.get("dimension", "Fact Challenge") for x in positive_items + negative_items})
        synthetic_cases = payload.get("synthetic_cases") or []
        scan_scope = payload.get("scan_scope") or f"all {len(synthetic_cases)} fictional cases"
        base_state = {
            "run_id": _dt.datetime.now().strftime("synthetic_model_scan_%Y%m%d_%H%M%S"),
            "case_key": short_hash(json.dumps(payload, ensure_ascii=False)[:2000]),
            "selected_dimensions": selected_dims,
            "opponent_point_counts": {"arguments": 0, "evidence": 0},
            "options": {
                "case_name": "Fictional Case Weakness Review",
                "scan_scope": scan_scope,
                "workflow_mode": "synthetic_analogue_model_weakness_scan",
                "confidentiality_mode": self.confidential_var.get(),
                "privacy_note": "Only locally generated fictional case material was sent to the selected model provider. No result was mapped to the real matter.",
            },
            "rounds": {"round1_opponent_attack": [], "round2_my_rebuttal": []},
        }
        return {
            "run_id": base_state["run_id"],
            "case_key": base_state["case_key"],
            "positive_state": dict(base_state, opponent_point_counts={"arguments": len(positive_items), "evidence": 0}),
            "negative_state": dict(base_state, opponent_point_counts={"arguments": len(negative_items), "evidence": 0}),
            "positive_weaknesses": positive_items,
            "negative_weaknesses": negative_items,
            "weakness_candidates": positive_items + negative_items,
            "selected_dimensions": selected_dims,
            "source": "synthetic_analogue_model_scan",
        }

    def run_synthetic_model_weakness_scan(
        self,
        payload,
        parent_window=None,
        progress_widget=None,
        status_label=None,
        buttons=None,
        dimensions_override=None,
    ):
        if not self.ensure_active_verified_provider():
            messagebox.showwarning(
                "Missing Model Provider",
                "Please verify a model provider first. This step sends only the fictional synthetic analogue case pack, not the original real matter.",
            )
            return
        enabled_dimensions = list(dimensions_override or self.selected_dimensions())
        if not enabled_dimensions:
            messagebox.showwarning(
                "No Dimension Selected",
                "Select at least one review dimension before scanning fictional matters.",
                parent=parent_window or self.root,
            )
            return
        fictional_case_count = len(payload.get("synthetic_cases") or [])
        expected_calls = fictional_case_count * len(enabled_dimensions) * 2
        ok = messagebox.askyesno(
            "Synthetic Case Model Scan",
            f"The software will independently review {fictional_case_count} fictional case(s) through {len(enabled_dimensions)} enabled dimension(s).\n\n"
            "Each dimension first writes one unrestricted free-form analysis. A short second pass then extracts only the outside card titles and side labels; it does not rewrite the analysis.\n\n"
            f"Expected provider calls: approximately {expected_calls} ({len(enabled_dimensions) * 2} per fictional case).\n\n"
            "The results will describe those fictional cases only. They will not be mapped back to the original real matter.\n\n"
            "The original real matter is not sent.\n\n"
            "Continue?",
            parent=parent_window or self.root,
        )
        if not ok:
            return
        self.set_weakness_scan_controls_locked(True)
        try:
            self.scan_btn.config(state=tk.DISABLED)
        except (tk.TclError, AttributeError):
            pass
        buttons = buttons or []
        for btn in buttons:
            try:
                btn.config(state=tk.DISABLED)
            except Exception:
                pass
        if status_label is not None:
            try:
                status_label.config(text="Starting independent free-form dimension reviews...")
            except Exception:
                pass
        if progress_widget is not None:
            try:
                progress_widget.start(12)
            except Exception:
                pass
        self.status_var.set("Status: sending synthetic analogue case to model for weakness scan...")

        def finish_ui(message):
            if progress_widget is not None:
                try:
                    progress_widget.stop()
                except Exception:
                    pass
            for btn in buttons:
                try:
                    btn.config(state=tk.NORMAL)
                except Exception:
                    pass
            self.set_weakness_scan_controls_locked(False)
            try:
                self.scan_btn.config(state=tk.NORMAL)
            except (tk.TclError, AttributeError):
                pass
            if status_label is not None:
                try:
                    status_label.config(text=message)
                except Exception:
                    pass

        def worker():
            try:
                cases = payload.get("synthetic_cases") or []
                dimensions = list(dimensions_override or self.selected_dimensions())
                if not dimensions:
                    raise RuntimeError("Select at least one review dimension before scanning fictional matters.")
                combined_positive = []
                combined_negative = []
                case_errors = []
                completed_dimension_reviews = 0
                total_dimension_reviews = len(cases) * len(dimensions)
                for case_index, fictional_case in enumerate(cases, 1):
                    case_payload = copy.deepcopy(payload)
                    case_payload["synthetic_cases"] = [copy.deepcopy(fictional_case)]
                    case_payload["scan_scope"] = f"fictional case {case_index} of {len(cases)}"
                    title = str(fictional_case.get("title") or f"Fictional case {case_index}")
                    for dimension_index, dimension in enumerate(dimensions, 1):
                        review_number = ((case_index - 1) * len(dimensions)) + dimension_index
                        self.root.after(
                            0,
                            lambda n=review_number, total=total_dimension_reviews, case_title=title, dim=dimension: (
                                status_label.config(text=f"Free analysis {n}/{total}: {case_title} / {dim}")
                                if status_label is not None else None
                            ),
                        )
                        try:
                            free_analysis = self.call_cloud_text(
                                self.synthetic_dimension_free_analysis_prompt(case_payload, dimension),
                                max_tokens=6000,
                            )
                            if not str(free_analysis or "").strip():
                                raise RuntimeError("free-form dimension analysis was empty")
                            self.root.after(
                                0,
                                lambda n=review_number, total=total_dimension_reviews, dim=dimension: (
                                    status_label.config(text=f"Extracting card titles {n}/{total}: {dim}")
                                    if status_label is not None else None
                                ),
                            )
                            extracted = self.call_cloud_json(
                                self.synthetic_surface_extraction_prompt(free_analysis, dimension, title),
                                max_tokens=2200,
                                repair=False,
                            )
                            weaknesses = extracted.get("important_weaknesses") or [] if isinstance(extracted, dict) else []
                            if not isinstance(weaknesses, list):
                                raise RuntimeError("surface-title extraction did not return a list")
                            for finding in weaknesses:
                                if not isinstance(finding, dict):
                                    continue
                                side = str(finding.get("affected_side") or "").strip().lower()
                                conclusion = self.ui_en_text(finding.get("conclusion") or "").strip()
                                if side not in ("positive", "negative") or not conclusion:
                                    continue
                                card = dict(finding)
                                card.update({
                                    "side": side,
                                    "source_case": title,
                                    "dimension": dimension,
                                    "name": conclusion,
                                    "surface_card_wording": conclusion,
                                    "one_sentence_summary": conclusion,
                                    "full_dimension_report": str(free_analysis).strip(),
                                    "analysis_mode": "free_form_then_surface_extraction",
                                })
                                if side == "positive":
                                    combined_positive.append(card)
                                else:
                                    combined_negative.append(card)
                            completed_dimension_reviews += 1
                        except Exception as dimension_exc:
                            case_errors.append(f"{title} / {dimension}: {dimension_exc}")
                        if review_number < total_dimension_reviews:
                            time.sleep(0.8)
                if not combined_positive and not combined_negative:
                    detail = "; ".join(case_errors) or "no usable fictional-case weakness cards were returned"
                    raise RuntimeError(f"All selected fictional-case scans failed: {detail}")
                combined_positive = self.dedupe_synthetic_model_cards(combined_positive)
                combined_negative = self.dedupe_synthetic_model_cards(combined_negative)
                res = {
                    "summary_title": "Selected Fictional-Case Weakness Scan",
                    "overview": f"Completed {completed_dimension_reviews} of {total_dimension_reviews} independent free-form dimension reviews.",
                    "positive_side_weakness_patterns": combined_positive,
                    "negative_side_weakness_patterns": combined_negative,
                    "case_errors": case_errors,
                    "analysis_mode": "independent_dimension_free_form_then_surface_extraction",
                    "engine_metadata": {
                        "provider": self.cloud_provider_var.get().strip() or "Not recorded",
                        "model": self.cloud_model_var.get().strip() or "Not recorded",
                    },
                }
                self.last_synthetic_weakness_summary = res
                def finish_and_open():
                    try:
                        panel_state = self.build_synthetic_model_scan_state(payload, res)
                        finish_ui(
                            f"Complete: {len(panel_state.get('weakness_candidates') or [])} fictional-case weakness card(s) ready."
                        )
                        self.last_weakness_state = panel_state
                        self.weakness_candidates = panel_state["weakness_candidates"]
                        self.save_weakness_scan_artifacts(panel_state)
                        self.open_weakness_scan_window(panel_state)
                        if status_label is not None:
                            status_label.config(
                                text="Complete: fictional-case weakness cards opened. The real matter was not analysed or mapped."
                            )
                        self.status_var.set("Status: fictional-case weakness scan complete; no real-case mapping performed")
                    except Exception as open_exc:
                        finish_ui("Could not open the fictional-case weakness cards.")
                        messagebox.showerror("Synthetic Weakness Display Failed", str(open_exc))
                self.root.after(0, finish_and_open)
            except Exception as exc:
                err = str(exc)
                self.root.after(0, lambda: finish_ui("Model weakness summary failed. Check API/provider settings and try again."))
                self.root.after(0, lambda: messagebox.showerror("Model Weakness Summary Failed", err))
                self.root.after(0, lambda: self.status_var.set("Status: synthetic model weakness summary failed"))

        threading.Thread(target=worker, daemon=True).start()

    def synthetic_pattern_dimension(self, text):
        return self.simple_single_point_dimension(str(text or ""))

    def dedupe_synthetic_model_cards(self, cards):
        """Merge repeated fictional conclusions while preserving every source case."""
        kept = []
        signatures = []
        for card in cards or []:
            if not isinstance(card, dict):
                continue
            headline = str(
                card.get("surface_card_wording")
                or card.get("one_sentence_summary")
                or card.get("name")
                or ""
            ).lower()
            dimension = str(card.get("dimension") or "").strip().lower()
            word_signature = {
                word for word in re.findall(r"[a-z0-9]+", headline) if len(word) > 2
            }
            signature = (dimension, word_signature)
            duplicate_index = None
            for index, existing in enumerate(signatures):
                existing_dimension, existing_words = existing
                if dimension != existing_dimension or not word_signature or not existing_words:
                    continue
                overlap = len(word_signature & existing_words) / max(len(word_signature | existing_words), 1)
                if word_signature == existing_words or (len(word_signature) >= 5 and overlap >= 0.95):
                    duplicate_index = index
                    break
            if duplicate_index is None:
                kept.append(copy.deepcopy(card))
                signatures.append(signature)
                continue
            existing_card = kept[duplicate_index]
            sources = []
            for source in [existing_card.get("source_case"), card.get("source_case")]:
                for part in str(source or "").split("; "):
                    part = part.strip()
                    if part and part not in sources:
                        sources.append(part)
            existing_card["source_case"] = "; ".join(sources)
        return kept

    def current_real_case_points_for_side(self, side):
        if side == "positive":
            raw_points = (
                self.numbered_points(self.get_text(self.t_pos_args), "argument")
                + self.numbered_points(self.get_text(self.t_pos_ev), "evidence")
            )
        else:
            raw_points = (
                self.numbered_points(self.get_text(self.t_neg_args), "argument")
                + self.numbered_points(self.get_text(self.t_neg_ev), "evidence")
            )
        points = []
        for point in raw_points:
            text = re.sub(r"\s+", " ", str(point.get("text", "")).strip())
            if not text:
                continue
            if self.is_placeholder_case_target(text):
                continue
            if not self.has_case_specific_marker(text):
                continue
            points.append({**point, "text": text})
        return points

    def is_placeholder_case_target(self, text):
        low = str(text or "").lower()
        placeholders = [
            "real-case materials should be checked",
            "synthetic pattern",
            "analogue pattern",
            "the targeted argument or evidence",
            "the opponent's point",
            "positive side real-case",
            "negative side real-case",
            "case can argue",
            "opponent's conduct",
            "core liability issue",
            "must be tied to facts",
            "legal elements, and loss",
            "the selected point",
            "this point",
            "the claim",
            "the argument",
            "current-case point",
            "supposedly satisfied",
            "evidence angle",
            "contract angle",
            "argument 1",
            "argument 2",
            "argument 3",
            "positive side synthetic",
            "negative side synthetic",
            "check against this analogue",
            "map it back to the real case locally",
            "break the opponent's conclusion back into legal elements",
            "argue existing documents, communications, video, photos, or records",
            "balance-of-probabilities proof path",
            "attack originality, continuity, completeness, source reliability",
            "case can argue that the opponent's conduct triggers",
            "the record does not yet",
            "proof, rule application, or causation",
            "[specific",
            "[fill",
            "placeholder",
        ]
        return any(x in low for x in placeholders)

    def candidate_surface_rejection_reason(self, candidate):
        guide = self.weakness_plain_guide(candidate)
        summary = guide.get("one_sentence_summary") or guide.get("summary") or ""
        target_claim = guide.get("target_claim_or_element") or guide.get("target") or ""
        missing_items = guide.get("missing_evidence_or_step") or []
        attack_script = guide.get("attack_script") or []
        mapping_checklist = guide.get("mapping_checklist") or {}
        blob = "\n".join([
            str(guide.get("name", "")),
            str(summary),
            str(target_claim),
            "\n".join(str(x) for x in missing_items),
            "\n".join(str(x) for x in attack_script),
        ])
        if self.is_placeholder_case_target(blob):
            return "template_or_placeholder"
        if not self.full_card_passes_specificity_check(summary, target_claim, missing_items, attack_script, mapping_checklist):
            return "not_mapped_to_concrete_case_facts"
        return ""

    def candidate_surface_key(self, candidate):
        guide = self.weakness_plain_guide(candidate)
        text = " ".join([
            str(guide.get("name", "")),
            str(guide.get("one_sentence_summary") or guide.get("summary") or ""),
            str(guide.get("target_claim_or_element") or guide.get("target") or ""),
        ]).lower()
        text = re.sub(r"\b(positive|negative)\s+side\b", "", text)
        text = re.sub(r"\b(argument|evidence)\s*\d+\b", "", text)
        text = re.sub(r"[^a-z0-9]+", " ", text).strip()
        words = [w for w in text.split() if len(w) > 2]
        return " ".join(words[:34])

    def filter_surface_ready_candidates(self, candidates):
        kept = []
        seen = set()
        rejected = []
        pending = []
        for candidate in candidates or []:
            reason = self.candidate_surface_rejection_reason(candidate)
            if reason:
                candidate["surface_rejected_reason"] = reason
                rejected.append(candidate)
                if len(pending) < 6:
                    pending_candidate = copy.deepcopy(candidate)
                    pending_candidate["surface_pending"] = True
                    pending_candidate["plain_guide"] = self.pending_surface_guide(pending_candidate, reason)
                    pending.append(pending_candidate)
                continue
            key = self.candidate_surface_key(candidate)
            if key and key in seen:
                candidate["surface_rejected_reason"] = "duplicate_surface_card"
                rejected.append(candidate)
                continue
            if key:
                seen.add(key)
            kept.append(candidate)
        if kept:
            return kept, rejected
        return pending, rejected

    def pending_surface_guide(self, candidate, reason):
        side = "Positive side" if candidate.get("side") == "positive" else "Negative side"
        kind = self.candidate_kind_en(candidate) or "argument/evidence"
        target = self.ui_en_text(candidate.get("opponent_point") or candidate.get("targeting", ""))
        if self.bad_ui_text(target):
            target = f"{side} {kind} {candidate.get('opponent_point_index', '')}".strip()
        reason_text = (
            "The full card was refused because this pattern is still too generic."
            if reason == "template_or_placeholder"
            else "The full card was refused because it is not mapped to concrete case facts yet."
        )
        return {
            "name": "Needs concrete facts",
            "summary": reason_text,
            "one_sentence_summary": (
                f"{reason_text} Add party names, dates, clauses, records, payments, messages, reports, "
                f"or other concrete evidence for this {kind}."
            ),
            "target_claim_or_element": target,
            "mapping_checklist": {},
            "missing_evidence_or_step": [],
            "attack_script": [],
            "signal_of_success": "No court-ready question is displayed until the point is mapped to concrete facts.",
            "defense": "Add concrete records or case facts, then rerun the scan.",
            "severity": "Pending",
            "target": target,
            "source": "Rejected template-pattern card",
            "reason": reason_text,
            "tags": "Needs facts, not court-ready",
            "attacker": "Negative side" if candidate.get("side") == "positive" else "Positive side",
            "defender": side,
        }

    def has_case_specific_marker(self, text):
        text = str(text or "")
        if re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b20\d{2}\b|\b19\d{2}\b", text):
            return True
        if re.search(r"\$\s?\d|AUD\s?\d|USD\s?\d|RMB\s?\d|CNY\s?\d|¥\s?\d|\b\d+(?:,\d{3})*(?:\.\d+)?\s?(?:dollars|yuan|元|万元|million|k|%)\b", text, re.I):
            return True
        if re.search(r"\b(?:contract|agreement|clause|section|invoice|receipt|email|message|letter|report|record|log|photo|video|advertisement|payment|bank|signature|order|delivery|notice|permit|certificate|inspection)\b", text, re.I):
            return True
        if re.search(r"[\u4e00-\u9fff]{2,}(?:合同|协议|条款|发票|收据|邮件|微信|短信|报告|记录|日志|照片|视频|广告|付款|银行|签字|订单|交付|通知|检测|鉴定)", text):
            return True
        if re.search(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}\b", text):
            return True
        return False

    def best_real_point_for_synthetic_pattern(self, pattern_text, real_points):
        if not real_points:
            return None
        attack_text = str(pattern_text or "").lower()
        best_score = -1
        best_point = None
        for point in real_points:
            tokens = set(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]{3,}", point["text"].lower()))
            score = sum(1 for token in tokens if token in attack_text)
            if score > best_score:
                best_score = score
                best_point = point
        return best_point or real_points[0]

    def synthetic_pattern_candidate(self, side, seq, text, source, real_point):
        clean = self.ui_en_text(text) or str(text or "").strip()
        clean = re.sub(r"\s+", " ", clean).strip()
        dim = self.synthetic_pattern_dimension(clean)
        target_side = "Positive side" if side == "positive" else "Negative side"
        point_text = re.sub(r"\s+", " ", str((real_point or {}).get("text", "")).strip())
        if not point_text or self.is_placeholder_case_target(point_text):
            return None
        point_kind = self.ui_en_text((real_point or {}).get("kind", "")) or "argument"
        point_index = (real_point or {}).get("index") or seq
        weakness_text = (
            f"{clean} Mapping-back target: {target_side} {point_kind} {point_index} - "
            f"{self.compact(point_text, 220)}"
        )
        return {
            "id": f"SYN{side[:1].upper()}{seq:03d}",
            "select_id": f"SYN{side[:1].upper()}{seq}",
            "display_id": str(seq),
            "side": side,
            "dimension": dim,
            "score": 30,
            "priority_score": 30,
            "rule": "Synthetic analogue pattern",
            "risk_tags": ["Synthetic analogue", "Mapping-back"],
            "source_label": source,
            "targeting": f"{target_side} {point_kind} {point_index}: {point_text}",
            "opponent_point_kind": point_kind,
            "opponent_point_index": point_index,
            "opponent_point": point_text,
            "weakness": weakness_text,
            "weakness_lines": [weakness_text],
            "mapping_pattern": clean,
            "mapping_source": source,
            "attack_item": {
                "dimension": dim,
                "targeting": f"{target_side} {point_kind} {point_index}: {point_text}",
                "finding": weakness_text,
                "question": f"How does this analogue weakness apply to this specific point: {point_text}?",
                "attack": weakness_text,
            },
            "rebuttal_item": {},
            "priority_reason": f"Fictional analogue pattern has been mapped to a specific current-case {point_kind}: {self.compact(point_text, 100)}.",
        }

    def build_synthetic_mapping_scan_state(self, payload):
        positive_items = []
        negative_items = []
        positive_points = self.current_real_case_points_for_side("positive")
        negative_points = self.current_real_case_points_for_side("negative")

        def add_pattern(pattern_text, source_label):
            if positive_points:
                point = self.best_real_point_for_synthetic_pattern(pattern_text, positive_points)
                candidate = self.synthetic_pattern_candidate("positive", len(positive_items) + 1, pattern_text, source_label, point)
                if candidate:
                    positive_items.append(candidate)
            if negative_points:
                point = self.best_real_point_for_synthetic_pattern(pattern_text, negative_points)
                candidate = self.synthetic_pattern_candidate("negative", len(negative_items) + 1, pattern_text, source_label, point)
                if candidate:
                    negative_items.append(candidate)

        for item in payload.get("synthetic_cases") or []:
            title = self.ui_en_text(item.get("title", "Synthetic case")) or "Synthetic case"
            for weakness in item.get("attackable_weaknesses") or []:
                add_pattern(weakness, f"{title} - attackable weakness")
            for question in item.get("mapping_back_questions") or []:
                add_pattern(question, f"{title} - mapping-back question")
        for pattern in payload.get("cross_case_weakness_patterns") or []:
            add_pattern(pattern, "Cross-case weakness pattern")

        selected_dims = sorted({x.get("dimension", "Fact Challenge") for x in positive_items + negative_items})
        base_state = {
            "run_id": _dt.datetime.now().strftime("synthetic_mapping_%Y%m%d_%H%M%S"),
            "case_key": short_hash(json.dumps(payload, ensure_ascii=False)[:2000]),
            "selected_dimensions": selected_dims,
            "opponent_point_counts": {"arguments": 0, "evidence": 0},
            "options": {
                "case_name": self.case_name_var.get().strip(),
                "workflow_mode": "synthetic_analogue_mapping_back",
                "confidentiality_mode": self.confidential_var.get(),
                "privacy_note": "Fictional analogue patterns were mapped back locally; no reusable training store was created.",
            },
            "rounds": {"round1_opponent_attack": [], "round2_my_rebuttal": []},
        }
        panel_state = {
            "run_id": base_state["run_id"],
            "case_key": base_state["case_key"],
            "positive_state": dict(base_state, opponent_point_counts={"arguments": len(positive_items), "evidence": 0}),
            "negative_state": dict(base_state, opponent_point_counts={"arguments": len(negative_items), "evidence": 0}),
            "positive_weaknesses": positive_items,
            "negative_weaknesses": negative_items,
            "weakness_candidates": positive_items + negative_items,
            "selected_dimensions": selected_dims,
            "source": "synthetic_analogue_mapping_back",
        }
        return panel_state

    def map_synthetic_analogue_back_to_case(self, payload):
        state = self.build_synthetic_mapping_scan_state(payload)
        if not state.get("weakness_candidates"):
            messagebox.showinfo(
                "No Concrete Mapping",
                "No weakness card was generated because the analogue patterns could not be mapped to concrete current-case arguments or evidence.\n\n"
                "Add real Positive/Negative arguments or evidence first, then run Map Patterns To Current Case again.",
            )
            return
        self.last_weakness_state = state
        self.weakness_candidates = state["weakness_candidates"]
        self.save_weakness_scan_artifacts(state)
        self.open_weakness_scan_window(state)
        self.status_var.set("Status: synthetic analogue patterns mapped back to current case")

    def open_synthetic_advanced_opposition(self, synthetic_case, case_number):
        routes = self.verified_provider_snapshots()
        if not routes:
            messagebox.showwarning(
                "Verified Model Required",
                "Verify at least one model provider before starting the fictional-case 18-dimension opposition.",
                parent=self.root,
            )
            return

        title = str(synthetic_case.get("title") or f"Analogue {case_number:02d}").strip()
        fictional_matter = (
            "FICTIONAL SYNTHETIC MATTER ONLY\n"
            "The following material is fictional. Do not infer, request, or introduce facts from the current real matter.\n\n"
            + self.render_synthetic_case_detail(copy.deepcopy(synthetic_case), case_number)
        )
        from Nido_Advanced_Main_Opposition_2R_EN import open_advanced_main_opposition_review
        open_advanced_main_opposition_review(
            self.root,
            fictional_matter,
            routes,
            f"Synthetic Analogue {case_number:02d} - {title}",
            "Only this selected fictional matter is transmitted. No current real-case text, argument, or evidence is included.",
            model_caller=self._offline_advanced_model_call,
        )

    def open_synthetic_analogue_window(self, payload):
        win = tk.Toplevel(self.root)
        win.title("Synthetic Analogue Case Pack")
        win.geometry("1100x760")
        win.configure(bg=self.C["bg"])
        tk.Label(
            win,
            text="Synthetic Analogue Case Pack",
            bg=self.C["bg"],
            fg=self.C["gold"],
            font=("Microsoft YaHei UI", 15, "bold"),
        ).pack(anchor=tk.W, padx=14, pady=(12, 4))
        tk.Label(
            win,
            text="Step 1 is local-only: generate 20 similar fictional matters. Add, delete, or edit the pack here. Select between 1 and 5 fictional cases, then run the gold control. Every selected case is independently investigated through all 18 dimensions; the original real matter is not sent.",
            bg=self.C["bg"],
            fg=self.C["muted"],
            font=("Microsoft YaHei UI", 10),
            wraplength=920,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, padx=14, pady=(0, 8))
        body = tk.Frame(win, bg=self.C["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 10))

        left = tk.Frame(body, bg=self.C["panel"], padx=8, pady=8, width=310)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
        left.pack_propagate(False)
        tk.Label(left, text="Case Directory", bg=self.C["panel"], fg=self.C["gold"], font=("Microsoft YaHei UI", 11, "bold")).pack(anchor=tk.W)
        case_list = tk.Listbox(left, bg=self.C["entry"], fg=self.C["text"], selectbackground="#1f6feb", selectforeground="#ffffff", relief="flat", font=("Microsoft YaHei UI", 10), activestyle="none", selectmode=tk.EXTENDED, exportselection=False)
        case_list.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

        detail = scrolledtext.ScrolledText(body, bg=self.C["entry"], fg=self.C["text"], wrap=tk.WORD, relief="flat", font=("Microsoft YaHei UI", 11))
        self.bind_local_scroll(detail)
        detail.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        def refresh_case_list(select_index=None):
            case_list.delete(0, tk.END)
            cases = payload.setdefault("synthetic_cases", [])
            for idx, item in enumerate(cases, 1):
                case_list.insert(tk.END, f"{idx:02d}. {item.get('title', 'Untitled Analogue')}")
            if cases:
                if select_index is None:
                    select_index = min(max(case_list.curselection()[0] if case_list.curselection() else 0, 0), len(cases) - 1)
                select_index = min(max(int(select_index), 0), len(cases) - 1)
                case_list.selection_clear(0, tk.END)
                case_list.selection_set(select_index)
                case_list.activate(select_index)
                show_case_detail(select_index)
            else:
                detail.delete("1.0", tk.END)
                detail.insert("1.0", "No synthetic cases in this pack. Use Add Case to create one.")

        def selected_case_index():
            sel = case_list.curselection()
            return int(sel[0]) if sel else 0

        def selected_case_indices():
            return [int(index) for index in case_list.curselection()]

        def show_case_detail(index=None):
            cases = payload.setdefault("synthetic_cases", [])
            if not cases:
                return
            if index is None:
                index = selected_case_index()
            index = min(max(int(index), 0), len(cases) - 1)
            detail.delete("1.0", tk.END)
            detail.insert("1.0", self.render_synthetic_case_detail(cases[index], index + 1))

        def add_case_dialog():
            edit = tk.Toplevel(win)
            edit.title("Add Synthetic Case")
            edit.geometry("760x560")
            edit.configure(bg=self.C["bg"])
            tk.Label(edit, text="Title", bg=self.C["bg"], fg=self.C["text"]).pack(anchor=tk.W, padx=12, pady=(12, 2))
            title_var = tk.StringVar(value=f"Manual Analogue {len(payload.setdefault('synthetic_cases', [])) + 1:02d}")
            tk.Entry(edit, textvariable=title_var, bg=self.C["entry"], fg=self.C["text"], insertbackground=self.C["text"], relief="flat", font=("Microsoft YaHei UI", 11)).pack(fill=tk.X, padx=12)
            tk.Label(edit, text="Fictional case content", bg=self.C["bg"], fg=self.C["text"]).pack(anchor=tk.W, padx=12, pady=(10, 2))
            editor = scrolledtext.ScrolledText(edit, bg=self.C["entry"], fg=self.C["text"], insertbackground=self.C["text"], wrap=tk.WORD, relief="flat", font=("Microsoft YaHei UI", 10))
            editor.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 10))
            editor.insert("1.0", "Fictional facts:\n\nPositive position:\n\nNegative position:\n\nInitial weakness directions:\n- ")
            btns = tk.Frame(edit, bg=self.C["bg"])
            btns.pack(fill=tk.X, padx=12, pady=(0, 12))
            def save_manual_case():
                raw = editor.get("1.0", tk.END).strip()
                if not raw:
                    messagebox.showwarning("Missing Content", "Please enter the fictional case content.", parent=edit)
                    return
                payload.setdefault("synthetic_cases", []).append({
                    "title": title_var.get().strip() or f"Manual Analogue {len(payload.setdefault('synthetic_cases', [])) + 1:02d}",
                    "fictional_facts": raw,
                    "positive_position": "See manually entered fictional case content.",
                    "negative_position": "See manually entered fictional case content.",
                    "attackable_weaknesses": ["Manual case added for batch model weakness scanning."],
                    "mapping_back_questions": ["What weakness does this manually added analogue expose?"],
                })
                edit.destroy()
                refresh_case_list(len(payload.get("synthetic_cases", [])) - 1)
            tk.Button(btns, text="Cancel", command=edit.destroy, bg="#333", fg=self.C["text"], relief="flat", padx=14, pady=6).pack(side=tk.RIGHT)
            tk.Button(btns, text="Add Case", command=save_manual_case, bg="#1f6feb", fg="white", relief="flat", padx=14, pady=6).pack(side=tk.RIGHT, padx=(0, 8))
            edit.transient(win)
            edit.grab_set()

        def delete_selected_case():
            cases = payload.setdefault("synthetic_cases", [])
            if not cases:
                return
            idx = selected_case_index()
            if messagebox.askyesno("Delete Synthetic Case", f"Delete case {idx + 1:02d} from this batch?", parent=win):
                cases.pop(idx)
                refresh_case_list(min(idx, len(cases) - 1) if cases else None)

        case_list.bind("<<ListboxSelect>>", lambda _e: show_case_detail())
        refresh_case_list(0)

        progress_row = tk.Frame(win, bg=self.C["bg"])
        progress_row.pack(fill=tk.X, padx=14, pady=(0, 6))
        scan_status = tk.Label(
            progress_row,
            text="Ready: the real matter remains local; only the fictional pack can be sent.",
            bg=self.C["bg"],
            fg=self.C["muted"],
            font=("Microsoft YaHei UI", 9),
            anchor=tk.W,
        )
        scan_status.pack(fill=tk.X, pady=(0, 4))
        progress = ttk.Progressbar(progress_row, mode="indeterminate")
        progress.pack(fill=tk.X)

        controls = tk.Frame(win, bg=self.C["bg"])
        controls.pack(fill=tk.X, padx=14, pady=(0, 12))
        report = lambda: self.render_synthetic_analogue_report(payload)
        def copy_report():
            self.root.clipboard_clear()
            self.root.clipboard_append(report())
            self.status_var.set("Status: Synthetic analogue case directory copied")
        add_btn = tk.Button(controls, text="Add Case", command=add_case_dialog, bg="#1a3a1a", fg="white", relief="flat", padx=14, pady=7)
        add_btn.pack(side=tk.LEFT)
        delete_btn = tk.Button(controls, text="Delete Case", command=delete_selected_case, bg="#5a2430", fg="white", relief="flat", padx=14, pady=7)
        delete_btn.pack(side=tk.LEFT, padx=(8, 0))
        copy_btn = tk.Button(controls, text="Copy Directory", command=copy_report, bg="#243b5a", fg="white", relief="flat", padx=14, pady=7)
        copy_btn.pack(side=tk.LEFT, padx=(8, 0))
        def scan_selected_cases():
            cases = payload.get("synthetic_cases") or []
            indices = selected_case_indices()
            if not cases or not indices:
                messagebox.showwarning(
                    "No Synthetic Case Selected",
                    "Select between 1 and 5 fictional cases before scanning.",
                    parent=win,
                )
                return
            if len(indices) > 5:
                messagebox.showwarning(
                    "Selection Limit",
                    "A maximum of 5 fictional cases can be scanned at the same time.",
                    parent=win,
                )
                return
            selected_cases = [copy.deepcopy(cases[index]) for index in indices]
            selected_payload = copy.deepcopy(payload)
            selected_payload["synthetic_cases"] = selected_cases
            selected_payload["scan_scope"] = f"{len(selected_cases)} selected fictional case(s), each across all 18 dimensions"
            all_dimensions = [name for name, _description in DIMENSIONS]
            self.run_synthetic_model_weakness_scan(
                selected_payload,
                parent_window=win,
                progress_widget=progress,
                status_label=scan_status,
                buttons=[add_btn, delete_btn, copy_btn, selected_scan_btn, close_btn],
                dimensions_override=all_dimensions,
            )

        selected_scan_btn = tk.Button(
            controls,
            text="18D Weakness Scan for Selected Cases (Max 5)",
            command=scan_selected_cases,
            bg="#9a6a10",
            fg="white",
            relief="flat",
            padx=14,
            pady=7,
        )
        selected_scan_btn.pack(side=tk.LEFT, padx=(8, 0))
        close_btn = tk.Button(controls, text="Close", command=win.destroy, bg="#333", fg=self.C["text"], relief="flat", padx=14, pady=7)
        close_btn.pack(side=tk.RIGHT)

    def cloud_parse_current_case(self):
        self.analyse_imported_case()

    def analyse_imported_case(self):
        case_text = self._last_imported_raw_text.strip() or self.get_text(self.t_bg)
        if not case_text:
            messagebox.showwarning("Missing Case Background", "Please import or enter the full case background first.")
            return
        private_routes = self.verified_private_provider_snapshots()
        public_routes = [item for item in self.verified_provider_snapshots() if not self.is_private_model_endpoint(item.get("base_url"))]
        confidentiality = self.confidential_var.get()
        if confidentiality == "Local-only confidentiality":
            if private_routes:
                self._run_semantic_case_analysis(case_text, private_routes[0], redact=False, mode_label="Private model semantic analysis complete")
            else:
                self.open_import_analysis_choices()
            return
        if confidentiality == "External aid after redaction":
            if not public_routes:
                messagebox.showwarning("No Verified External Model", "Verify a public model provider before requesting redacted external analysis.")
                return
            ok = messagebox.askyesno(
                "Confirm Redacted External Analysis",
                "The software will locally redact identifiers before sending the prepared matter to the verified external model.\n\nContinue?",
            )
            if ok:
                self._run_semantic_case_analysis(case_text, public_routes[0], redact=True, mode_label="Redacted external semantic analysis complete")
            return
        routes = self.verified_provider_snapshots()
        if not routes:
            messagebox.showwarning("No Verified Model", "Verify a model provider before semantic case analysis.")
            return
        ok = messagebox.askyesno(
            "Confirm Authorized Model Analysis",
            "This mode may send the original matter text to the selected verified provider.\n\nContinue?",
        )
        if ok:
            self._run_semantic_case_analysis(case_text, routes[0], redact=False, mode_label="Authorized model semantic analysis complete")

    def _run_semantic_case_analysis(self, case_text, provider, redact, mode_label):
        if self.case_analysis_busy and getattr(self, "_semantic_analysis_active", False):
            return
        self._set_case_analysis_busy(True, "Analysing the complete case - please wait. Controls are temporarily locked.")
        self._semantic_analysis_active = True
        try:
            self.activate_provider_snapshot(provider)
            prepared_text = case_text
            if redact:
                prepared_text = self._redact_external_matter(case_text)
        except Exception as exc:
            self._fail_semantic_case_analysis(str(exc)[:800])
            return
        self.cloud_status_var.set("Semantic case analysis in progress...")
        self.import_analysis_mode_var.set("Import mode: semantic legal analysis in progress")

        def worker():
            try:
                prompt = (
                    "You are a legal-preparation assistant for the English competition edition of AI Lawyer Opposition.\n"
                    "Read the following case question or matter materials. The source may be Chinese, English, or mixed-language.\n"
                    "Extract the case background, positive-side arguments/evidence, and negative-side arguments/evidence.\n"
                    "This software prepares adversarial lawyer-reference material. It is not a neutral final legal decision.\n"
                    "Write every JSON string value in clear professional English. Preserve proper names, dates, amounts, court names, and citations where possible.\n\n"
                    f"Complete source case material:\n{prepared_text}\n\n"
                    "Return strict JSON only, with this shape:\n"
                    "{"
                    "\"case_name\":\"short English case name\","
                    "\"jurisdiction\":\"jurisdiction in English\","
                    "\"background\":\"English factual background, within 300 words\","
                    "\"pos_args\":\"positive/plaintiff/claimant-side core arguments, one per line, in English\","
                    "\"pos_ev\":\"positive/plaintiff/claimant-side main evidence list, one per line, in English\","
                    "\"neg_args\":\"negative/defendant/respondent-side core arguments, one per line, in English\","
                    "\"neg_ev\":\"negative/defendant/respondent-side main evidence list, one per line, in English\""
                    "}"
                )
                res = self.call_cloud_json(prompt, max_tokens=2500)
                self.cloud_parse_count += 1
                self.root.after(0, lambda r=res, label=mode_label: self._finish_semantic_case_analysis(r, label))
            except Exception as exc:
                msg = str(exc)[:800]
                self.root.after(0, lambda m=msg: self._fail_semantic_case_analysis(m))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_semantic_case_analysis(self, result, mode_label):
        try:
            prepared = self.prepare_cloud_parsed_case(result)
            side_fields = ("pos_args", "pos_ev", "neg_args", "neg_ev")
            if not any(prepared.get(key) for key in side_fields):
                raise RuntimeError(
                    "The model returned no usable positive-side or negative-side frames. "
                    "The imported case has been retained and was not replaced."
                )
            self.apply_cloud_parsed_case(prepared, mode_label)
            self.status_var.set("Status: case analysis complete")
        except Exception as exc:
            self._fail_semantic_case_analysis(str(exc)[:800])
            return
        self._semantic_analysis_active = False
        self._set_case_analysis_busy(False)
        if hasattr(self, "drop_label"):
            name = self.sanitize_case_name(self.case_name_var.get().strip() or Path(self.current_case_path).stem or "Imported case")
            self.drop_label.configure(
                bg=self.C["drop"], fg=self.C["green"],
                text=f"Case analysis complete: {name} | Click to import again",
            )

    def _fail_semantic_case_analysis(self, message):
        self.cloud_status_var.set("Cloud Parsing Failed")
        self.import_analysis_mode_var.set("Import mode: semantic analysis failed; skeleton retained")
        self.status_var.set("Status: case analysis failed; controls restored")
        self._semantic_analysis_active = False
        self._set_case_analysis_busy(False)
        if hasattr(self, "drop_label"):
            self.drop_label.configure(
                bg=self.C["drop"], fg=self.C["red"],
                text="Case analysis failed; imported case retained | Click to import again",
            )
        messagebox.showerror("Cloud Parsing Failed", message)

    def _redact_external_matter(self, matter_text):
        """Use the original fixed-rule redaction path without English name/org discovery."""
        from Nido_StrikeOver_Online_EN import PIIAnonymizer

        anonymizer = PIIAnonymizer()
        return anonymizer.anonymize(matter_text)
        candidates = anonymizer.discover_english_candidates(matter_text, include_generic=True)
        decisions = getattr(self, "_external_redaction_decisions", {})
        fingerprint = hashlib.sha256(
            json.dumps(
                [(item["original"], item["category"], item["confidence"]) for item in candidates],
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()

        if candidates and fingerprint != getattr(self, "_external_redaction_review_fingerprint", ""):
            dialog = tk.Toplevel(self.root)
            dialog.title("Review Names and Organisations")
            dialog.geometry("760x560")
            dialog.minsize(680, 460)
            dialog.configure(bg="#111827")
            dialog.transient(self.root)
            dialog.grab_set()

            shell = tk.Frame(dialog, bg="#111827", padx=20, pady=18)
            shell.pack(fill=tk.BOTH, expand=True)
            tk.Label(
                shell,
                text="Review names and organisations before redaction",
                bg="#111827", fg=self.C["gold"], font=("Microsoft YaHei UI", 15, "bold"),
            ).pack(anchor="w")
            tk.Label(
                shell,
                text=("High-confidence items with a legal role, title, or organisation suffix are always redacted. "
                      "Tick any additional personal names that should use consistent placeholders throughout the matter. "
                      "Court names and case citations are not selected automatically."),
                bg="#111827", fg="#cbd5e1", wraplength=700, justify=tk.LEFT,
            ).pack(anchor="w", pady=(6, 12))

            holder = tk.Frame(shell, bg="#1f2937", highlightthickness=1, highlightbackground="#374151")
            holder.pack(fill=tk.BOTH, expand=True)
            canvas = tk.Canvas(holder, bg="#1f2937", highlightthickness=0)
            scrollbar = ttk.Scrollbar(holder, orient="vertical", command=canvas.yview)
            rows = tk.Frame(canvas, bg="#1f2937")
            rows.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.create_window((0, 0), window=rows, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            review_vars = []
            for candidate in candidates:
                high = candidate["confidence"] == "high"
                selected = high or decisions.get(candidate["original"], False)
                var = tk.BooleanVar(value=selected)
                label = PIIAnonymizer.CATEGORY_LABELS_EN.get(candidate["category"], candidate["category"])
                suffix = "automatic" if high else "confirm"
                tk.Checkbutton(
                    rows,
                    text=f"{candidate['original']}   —   {label} · {suffix}",
                    variable=var,
                    state=tk.DISABLED if high else tk.NORMAL,
                    bg="#1f2937", fg="#f8fafc", disabledforeground="#93c5fd",
                    selectcolor="#111827", activebackground="#1f2937", activeforeground="#ffffff",
                    anchor="w", justify=tk.LEFT, padx=10, pady=5,
                ).pack(fill=tk.X, anchor="w")
                if not high:
                    review_vars.append((candidate, var))

            actions = tk.Frame(shell, bg="#111827")
            actions.pack(fill=tk.X, pady=(14, 0))

            def apply_review():
                for candidate, var in review_vars:
                    decisions[candidate["original"]] = bool(var.get())
                dialog.destroy()

            def use_automatic_only():
                for candidate, _var in review_vars:
                    decisions[candidate["original"]] = False
                dialog.destroy()

            tk.Button(
                actions, text="Apply Selections", command=apply_review,
                bg="#2563eb", fg="white", relief=tk.FLAT, padx=18, pady=8,
                font=("Microsoft YaHei UI", 10, "bold"),
            ).pack(side=tk.RIGHT)
            tk.Button(
                actions, text="Use Automatic Items Only", command=use_automatic_only,
                bg="#374151", fg="white", relief=tk.FLAT, padx=16, pady=8,
            ).pack(side=tk.RIGHT, padx=(0, 8))
            dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
            self.root.wait_window(dialog)
            self._external_redaction_review_fingerprint = fingerprint

        for candidate in candidates:
            if candidate["confidence"] != "high" and decisions.get(candidate["original"], False):
                anonymizer.add_manual(candidate["original"], candidate["category"])
        self._external_redaction_decisions = decisions
        return anonymizer.anonymize(matter_text)

    @staticmethod
    def _semantic_text(value):
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            lines = []
            for item in value:
                if isinstance(item, dict):
                    text = next((str(item.get(key) or "").strip() for key in ("text", "argument", "evidence", "point", "summary") if item.get(key)), "")
                else:
                    text = str(item).strip()
                if text:
                    lines.append(text)
            return "\n".join(lines)
        if isinstance(value, dict):
            lines = []
            for key, item in value.items():
                text = NidoOldSkinApp._semantic_text(item)
                if text:
                    lines.append(f"{key}: {text}")
            return "\n".join(lines)
        return str(value).strip()

    def prepare_cloud_parsed_case(self, res):
        if not isinstance(res, dict):
            raise RuntimeError("The model response was not a JSON object.")

        def pick(*keys):
            for key in keys:
                text = self._semantic_text(res.get(key))
                if text:
                    return text
            return ""

        positive = res.get("positive_side") if isinstance(res.get("positive_side"), dict) else {}
        negative = res.get("negative_side") if isinstance(res.get("negative_side"), dict) else {}
        prepared = {
            "case_name": pick("case_name", "matter_name", "title"),
            "jurisdiction": pick("jurisdiction", "governing_jurisdiction", "region"),
            "background": pick("background", "case_background", "facts", "factual_background", "summary"),
            "pos_args": pick("pos_args", "positive_args", "positive_arguments", "plaintiff_args", "claimant_args"),
            "pos_ev": pick("pos_ev", "positive_evidence", "plaintiff_evidence", "claimant_evidence"),
            "neg_args": pick("neg_args", "negative_args", "negative_arguments", "defendant_args", "respondent_args"),
            "neg_ev": pick("neg_ev", "negative_evidence", "defendant_evidence", "respondent_evidence"),
        }
        if not prepared["pos_args"]:
            prepared["pos_args"] = self._semantic_text(positive.get("arguments") or positive.get("positions"))
        if not prepared["pos_ev"]:
            prepared["pos_ev"] = self._semantic_text(positive.get("evidence"))
        if not prepared["neg_args"]:
            prepared["neg_args"] = self._semantic_text(negative.get("arguments") or negative.get("positions"))
        if not prepared["neg_ev"]:
            prepared["neg_ev"] = self._semantic_text(negative.get("evidence"))

        # Never let an empty or whitespace-only model field erase the imported
        # matter. The original source stays available even when parsing fails.
        if not prepared["background"]:
            prepared["background"] = self.get_text(self.t_bg).strip() or self._last_imported_raw_text.strip()
        return prepared

    def apply_cloud_parsed_case(self, res, mode_label="Semantic legal analysis complete"):
        if res.get("case_name"):
            self.case_name_var.set(str(res["case_name"]).strip())
        if res.get("jurisdiction"):
            self.jur_var.set(str(res["jurisdiction"]).strip())
        mapping = [
            (self.t_bg, "background"),
            (self.t_pos_args, "pos_args"),
            (self.t_pos_ev, "pos_ev"),
            (self.t_neg_args, "neg_args"),
            (self.t_neg_ev, "neg_ev"),
        ]
        filled = 0
        for widget, key in mapping:
            val = self._semantic_text(res.get(key))
            if val:
                self.set_text(widget, val)
                filled += 1
        self.cloud_status_var.set(f"Cloud case parsing complete; {filled} field(s) filled")
        self.import_analysis_mode_var.set(f"Import mode: {mode_label}")

    def open_import_analysis_choices(self):
        win = tk.Toplevel(self.root)
        win.title("Choose Case Analysis Mode")
        win.geometry("780x430")
        win.configure(bg=self.C["bg"])
        win.transient(self.root)
        win.grab_set()
        body = tk.Frame(win, bg=self.C["bg"], padx=28, pady=24)
        body.pack(fill=tk.BOTH, expand=True)
        tk.Label(body, text="Case imported securely", bg=self.C["bg"], fg=self.C["gold"], font=("Microsoft YaHei UI", 19, "bold")).pack(anchor=tk.W)
        tk.Label(
            body,
            text="The local function has retained the case text and created only a structural skeleton. Choose whether to continue with a verified private model, a redacted external model, or the skeleton only.",
            bg=self.C["bg"], fg=self.C["text"], justify=tk.LEFT, wraplength=710, font=("Microsoft YaHei UI", 11),
        ).pack(anchor=tk.W, pady=(12, 20))

        def connect_private():
            private_routes = self.verified_private_provider_snapshots()
            if not private_routes:
                messagebox.showwarning(
                    "No Connected Local or Private Model",
                    "No verified local or private model connection was found.\n\n"
                    "Connect and verify a localhost model, private-network endpoint, "
                    "or approved internal law-firm model before using this option.\n\n"
                    "Case analysis has not started.",
                    parent=win,
                )
                self.import_analysis_mode_var.set("Import mode: stopped - no verified local or private model")
                self.cloud_status_var.set("No connected local or private model; analysis stopped")
                win.destroy()
                return
            win.destroy()
            self._run_semantic_case_analysis(
                self._last_imported_raw_text.strip() or self.get_text(self.t_bg),
                private_routes[0],
                redact=False,
                mode_label="Private model semantic analysis complete",
            )

        def use_external():
            public_routes = [item for item in self.verified_provider_snapshots() if not self.is_private_model_endpoint(item.get("base_url"))]
            if not public_routes:
                messagebox.showwarning("No Verified External Model", "Verify a public model provider first, then select Analyse Imported Case.", parent=win)
                return
            win.destroy()
            self.confidential_var.set("External aid after redaction")
            self.local_only_var.set(False)
            self.refresh_cloud_panel()
            self.analyse_imported_case()

        def skeleton_only():
            self.import_analysis_mode_var.set("Import mode: Skeleton only - no semantic legal analysis performed")
            self.status_var.set("Status: case structure loaded; semantic legal analysis not performed")
            win.destroy()

        options = tk.Frame(body, bg=self.C["bg"])
        options.pack(fill=tk.X, pady=(4, 0))
        choice_buttons = [
            ("Connect Local / Private Model", connect_private, "#9d2b3d", "#b63b4e"),
            ("Use Redacted External Model", use_external, "#187a70", "#229488"),
            ("Continue with Skeleton Only", skeleton_only, "#315c8c", "#3d73ad"),
        ]
        for label, command, colour, active_colour in choice_buttons:
            tk.Button(
                options,
                text=label,
                command=command,
                bg=colour,
                activebackground=active_colour,
                fg="white",
                activeforeground="white",
                relief="raised",
                overrelief="ridge",
                bd=2,
                highlightthickness=1,
                highlightbackground="#52627a",
                font=("Microsoft YaHei UI", 10, "bold"),
                padx=15,
                pady=11,
                cursor="hand2",
            ).pack(fill=tk.X, padx=2, pady=6)

    def call_cloud_json(self, prompt, max_tokens=1000, repair=True):
        text = self.call_cloud_text(prompt, max_tokens=max_tokens)
        try:
            return self.extract_json_object(text)
        except Exception as first_exc:
            if not repair:
                raise
            if '"case_overview"' in prompt and '"dimensions"' in prompt:
                expected_shape = (
                    "Expected root keys for a whole-case dimension review: case_overview and dimensions. "
                    "Each dimensions item must preserve dimension and findings. Each finding must preserve conclusion, "
                    "plain_explanation, core_problem, relevant_facts, what_it_proves, what_it_does_not_prove, questions, "
                    "defence_preparation, affected_side, and confidence when present. "
                )
            else:
                expected_shape = (
                    "Expected root keys for a synthetic summary response: summary_title, overview, "
                    "positive_side_weakness_patterns, negative_side_weakness_patterns, comparison_instructions. "
                    "Older responses may contain positive_side_weaknesses or negative_side_weaknesses; preserve them "
                    "only if they are present in the broken output. "
                )
            repair_prompt = (
                "Repair the following model output into valid strict JSON only. "
                "Do not add commentary. Do not invent new facts. Preserve the same keys and content as much as possible. "
                "If an item is malformed or incomplete, drop that item rather than returning invalid JSON.\n\n"
                f"{expected_shape}\n\n"
                "Broken output:\n"
                f"{text[:24000]}"
            )
            try:
                repaired = self.call_cloud_text(repair_prompt, max_tokens=min(max_tokens, 4000))
                return self.extract_json_object(repaired)
            except Exception as repair_exc:
                raise RuntimeError(
                    "The model returned malformed JSON and automatic repair failed. "
                    f"Original parse error: {first_exc}; repair error: {repair_exc}"
                )

    def call_cloud_text(self, prompt, max_tokens=1000):
        self.ensure_active_verified_provider()
        provider = self.cloud_provider_var.get()
        preset = PROVIDER_PRESETS.get(provider, PROVIDER_PRESETS["deepseek"])
        api_key = self.cloud_api_key_var.get().strip()
        base_url = self.cloud_base_url_var.get().strip().rstrip("/")
        model = self.cloud_model_var.get().strip()
        if not api_key:
            raise RuntimeError("Missing API Key。")
        if not base_url or not model:
            raise RuntimeError("缺少接口 URL 或模型名称。")

        if preset["kind"] == "anthropic":
            url = base_url + "/messages"
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            payload = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
            data = self.http_json(url, headers, payload)
            blocks = data.get("content") or []
            return "\n".join(b.get("text", "") for b in blocks if isinstance(b, dict))

        if preset["kind"] == "gemini_native":
            url = f"{base_url}/models/{model}:generateContent?key={urllib.parse.quote(api_key)}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": max_tokens,
                },
            }
            data = self.http_json(url, headers, payload)
            parts = []
            for cand in data.get("candidates", []):
                for part in cand.get("content", {}).get("parts", []):
                    if isinstance(part, dict) and part.get("text"):
                        parts.append(part["text"])
            return "\n".join(parts).strip()

        url = base_url
        if not url.endswith("/chat/completions"):
            url += "/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }
        data = self.http_json(url, headers, payload)
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")

    def http_json(self, url, headers, payload):
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw)

    def extract_json_object(self, text):
        text = (text or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            return json.loads(text)
        except Exception:
            pass
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise RuntimeError("外部模型没有返回可解析 JSON。")

    def _build_case(self):
        p = self._panel()
        self.set_help(p, "Case information: import or paste full facts. The app uses this material and side frames for local Weakness Scan and opposition.")
        row = tk.Frame(p, bg=self.C["panel"])
        row.pack(fill=tk.X)
        tk.Label(
            row,
            text="Step 2 - Case Information",
            bg=self.C["panel"],
            fg=self.C["text"],
            font=("Microsoft YaHei UI", 12, "bold"),
        ).pack(side=tk.LEFT)
        import_btn = tk.Button(
            row,
            text="Import Case File (PDF/Word/TXT/JSON)",
            command=self.import_case_file,
            bg="#1a3a5a",
            fg="white",
            relief="flat",
            padx=12,
            pady=5,
            cursor="hand2",
        )
        self.set_help(import_btn, "Import PDF, Word, TXT, or JSON. Without semantic model analysis, the app retains only a local structural index and does not invent legal positions.")
        import_btn.pack(side=tk.RIGHT)
        analyse_btn = tk.Button(
            row,
            text="Analyse Imported Case",
            command=self.analyse_imported_case,
            bg="#176b62",
            fg="white",
            relief="flat",
            padx=12,
            pady=5,
            cursor="hand2",
        )
        self.set_help(analyse_btn, "Run semantic case analysis after verifying a local/private model or authorizing a redacted external model. Re-import is not required.")
        analyse_btn.pack(side=tk.RIGHT, padx=(0, 8))

        meta = tk.Frame(p, bg=self.C["panel"])
        meta.pack(fill=tk.X, pady=6)
        tk.Label(meta, text="Case Name", bg=self.C["panel"], fg=self.C["muted"]).pack(side=tk.LEFT)
        case_name_entry = tk.Entry(meta, textvariable=self.case_name_var, width=42, bg=self.C["entry"], fg=self.C["text"], relief="flat")
        self.set_help(case_name_entry, "Case Name: used for saving, reports, and run-folder naming. It does not affect legal judgment.")
        case_name_entry.pack(side=tk.LEFT, padx=6)
        tk.Label(meta, text="Jurisdiction", bg=self.C["panel"], fg=self.C["muted"]).pack(side=tk.LEFT, padx=(14, 0))
        jur_combo = ttk.Combobox(
            meta,
            textvariable=self.jur_var,
            values=JURISDICTION_OPTIONS,
            width=34,
            state="readonly",
        )
        self.set_help(jur_combo, "Jurisdiction: choose the governing region for local prompts and law-pack routing.")
        jur_combo.pack(side=tk.LEFT, padx=6)
        framework_btn = tk.Button(
            meta,
            text="Add Jurisdiction Frame",
            command=self.open_legal_framework_pack_dialog,
            bg="#2f3f5f",
            fg="white",
            relief="flat",
            padx=10,
            cursor="hand2",
        )
        self.set_help(framework_btn, "Add Jurisdiction Frame: insert common issue and evidence-preparation frames for the selected jurisdiction.")
        framework_btn.pack(side=tk.LEFT, padx=(4, 0))
        law_btn = tk.Button(
            meta,
            text="Update Official Law Pack",
            command=self.open_official_legal_pack_dialog,
            bg="#5a3d1a",
            fg="white",
            relief="flat",
            padx=10,
            cursor="hand2",
        )
        self.set_help(law_btn, "Update Official Law Pack: open the local official-source update entry. Legal conclusions still require lawyer review.")
        law_btn.pack(side=tk.LEFT, padx=(6, 0))

        tk.Label(
            p,
            textvariable=self.import_analysis_mode_var,
            bg=self.C["panel"],
            fg=self.C["gold"],
            anchor=tk.W,
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(fill=tk.X, pady=(0, 4))

        self.case_analysis_busy_frame = tk.Frame(
            p,
            bg="#4a3210",
            highlightthickness=1,
            highlightbackground=self.C["gold"],
            padx=12,
            pady=9,
        )
        tk.Label(
            self.case_analysis_busy_frame,
            textvariable=self.case_analysis_busy_var,
            bg="#4a3210",
            fg="#fff4c2",
            anchor=tk.W,
            font=("Microsoft YaHei UI", 11, "bold"),
        ).pack(fill=tk.X)
        self.case_analysis_progress = ttk.Progressbar(
            self.case_analysis_busy_frame,
            mode="indeterminate",
        )

        self.drop_label = tk.Label(
            p,
            text="Drop a case file anywhere, or click Import. Choose private, redacted external, or skeleton-only analysis.",
            bg=self.C["drop"],
            fg="#b8f7d4",
            font=("Microsoft YaHei UI", 12, "bold"),
            pady=9,
            relief="flat",
            cursor="hand2",
        )
        self.drop_label.pack(fill=tk.X, pady=(2, 8))
        self.set_help(self.drop_label, "Drop a case file anywhere in the app, or click here to import. Legal positions are generated only after authorized semantic model analysis.")
        self.drop_label.bind("<Button-1>", lambda _e: self.import_case_file())
        self._setup_drop_widget(self.drop_label)

        tk.Label(p, text="Full Case / Filing Text / Disputed Facts", bg=self.C["panel"], fg=self.C["muted"]).pack(anchor=tk.W)
        self.t_bg = scrolledtext.ScrolledText(p, height=6, bg=self.C["entry"], fg=self.C["text"], relief="flat", font=("Microsoft YaHei UI", 10))
        self.set_help(self.t_bg, "Full case background: paste facts, filings, or disputed facts. This is the background for Weakness Scan; do not paste conclusions only.")
        self.bind_local_scroll(self.t_bg)
        self.t_bg.pack(fill=tk.X, pady=(2, 0))

    def open_manual_evidence_dialog(self, side):
        is_positive = side == "positive"
        widget = self.t_pos_ev if is_positive else self.t_neg_ev
        prefix = "P" if is_positive else "D"
        side_name = "Positive" if is_positive else "Negative"

        win = tk.Toplevel(self.root)
        win.title(f"Add {side_name} Evidence")
        win.geometry("620x430")
        win.configure(bg=self.C["panel"])
        win.transient(self.root)
        win.grab_set()

        body = tk.Frame(win, bg=self.C["panel"], padx=18, pady=16)
        body.pack(fill=tk.BOTH, expand=True)
        tk.Label(body, text=f"Add Evidence to {side_name} Side", bg=self.C["panel"], fg=self.C["text"], font=("Microsoft YaHei UI", 14, "bold")).pack(anchor=tk.W)

        tk.Label(body, text="Evidence type", bg=self.C["panel"], fg=self.C["muted"]).pack(anchor=tk.W, pady=(14, 3))
        type_var = tk.StringVar(value="Video recording")
        type_box = ttk.Combobox(
            body,
            textvariable=type_var,
            values=["Video recording", "Audio recording", "Photograph", "Document", "Message / Email", "Witness account", "Physical evidence", "Other"],
            state="readonly",
        )
        type_box.pack(fill=tk.X)

        tk.Label(body, text="Date, source, or file reference (optional)", bg=self.C["panel"], fg=self.C["muted"]).pack(anchor=tk.W, pady=(12, 3))
        source_var = tk.StringVar()
        tk.Entry(body, textvariable=source_var, bg=self.C["entry"], fg=self.C["text"], insertbackground=self.C["text"], relief="flat").pack(fill=tk.X)

        tk.Label(body, text="What this evidence shows", bg=self.C["panel"], fg=self.C["muted"]).pack(anchor=tk.W, pady=(12, 3))
        summary = scrolledtext.ScrolledText(body, height=8, bg=self.C["entry"], fg=self.C["text"], insertbackground=self.C["text"], wrap=tk.WORD, relief="flat", font=("Microsoft YaHei UI", 10))
        summary.pack(fill=tk.BOTH, expand=True)
        summary.focus_set()

        buttons = tk.Frame(body, bg=self.C["panel"])
        buttons.pack(fill=tk.X, pady=(12, 0))

        def add_evidence():
            description = summary.get("1.0", tk.END).strip()
            if not description:
                messagebox.showwarning("Missing Evidence Summary", "Describe what the evidence shows before adding it.", parent=win)
                return
            existing = self.get_text(widget)
            used = [int(value) for value in re.findall(rf"\[{prefix}(\d+)\]", existing, flags=re.IGNORECASE)]
            tag = f"[{prefix}{max(used, default=0) + 1}]"
            source = source_var.get().strip()
            entry = f"{tag} {type_var.get()}"
            if source:
                entry += f" | Date/source: {source}"
            entry += f"\n{description}"
            self.set_text(widget, f"{existing.rstrip()}\n{entry}".strip())
            self.status_var.set(f"Status: {tag} added to {side_name} evidence")
            win.destroy()

        tk.Button(buttons, text="Cancel", command=win.destroy, bg="#333", fg=self.C["text"], relief="flat", padx=18, pady=7).pack(side=tk.RIGHT)
        tk.Button(buttons, text="Add Evidence", command=add_evidence, bg="#1f6feb", fg="white", relief="flat", padx=18, pady=7).pack(side=tk.RIGHT, padx=(0, 8))

    def _build_side_panels(self):
        outer = tk.Frame(self.sf, bg=self.C["bg"])
        self.set_help(outer, "Side frames: left is the positive side, right is the negative side. Weakness Scan checks each side for attackable points.")
        outer.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        left = tk.Frame(outer, bg=self.C["bg"])
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))
        tk.Label(left, text="Positive Frame - Arguments and Evidence", bg=self.C["pos_header"], fg=self.C["green"], font=("Microsoft YaHei UI", 13, "bold")).pack(fill=tk.X)
        lb = tk.Frame(left, bg=self.C["panel"], padx=10, pady=10)
        lb.pack(fill=tk.BOTH, expand=True)
        tk.Label(lb, text="Arguments:", bg=self.C["panel"], fg=self.C["green"]).pack(anchor=tk.W)
        self.t_pos_args = scrolledtext.ScrolledText(lb, height=12, bg=self.C["entry"], fg=self.C["text"], relief="flat", font=("Microsoft YaHei UI", 10))
        self.set_help(self.t_pos_args, "Positive Arguments: core claims the positive side wants to protect. Weakness Scan finds where the other side can attack them.")
        self.bind_local_scroll(self.t_pos_args)
        self.t_pos_args.bind("<ButtonRelease-1>", lambda _e: self.apply_dragged_weakness_to_current_case("positive"))
        self.t_pos_args.pack(fill=tk.X, pady=(2, 8))
        pos_ev_header = tk.Frame(lb, bg=self.C["panel"])
        pos_ev_header.pack(fill=tk.X)
        tk.Label(pos_ev_header, text="Evidence (use [P1][P2] tags):", bg=self.C["panel"], fg=self.C["green"]).pack(side=tk.LEFT)
        tk.Button(pos_ev_header, text="+ Add Evidence", command=lambda: self.open_manual_evidence_dialog("positive"), bg="#114b3a", fg="white", relief="flat", padx=9, pady=2).pack(side=tk.RIGHT)
        self.t_pos_ev = scrolledtext.ScrolledText(lb, height=8, bg=self.C["entry"], fg=self.C["text"], relief="flat", font=("Microsoft YaHei UI", 10))
        self.set_help(self.t_pos_ev, "Positive Evidence: evidence supporting positive arguments. Labels such as [P1] and [P2] are optional.")
        self.bind_local_scroll(self.t_pos_ev)
        self.t_pos_ev.pack(fill=tk.X)

        middle = tk.Frame(outer, bg=self.C["bg"], width=38)
        middle.pack(side=tk.LEFT, fill=tk.Y)
        middle.pack_propagate(False)
        swap_btn = tk.Button(
            middle,
            text="Swap",
            command=self.swap_sides,
            bg="#333",
            fg=self.C["text"],
            relief="flat",
            padx=4,
            pady=8,
        )
        self.set_help(swap_btn, "Swap: exchange the positive and negative arguments/evidence to review the matter from the other side.")
        swap_btn.pack(fill=tk.Y, expand=True, padx=2, pady=4)

        right = tk.Frame(outer, bg=self.C["bg"])
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 0))
        tk.Label(right, text="Negative Frame - Arguments and Evidence", bg=self.C["neg_header"], fg=self.C["red"], font=("Microsoft YaHei UI", 13, "bold")).pack(fill=tk.X)
        rb = tk.Frame(right, bg=self.C["panel"], padx=10, pady=10)
        rb.pack(fill=tk.BOTH, expand=True)
        tk.Label(rb, text="Arguments:", bg=self.C["panel"], fg=self.C["red"]).pack(anchor=tk.W)
        self.t_neg_args = scrolledtext.ScrolledText(rb, height=12, bg=self.C["entry"], fg=self.C["text"], relief="flat", font=("Microsoft YaHei UI", 10))
        self.set_help(self.t_neg_args, "Negative Arguments: core claims the negative side wants to protect. Weakness Scan finds where the positive side can attack them.")
        self.bind_local_scroll(self.t_neg_args)
        self.t_neg_args.bind("<ButtonRelease-1>", lambda _e: self.apply_dragged_weakness_to_current_case("negative"))
        self.t_neg_args.pack(fill=tk.X, pady=(2, 8))
        neg_ev_header = tk.Frame(rb, bg=self.C["panel"])
        neg_ev_header.pack(fill=tk.X)
        tk.Label(neg_ev_header, text="Evidence (use [D1][D2] tags):", bg=self.C["panel"], fg=self.C["red"]).pack(side=tk.LEFT)
        tk.Button(neg_ev_header, text="+ Add Evidence", command=lambda: self.open_manual_evidence_dialog("negative"), bg="#6f1d3b", fg="white", relief="flat", padx=9, pady=2).pack(side=tk.RIGHT)
        self.t_neg_ev = scrolledtext.ScrolledText(rb, height=8, bg=self.C["entry"], fg=self.C["text"], relief="flat", font=("Microsoft YaHei UI", 10))
        self.set_help(self.t_neg_ev, "Negative Evidence: evidence supporting negative arguments. Labels such as [D1] and [D2] are optional.")
        self.bind_local_scroll(self.t_neg_ev)
        self.t_neg_ev.pack(fill=tk.X)

    def _build_dimensions(self):
        p = self._panel()
        self.set_help(p, "Opposition dimensions: choose which attack angles are enabled for this run.")
        top = tk.Frame(p, bg=self.C["panel"])
        top.pack(fill=tk.X)
        tk.Label(top, text="Step 3 - Opposition Dimensions", bg=self.C["panel"], fg=self.C["text"], font=("Microsoft YaHei UI", 12, "bold")).pack(side=tk.LEFT)
        clear_btn = tk.Button(top, text="Clear", command=lambda: self.set_all_dims(False), bg="#333", fg="white", relief="flat", padx=10)
        self.set_help(clear_btn, "Clear all dimensions so you can keep only a few focused angles.")
        clear_btn.pack(side=tk.LEFT, padx=(12, 3))
        self.weakness_lock_widgets.append(clear_btn)
        all_btn = tk.Button(top, text="Select All", command=lambda: self.set_all_dims(True), bg="#333", fg="white", relief="flat", padx=10)
        self.set_help(all_btn, "Enable all 18 dimensions for a full scan.")
        all_btn.pack(side=tk.LEFT, padx=3)
        self.weakness_lock_widgets.append(all_btn)

        flow = tk.Frame(top, bg=self.C["panel"])
        flow.pack(side=tk.RIGHT)
        weakness_indicator = tk.Frame(flow, bg="#111827", padx=8, pady=4)
        weakness_indicator.pack(side=tk.LEFT, padx=(0, 8))
        self.weakness_progress = ttk.Progressbar(weakness_indicator, mode="indeterminate", length=120)
        tk.Label(
            weakness_indicator,
            textvariable=self.weakness_run_status_var,
            bg="#111827",
            fg=self.C["teal"],
            font=("Microsoft YaHei UI", 9, "bold"),
            width=34,
            anchor="w",
        ).pack(side=tk.LEFT)
        self.scan_btn = tk.Button(
            flow,
            text="1 Scan Weaknesses",
            command=self.run_weakness_scan,
            bg="#1a4a42",
            fg="white",
            relief="flat",
            padx=12,
            pady=5,
        )
        self.set_help(self.scan_btn, "Scan Weaknesses: open the local weakness list for review and drag useful findings into the case.")
        self.scan_btn.pack(side=tk.LEFT, padx=(0, 6))
        synthetic_scan_btn = tk.Button(
            flow,
            text="2 Synthetic Case Scan",
            command=self.generate_synthetic_analogue_case,
            bg="#4a3b78",
            fg="white",
            relief="flat",
            padx=12,
            pady=5,
        )
        self.set_help(synthetic_scan_btn, "Synthetic Case Scan: create fictional analogue matters locally from an identifier-reduced skeleton. The next step can send only the fictional analogue case to a verified model provider for stronger weakness scanning.")
        synthetic_scan_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.weakness_lock_widgets.append(synthetic_scan_btn)
        grid = tk.Frame(p, bg=self.C["panel"])
        grid.pack(fill=tk.X, pady=(8, 0))
        for idx, (name, _desc) in enumerate(DIMENSIONS):
            cb = tk.Checkbutton(
                grid,
                text=self.dim_label(name),
                variable=self.dimension_vars[name],
                bg=self.C["panel"],
                fg=self.C["text"],
                selectcolor="#3e1a1a",
                activebackground=self.C["panel"],
                activeforeground=self.C["text"],
            )
            cb.grid(row=idx // 6, column=idx % 6, sticky="w", padx=6, pady=2)
            self.weakness_lock_widgets.append(cb)
            self.set_help(cb, f"{self.dim_label(name)}: {DIMENSION_DESC_EN.get(name, _desc)}.")

    def _build_controls(self):
        p = self._panel()
        self.set_help(p, "Main controls: run the local workflow, export, save/load the case, and open the current run folder.")
        top_row = tk.Frame(p, bg=self.C["panel"])
        top_row.pack(fill=tk.X)
        bottom_row = tk.Frame(p, bg=self.C["panel"])
        bottom_row.pack(fill=tk.X, pady=(8, 0))

        self.run_btn = tk.Button(top_row, text="Start Opposition", command=self.choose_offline_opposition_mode, bg=self.C["accent"], fg="white", relief="flat", padx=22, pady=8, font=("Microsoft YaHei UI", 12, "bold"))
        export_btn = tk.Button(top_row, text="Export Report", command=self.export_report, bg="#1a3a1a", fg="white", relief="flat", padx=14, pady=8)
        self.set_help(export_btn, "Export Report: save the current local case structure and weakness-scan material.")
        export_btn.pack(side=tk.LEFT, padx=8)
        professional_row = tk.Frame(p, bg="#192238", padx=8, pady=7)
        professional_row.pack(fill=tk.X, pady=(8, 0))
        tk.Label(
            professional_row,
            text="Professional report",
            bg="#192238",
            fg=self.C["gold"],
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(side=tk.LEFT)
        report_type_box = ttk.Combobox(
            professional_row,
            textvariable=self.professional_report_type_var,
            values=list(PROFESSIONAL_REPORT_TYPES.values()),
            state="readonly",
            width=31,
        )
        report_type_box.pack(side=tk.LEFT, padx=(8, 6))
        self.set_help(report_type_box, "Choose the professional audience and structure. This changes presentation, not the underlying facts or legal validity.")
        output_format_box = ttk.Combobox(
            professional_row,
            textvariable=self.professional_output_format_var,
            values=["Word + PDF", "Editable Word", "PDF", "Markdown + JSON"],
            state="readonly",
            width=18,
        )
        output_format_box.pack(side=tk.LEFT, padx=6)
        self.set_help(output_format_box, "Choose Word, PDF, both, or a portable Markdown plus structured JSON package.")
        for label, variable in (
            ("Contents", self.professional_include_contents_var),
            ("Pages", self.professional_include_pages_var),
            ("Sources", self.professional_include_sources_var),
            ("Evidence index", self.professional_include_evidence_var),
        ):
            tk.Checkbutton(
                professional_row,
                text=label,
                variable=variable,
                bg="#192238",
                fg=self.C["text"],
                selectcolor=self.C["entry"],
                activebackground="#192238",
                activeforeground=self.C["text"],
            ).pack(side=tk.LEFT, padx=3)
        professional_export_btn = tk.Button(
            professional_row,
            text="Export Professional Pack",
            command=self.export_professional_report,
            bg="#3157d5",
            fg="white",
            relief="flat",
            padx=13,
            pady=6,
        )
        professional_export_btn.pack(side=tk.RIGHT)
        self.set_help(professional_export_btn, "Create a lawyer working paper or selected report as Word/PDF with model provenance, evidence indexing, verification tasks and professional limits.")
        save_btn = tk.Button(bottom_row, text="Save Case", command=self.save_case, bg="#1a3a1a", fg="white", relief="flat", padx=14, pady=8)
        self.set_help(save_btn, "Save Case: save the current case text, side frames, jurisdiction, and settings for later reload.")
        save_btn.pack(side=tk.LEFT)
        load_btn = tk.Button(bottom_row, text="Load Case", command=self.load_case, bg="#1a3a1a", fg="white", relief="flat", padx=14, pady=8)
        self.set_help(load_btn, "Load Case: reload a saved case file into the interface.")
        load_btn.pack(side=tk.LEFT, padx=8)
        open_dir_btn = tk.Button(bottom_row, text="Open Output Folder", command=self.open_run_dir, bg="#243b5a", fg="white", relief="flat", padx=14, pady=8)
        self.set_help(open_dir_btn, "Open Output Folder: open the latest run folder, including raw_internal_state.json and safe_display_state_en.json.")
        open_dir_btn.pack(side=tk.LEFT, padx=8)
        self.status_var = tk.StringVar(value="Status: Ready")
        tk.Label(bottom_row, textvariable=self.status_var, bg=self.C["panel"], fg=self.C["muted"], font=("Microsoft YaHei UI", 11)).pack(side=tk.LEFT, padx=14)
        self.standard_weakness_progress_var = tk.DoubleVar(value=0.0)
        self.standard_weakness_progress_text_var = tk.StringVar(value="0%")
        self.standard_weakness_progress_frame = tk.Frame(bottom_row, bg=self.C["panel"])
        self.standard_weakness_progress_bar = ttk.Progressbar(
            self.standard_weakness_progress_frame,
            orient=tk.HORIZONTAL,
            mode="determinate",
            maximum=100,
            length=220,
            variable=self.standard_weakness_progress_var,
        )
        self.standard_weakness_progress_bar.pack(side=tk.LEFT, padx=(0, 8))
        self.standard_weakness_progress_label = tk.Label(
            self.standard_weakness_progress_frame,
            textvariable=self.standard_weakness_progress_text_var,
            bg=self.C["panel"],
            fg="#d5aa52",
            font=("Microsoft YaHei UI", 10, "bold"),
            width=5,
            anchor="e",
        )
        self.standard_weakness_progress_label.pack(side=tk.LEFT)
        self.progress = ttk.Progressbar(p, mode="indeterminate", length=160)

    def _build_lawyer_workflow_controls(self):
        return

    def _build_output(self):
        p = tk.Frame(self.sf, bg=self.C["panel"], padx=10, pady=8)
        self.set_help(p, "Opposition Results: local two-round opposition, safe display state, and report material. Outputs support lawyer preparation and do not replace professional judgment.")
        # Keep result widgets alive for export compatibility, but the offline UI
        # no longer presents local function-generated opposition as legal debate.
        row = tk.Frame(p, bg=self.C["panel"])
        row.pack(fill=tk.X)
        tk.Label(row, text="Opposition Results", bg=self.C["panel"], fg=self.C["text"], font=("Microsoft YaHei UI", 12, "bold")).pack(side=tk.LEFT)
        fullscreen_btn = tk.Button(row, text="Fullscreen", command=self.open_fullscreen, bg=self.C["accent"], fg="white", relief="flat", padx=10, pady=3)
        self.set_help(fullscreen_btn, "Fullscreen: open the opposition results in a larger reading window.")
        fullscreen_btn.pack(side=tk.RIGHT)
        summary_btn = tk.Button(row, text="Summary", command=self.open_summary_window, bg="#1a4a42", fg="white", relief="flat", padx=10, pady=3)
        self.set_help(summary_btn, "Summary: open a compact case summary window.")
        summary_btn.pack(side=tk.RIGHT, padx=8)
        self.nb = ttk.Notebook(p)
        self.nb.pack(fill=tk.BOTH, expand=True, pady=5)
        self.outputs = {}
        self.output_tabs = {}
        for key, title in [
            ("attacks", "Attack Details"),
            ("json", "Safe Display State"),
        ]:
            f = ttk.Frame(self.nb)
            self.nb.add(f, text=title)
            self.output_tabs[key] = f
            t = scrolledtext.ScrolledText(f, bg=self.C["entry"], fg=self.C["text"], font=("Microsoft YaHei UI", 11), wrap=tk.WORD, relief="flat")
            self.set_help(t, f"{title}: inspect the current run. Safe Display State is separate from raw_internal_state.json.")
            self.bind_local_scroll(t)
            t.pack(fill=tk.BOTH, expand=True)
            self.configure_output_tags(t)
            self.outputs[key] = t

    def configure_output_tags(self, widget):
        widget.tag_config("title", foreground=self.C["gold"], font=("Microsoft YaHei UI", 13, "bold"))
        widget.tag_config("section", foreground=self.C["teal"], font=("Microsoft YaHei UI", 12, "bold"))
        widget.tag_config("neg", foreground=self.C["pink"], font=("Microsoft YaHei UI", 11))
        widget.tag_config("pos", foreground=self.C["blue"], font=("Microsoft YaHei UI", 11))
        widget.tag_config("neg_header", foreground=self.C["pink"], font=("Microsoft YaHei UI", 12, "bold"))
        widget.tag_config("pos_header", foreground=self.C["blue"], font=("Microsoft YaHei UI", 12, "bold"))
        widget.tag_config("label", foreground="#89b4fa", font=("Microsoft YaHei UI", 10, "bold"))
        widget.tag_config("warn", foreground=self.C["gold"])
        widget.tag_config("muted", foreground=self.C["muted"])

    def set_all_dims(self, value):
        for var in self.dimension_vars.values():
            var.set(value)

    def dim_label(self, name):
        return DIMENSION_LABELS_EN.get(str(name or ""), str(name or ""))

    def _setup_global_drop(self):
        self._setup_drop_widget(self.root)
        self._setup_drop_children(self.root)

    def _setup_drop_children(self, widget):
        try:
            children = widget.winfo_children()
        except Exception:
            children = []
        for child in children:
            self._setup_drop_widget(child)
            self._setup_drop_children(child)

    def _setup_drop_widget(self, widget):
        if not TkinterDnD:
            return
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self.on_drop)
            widget.dnd_bind("<<DragEnter>>", self.on_drag_enter)
            widget.dnd_bind("<<DragLeave>>", self.on_drag_leave)
        except Exception:
            pass

    def on_drag_enter(self, _event):
        if self.case_analysis_busy:
            return
        if hasattr(self, "drop_label"):
            self.drop_label.config(bg=self.C["drop_active"], text="Release to import the case file")

    def on_drag_leave(self, _event):
        if self.case_analysis_busy:
            return
        if hasattr(self, "drop_label"):
            self.drop_label.config(bg=self.C["drop"], text="Drop a case file anywhere, or click Import. Choose private, redacted external, or skeleton-only analysis.")

    def on_drop(self, event):
        if self.case_analysis_busy:
            self.status_var.set("Status: case analysis is already running; please wait")
            return
        paths = self.split_drop_paths(event.data)
        if paths:
            self.load_case_path(paths[0])
        self.on_drag_leave(event)

    def split_drop_paths(self, data):
        try:
            return list(self.root.tk.splitlist(data))
        except Exception:
            return [data.strip().strip("{}")] if data and data.strip() else []

    def import_case_file(self):
        if self.case_analysis_busy:
            self.status_var.set("Status: case analysis is already running; please wait")
            return
        path = filedialog.askopenfilename(
            title="Import case file",
            filetypes=[
                ("Supported case files", "*.pdf *.docx *.txt *.md *.json"),
                ("PDF", "*.pdf"),
                ("Word", "*.docx"),
                ("Text/Markdown/JSON", "*.txt *.md *.json"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.load_case_path(path)

    def load_case_path(self, path):
        if self.case_analysis_busy:
            self.status_var.set("Status: case analysis is already running; please wait")
            return
        keep_busy = False
        self._set_case_analysis_busy(True, "Importing and reading the case file - please wait.")
        try:
            self.status_var.set("Status: importing case...")
            self.drop_label.config(bg=self.C["drop_active"], text="Parsing case locally...")
            self.root.update_idletasks()
            text, encoding = extract_case_file_text(path)
            if self.is_tactic_combo_text(text):
                self.apply_tactic_combo_text(text)
                self.drop_label.config(
                    bg=self.C["drop"],
                    fg=self.C["green"],
                    text="Tactic package appended to current arguments; original case was not overwritten",
                )
                self.status_var.set("Status: tactic package appended")
                return
            cleaned_text = self.clean_imported_case_text(text)
            self._last_imported_raw_text = cleaned_text
            self._last_imported_path = path
            self._last_imported_encoding = encoding
            explicit_frames = self.has_explicit_imported_side_frames(text)
            if explicit_frames:
                parsed = self.auto_split_case_material(text, path, encoding)
            else:
                parsed = {
                    "case_name": Path(path).stem,
                    "jurisdiction": self.jur_var.get(),
                    "case_text": self.build_local_case_skeleton(cleaned_text, path, encoding),
                    "pos_args": "",
                    "pos_ev": "",
                    "neg_args": "",
                    "neg_ev": "",
                }
            self.apply_imported_case(parsed)
            self.current_case_path = path
            self.drop_label.config(
                bg=self.C["drop"],
                fg=self.C["green"],
                text=f"Case parsed: {self.sanitize_case_name(parsed.get('case_name', Path(path).stem))} | Click to import again",
            )
            if explicit_frames:
                self.import_analysis_mode_var.set("Import mode: Structured case data loaded - supplied side frames preserved")
                self.status_var.set("Status: structured case data loaded")
            else:
                self.import_analysis_mode_var.set("Import mode: Skeleton only - no semantic legal analysis performed")
                self.status_var.set("Status: case structure loaded locally")
                self.root.after(50, self.open_import_analysis_choices)
        except Exception as exc:
            self.drop_label.config(bg=self.C["drop"], fg=self.C["red"], text="Import failed. Please check the file format.")
            self.status_var.set("Status: import failed")
            messagebox.showerror("Import failed", str(exc))
        finally:
            if not keep_busy:
                self._set_case_analysis_busy(False)

    def _case_analysis_descendants(self, widget):
        found = []
        try:
            children = widget.winfo_children()
        except (tk.TclError, AttributeError):
            children = []
        for child in children:
            if isinstance(child, tk.Toplevel):
                continue
            found.append(child)
            found.extend(self._case_analysis_descendants(child))
        return found

    def _set_case_analysis_busy(self, busy, message=""):
        """Disable and visibly dim the whole interface while analysis runs."""
        muted = "#667085"
        if busy:
            if not self.case_analysis_busy:
                self.case_analysis_busy = True
                self.case_analysis_widget_states = {}
                for widget in self._case_analysis_descendants(self.root):
                    if isinstance(widget, tk.Toplevel):
                        continue
                    saved = {}
                    for option in ("state", "foreground", "disabledforeground", "insertbackground"):
                        try:
                            saved[option] = widget.cget(option)
                        except (tk.TclError, AttributeError):
                            pass
                    if not saved:
                        continue
                    self.case_analysis_widget_states[widget] = saved
                    try:
                        if "foreground" in saved:
                            widget.configure(foreground=muted)
                    except tk.TclError:
                        pass
                    try:
                        if "disabledforeground" in saved:
                            widget.configure(disabledforeground=muted)
                    except tk.TclError:
                        pass
                    try:
                        if "state" in saved:
                            widget.configure(state=tk.DISABLED)
                    except tk.TclError:
                        pass
            self.case_analysis_busy_var.set(message or "Analysing the complete case - please wait.")
            self.import_analysis_mode_var.set("Import mode: analysing the complete case - please wait")
            self.status_var.set("Status: case analysis in progress; controls locked")
            try:
                self.root.configure(cursor="watch")
            except tk.TclError:
                pass
            self.root.update_idletasks()
            return

        for widget, saved in reversed(list(self.case_analysis_widget_states.items())):
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
            except (tk.TclError, AttributeError):
                continue
        self.case_analysis_widget_states = {}
        self.case_analysis_busy = False
        try:
            self.root.configure(cursor="")
        except tk.TclError:
            pass
        if hasattr(self, "drop_label"):
            self.drop_label.configure(cursor="hand2")

    def has_explicit_imported_side_frames(self, text):
        try:
            data = json.loads(str(text or ""))
        except Exception:
            return False
        if not isinstance(data, dict):
            return False
        side_keys = {
            "pos_args", "positive_args", "plaintiff_args", "my_args",
            "pos_ev", "positive_evidence", "plaintiff_evidence", "my_evidence",
            "neg_args", "negative_args", "defendant_args", "opponent_args",
            "neg_ev", "negative_evidence", "defendant_evidence", "opponent_evidence",
        }
        return any(key in data and data.get(key) not in (None, "", [], {}) for key in side_keys)

    def build_local_case_skeleton(self, text, path, encoding):
        """Build a non-semantic index. It must not infer legal claims or party positions."""
        source = str(text or "").strip()
        lines = [line.strip() for line in source.splitlines() if line.strip()]
        headings = []
        captions = []
        for line in lines:
            compact = line.lstrip("#*- ").strip()
            if line.startswith("#") or (len(compact) <= 100 and compact.endswith((':', '：'))):
                headings.append(compact.rstrip(':：').strip())
            if re.search(r"\b(v\.?|vs\.?|versus)\b", compact, re.I):
                captions.append(compact)
        date_patterns = [
            r"\b(?:19|20)\d{2}[-/.](?:0?[1-9]|1[0-2])[-/.](?:0?[1-9]|[12]\d|3[01])\b",
            r"\b(?:0?[1-9]|[12]\d|3[01])[-/.](?:0?[1-9]|1[0-2])[-/.](?:19|20)\d{2}\b",
            r"\b(?:0?[1-9]|[12]\d|3[01])\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+(?:19|20)\d{2}\b",
        ]
        dates = []
        for pattern in date_patterns:
            dates.extend(re.findall(pattern, source, flags=re.I))
        amounts = re.findall(
            r"(?i)(?:AUD|USD|GBP|EUR|CNY|RMB|\$|£|€|¥)\s?\d[\d,]*(?:\.\d{1,2})?|\b\d[\d,]*(?:\.\d{1,2})?\s?(?:dollars?|yuan|pounds?|euros?)\b",
            source,
        )

        def unique(values, limit):
            result = []
            seen = set()
            for value in values:
                clean = str(value).strip()
                key = clean.casefold()
                if clean and key not in seen:
                    seen.add(key)
                    result.append(clean)
                if len(result) >= limit:
                    break
            return result

        headings = unique(headings, 12)
        captions = unique(captions, 8)
        dates = unique(dates, 20)
        amounts = unique(amounts, 20)

        def section(label, values):
            if not values:
                return f"{label}: none detected by the local structural index"
            return label + ":\n" + "\n".join(f"- {value}" for value in values)

        return (
            "[LOCAL STRUCTURAL INDEX - NO SEMANTIC LEGAL ANALYSIS]\n"
            "This index identifies visible document structure only. It does not decide facts, legal issues, evidence weight, or either side's position.\n\n"
            f"Imported file: {path}\n"
            f"Read mode: {encoding}\n"
            f"Document title: {Path(path).stem}\n\n"
            f"{section('Possible case captions', captions)}\n\n"
            f"{section('Visible headings', headings)}\n\n"
            f"{section('Dates found', dates)}\n\n"
            f"{section('Amounts found', amounts)}\n\n"
            "[ORIGINAL SOURCE MATERIAL - RETAINED LOCALLY]\n"
            f"{source}"
        )

    def is_tactic_combo_text(self, text):
        text = str(text or "")
        english = "## Nido Tactic Package" in text and "## Tactics For Positive Side" in text and "## Tactics For Negative Side" in text
        chinese = "## Nido 战术组合包" in text and "## 给正方使用的战术" in text and "## 给反方使用的战术" in text
        return english or chinese

    def extract_tactic_combo_section(self, text, heading, next_headings):
        start = text.find(heading)
        if start < 0:
            return ""
        start += len(heading)
        ends = [text.find(h, start) for h in next_headings if text.find(h, start) >= 0]
        end = min(ends) if ends else len(text)
        return text[start:end].strip()

    def append_text_to_widget(self, widget, title, text):
        text = str(text or "").strip()
        if not text:
            return
        existing = self.get_text(widget)
        addition = f"\n\n【{title}】\n{text}"
        self.set_text(widget, (existing + addition).strip() if existing else addition.strip())

    def apply_tactic_combo_text(self, text):
        positive_text = self.extract_tactic_combo_section(
            text,
            "## Tactics For Positive Side",
            ["## Tactics For Negative Side", "## Original Selected Weaknesses", "## Usage"],
        )
        negative_text = self.extract_tactic_combo_section(
            text,
            "## Tactics For Negative Side",
            ["## Original Selected Weaknesses", "## Usage"],
        )
        if not positive_text and not negative_text:
            positive_text = self.extract_tactic_combo_section(
                text,
                "## 给正方使用的战术",
                ["## 给反方使用的战术", "## 原始选中Weakness", "## 使用方式"],
            )
            negative_text = self.extract_tactic_combo_section(
                text,
                "## 给反方使用的战术",
                ["## 原始选中Weakness", "## 使用方式"],
            )
        positive_text = positive_text.replace("None.", "").replace("暂无。", "").strip()
        negative_text = negative_text.replace("None.", "").replace("暂无。", "").strip()
        self.append_text_to_widget(self.t_pos_args, "Tactic Package: for attacking negative-side weaknesses", positive_text)
        self.append_text_to_widget(self.t_neg_args, "Tactic Package: for attacking positive-side weaknesses", negative_text)

    def refresh_law_status(self):
        region = self.current_law_region()["label"]
        self.law_status_var.set(f"{region} / official law pack")

    def apply_imported_case(self, parsed):
        self.case_name_var.set(self.sanitize_case_name(parsed.get("case_name", "")))
        self.jur_var.set(self.normalise_jurisdiction_option(parsed.get("jurisdiction") or self.jur_var.get()))
        if parsed.get("local_law_region"):
            self.jur_var.set(self.normalise_jurisdiction_option(parsed.get("local_law_region")))
        if "case_search_enabled" in parsed:
            self.case_search_var.set(bool(parsed.get("case_search_enabled")))
            self.refresh_law_status()
        report_settings = parsed.get("professional_report_settings") or {}
        if isinstance(report_settings, dict):
            report_type = str(report_settings.get("report_type") or "")
            if report_type in PROFESSIONAL_REPORT_TYPES:
                self.professional_report_type_var.set(PROFESSIONAL_REPORT_TYPES[report_type])
            output_format = str(report_settings.get("output_format") or "")
            if output_format in {"Word + PDF", "Editable Word", "PDF", "Markdown + JSON"}:
                self.professional_output_format_var.set(output_format)
            if "include_contents" in report_settings:
                self.professional_include_contents_var.set(bool(report_settings.get("include_contents")))
            if "include_page_numbers" in report_settings:
                self.professional_include_pages_var.set(bool(report_settings.get("include_page_numbers")))
            if "include_source_references" in report_settings:
                self.professional_include_sources_var.set(bool(report_settings.get("include_source_references")))
            if "include_evidence_index" in report_settings:
                self.professional_include_evidence_var.set(bool(report_settings.get("include_evidence_index")))
        self.set_text(self.t_bg, parsed.get("case_text", ""))
        self.set_text(self.t_pos_args, parsed.get("pos_args", ""))
        self.set_text(self.t_pos_ev, parsed.get("pos_ev", ""))
        self.set_text(self.t_neg_args, parsed.get("neg_args", ""))
        self.set_text(self.t_neg_ev, parsed.get("neg_ev", ""))

    def set_text(self, widget, value):
        value = str(value or "")
        value = value.replace("跨Jurisdiction", "Cross-Jurisdiction")
        value = value.replace("跨法域武器", "Cross-Jurisdiction Weapon")
        value = value.replace("跨界", "Cross-Boundary")
        try:
            original_state = str(widget.cget("state"))
        except (tk.TclError, AttributeError):
            original_state = str(tk.NORMAL)
        try:
            if original_state == str(tk.DISABLED):
                widget.configure(state=tk.NORMAL)
            widget.delete("1.0", tk.END)
            widget.insert("1.0", value)
        finally:
            if original_state == str(tk.DISABLED):
                widget.configure(state=tk.DISABLED)

    def get_text(self, widget):
        return widget.get("1.0", tk.END).strip()

    def open_legal_framework_pack_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("Select Jurisdiction Frame")
        win.configure(bg=self.C["bg"])
        win.geometry("560x430")
        win.transient(self.root)
        win.grab_set()

        tk.Label(
            win,
            text="Add Jurisdiction Frame",
            bg=self.C["bg"],
            fg=self.C["gold"],
            font=("Microsoft YaHei UI", 15, "bold"),
        ).pack(anchor=tk.W, padx=14, pady=(12, 4))
        tk.Label(
            win,
            text="Use this to build a jurisdiction starting frame before entering a specific case. It is not legal advice; latest law and authorities must be reviewed by a lawyer or firm database.",
            bg=self.C["panel"],
            fg=self.C["text"],
            wraplength=520,
            justify=tk.LEFT,
            padx=10,
            pady=8,
        ).pack(fill=tk.X, padx=14, pady=(0, 10))

        body = tk.Frame(win, bg=self.C["bg"], padx=14)
        body.pack(fill=tk.BOTH, expand=True)
        tk.Label(body, text="Select Country/Region", bg=self.C["bg"], fg=self.C["muted"]).pack(anchor=tk.W)
        pack_var = tk.StringVar(value=self.match_framework_pack_key(self.jur_var.get()))
        combo = ttk.Combobox(
            body,
            textvariable=pack_var,
            values=list(LEGAL_FRAMEWORK_PACKS.keys()),
            state="readonly",
            width=42,
        )
        combo.pack(anchor=tk.W, pady=(4, 8))

        preview = scrolledtext.ScrolledText(body, height=12, bg=self.C["entry"], fg=self.C["text"], relief="flat", wrap=tk.WORD)
        self.bind_local_scroll(preview)
        preview.pack(fill=tk.BOTH, expand=True)

        def refresh_preview(*_):
            pack = LEGAL_FRAMEWORK_PACKS.get(pack_var.get(), {})
            preview.delete("1.0", tk.END)
            preview.insert(tk.END, "\n\n".join([
                pack.get("case_text", ""),
                "[Positive-Side Preparation Path]\n" + pack.get("pos_args", ""),
                "[Negative-Side Preparation Path]\n" + pack.get("neg_args", ""),
            ]))

        combo.bind("<<ComboboxSelected>>", refresh_preview)
        refresh_preview()

        controls = tk.Frame(win, bg=self.C["bg"], padx=14, pady=12)
        controls.pack(fill=tk.X)

        def apply_selected_pack():
            self.apply_legal_framework_pack(pack_var.get())
            win.destroy()

        tk.Button(controls, text="Add To Current Case", command=apply_selected_pack, bg=self.C["accent"], fg="white", relief="flat", padx=18, pady=7).pack(side=tk.LEFT)
        tk.Button(controls, text="Cancel", command=win.destroy, bg="#333", fg=self.C["text"], relief="flat", padx=18, pady=7).pack(side=tk.RIGHT)

    def match_framework_pack_key(self, jurisdiction):
        jur = (jurisdiction or "").lower().strip()
        if "australia" in jur or jur in {"au", "aus"} or "nsw" in jur or "vic" in jur or "qld" in jur:
            return "Australia / AU"
        if "uk" in jur or "united kingdom" in jur or "england" in jur or "britain" in jur:
            return "United Kingdom / UK"
        if "us" in jur or "usa" in jur or "united states" in jur or "america" in jur or "california" in jur or "new york" in jur or "texas" in jur or "florida" in jur:
            return "United States / US"
        if "eu" in jur or "europe" in jur or "european" in jur:
            return "European Union / EU"
        if "china" in jur or jur == "cn" or "中国" in jur:
            return "China / CN"
        return "Australia / AU" if not jurisdiction else "Custom / User Provided"

    def apply_legal_framework_pack(self, pack_key):
        pack = LEGAL_FRAMEWORK_PACKS.get(pack_key)
        if not pack:
            messagebox.showwarning("Missing Jurisdiction Frame", "No frame was found for the selected jurisdiction.")
            return
        existing = "\n".join([
            self.get_text(self.t_bg),
            self.get_text(self.t_pos_args),
            self.get_text(self.t_pos_ev),
            self.get_text(self.t_neg_args),
            self.get_text(self.t_neg_ev),
        ]).strip()
        if existing:
            ok = messagebox.askyesno(
                "Existing Content",
                "The case area or side frames already contain content.\n\n"
                "Adding a jurisdiction frame will overwrite those fields. This is best used on a blank matter.\n"
                "Continue and overwrite?",
            )
            if not ok:
                return
        self.jur_var.set(self.normalise_jurisdiction_option(pack_key))
        if not self.case_name_var.get().strip():
            self.case_name_var.set(pack.get("case_name", f"{pack_key} Jurisdiction攻防模板"))
        self.set_text(self.t_bg, pack.get("case_text", ""))
        self.set_text(self.t_pos_args, pack.get("pos_args", ""))
        self.set_text(self.t_pos_ev, pack.get("pos_ev", ""))
        self.set_text(self.t_neg_args, pack.get("neg_args", ""))
        self.set_text(self.t_neg_ev, pack.get("neg_ev", ""))
        self.status_var.set(f"Status: jurisdiction frame added: {pack_key}")

    def open_official_legal_pack_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("Select Official Law Pack")
        win.configure(bg=self.C["bg"])
        win.geometry("560x360")
        win.transient(self.root)
        win.grab_set()

        tk.Label(
            win,
            text="Update Official Law Pack",
            bg=self.C["bg"],
            fg=self.C["gold"],
            font=("Microsoft YaHei UI", 15, "bold"),
        ).pack(anchor=tk.W, padx=14, pady=(12, 4))
        tk.Label(
            win,
            text="Select a country/state/region first. Federal systems must distinguish state law. Unconnected state law requires a firm database, official API, or licensed legal database.",
            bg=self.C["panel"],
            fg=self.C["text"],
            wraplength=520,
            justify=tk.LEFT,
            padx=10,
            pady=8,
        ).pack(fill=tk.X, padx=14, pady=(0, 10))

        body = tk.Frame(win, bg=self.C["bg"], padx=14)
        body.pack(fill=tk.BOTH, expand=True)
        tk.Label(body, text="Country/State/Region", bg=self.C["bg"], fg=self.C["muted"]).pack(anchor=tk.W)
        selected_var = tk.StringVar(value=self.normalise_jurisdiction_option(self.jur_var.get()))
        combo = ttk.Combobox(
            body,
            textvariable=selected_var,
            values=JURISDICTION_OPTIONS,
            state="readonly",
            width=48,
        )
        combo.pack(anchor=tk.W, pady=(4, 8))

        preview = scrolledtext.ScrolledText(body, height=8, bg=self.C["entry"], fg=self.C["text"], relief="flat", wrap=tk.WORD)
        self.bind_local_scroll(preview)
        preview.pack(fill=tk.BOTH, expand=True)

        def refresh_preview(*_):
            jur = selected_var.get()
            preview.delete("1.0", tk.END)
            if jur.startswith("Australia / AU"):
                preview.insert(tk.END, (
                    "The current version can check these official Australian legal sources online:\n"
                    "- Federal Register of Legislation API (Commonwealth)\n"
                    "- Official Australian Consumer Law source\n"
                    "- Official NSW legislation source\n"
                    "- Queensland legislation API\n\n"
                    "Important: counsel must still confirm the applicable Act, section, commencement date, "
                    "amendments, and current version for each state or territory."
                ))
            else:
                preview.insert(tk.END, (
                    "An official legal source for this jurisdiction or state has not yet been configured.\n\n"
                    "A production deployment should connect one or more of the following:\n"
                    "1. The firm's own legislation and case-law database;\n"
                    "2. The official legislation API for the selected jurisdiction;\n"
                    "3. An appropriately licensed commercial legal database.\n\n"
                    "Until a source is configured, the software can organise arguments and identify evidentiary gaps, "
                    "but it must not claim that it has retrieved the jurisdiction's current law."
                ))

        combo.bind("<<ComboboxSelected>>", refresh_preview)
        refresh_preview()

        controls = tk.Frame(win, bg=self.C["bg"], padx=14, pady=12)
        controls.pack(fill=tk.X)

        def run_update():
            jur = selected_var.get()
            self.jur_var.set(jur)
            win.destroy()
            self.update_latest_legal_pack(jur)

        tk.Button(controls, text="Update Selected Jurisdiction", command=run_update, bg=self.C["accent"], fg="white", relief="flat", padx=18, pady=7).pack(side=tk.LEFT)
        tk.Button(controls, text="Cancel", command=win.destroy, bg="#333", fg=self.C["text"], relief="flat", padx=18, pady=7).pack(side=tk.RIGHT)

    def normalise_jurisdiction_option(self, jurisdiction):
        jur = (jurisdiction or "").strip()
        if jur in JURISDICTION_OPTIONS:
            return jur
        pack_key = self.match_framework_pack_key(jur)
        if pack_key == "Australia / AU":
            low = jur.lower()
            for state in ["NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT"]:
                if state.lower() in low:
                    return f"Australia / AU - {state}"
            return "Australia / AU - Commonwealth"
        if pack_key == "United States / US":
            low = jur.lower()
            if "california" in low or " ca" in low:
                return "United States / US - California / CA"
            if "new york" in low or " ny" in low:
                return "United States / US - New York / NY"
            if "texas" in low or " tx" in low:
                return "United States / US - Texas / TX"
            if "florida" in low or " fl" in low:
                return "United States / US - Florida / FL"
            return "United States / US - Federal"
        return pack_key if pack_key in JURISDICTION_OPTIONS else "Custom / User Provided"

    def update_latest_legal_pack(self, jurisdiction=None):
        jurisdiction = jurisdiction or self.jur_var.get()
        pack_key = self.match_framework_pack_key(jurisdiction)
        if pack_key != "Australia / AU":
            messagebox.showinfo(
                "Jurisdiction Not Connected",
                f"Current selection: {jurisdiction}\n\n"
                "Official legal sources for this country/state/region are not connected yet.\n"
                "Federal systems must specify state law, such as California / CA or New York / NY.\n\n"
                "Commercial deployment should connect a firm law library, official API, or licensed legal database.",
            )
            return
        if self.get_text(self.t_bg).strip():
            ok = messagebox.askyesno(
                "Existing Case Background",
                "Update Official Law Pack is best used to build an official-source starting point before a specific case is entered.\n\n"
                "Continuing will append the source index to the top of the case window and will not delete existing content.\n"
                "Continue?",
            )
            if not ok:
                return
        ok = messagebox.askyesno(
            "Update Australian Official Law Pack Online",
            "The app will access Australian official legal sources online and save the source index locally.\n\n"
            "It will not upload your case content; it only downloads/checks official legal sources.\n"
            "Start update?",
        )
        if not ok:
            return

        self.status_var.set(f"Status: updating Australian official law pack: {jurisdiction}")
        threading.Thread(target=self._update_latest_legal_pack_thread, args=(pack_key, jurisdiction), daemon=True).start()

    def _update_latest_legal_pack_thread(self, pack_key, jurisdiction):
        try:
            sources = OFFICIAL_LEGAL_SOURCE_PACKS.get(pack_key, [])
            stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            out_dir = HERE / "legal_packs" / "Australia_AU" / stamp
            out_dir.mkdir(parents=True, exist_ok=True)
            results = []
            for idx, source in enumerate(sources, 1):
                result = dict(source)
                result["checked_at"] = _dt.datetime.now().isoformat(timespec="seconds")
                try:
                    req = urllib.request.Request(source["url"], headers={"User-Agent": "Nido-StrikeOver/1.0"})
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        data = resp.read(250000)
                        result["status"] = "ok"
                        result["http_status"] = getattr(resp, "status", None)
                        result["content_type"] = resp.headers.get("Content-Type", "")
                        result["bytes_saved"] = len(data)
                        suffix = ".json" if source.get("kind") == "json" else ".html"
                        safe_name = re.sub(r"[^A-Za-z0-9_\-]+", "_", source["name"]).strip("_")
                        file_path = out_dir / f"{idx:02d}_{safe_name}{suffix}"
                        file_path.write_bytes(data)
                        result["local_file"] = str(file_path)
                except Exception as exc:
                    result["status"] = "error"
                    result["error"] = str(exc)
                results.append(result)

            index = {
                "pack": pack_key,
                "jurisdiction": jurisdiction,
                "created_at": _dt.datetime.now().isoformat(timespec="seconds"),
                "purpose": "Official-source index for current Australian legal material. This is not legal advice.",
                "privacy_note": "No case content is uploaded by this update function; it only contacts official legal source URLs.",
                "sources": results,
            }
            (out_dir / "official_legal_sources_index.json").write_text(
                json.dumps(index, ensure_ascii=False, indent=2),
                encoding="utf-8-sig",
            )
            report = self.render_latest_legal_pack_report(index, out_dir)
            (out_dir / "official_legal_sources_report.md").write_text(report, encoding="utf-8-sig")
            source_findings = []
            for source_index, item in enumerate(results, 1):
                status = str(item.get("status") or "not checked")
                source_findings.append({
                    "id": f"SOURCE-{source_index:03d}",
                    "analysis_stage": "official_legal_source_check",
                    "dimension": item.get("kind") or "Official source",
                    "title": item.get("name") or f"Official source {source_index}",
                    "finding": f"Retrieval status: {status}; HTTP status: {item.get('http_status') or 'not recorded'}.",
                    "affected_side": "Not applicable",
                    "factual_basis": item.get("url") or "",
                    "evidence_references": [item.get("local_file")] if item.get("local_file") else [],
                    "significance": "Availability check only; currency, legal effect and applicability require lawyer verification.",
                    "confidence": "Observed retrieval result only",
                    "provider": "Official-source retrieval",
                    "model": "No AI model used",
                    "source_reference": item.get("url") or "",
                    "review_status": "ai_generated_unverified",
                })
            source_standard = build_standard_report(
                "legal_source_pack",
                "official_legal_source_check",
                self.case_name_var.get().strip() or "Australian official legal source pack",
                jurisdiction,
                findings=source_findings,
                provider_runs=[{
                    "provider": "Official-source retrieval",
                    "model": "No AI model used",
                    "engine_source": "Direct HTTP retrieval of configured official URLs",
                    "run_reference": stamp,
                }],
                input_scope={
                    "configured_sources": len(results),
                    "successful_retrievals": sum(1 for item in results if item.get("status") == "ok"),
                    "case_content_uploaded": False,
                },
                sections={"legacy_source_report": report},
                missing_material=[
                    item.get("name") or item.get("url")
                    for item in results if item.get("status") != "ok"
                ],
                limitations=[
                    "Successful retrieval does not prove that a source is current, complete, authoritative for the issue, or legally applicable.",
                    "A lawyer must verify the text, commencement, amendments, jurisdiction, citations and subsequent treatment.",
                ],
            )
            write_standard_companions(out_dir, "official-legal-sources", source_standard)

            def apply_report():
                current = self.get_text(self.t_bg).strip()
                combined = report if not current else report + "\n\n---\n\n【原有案情】\n" + current
                self.set_text(self.t_bg, combined)
                self.jur_var.set(jurisdiction)
                if not self.case_name_var.get().strip():
                    self.case_name_var.set("澳洲最新法律资料包 - 官方源索引")
                self.status_var.set(f"Status: Australian law pack updated: {out_dir}")
                ok_count = sum(1 for item in results if item.get("status") == "ok")
                messagebox.showinfo(
                    "Update Complete",
                    f"Checked {len(results)} Australian official legal sources; successful: {ok_count}.\n\nSaved folder:\n{out_dir}",
                )

            self.root.after(0, apply_report)
        except Exception as exc:
            err = str(exc)
            self.root.after(0, lambda err=err: messagebox.showerror("Update Failed", err))
            self.root.after(0, lambda: self.status_var.set("Status: official law pack update failed"))

    def render_latest_legal_pack_report(self, index, out_dir):
        lines = [
            "# 澳洲最新法律资料包 - 官方来源索引",
            "",
            f"更新时间：{index.get('created_at')}",
            f"保存目录：{out_dir}",
            "",
            "用途：给 Nido 律师攻防提供澳洲官方法律来源入口。各国法律不同，本资料包只代表当前选择的Jurisdiction来源。",
            "重要边界：本资料包不是正式法律意见；具体条文、判例、州/领地规则和客户事实必须由律师复核。",
            "隐私边界：更新过程只访问官方法律来源，不上传案件内容。",
            "",
            "## 官方来源",
        ]
        for item in index.get("sources", []):
            status = "成功" if item.get("status") == "ok" else "失败"
            lines.extend([
                "",
                f"### {item.get('name')} [{status}]",
                f"- 层级：{item.get('level')}",
                f"- 官方地址：{item.get('url')}",
                f"- 说明：{item.get('note')}",
            ])
            if item.get("status") == "ok":
                lines.append(f"- 本地缓存：{item.get('local_file')}")
            else:
                lines.append(f"- 错误：{item.get('error')}")
        lines.extend([
            "",
            "## 使用建议",
            "1. 先根据案件选择具体Jurisdiction：联邦、NSW、VIC、QLD 等。",
            "2. 再由律师或律所资料库确认具体 Act、section、commencement、amendment 和当前版本。",
            "3. Nido 负责攻防结构、证据缺口和追问路径；具体法律结论由律师复核。",
        ])
        return "\n".join(lines)

    def auto_split_case_material(self, raw_text, path, encoding):
        text = self.clean_imported_case_text(raw_text)
        if not text:
            raise RuntimeError("No text could be extracted from the file.")
        structured = self.parse_case_structure(text, path)
        header = f"[Imported file] {path}\n[Read mode] {encoding}\n\n"
        return {
            "case_name": self.sanitize_case_name(structured.get("case_name") or Path(path).stem),
            "jurisdiction": structured.get("jurisdiction") or self.guess_jurisdiction(text),
            "case_text": header + (structured.get("background") or self.first_excerpt(text)),
            "pos_args": structured.get("pos_args") or "",
            "pos_ev": structured.get("pos_ev") or "",
            "neg_args": structured.get("neg_args") or "",
            "neg_ev": structured.get("neg_ev") or "",
            "local_law_region": structured.get("local_law_region") or self.current_law_region()["label"],
            "case_search_enabled": bool(structured.get("case_search_enabled")),
        }

    def clean_imported_case_text(self, raw_text):
        text = str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            return ""
        drop_patterns = [
            r"^\s*\[Language note\].*$",
            r"^\s*好的[，,]\s*这是.*(?:英文|翻译|版本|文本).*$",
            r"^\s*以下是.*(?:英文|翻译|版本|文本).*$",
            r"^\s*这是.*(?:英文|翻译|版本|文本).*$",
            r"^\s*Here is .* translated .* version.*$",
            r"^\s*Below is .* translated .* version.*$",
            r"^\s*Sure[,.]\s*here is .*$",
            r"^\s*---+\s*$",
        ]
        kept = []
        for line in text.split("\n"):
            if any(re.search(pattern, line, flags=re.IGNORECASE) for pattern in drop_patterns):
                continue
            kept.append(line)
        text = "\n".join(kept).strip()
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text

    def parse_case_structure(self, text, path):
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return self.normalise_case_json(data, path)
        except Exception:
            pass
        if self.is_legal_problem_text(text):
            return self.generic_legal_problem_case(text, path)
        if self.is_consumer_return_case(text):
            return self.consumer_return_case(text, path)
        if self.is_contract_formation_problem(text):
            return self.contract_formation_case(text, path)
        return self.generic_case(text, path)

    def normalise_case_json(self, data, path):
        def pick(*keys):
            for key in keys:
                val = data.get(key)
                if isinstance(val, (list, tuple)):
                    val = "\n".join(str(x) for x in val)
                if val:
                    return str(val).strip()
            return ""
        blob = json.dumps(data, ensure_ascii=False)
        return {
            "case_name": pick("case_name", "name", "Case Name", "title") or Path(path).stem,
            "jurisdiction": pick("jurisdiction", "Jurisdiction", "法院", "court") or self.guess_jurisdiction(blob),
            "background": pick("background", "case_bg", "facts", "summary", "案件背景", "案情", "事实经过"),
            "pos_args": pick("pos_args", "positive_args", "plaintiff_args", "my_args", "正方论点", "原告论点", "我方论点"),
            "pos_ev": pick("pos_ev", "positive_evidence", "plaintiff_evidence", "my_evidence", "正方证据", "原告证据", "我方证据"),
            "neg_args": pick("neg_args", "negative_args", "defendant_args", "opponent_args", "反方论点", "被告论点", "对方论点"),
            "neg_ev": pick("neg_ev", "negative_evidence", "defendant_evidence", "opponent_evidence", "反方证据", "被告证据", "对方证据"),
            "local_law_region": pick("local_law_region", "law_region", "法律地区", "当地法律地区"),
            "case_search_enabled": bool(data.get("case_search_enabled") or data.get("use_case_search") or data.get("判例参照")),
        }

    def is_consumer_return_case(self, text):
        lower = text.lower()
        return any(x in text for x in ["退货", "划痕", "消费者", "收货", "质检"]) or "acl" in lower

    def consumer_return_case(self, text, path):
        pos_args = [
            "划痕可能是收货时已经存在的产品瑕疵，商品不符合消费者合理期待。",
            "消费者可依据消费者保护规则主张退货、退款或其他合理补救。",
            "退货期限应结合实际收货、发现瑕疵和合理通知时间判断。",
            "商家拒绝退货可能造成消费者额外维权成本。",
        ]
        neg_args = [
            "出货前质检合格，划痕可能由物流、收货后开机使用或保存不当造成。",
            "如能证明交易当时退货规则已经清楚提示，才可主张对方受退货期限安排约束。",
            "收货后才发现划痕，不能直接倒推出货前存在瑕疵。",
            "拆箱视频需要证明原始性、连续性、封条状态和首次开箱过程。",
        ]
        if "律师费" in text or "legal costs" in text.lower():
            pos_args.append("消费者可主张律师费或维权费用由商家拒退行为导致。")
            neg_args.append("律师费需单独证明合理性、必要性和与商家行为的直接因果关系。")
        if "商誉" in text or "reputation" in text.lower():
            neg_args.append("消费者频繁退货或不完整投诉可能对商家信誉造成额外损害。")

        pos_ev = []
        neg_ev = []
        if "视频" in text or "拆箱" in text:
            pos_ev.append("[P1] 收货/拆箱视频，用于证明发现划痕时间和商品状态。")
            neg_ev.append("[D1] 调取原始视频、时间戳、连续帧、封条和外包装状态，用于质疑视频证明力。")
        if "聊天" in text:
            pos_ev.append("[P2] 与商家客服聊天记录，用于证明通知时间和维权经过。")
        if "ACL" in text or "消费者法" in text:
            pos_ev.append("[P3] 消费者保护法规则，用于支持消费者补救主张。")
        if "质检" in text:
            neg_ev.append("[D2] 出货前质检记录，用于证明出库时无明显瑕疵。")
        if "物流" in text or "签收" in text:
            neg_ev.append("[D3] 物流签收/包装完整性材料，用于排查运输和签收状态。")
        if "退货记录" in text:
            neg_ev.append("[D4] 退货历史记录，用于提示诚信交易、Comparative Fault或滥用退货风险。")

        return {
            "case_name": self.guess_case_name(text, path, default="手机退货消费者纠纷"),
            "jurisdiction": self.guess_jurisdiction(text),
            "background": self.first_excerpt(text, 1800),
            "pos_args": "\n".join(f"{i+1}. {x}" for i, x in enumerate(pos_args)),
            "pos_ev": "\n".join(pos_ev) or "1. 消费者提交的视频、照片、聊天记录或消费者法规材料。",
            "neg_args": "\n".join(f"{i+1}. {x}" for i, x in enumerate(neg_args)),
            "neg_ev": "\n".join(neg_ev) or "1. 商家质检、平台规则、物流签收和消费者使用记录。",
        }

    def is_contract_formation_problem(self, text):
        lower = text.lower()
        markers = [
            "advertisement",
            "offer",
            "acceptance",
            "counter-offer",
            "counter offer",
            "postal rule",
            "revocation",
            "consideration",
            "intention to create legal relations",
            "contract",
            "piano",
            "instrument",
            "take the instrument",
            "at her price",
        ]
        chinese_markers = ["要约", "承诺", "反要约", "邮寄规则", "撤回", "对价", "合同成立", "钢琴"]
        hits = sum(1 for m in markers if m in lower) + sum(1 for m in chinese_markers if m in text)
        party_like = bool(re.search(r"\b[A-Z][a-z]+(?:\s+and\s+[A-Z][a-z]+)?\b", text))
        return hits >= 2 and party_like

    def contract_formation_case(self, text, path):
        lower = text.lower()
        has_kate = "kate" in lower
        has_james = "james" in lower
        has_julie = "julie" in lower
        item = "钢琴/乐器" if ("piano" in lower or "instrument" in lower or "钢琴" in text) else "标的物"
        price = "$4,000" if "$4,000" in text or "4000" in text.replace(",", "") else "约定价格"

        pos_args = [
            f"James 可主张 Kate 的广告和后续通信形成了可被承诺的交易基础，标的为{item}，价格为{price}。",
            "James 表示愿意按对方价格购买，可被解释为对交易条件的接受或明确购买意图。",
            "若 Kate 后续回信包含保留期限或明确出售意向，James 可主张其在期限内作出了承诺。",
            "若适用邮寄承诺规则，James 的承诺可能在寄出时生效，而不是到达 Kate 时才生效。",
            "Kate 后续将标的交给第三人，可能构成对 James 已成立合同的违约或至少形成损害争议。",
        ]
        neg_args = [
            "Kate 可主张杂志广告通常只是邀请要约，并非可直接承诺的确定要约。",
            "James 的第一封信可能只是提出购买要约，Kate 的回信若改变或补充条件，则可能构成反要约。",
            "若所谓保留一周缺少独立对价，Kate 可主张该保留承诺本身未必有约束力。",
            "若 James 的承诺到达较晚，Kate 可主张在收到承诺前已经有效撤回、出售或另行处分标的。",
            "与 Julie 的安排可能构成独立交易或家庭安排争点，需审查对价和创设法律关系意图。",
        ]
        if has_julie:
            pos_args.append("James 可攻击 Kate 与 Julie 的后续安排不能当然消灭先前已对 James 形成的权利。")
            neg_args.append("Kate 可强调 Julie 提供照看孩子或其他利益，形成新的对价和独立安排。")
        if "may" in lower or "1 may" in lower or "5 may" in lower or "6 may" in lower or "11 may" in lower:
            pos_args.append("时间线应重点比较：Kate 回信、James 回信寄出、第三人安排和最终送达之间的法律效果。")
            neg_args.append("Kate 可把时间线压向送达规则、撤回时间和第三人交易先发生这一侧。")

        pos_ev = [
            "[P1] 杂志广告文本：证明标的、价格和交易背景。",
            "[P2] James 致 Kate 的购买表示：证明 James 愿意按价格购买。",
            "[P3] Kate 回信内容：证明是否存在保留期限、出售意向或可承诺条件。",
            "[P4] James 后续回信及寄出时间：用于主张承诺及邮寄规则。",
        ]
        neg_ev = [
            "[D1] 广告的一般法律性质：用于主张广告只是邀请要约。",
            "[D2] Kate 回信的具体措辞：用于主张反要约、条件变更或保留承诺无独立对价。",
            "[D3] James 回信到达时间：用于主张承诺未及时到达或撤回/处分已先发生。",
        ]
        if has_julie:
            neg_ev.append("[D4] Kate 与 Julie 的安排及 Julie 提供的利益：用于证明第三人交易、对价或家庭安排争点。")
        if any(x in lower for x in ["may", "june", "date"]):
            pos_ev.append("[P5] 全部通信和交付日期：用于重建 offer/acceptance/revocation 时间线。")
            neg_ev.append("[D5] 第三人交付或处分日期：用于抗辩 James 权利尚未确定。")

        case_name = self.guess_case_name(text, path, default="")
        if not case_name or case_name == Path(path).stem:
            if has_james and has_kate:
                case_name = "James v Kate 合同成立争议"
            else:
                case_name = "合同成立教材题"
        return {
            "case_name": case_name,
            "jurisdiction": self.guess_jurisdiction(text),
            "background": self.first_excerpt(text, 2400),
            "pos_args": "\n".join(f"{i+1}. {x}" for i, x in enumerate(pos_args)),
            "pos_ev": "\n".join(pos_ev),
            "neg_args": "\n".join(f"{i+1}. {x}" for i, x in enumerate(neg_args)),
            "neg_ev": "\n".join(neg_ev),
        }

    def is_legal_problem_text(self, text):
        lower = text.lower()
        legal_markers = [
            "plaintiff", "defendant", "claimant", "respondent", "applicant",
            "sue", "sued", "liable", "liability", "breach", "damages",
            "negligence", "duty", "contract", "agreement", "consideration",
            "consumer", "warranty", "misrepresentation", "remedy", "court",
            "advise", "legal position", "rights", "obligations",
        ]
        chinese_markers = [
            "原告", "被告", "起诉", "主张", "抗辩", "违约", "侵权", "损害",
            "赔偿", "合同", "责任", "证据", "法院", "消费者", "义务", "权利",
        ]
        hits = sum(1 for m in legal_markers if m in lower) + sum(1 for m in chinese_markers if m in text)
        has_fact_shape = len(text.strip()) > 80 and bool(re.search(r"[。.!?]\s*", text))
        return hits >= 2 and has_fact_shape

    def generic_legal_problem_case(self, text, path):
        lower = text.lower()
        parties = self.extract_party_names(text)
        claimant, opponent = self.infer_litigation_sides(text, parties)
        p1 = claimant or (parties[0] if parties else "claimant side")
        p2 = opponent or (parties[1] if len(parties) > 1 else "defence side")
        issues = self.detect_legal_issue_tags(text)

        pos_args = [
            f"{p1} can argue that the opponent's conduct triggers the core liability issue and must be tied to facts, legal elements, and loss.",
            "The key timeline, conduct, damage, and transaction outcome should be connected into a complete proof chain.",
            "Written materials, communications, payment, delivery, notice, inspection, or scene records should be treated as the main support for the claimant's burden.",
        ]
        neg_args = [
            f"{p2} can attack the preconditions for liability: whether the facts are proved, the legal rule applies, and the causal chain is intact.",
            "Break the opponent's conclusion back into legal elements and ask whether the evidence meets the proof threshold for each element.",
            "Ambiguity, missing records, alternative causes, late notice, or plaintiff-side fault should be converted into defence paths.",
        ]
        if "contract" in issues:
            pos_args.append("Contract angle: argue offer, acceptance, consideration, intention, performance, or breach has created enforceable rights.")
            neg_args.append("Contract angle: attack whether the advertisement or negotiation was only an invitation to treat, whether terms were certain, acceptance was timely, and consideration/intention existed.")
        if "tort" in issues:
            pos_args.append("Tort angle: argue duty, breach, foreseeable harm, and causation.")
            neg_args.append("Tort angle: attack the scope of duty, breach, causation, foreseeability, and plaintiff-side contributory fault.")
        if "consumer" in issues:
            pos_args.append("Consumer angle: argue the goods or services failed reasonable expectations and the remedy has a statutory basis.")
            neg_args.append("Consumer angle: attack timing of the defect, reasonable notice, intervening use, remedy proportionality, and proof.")
        if "evidence" in issues:
            pos_args.append("Evidence angle: argue existing documents, communications, video, photos, or records create a balance-of-probabilities proof path.")
            neg_args.append("Evidence angle: attack originality, continuity, completeness, source reliability, and missing materials.")

        pos_ev = [
            "[P1] Communications, contract, advertisement, payment, delivery, notice, inspection, or scene records in the problem.",
            "[P2] Original materials proving the claimant's conduct, timeline, and loss outcome.",
            "[P3] Rules for the relevant jurisdiction, problem prompt, or assigned legal principles.",
        ]
        neg_ev = [
            "[D1] Missing originals, timestamps, third-party records, or complete context in the opponent's evidence.",
            "[D2] Materials showing an alternative cause, late notice, plaintiff-side fault, or failure of a legal precondition.",
            "[D3] Restrictive interpretation materials for key terms, elements, and remedy scope.",
        ]
        return {
            "case_name": self.guess_case_name(text, path, default=self.guess_problem_case_name(text, path, [p1, p2])),
            "jurisdiction": self.guess_jurisdiction(text),
            "background": self.first_excerpt(text, 2400),
            "pos_args": "\n".join(f"{i+1}. {x}" for i, x in enumerate(pos_args)),
            "pos_ev": "\n".join(pos_ev),
            "neg_args": "\n".join(f"{i+1}. {x}" for i, x in enumerate(neg_args)),
            "neg_ev": "\n".join(neg_ev),
        }

    def infer_litigation_sides(self, text, parties):
        patterns = [
            r"\b([A-Z][a-z]{2,18})\s+sues\s+([A-Z][a-z]{2,18})\b",
            r"\b([A-Z][a-z]{2,18})\s+is\s+suing\s+([A-Z][a-z]{2,18})\b",
            r"\b([A-Z][a-z]{2,18})\s+brings\s+(?:an\s+)?action\s+against\s+([A-Z][a-z]{2,18})\b",
            r"\b([A-Z][a-z]{2,18})\s+claims\s+against\s+([A-Z][a-z]{2,18})\b",
            r"([\u4e00-\u9fff]{2,4})\s*(?:起诉|诉|控告)\s*([\u4e00-\u9fff]{2,4})",
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.I)
            if m:
                return m.group(1), m.group(2)
        # If the problem asks to advise a named party, treat that party as the client side.
        m = re.search(r"\badvise\s+([A-Z][a-z]{2,18})\b", text, re.I)
        if m:
            claimant = m.group(1)
            opponent = next((p for p in parties if p != claimant), "")
            return claimant, opponent
        return "", ""

    def extract_party_names(self, text):
        names = []
        for m in re.finditer(r"\b([A-Z][a-z]{2,18})\b", text):
            name = m.group(1)
            if name in {
                "The", "This", "That", "They", "Their", "Court", "Section",
                "Australia", "Australian", "New", "South", "Wales", "James",
            }:
                pass
            if name not in names and name.lower() not in {"the", "this", "that", "court", "australia", "australian"}:
                names.append(name)
            if len(names) >= 4:
                break
        # Keep James in real textbook cases; the pass above only avoids returning early.
        if "James" in text and "James" not in names:
            names.insert(0, "James")
        return names[:4]

    def detect_legal_issue_tags(self, text):
        lower = text.lower()
        tags = set()
        if any(x in lower for x in ["contract", "agreement", "offer", "acceptance", "consideration", "breach"]):
            tags.add("contract")
        if any(x in lower for x in ["negligence", "duty", "injury", "reasonable care", "foresee"]):
            tags.add("tort")
        if any(x in lower for x in ["consumer", "warranty", "acl", "refund", "return"]):
            tags.add("consumer")
        if any(x in lower for x in ["evidence", "video", "photo", "record", "document", "email", "message"]) or any(x in text for x in ["证据", "视频", "照片", "记录"]):
            tags.add("evidence")
        return tags

    def guess_problem_case_name(self, text, path, parties):
        if len(parties) >= 2:
            return f"{parties[0]} v {parties[1]} legal problem"
        return Path(path).stem or "legal problem"

    def generic_case(self, text, path):
        return {
            "case_name": self.guess_case_name(text, path),
            "jurisdiction": self.guess_jurisdiction(text),
            "background": self.first_excerpt(text, 2400),
            "pos_args": self.extract_section(text, ["我方", "正方", "原告", "申请人", "权利人"]),
            "pos_ev": self.extract_evidence(text),
            "neg_args": self.extract_section(text, ["对方", "反方", "被告", "无效方", "异议方"]),
            "neg_ev": self.extract_evidence(text),
        }

    def first_excerpt(self, text, limit=6500):
        return text[:limit] + ("\n\n[Note] The file is long, so the first section was loaded here. Keep the original file for full review." if len(text) > limit else "")

    def sanitize_case_name(self, name):
        name = str(name or "").strip()
        replacements = {
            "法律教材题": "legal problem",
            "合同成立争议": "contract formation dispute",
            "手机退货消费者纠纷": "consumer phone return dispute",
            "网购手机退货纠纷": "online phone return dispute",
        }
        for old, new in replacements.items():
            name = name.replace(old, new)
        name = re.sub(r"\s+", " ", name).strip()
        return name

    def guess_case_name(self, text, path, default=None):
        for pattern in [
            r'"name"\s*:\s*"([^"]+)"',
            r'"case_name"\s*:\s*"([^"]+)"',
            r"Case Name\s*[:：]\s*(.+)",
            r"案名\s*[:：]\s*(.+)",
        ]:
            m = re.search(pattern, text)
            if m:
                return self.compact(m.group(1), 60)
        if "退货" in text and "手机" in text:
            return default or "网购手机退货纠纷"
        return default or Path(path).stem

    def guess_jurisdiction(self, text):
        lower = text.lower()
        if "australia" in lower or "澳洲" in text or "澳大利亚" in text or "nsw" in lower:
            return "Australia / AU"
        if "china" in lower or "中国" in text:
            return "China / CN"
        if "united states" in lower or "usa" in lower or "美国" in text:
            return "United States / US"
        return self.jur_var.get()

    def extract_section(self, text, terms):
        lines = []
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            if any(term in s for term in terms) and any(k in s for k in ["主张", "认为", "要求", "抗辩", "论点"]):
                lines.append(s)
        return "\n".join(lines[:10])

    def extract_evidence(self, text):
        terms = ["证据", "视频", "照片", "聊天记录", "质检", "物流", "签收", "合同", "截图", "法条", "报告"]
        lines = []
        for line in text.splitlines():
            s = line.strip()
            if any(term in s for term in terms):
                lines.append(s)
        return "\n".join(lines[:10])

    def compact(self, text, max_len=80):
        text = re.sub(r"\s+", " ", text.strip())
        return text[:max_len] + ("..." if len(text) > max_len else "")

    def remove_repeated_prefix(self, title, text):
        title = re.sub(r"\s+", " ", str(title or "").strip()).strip(":： ")
        text = re.sub(r"\s+", " ", str(text or "").strip())
        if title and text.lower().startswith((title + ":").lower()):
            return text[len(title) + 1:].strip()
        if title and text.lower().startswith((title + " -").lower()):
            return text[len(title) + 2:].strip()
        return text

    def selected_dimensions(self):
        return [name for name, var in self.dimension_vars.items() if var.get()]

    def build_case_search_context(self, selected_dims, case_text, jurisdiction):
        region = self.current_law_region()
        context = {
            "enabled": bool(self.case_search_var.get()),
            "region": region["label"],
            "jurisdiction": jurisdiction,
            "verified": False,
            "results_by_dimension": {},
            "logs": [],
            "rule": "只引用搜索结果中明确出现的案例名称；搜索为空时不得编造案例。",
        }
        if not self.case_search_var.get():
            return context
        short_case = self.compact(case_text, 180)
        for name, _desc in selected_dims:
            if name not in {"Legal Application", "Precedent Attack", "Legal Text Interpretation", "Procedural Defect", "跨Jurisdiction武器", "Public Policy", "Proportionality Test"}:
                continue
            query = f"{name} {short_case}"
            result = self.case_search_engine.search(query, jurisdiction)
            context["results_by_dimension"][name] = result
            context["logs"].extend(self.case_search_engine.log)
            if result.get("verified"):
                context["verified"] = True
        return context

    def apply_case_search_context_to_rounds(self, r1, r2, case_search_context):
        if not case_search_context.get("enabled"):
            return r1, r2
        results_by_dim = case_search_context.get("results_by_dimension", {})
        for item in r1:
            dim = item.get("dimension", "")
            result = results_by_dim.get(dim)
            item["case_search_region"] = case_search_context.get("region", "")
            if result and result.get("verified"):
                titles = [x.get("title", "") for x in result.get("results", [])[:3] if x.get("title")]
                item["case_reference_source"] = f"{result.get('source', '')}: " + "；".join(titles)
                item["question"] = (
                    str(item.get("question") or "")
                    + " 判例参照只可使用搜索结果中明确出现的案例，并需律师核验法院、年份和适用范围。"
                ).strip()
            elif dim in {"Legal Application", "Precedent Attack", "Legal Text Interpretation"}:
                item["case_reference_source"] = "判例参照未取得已验证结果；不得编造案例。"
        for item in r2:
            dim = item.get("dimension", "")
            result = results_by_dim.get(dim)
            item["case_search_region"] = case_search_context.get("region", "")
            needed = item.get("needed_material") or []
            if isinstance(needed, str):
                needed = [needed]
            if result and result.get("verified"):
                needed.extend(["判例原文", "法院和年份", "适用Jurisdiction确认", "与本案事实的可区分点"])
            elif dim in {"Legal Application", "Precedent Attack", "Legal Text Interpretation"}:
                needed.append("如无已验证判例，只用一般法律原则或律师确认材料")
            item["needed_material"] = list(dict.fromkeys(str(x) for x in needed if x))
        return r1, r2

    def is_law_dimension(self, dimension):
        return any(
            key in dimension
            for key in ["法律", "先例", "程序", "跨Jurisdiction", "Public Policy", "比例", "文本"]
        )

    def current_case_materials(self):
        return self.case_materials_for_side("positive")

    def legacy_lawyer_frame(self, side_label, action_label, dimension_count=18):
        return {
            "source": "old_1_0_attorney_frame",
            "side": side_label,
            "action": action_label,
            "regulator_notice": [
                f"你的用户是{side_label}。",
                f"你是{side_label}的代理律师团，受聘代表{side_label}应诉。",
                f"你已经完成了案件研究，准备就{dimension_count}个攻击维度向对方发起论证。",
                f"你方的立场已经在诉讼材料中明确表达，你的工作是把这些立场论证到位。",
                "每个攻击维度由独立的律师负责，维度之间互不干扰。",
            ],
            "role_rules": [
                f"你为{side_label}工作，你的产出服务于{side_label}的利益。",
                f"你的目标是说服法官团采纳{side_label}的主张。",
                "真相判断是法官的工作，不是你的工作。",
                "客观平衡是审判系统的责任，不是律师的责任。",
                "我只百分百维护本方利益，凡不符合本方利益的妥协概不接受。",
            ],
            "r2_rule": "反驳必须直接对应对方的具体攻击点，不是泛泛而谈。",
        }

    def apply_legacy_lawyer_frame_to_rounds(self, r1, r2, dimension_count=18):
        neg_frame = self.legacy_lawyer_frame("反方", "攻击正方", dimension_count)
        pos_frame = self.legacy_lawyer_frame("正方", "反驳反方攻击", dimension_count)
        for item in r1:
            item["legacy_lawyer_frame"] = neg_frame
            item["legacy_role_line"] = "反方代理律师团只服务反方利益，任务是攻击正方主张并说服法官不采纳正方路径。"
        for item in r2:
            item["legacy_lawyer_frame"] = pos_frame
            item["legacy_role_line"] = "正方代理律师团只服务正方利益，任务是逐条回应反方攻击并维护正方诉求。"
        return r1, r2

    def case_materials_for_side(self, target_side="positive"):
        case_text = self.get_text(self.t_bg)
        pos_args = self.get_text(self.t_pos_args)
        pos_ev = self.get_text(self.t_pos_ev)
        neg_args = self.get_text(self.t_neg_args)
        neg_ev = self.get_text(self.t_neg_ev)
        if target_side == "negative":
            my_position = "\n\n".join(x for x in [
                "被扫描方：围绕反方画框的论点和证据，检查其可被攻击的Weakness。",
                "【反方论点】\n" + neg_args if neg_args else "",
                "【反方证据】\n" + neg_ev if neg_ev else "",
            ] if x)
            opponent_position = "\n\n".join(x for x in [
                "攻击方：围绕正方画框的论点和证据，寻找反方事实、证据、Legal Application和因果链漏洞。",
                "【正方论点】\n" + pos_args if pos_args else "",
                "【正方证据】\n" + pos_ev if pos_ev else "",
            ] if x)
        else:
            my_position = "\n\n".join(x for x in [
                "被扫描方：围绕正方画框的论点和证据，检查其可被攻击的Weakness。",
                "【正方论点】\n" + pos_args if pos_args else "",
                "【正方证据】\n" + pos_ev if pos_ev else "",
            ] if x)
            opponent_position = "\n\n".join(x for x in [
                "攻击方：围绕反方画框的论点和证据，寻找正方事实、证据、Legal Application和因果链漏洞。",
                "【反方论点】\n" + neg_args if neg_args else "",
                "【反方证据】\n" + neg_ev if neg_ev else "",
            ] if x)
        structured = {
            "pos_args": pos_args,
            "pos_ev": pos_ev,
            "neg_args": neg_args,
            "neg_ev": neg_ev,
        }
        return case_text, my_position, opponent_position, structured

    def run_nido_local_state(self, selected, workflow_mode="full_attack", target_side="positive"):
        case_text, my_position, opponent_position, structured = self.case_materials_for_side(target_side)
        mode = self.mode_var.get()
        jurisdiction = self.jur_var.get().strip()
        active_language_sops = self.active_personal_sops("language_rhetoric")
        active_case_sops = self.active_personal_sops("case_decomposition")
        options = {
            "local_only": True,
            "strategy_enhanced": self.strategy_enhanced_var.get(),
            "strategy_enhanced_label": "Strategy boost",
            "confidentiality_mode": "Local-only confidentiality",
            "external_assist_provider": "",
            "cloud_parse_count": self.cloud_parse_count,
            "case_name": self.case_name_var.get().strip(),
            "workflow_mode": workflow_mode,
            "target_side": target_side,
            "round_policy": "two_round_only",
            "structured_case": structured,
            "personal_sop_language_active": len(active_language_sops),
            "personal_sop_case_active": len(active_case_sops),
        }

        run_id = _dt.datetime.now().strftime("nido_strikeover_2r_%Y%m%d_%H%M%S")
        case_key = short_hash("\n".join([mode, jurisdiction, case_text, my_position, opponent_position]))
        selected_dims = [d for d in self.engine.dimensions if d[0] in selected]
        case_search_context = self.build_case_search_context(selected_dims, case_text, jurisdiction)
        options["case_search_enabled"] = bool(case_search_context.get("enabled"))
        options["case_search_region"] = case_search_context.get("region", "")
        signals = self.engine.scan(case_text, my_position, opponent_position, mode)
        stance_frame = self.engine.build_stance_frame(my_position, opponent_position, mode)
        persona_anchors = (
            self.engine.build_persona_anchors(selected_dims)
            if hasattr(self.engine, "build_persona_anchors")
            else {}
        )
        signals["stance_frame"] = stance_frame
        signals["persona_anchors"] = persona_anchors
        signals["options"] = options
        signals["case_search_context"] = case_search_context

        r1 = [self.engine.attack(name, desc, signals, mode) for name, desc in selected_dims]
        if options.get("strategy_enhanced"):
            r1 = [self.engine.apply_strategy_enhancement(item) for item in r1]
        r2 = [self.engine.defend(item, signals, mode) for item in r1]
        r1, r2 = self.enhance_main_rounds_with_personal_sop(r1, r2)
        r1, r2 = self.apply_case_search_context_to_rounds(r1, r2, case_search_context)
        r1, r2 = self.apply_legacy_lawyer_frame_to_rounds(r1, r2, len(selected_dims))

        stance_reviews = (
            self.engine.review_stance_continuity(r1, r2, [], [], stance_frame, persona_anchors)
            if hasattr(self.engine, "review_stance_continuity")
            else {}
        )
        review = self.engine.review(selected_dims, signals, mode, options, stance_reviews)
        trace = self.engine.build_execution_trace(selected_dims, signals, options)
        trace["round_policy"] = "two_round_only"
        trace.setdefault("counts", {})["personal_sop_language_active"] = len(active_language_sops)
        trace.setdefault("counts", {})["personal_sop_case_active"] = len(active_case_sops)

        return {
            "run_id": run_id,
            "case_key": case_key,
            "app": APP_TITLE,
            "mode": mode,
            "jurisdiction": jurisdiction,
            "options": options,
            "architecture": {
                "primary_executor": "local_secure_engine",
                "auxiliary_processors": ["local_model_optional", "cloud_model_optional", "case_search_optional"],
                "rule": "本地引擎负责Weakness Scan、律师选择、两轮攻防和最终写回；外部模型只在授权时作为辅助。",
                "legacy_attorney_frame": "已接入旧版1.0正反方代理律师团画框：律师只服务本方利益，真相判断交给法官，客观平衡不是律师任务。",
            },
            "selected_dimensions": [name for name, _ in selected_dims],
            "stance_frame": stance_frame,
            "persona_anchors": persona_anchors,
            "stance_reviews": stance_reviews,
            "execution_trace": trace,
            "signals": signals,
            "case_search_context": case_search_context,
            "workflow_mode": workflow_mode,
            "rounds": {
                "round1_opponent_attack": r1,
                "round2_my_rebuttal": r2,
                "final_reviewer": review,
            },
        }

    def enhance_main_rounds_with_personal_sop(self, r1, r2):
        enhanced_r1 = []
        for item in r1:
            new_item = dict(item)
            dimension = new_item.get("dimension", "")
            for key in ("finding", "question", "attack"):
                if new_item.get(key):
                    new_item[key] = self.polish_main_round_language_sop(new_item[key], role="attack")
            focus = self.main_dimension_attack_focus(dimension)
            if focus and focus not in str(new_item.get("question", "")):
                new_item["question"] = (str(new_item.get("question", "")).strip() + " " + focus).strip()
            enhanced_r1.append(new_item)

        enhanced_r2 = []
        for item in r2:
            new_item = dict(item)
            dimension = new_item.get("dimension", "")
            response = str(new_item.get("response", "")).strip()
            dimension_response = self.main_dimension_rebuttal_focus(dimension)
            if dimension_response and dimension_response not in response:
                response = (response + " 维度防守落点：" + dimension_response).strip()
            new_item["response"] = self.polish_main_round_language_sop(response, role="rebuttal")
            needed = new_item.get("needed_material") or []
            if isinstance(needed, str):
                needed = [needed]
            needed = list(needed) + self.main_dimension_needed_materials(dimension)
            new_item["needed_material"] = list(dict.fromkeys(str(x) for x in needed if str(x).strip()))
            enhanced_r2.append(new_item)
        return enhanced_r1, enhanced_r2

    def polish_main_round_language_sop(self, text, role="attack"):
        text = re.sub(r"\s+", " ", str(text or "")).strip()
        if not text:
            return text
        if role == "attack":
            replacements = [
                ("可以", "应当"),
                ("可能", "可能"),
                ("要求说明", "要求逐项说明"),
                ("事实基础", "事实前提"),
                ("证明来源", "证据来源"),
            ]
            for old, new in replacements:
                text = text.replace(old, new)
            if "证明责任" not in text and any(x in text for x in ["证据", "事实", "规则", "条款", "时间"]):
                text += " 攻击落点应压回对方证明责任，不替对方补全事实。"
        else:
            text = text.replace("不替对方补强", "不替对方补强")
            if "总立场" not in text:
                text += " 回应不得削弱本方总立场。"
            if "限缩" not in text and "补证" not in text:
                text += " 同时保留限缩、补证和替代论证空间。"

        for item in self.active_personal_sops("language_rhetoric")[:3]:
            rule = re.sub(r"\s+", " ", str(item.get("rule", "")).strip())
            if not rule:
                continue
            self.log_personal_sop_call(item, context=f"main_round_{role}")
            if role == "attack":
                if "证明对象" in rule and "证明对象" not in text:
                    text += " 先锁定证明对象，再压回事实前提、证据来源和证明责任。"
                elif "追问" in rule and "追问" not in text:
                    text += " 追问应聚焦事实前提、证据来源和证明责任。"
            else:
                if "单点" in rule and "攻击范围" not in text:
                    text += " 先限定对方攻击范围，再逐项回应。"
                elif "总立场" in rule and "总立场" not in text:
                    text += " 回应时不得削弱本方总立场。"
        return text

    def main_dimension_attack_focus(self, dimension):
        focuses = {
            "Fact Challenge": "继续追问原始来源、形成时间、连续性和真实性。",
            "Legal Application": "继续追问具体法条前提、构成要件和事实映射。",
            "Precedent Attack": "继续追问引用案例或规则与本案是否真正同构。",
            "Logic Gap": "继续追问因果跳跃、循环论证和替代解释。",
            "Procedural Defect": "继续追问通知、送达、提交、确认和期限节点。",
            "Damage Causation": "继续追问责任、因果、损害和救济范围是否逐项成立。",
            "Quantum Dispute": "继续追问金额明细、计算口径和损失边界。",
            "Burden of Proof": "继续追问谁主张、谁举证、证明门槛是否已经达到。",
            "Legal Text Interpretation": "继续追问交易当时文本、提示方式和解释边界。",
            "Comparative Fault": "继续追问双方控制能力、注意义务和风险节点。",
            "Public Policy": "继续追问个案结论是否会被过度扩张成Public Policy。",
            "Reverse Thinking": "继续追问最坏前提成立时仍可守住哪条路径。",
            "跨Jurisdiction武器": "继续追问外部规则是否只是压力工具而非本案法律依据。",
            "Counterfactual Reasoning": "继续追问去掉关键事实后结论是否仍成立。",
            "Proportionality Test": "继续追问救济方式与损害、风险和成本是否相称。",
            "Narrative Deconstruction": "继续追问哪些是证据，哪些只是身份或情绪标签。",
            "Systemic Risk Amplification": "继续追问单案漏洞被接受后是否造成规则外溢风险。",
            "Missing Evidence": "继续追问应出现却未出现的记录、日志、第三方材料或反证。",
        }
        return focuses.get(dimension, "")

    def main_dimension_rebuttal_focus(self, dimension):
        focuses = {
            "Fact Challenge": "把事实来源、时间线和可验证材料列清；对方若只是概括怀疑，应指出其没有具体反证。",
            "Legal Application": "把适用规则拆成构成要件，逐项说明本案事实如何落入或为什么对方未满足前提。",
            "Precedent Attack": "说明引用规则、案例或惯例与本案的同构点，同时切开不相干差异。",
            "Logic Gap": "把我方结论拆回事实前提和因果节点，要求对方替代解释也必须有证据落点。",
            "Procedural Defect": "用节点表固定通知、送达、提交和回复时间，避免程序攻击变成全案否定。",
            "Damage Causation": "分开回应责任来源、损害发生、因果连接和救济范围，不让结果倒推责任。",
            "Quantum Dispute": "区分基础责任与金额计算；金额可后补明细，但不能让对方用金额争议否定全部事实。",
            "Burden of Proof": "确认本方证明范围，同时把对方反证所需事实和证明门槛压回对方。",
            "Legal Text Interpretation": "回到条款原文、交易当时版本、提示位置和接受记录，防止对方用抽象公平感改写文本。",
            "Comparative Fault": "区分双方注意义务和控制能力，只承认可证明的比例，不扩大为全盘责任。",
            "Public Policy": "把个案事实和规则外溢分开，对方若放大公共风险，应要求其给出制度或行业依据。",
            "Reverse Thinking": "把该点放入主备防线：即使某个Weakness成立，也要说明剩余证据链能否继续支撑。",
            "跨Jurisdiction武器": "说明外Jurisdiction、平台或监管材料只作辅助，核心仍落在本Jurisdiction规则和本案事实。",
            "Counterfactual Reasoning": "建立反事实边界，说明没有该事实时结果如何、有该事实时链条如何变化。",
            "Proportionality Test": "证明请求与损害、风险、履行成本相称，同时预留维修、折价或部分补偿等次级路径。",
            "Narrative Deconstruction": "把叙事标签还原为可证明事实，让故事服务证据链，不让故事代替证据链。",
            "Systemic Risk Amplification": "承认规则需要边界，但强调本案只处理已证明的具体事实，不无限扩张。",
            "Missing Evidence": "解释缺失材料的合理原因，同时说明现有积极证据为何仍能支撑我方路径。",
        }
        return focuses.get(dimension, "")

    def main_dimension_needed_materials(self, dimension):
        materials = {
            "Fact Challenge": ["原始记录", "形成过程说明", "可核验来源", "材料对应表"],
            "Legal Application": ["法条构成要件表", "本案事实对应表", "适用前提说明", "例外条款排除说明"],
            "Precedent Attack": ["引用案例或规则全文", "相同点/不同点对照表", "争点同构说明"],
            "Logic Gap": ["推理链条图", "替代解释排除表", "因果节点说明"],
            "Procedural Defect": ["通知记录", "送达或提交记录", "关键期限表", "对方回复或确认记录"],
            "Damage Causation": ["损害发生记录", "责任节点说明", "因果链材料", "介入因素排除表"],
            "Quantum Dispute": ["金额明细", "计算口径", "损失范围说明", "替代补救方案"],
            "Burden of Proof": ["证明对象列表", "证明责任分配表", "已提交证据清单", "对方反证缺口"],
            "Legal Text Interpretation": ["交易当时条款版本", "条款上下文", "提示或接受记录"],
            "Comparative Fault": ["双方控制能力说明", "注意义务节点表", "风险分担材料"],
            "Public Policy": ["规则边界说明", "行业惯例材料", "公共利益影响说明"],
            "Reverse Thinking": ["主备证据链", "去除该点后的支撑表", "风险开关表", "本Jurisdiction强制规则清单", "比较法/平台规则边界"],
            "跨Jurisdiction武器": ["本Jurisdiction规则依据", "外Jurisdiction材料全文", "比较法适用边界", "监管/平台规则适用范围"],
            "Counterfactual Reasoning": ["反事实条件表", "结果变化说明", "替代原因材料"],
            "Proportionality Test": ["请求范围说明", "救济比例说明", "替代方案清单"],
            "Narrative Deconstruction": ["事实标签对照表", "证据支撑清单", "叙事顺序时间线"],
            "Systemic Risk Amplification": ["规则外溢边界", "系统风险依据", "个案限制条件"],
            "Missing Evidence": ["未提交原因说明", "现有积极证据清单", "补交或调取路径"],
        }
        return materials.get(dimension, [])

    def run_weakness_scan(self):
        if self.running:
            self._run_standard_weakness_scan()
            return
        from Nido_Advanced_18D_Review_EN import show_scan_mode_dialog

        show_scan_mode_dialog(
            self.root,
            self._run_standard_weakness_scan,
            self._open_advanced_18d_review,
        )

    def _open_advanced_18d_review(self):
        from Nido_Advanced_18D_Review_EN import open_advanced_review

        mode = self.confidential_var.get()
        all_verified_routes = self.verified_provider_snapshots()
        routes = self.verified_private_provider_snapshots() if mode == "Local-only confidentiality" else all_verified_routes
        if not routes:
            if mode == "Local-only confidentiality":
                self.show_local_model_required_dialog(
                    public_model_detected=bool(all_verified_routes),
                    on_redacted_continue=self._open_advanced_18d_review,
                )
                self.set_weakness_run_status("Local or private model connection required")
            else:
                messagebox.showwarning(
                    "Verified Model Required",
                    "Verify at least one model provider before starting Advanced 18-Dimension Review.",
                    parent=self.root,
                )
                self.set_weakness_run_status("Verified model connection required")
            return
        case_text = self.get_text(self.t_bg)
        if mode == "External aid after redaction" and case_text:
            case_text = self._redact_external_matter(case_text)
            privacy_label = "External aid after redaction is active; the prepared redacted matter will be used for all 18 calls."
        elif mode == "Local-only confidentiality":
            privacy_label = "Local-only mode permits only verified local or private-model routes for this review."
        else:
            privacy_label = "Authorized original-text assistance is active. Confirm that all 18 transmissions are permitted."
        open_advanced_review(
            self.root,
            case_text,
            routes,
            self.case_name_var.get().strip() or "Current Matter",
            privacy_label,
        )

    def _run_standard_weakness_scan(self):
        if self.running:
            self.stop_weakness_scan()
            return
        private_routes = self.verified_private_provider_snapshots()
        verified_routes = self.verified_provider_snapshots()
        local_only = self.confidential_var.get() == "Local-only confidentiality"
        if (local_only and not private_routes) or (not local_only and not verified_routes):
            self.show_local_model_required_dialog(public_model_detected=bool(local_only and verified_routes))
            self.set_weakness_run_status("Local or private model connection required")
            return
        selected = self.selected_dimensions()
        if not selected:
            messagebox.showwarning("No Dimension Selected", "Please select at least one opposition dimension.")
            return
        if not self.get_text(self.t_bg):
            messagebox.showwarning("Missing Case Background", "Please enter or import the case background.")
            return
        if not self.ensure_real_case_external_privacy_gate("Weakness Scan"):
            return
        self.weakness_cancel_event.clear()
        self.running = True
        self.set_standard_weakness_progress(3, show=True)
        self.schedule_standard_weakness_progress_tick()
        self.set_weakness_scan_controls_locked(True)
        self.scan_btn.config(
            text="Analysis Running",
            bg="#374151",
            activebackground="#374151",
            state=tk.DISABLED,
        )
        self.weakness_run_status_var.set("Starting whole-case review...")
        self.status_var.set("Status: scanning weaknesses locally...")
        threading.Thread(target=self._run_weakness_scan_thread, args=(selected,), daemon=True).start()

    def show_local_model_required_dialog(self, public_model_detected=False, on_redacted_continue=None):
        if public_model_detected:
            self.set_confidentiality_alert(True)
        win = tk.Toplevel(self.root)
        win.title("Secure Model Connection Required")
        win.configure(bg="#111827")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        width, height = 660, 390
        self.root.update_idletasks()
        x = self.root.winfo_rootx() + max(20, (self.root.winfo_width() - width) // 2)
        y = self.root.winfo_rooty() + max(20, (self.root.winfo_height() - height) // 2)
        win.geometry(f"{width}x{height}+{x}+{y}")

        header = tk.Frame(win, bg="#172033", padx=28, pady=22)
        header.pack(fill=tk.X)
        tk.Label(
            header, text="SECURE LOCAL ANALYSIS", bg="#172033", fg="#d5aa52",
            font=("Helvetica", 9, "bold"), anchor="w",
        ).pack(fill=tk.X)
        tk.Label(
            header,
            text=(
                "Public model detected - Local-only mode is active"
                if public_model_detected else
                "A verified private model is required"
            ),
            bg="#172033", fg="#f4f7fb",
            font=("Helvetica", 18, "bold"), anchor="w",
        ).pack(fill=tk.X, pady=(7, 0))

        body = tk.Frame(win, bg="#111827", padx=28, pady=20)
        body.pack(fill=tk.BOTH, expand=True)
        tk.Label(
            body,
            text=(
                "The connected public model was recognized, but Local-only confidentiality prevents the real matter "
                "from being sent to that endpoint. Connect a private model, or explicitly switch to redacted external assistance."
                if public_model_detected else
                "Offline Weakness Scan reviews the complete matter. To preserve the confidentiality boundary, "
                "the scan starts only after a local or private law-firm model has been verified."
            ),
            bg="#111827", fg="#dbe7f5", font=("Helvetica", 11),
            justify=tk.LEFT, anchor="w", wraplength=590,
        ).pack(fill=tk.X)

        boundary = tk.Frame(body, bg="#182235", highlightthickness=1, highlightbackground="#334155", padx=16, pady=13)
        boundary.pack(fill=tk.X, pady=(17, 10))
        tk.Label(
            boundary, text="Accepted secure connections", bg="#182235", fg="#72d6cb",
            font=("Helvetica", 10, "bold"), anchor="w",
        ).pack(fill=tk.X)
        tk.Label(
            boundary,
            text="Localhost model  |  Private-network endpoint  |  Approved internal law-firm model",
            bg="#182235", fg="#c9d5e5", font=("Helvetica", 10), anchor="w",
        ).pack(fill=tk.X, pady=(5, 0))

        tk.Label(
            body,
            text="LOCAL MODE REQUIRES A VERIFIED LOCAL OR PRIVATE MODEL CONNECTION.",
            bg="#111827", fg="#ff5c73", font=("Helvetica", 9, "bold"), anchor="w",
        ).pack(fill=tk.X, pady=(2, 0))

        controls = tk.Frame(win, bg="#0d1422", padx=28, pady=16)
        controls.pack(fill=tk.X)

        def review_settings():
            win.destroy()
            try:
                self.canvas.yview_moveto(0)
                self.root.lift()
                self.root.focus_force()
            except (tk.TclError, AttributeError):
                pass

        def use_redacted_mode():
            self.confidential_var.set("External aid after redaction")
            self.set_confidentiality_alert(False)
            win.destroy()
            self.status_var.set("Status: redacted external assistance selected")
            self.root.lift()
            self.root.focus_force()
            if callable(on_redacted_continue):
                # Resume the action the user already selected after the privacy
                # boundary changes; the resumed action rechecks providers and
                # prepares the redacted matter before opening its window.
                self.root.after(80, on_redacted_continue)

        def use_local_mode():
            self.confidential_var.set("Local-only confidentiality")
            self.set_confidentiality_alert(False)
            win.destroy()
            self.set_weakness_run_status(
                "Local-only selected: add and verify a local or private model"
            )
            try:
                self.canvas.yview_moveto(0)
                self.root.lift()
                self.root.focus_force()
            except (tk.TclError, AttributeError):
                pass

        if public_model_detected:
            tk.Button(
                controls, text="Use Redacted External Mode", command=use_redacted_mode,
                bg="#14635b", activebackground="#19756b", fg="white",
                activeforeground="white", relief="flat", padx=20, pady=9,
                font=("Helvetica", 10, "bold"),
            ).pack(side=tk.RIGHT)

        tk.Button(
            controls, text="Review Model Settings", command=review_settings,
            bg="#315c8c", activebackground="#3b6fa8", fg="white",
            activeforeground="white", relief="flat", padx=20, pady=9,
            font=("Helvetica", 10, "bold"),
        ).pack(side=tk.RIGHT, padx=(0, 10) if public_model_detected else 0)
        tk.Button(
            controls, text="Use Local Model", command=use_local_mode,
            bg="#9f2f3f", activebackground="#7f1d2d", fg="white",
            activeforeground="white", relief="flat", padx=18, pady=9,
            font=("Helvetica", 10, "bold"),
        ).pack(side=tk.RIGHT, padx=(0, 10))

    def set_confidentiality_alert(self, active):
        try:
            style = ttk.Style(self.root)
            if active:
                style.configure(
                    "PrivacyAlert.TCombobox",
                    foreground="#ff7185", fieldbackground="#3a1720",
                    bordercolor="#ff4d67", lightcolor="#ff4d67", darkcolor="#ff4d67",
                )
                style.map(
                    "PrivacyAlert.TCombobox",
                    foreground=[("readonly", "#ff7185")],
                    fieldbackground=[("readonly", "#3a1720")],
                    selectbackground=[("readonly", "#3a1720")],
                    selectforeground=[("readonly", "#ff7185")],
                )
                self.confidential_combo.configure(style="PrivacyAlert.TCombobox")
                self.confidentiality_alert_frame.configure(
                    bg="#ff4d67", highlightthickness=2, highlightbackground="#ff4d67",
                )
                self.confidentiality_label.configure(fg="#ff7185", font=("Helvetica", 9, "bold"))
            else:
                self.confidential_combo.configure(style="TCombobox")
                self.confidentiality_alert_frame.configure(
                    bg=self.C["panel"], highlightthickness=0,
                )
                self.confidentiality_label.configure(fg=self.C["muted"], font=("Helvetica", 9, "normal"))
        except (tk.TclError, AttributeError):
            pass

    def on_confidentiality_mode_changed(self, *_):
        self.refresh_cloud_panel()
        if self.confidential_var.get() != "Local-only confidentiality":
            self.set_confidentiality_alert(False)

    def stop_weakness_scan(self):
        if not self.running:
            return
        self.weakness_cancel_event.set()
        self.scan_btn.config(text="Stopping...", bg="#6f1d2b", state=tk.DISABLED)
        self.set_weakness_run_status("Cancellation requested; waiting for the active operation to return...")

    def reset_weakness_scan_button(self):
        self.weakness_progress.stop()
        self.set_weakness_scan_controls_locked(False)
        self.scan_btn.config(
            text="1 Scan Weaknesses",
            bg="#1a4a42",
            activebackground="#1a4a42",
            state=tk.NORMAL,
        )

    def set_weakness_scan_controls_locked(self, locked):
        def descendants(widget):
            found = []
            for child in widget.winfo_children():
                if isinstance(child, tk.Toplevel):
                    continue
                found.append(child)
                found.extend(descendants(child))
            return found

        progress_frame = getattr(self, "standard_weakness_progress_frame", None)
        progress_widgets = set()
        if progress_frame is not None:
            progress_widgets.add(progress_frame)
            progress_widgets.update(descendants(progress_frame))
        widgets = [
            widget for widget in dict.fromkeys(descendants(self.root))
            if widget not in progress_widgets
        ]
        muted = "#667085"

        if locked:
            self.weakness_widget_states = {}
            for widget in widgets:
                saved = {}
                for option in ("state", "foreground", "disabledforeground", "insertbackground"):
                    try:
                        saved[option] = widget.cget(option)
                    except (tk.TclError, AttributeError):
                        pass
                if not saved:
                    continue
                self.weakness_widget_states[widget] = saved
                try:
                    if "foreground" in saved:
                        widget.config(foreground=muted)
                except tk.TclError:
                    pass
                try:
                    if "disabledforeground" in saved:
                        widget.config(disabledforeground=muted)
                except tk.TclError:
                    pass
                try:
                    if "state" in saved:
                        widget.config(state=tk.DISABLED)
                except tk.TclError:
                    pass
            try:
                self.root.config(cursor="watch")
            except tk.TclError:
                pass
            return

        for widget, saved in reversed(list(self.weakness_widget_states.items())):
            try:
                if widget.winfo_exists():
                    for option in ("foreground", "disabledforeground", "insertbackground"):
                        if option in saved:
                            try:
                                widget.config(**{option: saved[option]})
                            except tk.TclError:
                                pass
                    if "state" in saved:
                        widget.config(state=saved["state"])
            except (tk.TclError, AttributeError):
                continue
        self.weakness_widget_states = {}
        try:
            self.root.config(cursor="")
        except tk.TclError:
            pass

    def set_standard_weakness_progress(self, value=None, label=None, show=False):
        frame = getattr(self, "standard_weakness_progress_frame", None)
        if frame is None:
            return
        if show and not frame.winfo_manager():
            frame.pack(side=tk.RIGHT, padx=(12, 14))
        if value is not None:
            value = max(0.0, min(100.0, float(value)))
            if not show:
                value = max(value, float(self.standard_weakness_progress_var.get()))
            self.standard_weakness_progress_var.set(value)
            if label is None:
                label = f"{int(round(value))}%"
        if label is not None:
            self.standard_weakness_progress_text_var.set(str(label))
        try:
            frame.update_idletasks()
        except tk.TclError:
            pass

    def schedule_standard_weakness_progress_tick(self):
        """Keep the visible estimate moving while a provider call is opaque."""
        if not self.running:
            return
        current = float(self.standard_weakness_progress_var.get())
        if current < 80:
            # Model providers do not expose token-by-token completion. Creep
            # toward an 80% ceiling, then wait for the actual call to return.
            estimate = min(80.0, current + max(0.35, (80.0 - current) * 0.025))
            self.set_standard_weakness_progress(estimate)
        self.root.after(1200, self.schedule_standard_weakness_progress_tick)

    def set_weakness_run_status(self, text):
        self.weakness_run_status_var.set(str(text))
        self.status_var.set(f"Status: {text}")

    def use_external_whole_case_weakness_scan(self):
        if self.confidential_var.get() == "Local-only confidentiality":
            private_routes = self.verified_private_provider_snapshots()
            if private_routes:
                self.activate_provider_snapshot(private_routes[0])
                return True
            return False
        return (
            self.confidential_var.get() in ("External aid after redaction", "Authorized cloud expert")
            and self.has_verified_external_provider()
            and self.ensure_active_verified_provider()
        )

    def whole_case_dimension_prompt(self, dimensions):
        case_text = self.get_text(self.t_bg)
        dimension_names = [self.ui_en_text(name) or str(name) for name in dimensions]
        return f'''The text below is the original complete case supplied by the user. Read it directly and understand the ENTIRE case before analysing it. Do not use a pre-built case structure, extracted argument list, evidence classification, sentence-by-sentence split, or internal software labels.

Act as independent legal weakness reviewers, one for each listed dimension.

Language requirement: output every value in English only, even when the original case is written in Chinese or another language. Transliterate party names when necessary. Do not return Chinese explanations or Chinese headings.

For each dimension:
- independently identify zero or more genuinely material weaknesses by considering relationships across the whole case;
- return no finding if that dimension does not reveal a useful weakness;
- do not produce generic legal advice or merely restate the dimension;
- identify the concrete case facts and explain the weakness in natural plain language;
- diagnose only: do not provide lawyer questions, attack scripts, strategy, recommendations, cures, response language, preparation steps, or everyday examples;
- do not say a claim is false merely because the source document is not shown;
- do not invent facts, dates, amounts, documents, clauses, approvals, promises, precedents, or legal authorities;
- do not use internal labels such as Evidence angle, Mapping-back, Frame, Cross-Boundary, or Argument 1 as content.

Dimensions for this batch:
{json.dumps(dimension_names, ensure_ascii=False)}

Original complete case text:
{case_text}

Return strict JSON only:
{{
  "case_overview": "short whole-case understanding",
  "dimensions": [
    {{
      "dimension": "one dimension from this batch",
      "findings": [
        {{
          "conclusion": "short plain-language conclusion suitable for a surface card",
          "analysis": "natural connected explanation of the weakness, its factual basis, significance, and limits from this dimension's perspective",
          "relevant_facts": "specific facts from this case",
          "affected_side": "positive, negative, or both",
          "confidence": "high, medium, or low"
        }}
      ]
    }}
  ]
}}'''

    def whole_case_model_candidate(self, finding, dimension, side, index, provider_name=""):
        conclusion = self.ui_en_text(finding.get("conclusion") or finding.get("one_sentence_summary") or "")
        facts = self.ui_en_text(finding.get("relevant_facts") or "")
        explanation = self.ui_en_text(
            finding.get("analysis") or finding.get("full_analysis")
            or finding.get("plain_explanation") or finding.get("core_problem")
            or finding.get("source_explanation") or conclusion
        )
        full_card = {
            "full_analysis": explanation,
            "analysis": explanation,
            "plain_explanation": explanation,
            "core_problem": explanation,
            "what_it_proves": "",
            "what_it_does_not_prove": "",
            "simple_example": "",
            "attack_questions": [],
            "defence_preparation": [],
            "source_explanation": "",
            "one_sentence_summary": conclusion,
        }
        guide = {
            "name": conclusion or f"{dimension} weakness",
            "one_sentence_summary": full_card["one_sentence_summary"] or explanation,
            "summary": explanation,
            "core_problem": full_card["core_problem"],
            "target": facts or conclusion,
            "target_claim_or_element": facts or conclusion,
            "missing_evidence_or_step": [],
            "attack_script": [],
            "defense": "",
            "signal_of_success": "",
            "severity": {"high": "High", "medium": "Medium", "low": "Low"}.get(str(finding.get("confidence", "medium")).lower(), "Medium"),
            "source": f"Whole-case {dimension} review" + (f" by {provider_name}" if provider_name else ""),
            "reason": explanation,
            "tags": dimension,
            "model_full_card": full_card,
        }
        return {
            "id": f"{'P' if side == 'positive' else 'N'}{index:03d}",
            "side": side,
            "dimension": dimension,
            "score": 20,
            "priority_score": 20,
            "risk_tags": [dimension],
            "source_label": f"Whole case / {dimension}" + (f" / {provider_name}" if provider_name else ""),
            "targeting": facts or conclusion,
            "opponent_point_kind": "argument/evidence",
            "opponent_point_index": index,
            "opponent_point": facts or conclusion,
            "weakness": conclusion,
            "weakness_lines": [conclusion, explanation],
            "priority_reason": full_card["source_explanation"],
            "plain_guide": guide,
            "whole_case_model_scan": True,
        }

    def verified_provider_snapshots(self):
        snapshots = []
        for row in getattr(self, "cloud_api_rows", []):
            try:
                if not (row["verified"].get() and row["key"].get().strip()):
                    continue
                snapshots.append({
                    "name": row["name"].get().strip() or "custom",
                    "key": row["key"].get().strip(),
                    "base_url": row["base_url"].get().strip(),
                    "model": row["model"].get().strip(),
                })
            except Exception:
                pass
        current = self.cloud_provider_var.get().strip().lower()
        snapshots.sort(key=lambda item: 0 if item["name"].lower() == current else 1)
        return snapshots

    def whole_case_result_is_english(self, result):
        text = json.dumps(result, ensure_ascii=False) if isinstance(result, (dict, list)) else str(result or "")
        cjk_count = len(re.findall(r"[\u3400-\u9fff]", text))
        latin_count = len(re.findall(r"[A-Za-z]", text))
        return cjk_count <= max(6, int(latin_count * 0.08))

    def whole_case_material_finding_count(self, result):
        if not isinstance(result, dict):
            return 0
        count = 0
        for dimension in result.get("dimensions") or []:
            if not isinstance(dimension, dict):
                continue
            for finding in dimension.get("findings") or []:
                if not isinstance(finding, dict):
                    continue
                substance = finding.get("conclusion") or finding.get("one_sentence_summary") or finding.get("core_problem")
                if str(substance or "").strip():
                    count += 1
        return count

    def activate_provider_snapshot(self, snapshot):
        self.cloud_provider_var.set(snapshot["name"])
        self.cloud_api_key_var.set(snapshot["key"])
        self.cloud_base_url_var.set(snapshot["base_url"])
        self.cloud_model_var.set(snapshot["model"])

    def run_external_whole_case_weakness_scan(self, selected):
        # Main-patent application: one legal case is the target and selected
        # opposition dimensions are task units. Keep all dimensions in one
        # structured call so case context is shared once and every result maps
        # back to its dimension result slot.
        provider_routes = (
            self.verified_private_provider_snapshots()
            if self.confidential_var.get() == "Local-only confidentiality"
            else self.verified_provider_snapshots()
        )
        if not provider_routes:
            raise RuntimeError("No verified model provider is available for whole-case review.")
        merged_dimensions = []
        pending_batches = [list(selected)]
        completed_calls = 0
        total_dimensions = max(1, len(selected))
        completed_dimensions = 0
        self.root.after(0, lambda: self.set_standard_weakness_progress(10))

        def is_capacity_error(error_text):
            lowered = error_text.lower()
            if "429" in lowered or "resource_exhausted" in lowered or "too many requests" in lowered:
                return False
            return any(marker in lowered for marker in (
                "malformed json", "parse error", "jsondecode", "unterminated",
                "truncated", "output token", "max token", "413", "504",
                "deadline", "timed out", "timeout", "response too large",
            ))

        while pending_batches:
            batch = pending_batches.pop(0)
            call_no = completed_calls + 1
            planned_total = completed_calls + 1 + len(pending_batches)
            active_progress = 10 + (70 * (completed_dimensions + (0.15 * len(batch))) / total_dimensions)
            self.root.after(0, lambda value=min(80, active_progress): self.set_standard_weakness_progress(value))
            self.root.after(0, lambda n=call_no, total=planned_total: self.set_weakness_run_status(f"Structured whole-case call {n}/{total}..."))
            last_error = None
            batch_successes = 0
            for route in provider_routes:
                self.activate_provider_snapshot(route)
                route_name = route["name"].strip().lower()
                try:
                    self.root.after(0, lambda name=route["name"], n=call_no, total=planned_total, count=len(batch): self.set_weakness_run_status(f"{name}: one case, {count} dimensions, call {n}/{total}..."))
                    result = self.call_cloud_json(
                        self.whole_case_dimension_prompt(batch),
                        max_tokens=6000 if route_name == "gemini" else 8000,
                    )
                    if not self.whole_case_result_is_english(result):
                        raise RuntimeError(
                            "the model returned predominantly non-English whole-case findings; trying the next verified model"
                        )
                    if self.whole_case_material_finding_count(result) == 0:
                        raise RuntimeError(
                            "the model returned no material whole-case findings; trying the next verified model"
                        )
                    for dimension_result in result.get("dimensions") or []:
                        if isinstance(dimension_result, dict):
                            dimension_result = dict(dimension_result)
                            dimension_result["_provider_name"] = route["name"]
                            merged_dimensions.append(dimension_result)
                    batch_successes += 1
                    last_error = None
                except Exception as exc:
                    last_error = RuntimeError(f"{route['name']}: {exc}")
                    self.root.after(0, lambda name=route["name"]: self.set_weakness_run_status(f"{name} unavailable; trying the next verified model..."))
            if batch_successes:
                completed_calls += 1
                completed_dimensions += len(batch)
                completed_progress = 10 + (72 * completed_dimensions / total_dimensions)
                self.root.after(0, lambda value=min(82, completed_progress): self.set_standard_weakness_progress(value))
                continue
            if last_error is not None and is_capacity_error(str(last_error)) and len(batch) > 1:
                midpoint = (len(batch) + 1) // 2
                pending_batches = [batch[:midpoint], batch[midpoint:]] + pending_batches
                self.root.after(0, lambda count=len(batch): self.set_weakness_run_status(f"Output capacity reached; splitting {count} dimensions into smaller structured calls..."))
                continue
            raise RuntimeError(f"Structured whole-case call failed: {last_error}")

        self.root.after(0, lambda: self.set_standard_weakness_progress(88))
        positive_items = []
        negative_items = []
        for dim_item in merged_dimensions:
            dimension = self.ui_en_text(dim_item.get("dimension") or "Whole-case review")
            provider_name = self.ui_en_text(dim_item.get("_provider_name") or "")
            for finding in dim_item.get("findings") or []:
                affected = str(finding.get("affected_side") or "both").strip().lower()
                if affected not in ("positive", "negative", "both"):
                    affected = "both"
                if affected in ("positive", "both"):
                    positive_items.append(self.whole_case_model_candidate(finding, dimension, "positive", len(positive_items) + 1, provider_name))
                if affected in ("negative", "both"):
                    negative_items.append(self.whole_case_model_candidate(finding, dimension, "negative", len(negative_items) + 1, provider_name))
        if not positive_items and not negative_items:
            raise RuntimeError("The model completed the whole-case review but returned no material weaknesses.")
        for idx, item in enumerate(positive_items, 1):
            item["display_id"] = str(idx)
            item["select_id"] = f"P{idx}"
        for idx, item in enumerate(negative_items, 1):
            item["display_id"] = str(idx)
            item["select_id"] = f"N{idx}"
        self.root.after(0, lambda: self.set_standard_weakness_progress(93))
        base_state = {"opponent_point_counts": {"arguments": 0, "evidence": 0}}
        return {
            "run_id": _dt.datetime.now().strftime("whole_case_18d_%Y%m%d_%H%M%S"),
            "case_key": short_hash(self.get_text(self.t_bg)),
            "positive_state": dict(base_state),
            "negative_state": dict(base_state),
            "positive_weaknesses": positive_items,
            "negative_weaknesses": negative_items,
            "weakness_candidates": positive_items + negative_items,
            "selected_dimensions": selected,
            "workflow_mode": "external_whole_case_dimension_scan",
        }

    def _run_weakness_scan_thread(self, selected):
        try:
            if self.weakness_cancel_event.is_set():
                return
            if self.use_external_whole_case_weakness_scan():
                try:
                    panel_state = self.run_external_whole_case_weakness_scan(selected)
                    if self.weakness_cancel_event.is_set():
                        return
                    self.last_weakness_state = panel_state
                    self.weakness_candidates = panel_state["weakness_candidates"]
                    self.root.after(0, lambda: self.set_standard_weakness_progress(96))
                    self.save_weakness_scan_artifacts(panel_state)
                    self.root.after(0, lambda: self.open_weakness_scan_window(panel_state))
                    self.root.after(0, lambda: self.set_weakness_run_status("Whole-case review complete"))
                    self.root.after(0, lambda: self.set_standard_weakness_progress(100))
                    return
                except Exception as external_exc:
                    self.log(f"All verified external providers were unavailable: {external_exc}")
                    raise RuntimeError(
                        "All verified model providers were unavailable. The software did not substitute a local structured scan, "
                        f"because this workflow requires direct whole-case model review. Last error: {external_exc}"
                    )
            self.log("Starting local Weakness Scan: scanning positive-side and negative-side weaknesses separately.")
            self.root.after(0, lambda: self.set_standard_weakness_progress(10))
            self.root.after(0, lambda: self.set_weakness_run_status("Step 1/2: reviewing the positive-side position locally..."))
            pos_state = self.run_nido_local_state(selected, workflow_mode="weakness_scan_positive", target_side="positive")
            if self.weakness_cancel_event.is_set():
                return
            self.root.after(0, lambda: self.set_standard_weakness_progress(48))
            self.root.after(0, lambda: self.set_weakness_run_status("Step 2/2: reviewing the negative-side position locally..."))
            neg_state = self.run_nido_local_state(selected, workflow_mode="weakness_scan_negative", target_side="negative")
            if self.weakness_cancel_event.is_set():
                return
            self.root.after(0, lambda: self.set_standard_weakness_progress(86))
            pos_candidates = self.build_whole_case_local_candidates(pos_state, selected, target_side="positive", id_prefix="P")
            neg_candidates = self.build_whole_case_local_candidates(neg_state, selected, target_side="negative", id_prefix="N")
            pos_state["weakness_candidates"] = pos_candidates
            neg_state["weakness_candidates"] = neg_candidates
            for display_idx, item in enumerate(pos_candidates, 1):
                item["display_id"] = str(display_idx)
                item["select_id"] = f"P{display_idx}"
            for display_idx, item in enumerate(neg_candidates, 1):
                item["display_id"] = str(display_idx)
                item["select_id"] = f"N{display_idx}"
            all_candidates = pos_candidates + neg_candidates
            panel_state = {
                "run_id": pos_state.get("run_id"),
                "case_key": pos_state.get("case_key"),
                "positive_state": pos_state,
                "negative_state": neg_state,
                "positive_weaknesses": pos_candidates,
                "negative_weaknesses": neg_candidates,
                "weakness_candidates": all_candidates,
                "selected_dimensions": pos_state.get("selected_dimensions", []),
                "workflow_mode": "local_two_step_perspective_scan",
            }
            self.last_weakness_state = panel_state
            self.weakness_candidates = panel_state["weakness_candidates"]
            self.last_state = neg_state
            self.root.after(0, lambda: self.set_standard_weakness_progress(95))
            self.save_weakness_scan_artifacts(panel_state)
            self.root.after(0, lambda: self.open_weakness_scan_window(panel_state))
            self.root.after(0, lambda: self.set_weakness_run_status("Local weakness scan complete"))
            self.root.after(0, lambda: self.set_standard_weakness_progress(100))
        except Exception as exc:
            if self.weakness_cancel_event.is_set():
                self.root.after(0, lambda: self.set_weakness_run_status("Weakness scan cancelled"))
                self.root.after(0, lambda: self.set_standard_weakness_progress(label="Cancelled"))
            else:
                self.root.after(0, lambda: messagebox.showerror("Weakness Scan Failed", str(exc)))
                self.root.after(0, lambda: self.set_weakness_run_status("Weakness scan failed"))
                self.root.after(0, lambda: self.set_standard_weakness_progress(label="Failed"))
        finally:
            self.running = False
            self.root.after(0, self.reset_weakness_scan_button)

    def weakness_score(self, item, rebuttal=None):
        text = "\n".join(str(x or "") for x in [
            item.get("targeting"),
            item.get("finding"),
            item.get("question"),
            item.get("attack"),
            (rebuttal or {}).get("response"),
            "；".join(str(x) for x in ((rebuttal or {}).get("needed_material") or [])),
        ])
        concrete = sum(text.count(x) for x in ["原件", "时间戳", "连续", "封条", "质检", "物流", "签收", "页面", "下单", "明细", "因果", "视频"])
        pressure = sum(text.count(x) for x in ["证明", "排除", "要求", "追", "压", "不能", "必须", "逐项", "缺失", "门槛"])
        questions = text.count("？") + text.count("?")
        return concrete * 3 + pressure * 3 + questions

    def split_argument_points(self, text):
        points = []
        for raw in (text or "").splitlines():
            line = re.sub(r"\s+", " ", raw.strip())
            if not line:
                continue
            line = re.sub(r"^(?:\[\w+\]|\d+[.、)]|[（(]?\d+[）)]|[A-Z]\d+[.、:]?)\s*", "", line).strip()
            if line:
                points.append(line)
        if not points and text:
            points = [self.compact(text, 180)]
        return points

    def numbered_points(self, text, kind):
        return [
            {"kind": kind, "index": idx, "text": point}
            for idx, point in enumerate(self.split_argument_points(text), 1)
        ]

    def is_internal_strategy_point(self, text):
        low = re.sub(r"\s+", " ", str(text or "").strip().lower())
        markers = [
            "case can argue that",
            "summary can attack",
            "evidence angle:",
            "contract angle:",
            "consumer angle:",
            "tort angle:",
            "break the opponent's conclusion back into legal elements",
            "should be connected into a complete proof chain",
            "should be treated as the main support",
            "should be converted into defence paths",
            "communications, contract, advertisement, payment, delivery, notice, inspection, or scene records",
            "original materials proving the claimant's conduct",
            "rules for the relevant jurisdiction, problem prompt, or assigned legal principles",
            "missing originals, timestamps, third-party records, or complete context",
            "materials showing an alternative cause, late notice",
            "restrictive interpretation materials for key terms",
        ]
        return any(marker in low for marker in markers)

    def real_case_points_for_weakness(self):
        text = self.get_text(self.t_bg)
        text = re.sub(r"^\s*\[(?:Imported file|Read mode)[^\]]*\].*$", "", text, flags=re.MULTILINE | re.IGNORECASE)
        raw_parts = re.split(r"(?<=[.!?])\s+|\n+", text)
        points = []
        skip_markers = [
            "case summary:", "facts of the case", "legal issue", "analysis", "conclusion",
            "this is a hypothetical", "the following", "please advise", "you are a",
        ]
        factual_markers = [
            "agreed", "said", "sent", "paid", "sold", "bought", "requested", "refused",
            "delivered", "signed", "changed", "claimed", "invoiced", "received", "completed",
            "contract", "email", "message", "sms", "invoice", "payment", "report", "notice",
            "owner", "builder", "plaintiff", "defendant", "claimant", "respondent",
            "$", "aud", "usd", "202", "20",
        ]
        action_markers = [
            "agreed", "said", "sent", "paid", "sold", "bought", "requested", "refused",
            "delivered", "signed", "changed", "claimed", "invoiced", "received", "completed",
            "entered into", "carried out", "intervened", "advised",
        ]
        for raw in raw_parts:
            point = re.sub(r"^\s*(?:#+|[-*]\s+|\d+[.)]\s+)", "", raw.strip())
            point = re.sub(r"\s+", " ", point).strip()
            low = point.lower()
            if len(point) < 28 or len(point) > 520:
                continue
            if self.is_internal_strategy_point(point) or any(marker in low for marker in skip_markers):
                continue
            if ("hypothetical" in low or "dispute over" in low) and not any(marker in low for marker in action_markers):
                continue
            if not any(marker in low for marker in factual_markers):
                continue
            if point not in points:
                points.append(point)
            if len(points) >= 16:
                break
        return points

    def real_case_evidence_points_for_weakness(self):
        evidence_markers = [
            "contract", "agreement", "clause", "email", "message", "sms", "text", "invoice",
            "receipt", "payment", "bank", "photo", "video", "report", "notice", "record",
            "document", "screenshot", "inspection", "delivery", "signature", "signed",
        ]
        return [
            point for point in self.real_case_points_for_weakness()
            if any(marker in point.lower() for marker in evidence_markers)
        ][:10]

    def best_opponent_point_for_attack(self, item, opponent_points):
        if not opponent_points:
            return {"kind": "对方论点/证据", "index": 1, "text": item.get("targeting") or item.get("target") or "对方论点/证据"}
        attack_text = " ".join(str(item.get(k, "")) for k in ("targeting", "finding", "question", "attack")).lower()
        best_score = -1
        best_point = opponent_points[0]
        for point in opponent_points:
            tokens = set(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}", point["text"].lower()))
            score = sum(1 for token in tokens if token in attack_text)
            if score > best_score:
                best_score = score
                best_point = point
        return best_point

    def clean_weakness_scan_text(self, text):
        text = str(text or "")
        replacements = {
            "我方核心立场、证据链或说明文字": "对方该条论点/证据",
            "我方核心立场": "对方该条论点",
            "我方立场": "对方论点",
            "我方证据链": "对方证据链",
            "我方": "对方",
            "你方": "对方",
            "对方可以抓住": "可以抓住",
            "要求补齐": "无法直接证明",
            "补齐": "说明",
            "补证": "证据Weakness",
            "追问方向": "攻击方向",
            "追问": "攻击",
            "适用边界": "适用范围",
            "边界:": "范围:",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        text = text.replace("总立场", "该条论点")
        return text.strip()

    def ui_en_text(self, text):
        text = str(text or "")
        exact = {
            "对每个论点先拆解其前提事实，再追问该事实是否被证据直接支持，无支持即Weakness。": "For each argument, first split out its factual premises, then ask whether each premise is directly supported by evidence. Any unsupported premise becomes a weakness.",
            "对证据链按时间顺序排列，检查中间是否存在缺失环节，缺失即攻击入口。": "Arrange the evidence chain in chronological order and check for missing links. Each missing link becomes an attack entry.",
            "对损害范围反向推演：若无该行为，损害是否仍会发生，是则因果断裂。": "Run a reverse causation test on the claimed loss: if the loss would still occur without the alleged conduct, causation is broken.",
            "对法律要件逐项比对事实，找出要件与事实之间的定义偏差或覆盖缺口。": "Compare each legal element against the facts and identify definitional mismatches or coverage gaps.",
            "对程序节点检查通知送达与代理权限，任何形式瑕疵均可转化为程序攻击。": "For each procedural node, check notice, service, and authority to act. Any formal defect can become a procedural attack.",
            "锁定证明对象后，用‘请对方明确该主张所依赖的具体证据来源’压回举证责任。": "After locking the proof object, ask the opponent to identify the specific evidence source relied on by the assertion, forcing the issue back to burden of proof.",
            "对对方证据先质疑其完整性，再追问缺失部分是否影响结论，形成二段杀伤。": "First challenge the completeness of the opponent's evidence, then ask whether the missing parts affect the conclusion, creating a two-step attack.",
            "用‘如果对方逻辑成立，那么类似情形都应适用同一标准’放大矛盾至公共政策层面。": "Use the question 'if the opponent's logic is correct, should the same standard apply to similar situations' to escalate the contradiction into a public policy issue.",
            "对量化争议先承认数值范围，再追问计算前提是否唯一，迫使对方暴露假设漏洞。": "For quantum disputes, first acknowledge the claimed numerical range, then ask whether the calculation premise is the only possible premise, exposing assumption gaps.",
            "对合同变更主张，追问变更是否有书面确认或对价，无则视为单方主张无效。": "For a contract variation claim, ask whether the variation has written confirmation or consideration. If not, treat it as an ineffective unilateral assertion.",
            "对平台责任，先区分其是主动行为还是被动工具，再据此分配注意义务标准。": "For platform liability, first distinguish active conduct from passive tool status, then allocate the standard of care accordingly.",
            "对替代救济，先问对方是否已穷尽其他途径，未穷尽则损害非不可挽回。": "For alternative relief, first ask whether the opponent has exhausted other routes. If not, the harm is not irreparable.",
            "Weakness Scan规则应先由本地函数独立判断，再用案件细分规则复查遗漏角度，后置规则不得覆盖本地第一判断。": "Weakness Scan should first be judged independently by local functions, then reviewed by case-decomposition rules for missed angles. Later rules must not override the first local judgment.",
            "案件细分规则应在Missing Evidence方向检查Missing Evidence，只记录可迁移的Weakness方法，不记录案件事实。": "In the Missing Evidence dimension, check for missing evidence as a reusable weakness method only; do not store case facts.",
            "语言骨架规则应先由函数提供对象、Weakness、证明责任和风险变量，再由前台骨架填充成律师角色发言。": "The language skeleton should receive the object, weakness, burden of proof, and risk variables from functions, then fill them into party-advocate court language.",
            "对每个论点先拆解其前提事实，再追问该事实是否被证据直接支持，无支持即Weakness...": "For each argument, split out factual premises and ask whether each premise is directly supported by evidence.",
        }
        if text.strip() in exact:
            return exact[text.strip()]
        replacements = {
            "正方": "Positive side",
            "反方": "Negative side",
            "我方核心立场、证据链或说明文字": "the opponent's argument/evidence",
            "我方核心立场": "the opponent's argument",
            "我方立场": "the opponent's position",
            "我方证据链": "the opponent's evidence chain",
            "对方该条论点/证据": "the opponent's argument/evidence",
            "对方该条论点": "the opponent's argument",
            "对方论点": "the opponent's argument",
            "相对方证据反推": "opposing evidence cross-check",
            "论点": "argument",
            "证据": "evidence",
            "可结合相对方证据": "Can cross-check against opposing evidence",
            "该条论点/证据的事实基础、证据来源、规则适用或因果链存在可攻击空间。": "The factual basis, evidence source, rule application, or causal chain leaves an attackable gap.",
            "该论点可能引出隐私、商业秘密、越权调取或不当施压等反向法律风险。": "This point may create reverse legal risk, including privacy, commercial confidentiality, unauthorized access, or improper pressure.",
            "可先压证明责任或证据使用门槛": "Prioritize proof burden or admissibility threshold",
            "可跨界打开侧翼Weakness": "Open a side weakness through cross-boundary rules",
            "可切断因果、程序或金额链条": "Cut causation, procedure, or quantum chain",
            "可作为基础事实/规则Weakness": "Use as a basic fact/rule weakness",
            "过滤通过": "Filter passed",
            "过滤拦截": "Filter blocked",
            "语言修辞": "Language rhetoric",
            "案件细分": "Case decomposition",
            "语言骨架": "Language skeleton",
            "跨Jurisdiction": "Cross-Jurisdiction",
            "跨界": "Cross-Boundary",
            "本地Jurisdiction模板": "Local jurisdiction template",
            "本地规则清单": "Local rule checklist",
            "跨界维度引用边界": "Cross-boundary reference limit",
            "命中": "hits ",
            "覆盖": "covers ",
            "来源": "source",
            "状态": "status",
            "启用": "enabled",
            "停用": "disabled",
            "调用次数": "call count",
            "通过": "approved",
            "标题": "Title",
            "类型": "Type",
            "生成时间": "Created",
            "候选规则": "Candidate rule",
            "说明": "Note",
            "训练命中": "Training hits",
            "覆盖虚构案": "Virtual matters covered",
            "来源类型": "Source type",
            "暂无新增 SOP。": "No new SOP candidates.",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        text = re.sub(r"[\u4e00-\u9fff]+\s*Jurisdiction", "Cross-Jurisdiction", text, flags=re.IGNORECASE)
        text = text.replace("跨界", "Cross-Boundary")
        text = re.sub(r"[\u4e00-\u9fff]+", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def has_cjk_text(self, text):
        return bool(re.search(r"[\u4e00-\u9fff]", str(text or "")))

    def bad_ui_text(self, text):
        text = str(text or "").strip()
        if not text:
            return True
        if self.has_cjk_text(text):
            return True
        if "�" in text or "??" in text:
            return True
        if not re.search(r"[A-Za-z]", text):
            return True
        return False

    def candidate_kind_en(self, candidate):
        kind = self.ui_en_text(candidate.get("opponent_point_kind", ""))
        if self.bad_ui_text(kind):
            raw = str(candidate.get("opponent_point_kind", ""))
            kind = "evidence" if "evidence" in raw.lower() else "argument"
        return kind

    def weakness_source_en(self, candidate):
        kind = self.candidate_kind_en(candidate)
        index = candidate.get("opponent_point_index", "")
        source = self.ui_en_text(candidate.get("source_label", ""))
        if self.bad_ui_text(source) or source.strip(" []/;,:") == "":
            source = f"{kind}{index}"
            if candidate.get("opponent_point"):
                source += " + opposing evidence cross-check"
        return source

    def weakness_reason_en(self, candidate):
        raw = self.ui_en_text(candidate.get("priority_reason", ""))
        if not self.bad_ui_text(raw) and raw.strip(" []/;,:"):
            return raw
        dim = self.ui_en_text(candidate.get("dimension", "")) or "Fact Challenge"
        reason_map = {
            "Fact Challenge": "evidence; test factual premise and source reliability",
            "Legal Application": "legal rule; test every element against the facts",
            "Logic Gap": "logic; expose missing links between premise and conclusion",
            "Procedural Defect": "procedure; check notice, timing, authority, and record path",
            "Damage Causation": "causation; separate liability, cause, and loss",
            "Quantum Dispute": "quantum; require method, particulars, and calculation range",
            "Burden of Proof": "proof burden; force the opponent back to admissible proof",
            "Missing Evidence": "missing evidence; identify absent records or source gaps",
            "Cross-Jurisdiction Weapon": "jurisdiction; use external rules only as boundary checks",
        }
        return reason_map.get(dim, "risk; open a concrete weakness for cross-examination")

    def weakness_text_en(self, candidate):
        parts = []
        for value in candidate.get("weakness_lines", []) or []:
            cleaned = self.ui_en_text(self.clean_weakness_scan_text(value))
            if not self.bad_ui_text(cleaned) and cleaned.strip(" []/;,:"):
                parts.append(cleaned)
        if not parts:
            cleaned = self.ui_en_text(self.clean_weakness_scan_text(candidate.get("weakness", "")))
            if not self.bad_ui_text(cleaned) and cleaned.strip(" []/;,:"):
                parts.append(cleaned)
        if parts:
            return self.compact(" ".join(dict.fromkeys(parts)), 190)
        dim = self.ui_en_text(candidate.get("dimension", "")) or "Fact Challenge"
        target = self.ui_en_text(candidate.get("opponent_point") or candidate.get("targeting", ""))
        target = target if not self.bad_ui_text(target) else "the targeted argument or evidence"
        fallback_map = {
            "Fact Challenge": "This point needs direct factual proof, not an isolated assertion.",
            "Legal Application": "The rule must be matched element-by-element to the facts before the conclusion follows.",
            "Logic Gap": "The inference chain has a visible gap between the stated premise and the requested conclusion.",
            "Procedural Defect": "The proof path should be checked for notice, timing, authority, and record defects.",
            "Damage Causation": "Liability, causation, and loss must be separated; an alternative cause can break the chain.",
            "Quantum Dispute": "The claimed amount needs particulars, method, and a reliable calculation path.",
            "Burden of Proof": "The opponent still carries the burden of proving the factual premise with admissible evidence.",
            "Missing Evidence": "Key source material appears absent, so the probative value should be reduced.",
            "Cross-Jurisdiction Weapon": "External rules cannot replace this jurisdiction's facts, law, and proof threshold.",
        }
        base = fallback_map.get(dim, "This point leaves an attackable gap in proof, rule application, or causation.")
        return f"{base} Target: {self.compact(target, 90)}"

    def weakness_surface_conclusion(self, candidate, guide=None):
        # Build the compact surface card from the completed internal card, not
        # directly from a dimension label. The dimension remains audit metadata.
        guide = guide or self.weakness_plain_guide(candidate)
        if candidate.get("synthetic_freeform_scan"):
            title = self.ui_en_text(
                guide.get("one_sentence_summary")
                or guide.get("name")
                or candidate.get("weakness")
                or "Weakness identified"
            )
            return {
                "title": self.compact(title, 300),
                "reason": "",
                "target": self.ui_en_text(candidate.get("synthetic_source_case") or ""),
                "source": f"Fictional case / {self.ui_en_text(candidate.get('dimension', 'review'))}",
            }
        if candidate.get("whole_case_model_scan"):
            target = self.compact(self.ui_en_text(guide.get("target") or candidate.get("opponent_point") or ""), 185)
            title = self.ui_en_text(guide.get("one_sentence_summary") or guide.get("name") or candidate.get("weakness") or "Whole-case weakness")
            reason = self.ui_en_text(guide.get("core_problem") or guide.get("summary") or "")
            return {
                "title": self.compact(title, 170),
                "reason": self.compact(reason, 300) if reason else "",
                "target": target,
                "source": f"Whole case / {self.ui_en_text(candidate.get('dimension', 'review'))}",
            }
        kind = (self.candidate_kind_en(candidate) or "argument").lower()
        is_evidence = "evidence" in kind
        target = self.ui_en_text(candidate.get("opponent_point") or candidate.get("targeting", ""))
        if self.bad_ui_text(target) or not target.strip(" []/;,:\n"):
            target = guide.get("target") or "the selected point"
        system_target = any(marker in target.lower() for marker in (
            "tactic package", "whole case", "synthetic pattern", "argument/evidence",
        ))
        if system_target:
            target = ""
        target = self.compact(target, 185)
        title_target = self.compact(target, 105)
        low_target = target.lower()
        if any(word in low_target for word in ("renovation contract", "contract", "agreement")):
            title = "The summary indicates that a contract existed, but it does not establish the contract's exact terms or scope"
        elif any(word in low_target for word in ("sms", "message", "email", "text message")):
            title = "This communication shows that something was said, but it may not prove the larger agreement claimed from it"
        elif any(word in low_target for word in ("invoice", "payment", "receipt", "bank transfer")):
            title = "This payment material does not by itself establish the full amount or legal obligation claimed"
        elif is_evidence:
            title = f'This evidence does not fully prove the conclusion drawn from: "{title_target}"'
        else:
            title = ""

        weakness = self.weakness_text_en(candidate)
        guide_summary = guide.get("one_sentence_summary") or guide.get("summary") or ""
        reason = self.remove_repeated_prefix(guide.get("name", ""), guide_summary)
        # Existing full-card summaries commonly use "..., but the record ...".
        # Keep only the explanatory half so the surface card reads as a conclusion.
        match = re.search(r"\bbut\b\s+(.+)$", str(reason), flags=re.IGNORECASE)
        if match:
            reason = match.group(1).strip()
        if self.bad_ui_text(reason) or not str(reason).strip(" []/;,:\n"):
            reason = weakness
        if any(word in low_target for word in ("renovation contract", "contract", "agreement")):
            reason = "The case summary may show that a contract existed, but the signed contract is still needed to check the parties, price, work scope, payment terms, and rules for later changes."
        elif any(word in low_target for word in ("sms", "message", "email", "text message")):
            reason = "The communication proves only what was actually said. It does not automatically prove that price, responsibility, authority, or every consequence was accepted."
        reason = self.compact(reason, 240)
        generic_reason = any(marker in reason.lower() for marker in (
            "the record does not yet close the proof",
            "this point leaves an attackable gap",
            "proof, rule, causation, or remedy path",
        ))
        if system_target and generic_reason:
            reason = "The available material does not provide enough factual or evidentiary support for the conclusion being claimed."
        if reason:
            reason = reason[0].upper() + reason[1:]
        # Surface cards show the substantive conclusion only. Template framing,
        # source labels, severity, and explanatory detail belong in the full card.
        title = reason or weakness or "The selected material does not adequately support the conclusion claimed."
        return {
            "title": self.compact(title, 300),
            "reason": "",
            "target": target,
            "source": f"{self.candidate_kind_en(candidate).title()} {candidate.get('opponent_point_index', '')}".strip(),
        }

    def weakness_case_surface_name(self, dimension, target):
        text = str(target or "")
        low = text.lower()
        rules = [
            (["variation", "novation", "change order"], "Written variation gap"),
            (["email", "message", "sms", "wechat", "text"], "Message proof gap"),
            (["payment", "invoice", "receipt", "bank", "$", "aud", "usd"], "Payment proof gap"),
            (["delivery", "shipment", "logistic", "handover"], "Delivery record gap"),
            (["advertisement", "website", "screenshot", "platform"], "Ad record gap"),
            (["damage", "loss", "causation", "injury"], "Causation proof gap"),
            (["authority", "agent", "signature", "signed"], "Authority proof gap"),
            (["deadline", "notice", "service", "filing"], "Notice timing gap"),
            (["expert", "inspection", "report", "valuation"], "Report foundation gap"),
            (["contract", "agreement", "clause"], "Clause proof gap"),
        ]
        for needles, name in rules:
            if any(n in low for n in needles):
                return name
        dim_map = {
            "Fact Challenge": "Fact proof gap",
            "Legal Application": "Element proof gap",
            "Logic Gap": "Reasoning gap",
            "Procedural Defect": "Procedure proof gap",
            "Damage Causation": "Causation gap",
            "Quantum Dispute": "Amount proof gap",
            "Burden of Proof": "Burden proof gap",
            "Missing Evidence": "Missing record gap",
            "Cross-Jurisdiction Weapon": "Rule entry gap",
        }
        return dim_map.get(dimension, "Proof gap")

    def current_case_marker_hint(self, target):
        target = self.compact(str(target or "").strip(), 180)
        if not target:
            return "the selected factual assertion"
        return target

    def weakness_plain_guide(self, candidate):
        if isinstance(candidate, dict) and isinstance(candidate.get("plain_guide"), dict):
            guide = dict(candidate["plain_guide"])
            guide.setdefault("name", "Synthetic weakness")
            guide.setdefault("one_sentence_summary", guide.get("summary") or self.weakness_text_en(candidate))
            guide.setdefault("target", self.ui_en_text(candidate.get("opponent_point") or candidate.get("targeting", "")) or "Synthetic-side claim")
            guide.setdefault("target_claim_or_element", guide["target"])
            guide.setdefault("mapping_checklist", {})
            guide.setdefault("missing_evidence_or_step", [])
            guide.setdefault("attack_script", [])
            guide.setdefault("signal_of_success", "The other side cannot produce the requested record or gives an uncertain answer.")
            guide.setdefault("severity", "Medium")
            guide.setdefault("source", self.weakness_source_en(candidate))
            guide.setdefault("reason", self.weakness_reason_en(candidate))
            guide.setdefault("tags", "Synthetic analogue, model weakness scan")
            guide.setdefault("attacker", "Negative side" if candidate.get("side") == "positive" else "Positive side")
            guide.setdefault("defender", "Positive side" if candidate.get("side") == "positive" else "Negative side")
            return guide
        dim = self.ui_en_text(candidate.get("dimension", "")) or "Fact Challenge"
        target = self.ui_en_text(candidate.get("opponent_point") or candidate.get("targeting", ""))
        if self.bad_ui_text(target):
            target = ""
        target_short = self.compact(target, 130)
        source = self.weakness_source_en(candidate)
        reason = self.weakness_reason_en(candidate)
        tags = [self.ui_en_text(x) for x in (candidate.get("risk_tags") or [])]
        tags = [x for x in tags if not self.bad_ui_text(x)]

        # Do not manufacture a full card from dimension templates. Local mode
        # may display only case-specific content already present in the scan.
        weakness = self.weakness_text_en(candidate)
        existing_questions = []
        attack_item = candidate.get("attack_item") or {}
        for value in (attack_item.get("question"), candidate.get("question")):
            clean = self.ui_en_text(value)
            if clean and not self.bad_ui_text(clean) and clean != weakness:
                existing_questions.append(clean)
        return {
            "name": self.weakness_case_surface_name(dim, target_short or weakness),
            "one_sentence_summary": weakness,
            "summary": weakness,
            "target": target_short,
            "target_claim_or_element": target_short,
            "mapping_checklist": {},
            "missing_evidence_or_step": [],
            "attack_script": list(dict.fromkeys(existing_questions)),
            "signal_of_success": "",
            "defense": "",
            "severity": self.weakness_severity(candidate, dim),
            "source": source,
            "reason": reason,
            "tags": ", ".join(tags),
            "attacker": "Negative side" if candidate.get("side") == "positive" else "Positive side",
            "defender": "Positive side" if candidate.get("side") == "positive" else "Negative side",
        }

    def weakness_severity(self, candidate, dimension):
        high_dims = {"Damage Causation", "Legal Application", "Burden of Proof", "Missing Evidence", "Quantum Dispute"}
        tags = " ".join(str(x) for x in (candidate.get("risk_tags") or []))
        text = f"{dimension} {tags} {candidate.get('priority_reason', '')}"
        if dimension in high_dims or any(word in text.lower() for word in ["core", "fatal", "burden", "missing evidence", "causation"]):
            return "High"
        if dimension in {"Fact Challenge", "Logic Gap", "Procedural Defect"}:
            return "Medium"
        return "Low"

    def side_label_en(self, side):
        return "Positive side" if side in ("positive", "正方") else "Negative side"

    def weakness_lines_for_scan(self, item, my_evidence_points):
        lines = []
        targeting = self.clean_weakness_scan_text(item.get("targeting") or item.get("target") or "")
        finding = self.clean_weakness_scan_text(item.get("finding") or item.get("attack") or "")
        if finding:
            lines.append(self.compact(finding, 150))
        if targeting and targeting not in finding and "最容易被具体化" not in targeting:
            lines.append(self.compact(targeting, 120))
        if my_evidence_points:
            evidence_line = "；".join(my_evidence_points[:3])
            lines.append(f"可结合相对方证据：{evidence_line}")
        cleaned = []
        for line in lines:
            line = self.clean_weakness_scan_text(line)
            line = re.sub(r"^(攻击对象具体化|Weakness切口|追问方向|材料缺口)[:：]\s*", "", line)
            if line and line not in cleaned:
                cleaned.append(line)
        return cleaned[:3] or ["该条论点/证据的事实基础、证据来源、规则适用或因果链存在可攻击空间。"]

    def target_side_points(self, structured, target_side):
        if target_side == "positive":
            raw_args = self.split_argument_points(structured.get("pos_args", ""))
            raw_evidence = self.split_argument_points(structured.get("pos_ev", ""))
            support = self.split_argument_points(structured.get("neg_ev", ""))
        else:
            raw_args = self.split_argument_points(structured.get("neg_args", ""))
            raw_evidence = self.split_argument_points(structured.get("neg_ev", ""))
            support = self.split_argument_points(structured.get("pos_ev", ""))

        args = [point for point in raw_args if not self.is_internal_strategy_point(point)]
        evidence = [point for point in raw_evidence if not self.is_internal_strategy_point(point)]
        support = [point for point in support if not self.is_internal_strategy_point(point)]

        if not args:
            args = self.real_case_points_for_weakness()
        if not evidence:
            evidence = self.real_case_evidence_points_for_weakness()

        return (
            [{"kind": "argument", "index": idx, "text": point} for idx, point in enumerate(args, 1)],
            [{"kind": "evidence", "index": idx, "text": point} for idx, point in enumerate(evidence, 1)],
            support,
        )

    def weakness_dimension_for_rule(self, rule_name):
        mapping = {
            "原始性": "Fact Challenge",
            "连续性": "Fact Challenge",
            "来源": "Fact Challenge",
            "时间戳": "Procedural Defect",
            "证明对象错位": "Logic Gap",
            "关联性": "Burden of Proof",
            "第三方佐证": "Burden of Proof",
            "矛盾": "Counterfactual Reasoning",
            "前提未证明": "Burden of Proof",
            "法律要件缺口": "Legal Application",
            "因果跳跃": "Logic Gap",
            "时间顺序": "Procedural Defect",
            "主体不清": "Fact Challenge",
            "损失量化": "Damage Causation",
            "规则适用扩大": "Legal Text Interpretation",
            "确定性夸大": "Reverse Thinking",
            "先例同构": "Precedent Attack",
            "补救比例": "Proportionality Test",
            "Public Policy外溢": "Public Policy",
            "系统外溢": "Systemic Risk Amplification",
            "叙事标签": "Narrative Deconstruction",
            "Missing Evidence": "Missing Evidence",
            "跨Jurisdiction适用": "跨Jurisdiction武器",
            "过失分配": "Comparative Fault",
            "量化口径": "Quantum Dispute",
            "取证合法性": "跨Jurisdiction武器",
            "证据可采性": "Procedural Defect",
            "隐私边界": "跨Jurisdiction武器",
            "责任倒置": "Burden of Proof",
        }
        return mapping.get(rule_name, "Fact Challenge")

    def weakness_rule_score(self, text, weakness, kind):
        hay = f"{text}\n{weakness}"
        score = 10
        score += sum(hay.count(x) * 3 for x in ["原件", "时间戳", "连续", "封条", "质检", "物流", "签收", "页面", "下单", "因果", "金额", "律师费"])
        score += sum(hay.count(x) * 2 for x in ["不能", "没有", "缺少", "未证明", "无法", "排除", "对应", "只证明"])
        if kind == "证据":
            score += 3
        return score

    def weakness_tags_for_rule(self, rule_name, dimension, weakness):
        text = f"{rule_name}\n{dimension}\n{weakness}"
        tag_rules = [
            ("取证合法性", ["取证", "录音", "偷拍", "偷录", "监控", "越权", "取得方式"]),
            ("证据可采性", ["可采", "提交程序", "来源链条", "完整性", "证明力", "原始"]),
            ("隐私/商业秘密", ["隐私", "商业秘密", "第三方信息", "后台数据"]),
            ("平台/监管规则", ["平台", "监管", "投诉", "举报", "行业规则"]),
            ("责任倒置", ["证明责任倒置", "Burden of Proof倒置", "谁主张", "谁举证", "排除所有"]),
            ("反向法律责任", ["反向责任", "不当施压", "其他法律风险", "责任风险"]),
            ("跨Jurisdiction", ["跨Jurisdiction", "外Jurisdiction", "比较法", "其他地区", "州", "联邦"]),
            ("因果切断", ["因果", "导致", "原因", "介入因素", "替代原因"]),
            ("量化缺口", ["金额", "费用", "损失", "商誉", "量化", "计算口径"]),
            ("程序节点", ["程序", "期限", "送达", "通知", "提交", "时间顺序"]),
        ]
        tags = []
        for tag, needles in tag_rules:
            if any(x in text for x in needles):
                tags.append(tag)
        if dimension in ("跨Jurisdiction武器", "Reverse Thinking") and "跨界" not in tags:
            tags.insert(0, "跨界")
        if dimension in ("Burden of Proof", "Procedural Defect", "跨Jurisdiction武器") and not any(x in tags for x in ("责任倒置", "程序节点", "跨界")):
            tags.append("高压入口")
        return tags[:5]

    def weakness_source_label(self, target, support_evidence_points):
        kind = target.get("kind", "论点/证据")
        idx = target.get("index", "")
        if support_evidence_points:
            return f"{kind}{idx} + 相对方证据反推"
        return f"{kind}{idx}"

    def weakness_sort_key(self, candidate):
        tags = set(candidate.get("risk_tags") or [])
        tag_weight = {
            "责任倒置": 32,
            "取证合法性": 30,
            "证据可采性": 28,
            "反向法律责任": 26,
            "跨界": 24,
            "跨Jurisdiction": 22,
            "隐私/商业秘密": 20,
            "因果切断": 18,
            "程序节点": 16,
            "量化缺口": 12,
        }
        pressure_score = sum(tag_weight.get(tag, 0) for tag in tags)
        dim_weight = {
            "Burden of Proof": 20,
            "跨Jurisdiction武器": 18,
            "Procedural Defect": 16,
            "Legal Application": 14,
            "Logic Gap": 13,
            "Damage Causation": 12,
            "Legal Text Interpretation": 11,
            "Reverse Thinking": 10,
            "Systemic Risk Amplification": 9,
        }.get(candidate.get("dimension"), 0)
        evidence_bonus = 8 if candidate.get("opponent_point_kind") == "证据" else 0
        return (candidate.get("priority_score", candidate.get("score", 0)) + pressure_score + dim_weight + evidence_bonus, candidate.get("score", 0))

    def weakness_priority_reason(self, candidate):
        tags = candidate.get("risk_tags") or []
        reasons = []
        if any(x in tags for x in ("责任倒置", "取证合法性", "证据可采性", "反向法律责任")):
            reasons.append("可先压证明责任或证据使用门槛")
        if any(x in tags for x in ("跨界", "跨Jurisdiction", "平台/监管规则", "隐私/商业秘密")):
            reasons.append("可跨界打开侧翼Weakness")
        if any(x in tags for x in ("因果切断", "程序节点", "量化缺口")):
            reasons.append("可切断因果、程序或金额链条")
        if not reasons:
            reasons.append("可作为基础事实/规则Weakness")
        return "；".join(reasons[:2])

    def weakness_rules_for_target(self, target, support_evidence_points):
        text = str(target.get("text", "")).strip()
        lower = text.lower()
        kind = target.get("kind", "论点")
        rules = []

        def add(rule, weakness, score_boost=0):
            weakness = self.clean_weakness_scan_text(weakness)
            if weakness:
                rules.append({
                    "rule": rule,
                    "dimension": self.weakness_dimension_for_rule(rule),
                    "weakness": weakness,
                    "score": self.weakness_rule_score(text, weakness, kind) + score_boost,
                })

        if kind == "证据":
            add("证明对象错位", "该证据需要先说明它究竟证明哪一个关键事实；如果只能证明存在沟通、存在图片或存在结果，不能直接证明责任成立。")
            add("关联性", "该证据与被主张的法律后果之间存在距离，仍缺少主体、时间、标的物或交易节点的对应关系。")
            add("Missing Evidence", "若该证据真实支撑关键主张，应当还有配套的原始记录、版本记录、交互记录或第三方记录；缺失部分本身就是可攻击入口。", 4)
            if any(x in text for x in ["录音", "偷拍", "偷录", "监控", "截图", "聊天", "私自", "调取", "平台投诉", "举报", "监管", "隐私", "商业秘密"]) or any(x in lower for x in ["recording", "surveillance", "screenshot", "privacy", "complaint", "regulator"]):
                add("取证合法性", "该证据需要先检查取得方式是否合法合规；若存在私自录音、越权调取、隐私侵入或平台规则违规，证明力和可采性都可能被攻击。", 9)
                add("证据可采性", "即使材料内容对对方有利，也要单独审查其提交程序、来源链条、完整性和是否可作为本案证据使用。", 8)
                add("隐私边界", "若证据取得涉及隐私、商业秘密、平台后台数据或第三方信息，需要检查是否引出反向责任或排除/限缩使用。", 7)
            if any(x in text for x in ["视频", "录像", "照片", "图片", "截图"]) or any(x in lower for x in ["video", "photo", "image", "screenshot"]):
                add("原始性", "影像材料存在原始文件、拍摄设备、生成时间和是否经过剪辑处理的Weakness。", 8)
                add("连续性", "影像材料如果没有连续过程，容易只能证明某一刻状态，不能证明此前状态或责任来源。", 8)
                add("时间戳", "影像材料的时间戳、拍摄顺序和提交时间如果不能对应交易时间线，证明力会被压低。", 7)
                add("叙事标签", "影像或截图容易被包装成单方叙事，需要拆开哪些是可验证事实、哪些只是选择性呈现。", 4)
            if any(x in text for x in ["页面截图", "课程页面", "平台页面", "网页", "页面缓存", "广告页面", "宣传页面"]) or any(x in lower for x in ["webpage", "web page", "landing page", "cache", "browser"]):
                add("网页版本", "网页或课程页面截图必须证明购买时所见的当时版本；动态页面、缓存、后续更新或不同用户展示版本都可能削弱证明力。", 11)
                add("后台原始数据", "页面截图需要与平台后台原始配置、发布时间、版本记录或展示日志对应，否则只能证明截图内容，不能证明交易当时实际展示。", 10)
                add("完整滚动截屏", "网页截图若不是完整滚动页面，可能遗漏免责声明、课程调整条款、适用范围或退款限制，属于选择性呈现风险。", 9)
            if any(x in text for x in ["聊天", "短信", "邮件", "通知", "客服", "回复", "微信"]) or any(x in lower for x in ["message", "email", "chat", "notice"]):
                add("证明对象错位", "沟通记录通常只能证明说过什么、何时联系，不能当然证明基础事实真实或责任已经成立。", 7)
                add("连续性", "沟通记录若不是完整上下文，容易存在截取片段、遗漏前后承诺或遗漏对方回应的问题。", 6)
                add("主体不清", "沟通记录要证明发言主体、代理权限和对交易主体的约束关系，否则容易只是沟通事实而非法律承诺。", 5)
            if any(x in text for x in ["合同", "条款", "规则", "页面", "下单", "确认", "政策"]) or any(x in lower for x in ["contract", "term", "policy", "order"]):
                add("来源", "条款或页面材料要证明版本、展示位置、提示强度和对方实际接受，否则容易只是事后规则说明。", 8)
                add("时间顺序", "规则材料必须对应下单或交易当时版本，不能用之后页面倒推当时已经明示。", 7)
                add("法律要件缺口", "条款或规则证据还要对应具体构成要件，不能只证明有规则就直接证明本案请求成立。", 6)
                add("Legal Text Interpretation", "规则文本必须回到交易当时版本、上下文和提示方式，不能被事后解释扩大。", 5)
            if any(x in text for x in ["质检", "检测", "报告", "鉴定", "物流", "签收", "包装", "封条"]) or any(x in lower for x in ["inspection", "logistics", "delivery", "seal", "report"]):
                add("来源", "记录类材料要证明出具主体、记录时间、对象编号和保存链条，否则容易与本案标的物脱节。", 8)
                add("连续性", "记录类材料如果只覆盖某一个节点，不能自动排除前后节点的介入因素。", 7)
                add("因果跳跃", "记录类材料若只证明某节点状态，仍不能自动证明责任原因或排除其他介入因素。", 5)
            if support_evidence_points:
                add("矛盾", "该证据如果不能解释相对方证据链中的相反节点，容易出现证据冲突或证明力折损。", -3)
            add("第三方佐证", "该证据如果缺少第三方来源或客观记录支撑，容易被压回单方陈述或单方制作材料。")
        else:
            add("前提未证明", "该论点的基础事实尚未被独立证明，不能直接从主张跳到法律后果。")
            add("确定性夸大", "该论点如果把可能性、推测或单方感受说成确定事实，容易被要求逐项证明。")
            add("叙事标签", "该论点若使用身份、诚信、受害或公平等叙事标签，需要拆回可证明事实，不能让标签替代证据链。", 3)
            add("损失量化", "该论点若最终指向责任、补救或费用承担，需要说明损害范围、计算口径和直接对应关系，否则只能停留在责任叙事。", 2)
            add("补救比例", "即便该论点部分成立，也要单独审查请求的救济强度是否与争议程度、履行成本和替代方案相称。", 2)
            add("过失分配", "该论点需要检查双方各自控制能力、注意义务和风险节点，不能把复杂交易风险全部推给一方。", 2)
            add("跨Jurisdiction适用", "该论点若借用平台规则、监管逻辑或其他地区做法，需要区分诉讼内法律依据和诉讼外压力材料。", 1)
            add("Public Policy外溢", "该论点若被裁判接受，可能产生交易确定性、消费者保护或行业成本外溢，需要检查外溢链条是否真实。", 1)
            add("系统外溢", "该论点如果被作为一般规则接受，可能诱发重复索赔、平台规则失灵、行业成本上升或证据造假激励，需要检查系统性风险链条。", 1)
            if any(x in text for x in ["取证", "录音", "截图", "监控", "投诉", "举报", "监管", "平台施压", "隐私", "商业秘密"]) or any(x in lower for x in ["evidence", "recording", "surveillance", "complaint", "regulator", "privacy"]):
                add("取证合法性", "该论点如果依赖录音、截图、平台投诉、监管材料或后台数据，应先检查取证方式是否合法以及材料能否在本案中使用。", 8)
                add("隐私边界", "该论点可能引出隐私、商业秘密、越权调取或不当施压等反向法律风险。", 7)
            if any(x in text for x in ["证明责任", "Burden of Proof", "倒置", "谁证明", "要求我方证明", "排除所有"]) or any(x in lower for x in ["burden", "onus", "prove"]):
                add("责任倒置", "该论点可能把本应由主张方承担的证明责任倒置给相对方，应先拆清谁主张、谁举证、证明门槛是否已经达到。", 8)
            if any(x in text for x in ["因果", "造成", "导致", "由于", "引起", "损失", "律师费", "费用", "商誉", "信誉", "赔偿"]) or any(x in lower for x in ["cause", "caused", "damage", "loss", "cost"]):
                add("因果跳跃", "该论点从事实结果直接跳到责任或损失，中间仍需要排除其他原因、第三方因素或自身行为影响。", 9)
            if any(x in text for x in ["损失", "律师费", "费用", "商誉", "信誉", "赔偿"]) or any(x in lower for x in ["damage", "loss", "cost"]):
                add("损失量化", "损失、费用或商誉影响如果没有金额、计算方式和直接对应关系，容易停留在概括主张。", 8)
                add("量化口径", "该论点需要说明计算口径、范围边界和替代补救，否则金额争议会削弱请求强度。", 6)
                add("补救比例", "即便基础责任部分成立，也要审查请求的补救方式是否与损害程度、履行成本和替代方案相称。", 6)
            if any(x in text for x in ["时间", "期限", "收货", "下单", "通知", "迟延", "第二天", "7 天", "七天", "合理时间"]) or any(x in lower for x in ["date", "time", "deadline", "notice"]):
                add("时间顺序", "该论点依赖时间节点，但每个节点的发生时间、通知时间和规则起算点都可能被拆开攻击。", 9)
            if any(x in text for x in ["法律", "法", "ACL", "section", "条款", "规则", "消费者", "合同", "权利", "补救", "退货", "退款"]):
                add("法律要件缺口", "该论点引用法律或规则后，还需要逐项套入适用条件；法律存在不等于本案条件已经满足。", 9)
                add("规则适用扩大", "该论点可能把一般规则扩大到本案具体请求，仍要看交易类型、提示方式、时点和补救比例。", 7)
                add("先例同构", "若该论点依赖案例、惯例或规则类比，需要证明争点、主体、交易结构和救济路径真正同构。", 5)
                add("Public Policy外溢", "该论点若从个案跳到消费者保护、交易确定性或行业风险，需要证明外溢链条而非只作价值宣称。", 5)
            if any(x in text for x in ["谁", "主体", "商家", "平台", "消费者", "第三方", "物流", "客服"]) or any(x in lower for x in ["party", "platform", "seller", "buyer"]):
                add("主体不清", "该论点需要锁定责任主体和行为主体；平台、商家、物流或消费者自身行为不能混在一起。", 7)
                add("过失分配", "该论点需要区分双方控制能力、注意义务和风险节点，不能把单方责任直接扩大成全部责任。", 5)
            if any(x in text for x in ["平台", "监管", "投诉", "其他Jurisdiction", "州", "联邦", "跨境"]) or any(x in lower for x in ["platform", "regulator", "jurisdiction", "federal", "state"]):
                add("跨Jurisdiction适用", "若该论点引入平台、监管或其他Jurisdiction材料，需要说明其只是辅助压力还是本案可适用法律依据。", 5)
            if support_evidence_points:
                add("矛盾", "该论点如果不能解释相对方证据链中的相反节点，会出现事实张力。", -3)
        return rules

    def diverse_weakness_rules(self, rules, limit=12):
        ordered = sorted(rules, key=lambda x: -x.get("score", 0))
        selected = []
        used_dims = set()
        for rule in ordered:
            dim = rule.get("dimension", "")
            if dim and dim not in used_dims:
                selected.append(rule)
                used_dims.add(dim)
            if len(selected) >= limit:
                return selected
        for rule in ordered:
            if rule in selected:
                continue
            selected.append(rule)
            if len(selected) >= limit:
                break
        return selected

    def build_weakness_candidates(self, state, target_side="negative", id_prefix="W"):
        rounds = state.get("rounds", {})
        rebuttal_by_dim = {x.get("dimension"): x for x in rounds.get("round2_my_rebuttal", [])}
        structured = state.get("options", {}).get("structured_case", {})
        target_args, target_evidence, support_evidence_points = self.target_side_points(structured, target_side)
        target_points = target_args + target_evidence

        def is_generic_strategy_text(value):
            lowered = re.sub(r"\s+", " ", str(value or "")).strip().lower()
            return not lowered or any(marker in lowered for marker in (
                "[tactic package:", "tactic package:", "[read mode]",
                "[imported file]", "[language note]", "this point leaves an attackable gap",
                "ambiguity, missing records, alternative causes", "open a side weakness",
                "cross-boundary rules", "case can argue that the opponent's conduct",
                "break the opponent's conclusion back into legal elements",
                "evidence angle: argue existing documents", "evidence angle: attack originality",
                "the record does not yet close the proof", "positive side synthetic pattern",
                "negative side synthetic pattern",
            ))

        target_points = [
            target for target in target_points
            if not is_generic_strategy_text(target.get("text", ""))
        ]

        state["opponent_point_counts"] = {"arguments": len(target_args), "evidence": len(target_evidence)}
        candidates = []

        seen = set()
        seq = 1
        for target in target_points:
            per_target = self.weakness_rules_for_target(target, support_evidence_points)
            for rule in self.diverse_weakness_rules(per_target, limit=12):
                weakness = self.clean_weakness_scan_text(rule["weakness"])
                key = (
                    target.get("kind"),
                    target.get("index"),
                    re.sub(r"\s+", "", weakness)[:90],
                )
                if key in seen:
                    continue
                seen.add(key)
                dim = rule.get("dimension") or "Fact Challenge"
                tags = self.weakness_tags_for_rule(rule.get("rule", ""), dim, weakness)
                attack_item = {
                    "dimension": dim,
                    "targeting": f"{target.get('kind')}{target.get('index')}：{target.get('text')}",
                    "finding": weakness,
                    "question": weakness,
                    "attack": weakness,
                    "local_weakness_rule": rule.get("rule", ""),
                }
                candidates.append({
                    "id": f"{id_prefix}{seq:03d}",
                    "side": target_side,
                    "dimension": dim,
                    "score": rule["score"],
                    "priority_score": rule["score"],
                    "rule": rule.get("rule", ""),
                    "risk_tags": tags,
                    "source_label": self.weakness_source_label(target, support_evidence_points),
                    "targeting": self.clean_weakness_scan_text(attack_item["targeting"]),
                    "opponent_point_kind": target.get("kind", "论点/证据"),
                    "opponent_point_index": target.get("index", ""),
                    "opponent_point": self.clean_weakness_scan_text(target.get("text", "")),
                    "weakness": weakness,
                    "weakness_lines": [weakness],
                    "attack_item": attack_item,
                    "rebuttal_item": rebuttal_by_dim.get(dim, {}),
                })
                seq += 1

        if not candidates:
            for idx, item in enumerate(rounds.get("round1_opponent_attack", []), 1):
                dim = item.get("dimension", f"维度{idx}")
                rebuttal = rebuttal_by_dim.get(dim, {})
                score = self.weakness_score(item, rebuttal)
                opponent_point = self.best_opponent_point_for_attack(item, target_points)
                weakness = self.clean_weakness_scan_text(item.get("finding") or item.get("attack") or "")
                if is_generic_strategy_text(weakness) or is_generic_strategy_text(item.get("targeting", "")):
                    continue
                tags = self.weakness_tags_for_rule(dim, dim, weakness)
                candidates.append({
                    "id": f"{id_prefix}{idx:03d}",
                    "side": target_side,
                    "dimension": dim,
                    "score": score,
                    "priority_score": score,
                    "risk_tags": tags,
                    "source_label": self.weakness_source_label(opponent_point, support_evidence_points),
                    "targeting": self.clean_weakness_scan_text(item.get("targeting", "")),
                    "opponent_point_kind": opponent_point["kind"],
                    "opponent_point_index": opponent_point["index"],
                    "opponent_point": self.clean_weakness_scan_text(opponent_point["text"]),
                    "weakness": weakness,
                    "weakness_lines": self.weakness_lines_for_scan(item, support_evidence_points),
                    "attack_item": item,
                    "rebuttal_item": rebuttal,
                })
        for candidate in candidates:
            candidate["priority_reason"] = self.weakness_priority_reason(candidate)
            candidate["priority_score"] = self.weakness_sort_key(candidate)[0]
        candidates.sort(key=lambda x: (-x.get("priority_score", 0), -x.get("score", 0), x["id"]))
        return candidates

    def build_whole_case_local_candidates(self, state, selected_dimensions, target_side="negative", id_prefix="W"):
        """Select at most one concrete whole-case finding for each dimension."""
        all_candidates = self.build_weakness_candidates(state, target_side=target_side, id_prefix=id_prefix)
        selected = [self.dim_label(dimension) for dimension in (selected_dimensions or [])]
        by_dimension = {dimension.lower(): [] for dimension in selected}
        for candidate in all_candidates:
            dimension = self.dim_label(candidate.get("dimension"))
            key = dimension.lower()
            if key in by_dimension:
                candidate = dict(candidate)
                candidate["dimension"] = dimension
                by_dimension[key].append(candidate)

        whole_case_candidates = []
        for dimension in selected:
            options = by_dimension.get(dimension.lower()) or []
            if not options:
                continue
            best = max(options, key=self.weakness_sort_key)
            item = dict(best)
            item["id"] = f"{id_prefix}{len(whole_case_candidates) + 1:03d}"
            item["source_label"] = f"Whole-case local review / {self.ui_en_text(dimension)}"
            item["whole_case_local_scan"] = True
            item["whole_case_review_scope"] = {
                "arguments_reviewed": state.get("opponent_point_counts", {}).get("arguments", 0),
                "evidence_reviewed": state.get("opponent_point_counts", {}).get("evidence", 0),
                "dimension": dimension,
            }
            whole_case_candidates.append(item)

        whole_case_candidates.sort(
            key=lambda item: selected.index(item.get("dimension")) if item.get("dimension") in selected else len(selected)
        )
        return whole_case_candidates

    def build_standard_weakness_scan_report(self, state):
        candidates = [item for item in (state.get("weakness_candidates") or []) if isinstance(item, dict)]
        findings = []
        missing = []
        provider_runs = []
        for index, item in enumerate(candidates, 1):
            rebuttal = item.get("rebuttal_item") if isinstance(item.get("rebuttal_item"), dict) else {}
            needed = rebuttal.get("needed_material") or []
            if isinstance(needed, str):
                needed = [needed]
            missing.extend(str(value).strip() for value in needed if str(value).strip())
            provider = str(item.get("provider") or item.get("model_provider") or "").strip()
            model = str(item.get("model") or item.get("model_name") or "").strip()
            if provider or model:
                provider_runs.append({
                    "provider": provider or "Not recorded",
                    "model": model or "Not recorded",
                    "engine_source": "Weakness scan record",
                    "run_reference": item.get("dimension") or item.get("id"),
                })
            findings.append({
                "id": item.get("id") or f"W-{index:03d}",
                "analysis_stage": "weakness_scan",
                "dimension": self.dim_label(item.get("dimension", "")),
                "title": self.weakness_text_en(item) or f"Weakness {index}",
                "finding": self.weakness_text_en(item),
                "affected_side": item.get("side") or "Not assigned",
                "factual_basis": self.ui_en_text(item.get("opponent_point") or item.get("targeting") or ""),
                "evidence_references": [item.get("source_label")] if item.get("source_label") else [],
                "significance": item.get("priority_reason") or "Materiality requires lawyer assessment",
                "confidence": item.get("confidence") or "Not independently scored",
                "provider": provider or "Offline local workflow",
                "model": model or "No external model recorded",
                "source_reference": item.get("source_label") or "Weakness scan state",
                "review_status": "ai_generated_unverified",
            })
        workflow = str(state.get("workflow_mode") or "weakness_scan")
        synthetic = "synthetic" in workflow.lower()
        return build_standard_report(
            "weakness_scan",
            workflow,
            state.get("options", {}).get("case_name") or self.case_name_var.get().strip() or "Current matter",
            state.get("jurisdiction") or self.jur_var.get(),
            findings=findings,
            provider_runs=provider_runs,
            input_scope={
                "selected_dimensions": [self.dim_label(value) for value in (state.get("selected_dimensions") or [])],
                "candidate_count": len(candidates),
                "positive_findings": len(state.get("positive_weaknesses") or []),
                "negative_findings": len(state.get("negative_weaknesses") or []),
                "case_text_external_transmission": bool(((state.get("execution_trace") or {}).get("counts") or {}).get("cloud_calls_for_case_text")),
            },
            sections={
                "legacy_scan_report": self.strip_markers(self.render_weakness_candidates(state)),
                "review_transition": "AI finding -> lawyer review -> confirmed, modified or rejected",
            },
            missing_material=list(dict.fromkeys(missing)),
            synthetic=synthetic,
        )

    def save_weakness_scan_artifacts(self, state):
        stamp = _dt.datetime.now().strftime("weakness_scan_%Y%m%d_%H%M%S")
        run_dir = HERE / "runs" / stamp
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "weakness_candidates.json").write_text(
            json.dumps(state.get("weakness_candidates", []), ensure_ascii=False, indent=2),
            encoding="utf-8-sig",
        )
        (run_dir / "weakness_scan_report.md").write_text(
            self.strip_markers(self.render_weakness_candidates(state)),
            encoding="utf-8-sig",
        )
        (run_dir / "state_object.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8-sig")
        standard_report = self.build_standard_weakness_scan_report(state)
        write_standard_companions(run_dir, "weakness-scan", standard_report)
        self.last_run_dir = run_dir
        self.log(f"SavedWeakness Scan：{run_dir}")

    def render_weakness_scan(self, state):
        self.open_weakness_scan_window(state)

    def open_weakness_scan_window(self, state):
        from Nido_StrikeOver_Online_EN import is_non_material_weakness_display_record

        # Preserve the full saved state and all upstream findings.  Only this
        # presentation copy removes explicit no-finding / not-applicable cards.
        display_state = dict(state)
        for list_key in ("positive_weaknesses", "negative_weaknesses", "weakness_candidates"):
            if isinstance(state.get(list_key), list):
                display_state[list_key] = [
                    item for item in state.get(list_key, [])
                    if not is_non_material_weakness_display_record(item)
                ]

        synthetic_direct = state.get("workflow_mode") == "synthetic_analogue_model_weakness_scan"
        win = tk.Toplevel(self.root)
        win.title("Fictional Case Weakness Scan" if synthetic_direct else "Weakness Scan")
        win.geometry("1180x820")
        win.configure(bg=self.C["bg"])
        combo_win = None if synthetic_direct else self.open_tactic_combo_window(win, display_state)

        top = tk.Frame(win, bg=self.C["bg"], padx=10, pady=8)
        top.pack(fill=tk.X)
        tk.Label(
            top,
            text="Fictional Case Weakness Scan" if synthetic_direct else "Weakness Scan",
            bg=self.C["bg"],
            fg=self.C["gold"],
            font=("Microsoft YaHei UI", 15, "bold"),
        ).pack(side=tk.LEFT)
        tk.Label(
            top,
            text=(
                "These findings belong only to the locally generated fictional case pack. The real matter was not analysed or mapped."
                if synthetic_direct else
                "Double-click a card to inspect the full weakness. Drag it to the Tactic Combo window or a side argument box."
            ),
            bg=self.C["bg"],
            fg=self.C["muted"],
            font=("Microsoft YaHei UI", 10),
        ).pack(side=tk.LEFT, padx=12)
        if not synthetic_direct:
            tk.Button(
                top,
                text="Show Tactic Window",
                command=lambda w=combo_win: (w.deiconify(), w.lift()),
                bg="#8a5a13",
                fg="white",
                relief="flat",
                padx=12,
                pady=4,
            ).pack(side=tk.RIGHT, padx=8)

        if state.get("workflow_mode") == "local_two_step_perspective_scan":
            steps = ttk.Notebook(win)
            steps.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
            positive_step = tk.Frame(steps, bg=self.C["bg"])
            negative_step = tk.Frame(steps, bg=self.C["bg"])
            steps.add(positive_step, text="Step 1 - Positive Side")
            steps.add(negative_step, text="Step 2 - Negative Side")
            self.build_weakness_click_panel(
                positive_step,
                display_state.get("positive_state", display_state),
                display_state.get("positive_weaknesses", []),
                "Fictional Positive Side" if synthetic_direct else "Positive side",
                self.C["teal"],
                combo_window=combo_win,
            ).pack(fill=tk.BOTH, expand=True)
            self.build_weakness_click_panel(
                negative_step,
                display_state.get("negative_state", display_state),
                display_state.get("negative_weaknesses", []),
                "Fictional Negative Side" if synthetic_direct else "Negative side",
                self.C["pink"],
                combo_window=combo_win,
            ).pack(fill=tk.BOTH, expand=True)
            steps.select(positive_step)
        else:
            body = tk.PanedWindow(win, orient=tk.HORIZONTAL, bg=self.C["bg"], sashwidth=5)
            body.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
            pos_panel = self.build_weakness_click_panel(
                body,
                display_state.get("positive_state", display_state),
                display_state.get("positive_weaknesses", []),
                "Fictional Positive Side" if synthetic_direct else "Positive side",
                self.C["teal"],
                combo_window=combo_win,
            )
            neg_panel = self.build_weakness_click_panel(
                body,
                display_state.get("negative_state", display_state),
                display_state.get("negative_weaknesses", []),
                "Fictional Negative Side" if synthetic_direct else "Negative side",
                self.C["pink"],
                combo_window=combo_win,
            )
            body.add(pos_panel, minsize=560)
            body.add(neg_panel, minsize=560)

    def open_tactic_combo_window(self, owner, state):
        win = tk.Toplevel(owner)
        win.title("Tactic Combination Window")
        win.geometry("520x640+1220+120")
        win.configure(bg=self.C["bg"])
        win.tactic_combo_items = []
        panel = self.build_tactic_combo_panel(win, state)
        panel.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        win.protocol("WM_DELETE_WINDOW", win.withdraw)
        owner.bind("<Destroy>", lambda _e, w=win: w.destroy() if w.winfo_exists() else None)
        return win

    def build_tactic_combo_panel(self, win, state):
        panel = tk.Frame(win, bg=self.C["panel"], padx=8, pady=8)
        header = tk.Frame(panel, bg="#5a3d0a", padx=8, pady=5)
        header.pack(fill=tk.X)
        tk.Label(
            header,
            text="Tactic Combo Window",
            bg="#5a3d0a",
            fg="#ffffff",
            font=("Microsoft YaHei UI", 12, "bold"),
        ).pack(side=tk.LEFT)
        tk.Label(
            header,
            text="Dropped weaknesses are auto-assigned to each side",
            bg="#5a3d0a",
            fg="#ffe8a3",
            font=("Microsoft YaHei UI", 9),
        ).pack(side=tk.RIGHT)
        tk.Label(
            panel,
            text="Drop weakness cards here to build a reusable tactic package. Save JSON to import the same package into either the offline or online main window.",
            bg=self.C["panel"],
            fg=self.C["muted"],
            font=("Microsoft YaHei UI", 9),
            wraplength=470,
            justify=tk.LEFT,
        ).pack(fill=tk.X, pady=(8, 0))

        combo_list = tk.Listbox(
            panel,
            bg="#111827",
            fg=self.C["gold"],
            selectmode=tk.EXTENDED,
            activestyle="none",
            relief="flat",
            font=("Microsoft YaHei UI", 10),
        )
        combo_list.pack(fill=tk.BOTH, expand=True, pady=(8, 8))
        win.tactic_combo_list = combo_list

        def refresh_combo():
            combo_list.delete(0, tk.END)
            for item in win.tactic_combo_items:
                assigned = "for negative side" if item.get("side") == "positive" else "for positive side"
                weakness = self.weakness_text_en(item)
                combo_list.insert(
                    tk.END,
                    f"{item.get('select_id') or item.get('id')} -> {assigned} [{self.ui_en_text(item.get('dimension')) or 'Fact Challenge'}] {self.compact(weakness, 92)}",
                )

        def add_candidate(candidate):
            cid = candidate.get("select_id") or candidate.get("id")
            candidate_key = self.weakness_candidate_key(candidate)
            if not any(self.weakness_candidate_key(x) == candidate_key for x in win.tactic_combo_items):
                win.tactic_combo_items.append(dict(candidate))
                refresh_combo()
                self.status_var.set(f"Status: added to tactic combo: {cid}")
            else:
                self.status_var.set(f"Status: tactic combo already contains: {cid}")
                messagebox.showinfo(
                    "Weakness Already Added",
                    "This weakness card is already in the Tactic Combo and was not added again.",
                    parent=win,
                )

        def add_all_candidates():
            all_items = []
            if isinstance(state, dict):
                all_items.extend(state.get("positive_weaknesses") or [])
                all_items.extend(state.get("negative_weaknesses") or [])
                if not all_items:
                    all_items.extend(state.get("weakness_candidates") or [])
            added = 0
            existing = {self.weakness_candidate_key(x) for x in win.tactic_combo_items}
            for candidate in all_items:
                candidate_key = self.weakness_candidate_key(candidate)
                if candidate_key not in existing:
                    win.tactic_combo_items.append(dict(candidate))
                    existing.add(candidate_key)
                    added += 1
            refresh_combo()
            self.status_var.set(f"Status: added {added} weakness item(s) to tactic combo")

        def finish_combo_drop(_event=None):
            candidate = getattr(win, "dragging_weakness_candidate", None)
            if not candidate:
                return
            px, py = self.root.winfo_pointerx(), self.root.winfo_pointery()
            rx, ry = panel.winfo_rootx(), panel.winfo_rooty()
            in_panel = 0 <= px - rx <= panel.winfo_width() and 0 <= py - ry <= panel.winfo_height()
            if in_panel:
                add_candidate(candidate)
            win.dragging_weakness_candidate = None

        def remove_selected():
            remove = {win.tactic_combo_items[i].get("select_id") or win.tactic_combo_items[i].get("id") for i in combo_list.curselection()}
            win.tactic_combo_items = [x for x in win.tactic_combo_items if (x.get("select_id") or x.get("id")) not in remove]
            refresh_combo()

        def clear_combo():
            win.tactic_combo_items = []
            refresh_combo()

        def copy_combo():
            text = self.render_tactic_combo_text(state, win.tactic_combo_items)
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update()
            self.status_var.set(f"Status: copied {len(win.tactic_combo_items)} tactic item(s)")

        def apply_combo():
            applied = self.apply_tactic_combo_to_current_case(state, win.tactic_combo_items)
            if applied:
                self.status_var.set(f"Status: applied {len(win.tactic_combo_items)} tactic item(s) to current case")
                messagebox.showinfo(
                    "Tactic Combo Applied",
                    "Selected weaknesses were classified and appended to the current positive/negative argument panels.",
                    parent=win,
                )

        def save_combo():
            path = self.save_tactic_combo_package(state, win.tactic_combo_items)
            if path:
                messagebox.showinfo("Tactic Package Saved", f"{path}\n\nYou can import it into either the offline or online main window.")

        def open_export_dir():
            out_dir = HERE / "tactic_combo_exports"
            out_dir.mkdir(parents=True, exist_ok=True)
            try:
                os.startfile(str(out_dir))
            except Exception as exc:
                messagebox.showerror("Open Failed", str(exc))

        win.add_tactic_combo_candidate = add_candidate
        win.refresh_tactic_combo = refresh_combo
        win.finish_tactic_combo_drop = finish_combo_drop
        win.add_tactic_candidate = add_candidate
        win.dragging_weakness_candidate = None
        win.bind("<ButtonRelease-1>", finish_combo_drop)
        panel.bind("<ButtonRelease-1>", finish_combo_drop)
        combo_list.bind("<ButtonRelease-1>", finish_combo_drop)

        btns = tk.Frame(panel, bg=self.C["panel"])
        btns.pack(fill=tk.X)
        btns_top = tk.Frame(btns, bg=self.C["panel"])
        btns_top.pack(fill=tk.X)
        btns_bottom = tk.Frame(btns, bg=self.C["panel"])
        btns_bottom.pack(fill=tk.X, pady=(6, 0))
        tk.Button(btns_top, text="Apply To Current Case", command=apply_combo, bg=self.C["accent"], fg="white", relief="flat", padx=10, pady=5).pack(side=tk.LEFT)
        tk.Button(btns_top, text="Add All Weaknesses", command=add_all_candidates, bg="#2f3b52", fg=self.C["gold"], relief="flat", padx=10, pady=5).pack(side=tk.LEFT, padx=6)
        tk.Button(btns_top, text="Remove Selected", command=remove_selected, bg="#5a2448", fg="white", relief="flat", padx=10, pady=5).pack(side=tk.LEFT)
        tk.Button(btns_bottom, text="Clear", command=clear_combo, bg="#333", fg=self.C["text"], relief="flat", padx=10, pady=5).pack(side=tk.LEFT)
        tk.Button(btns_bottom, text="Copy Text", command=copy_combo, bg="#8a5a13", fg="white", relief="flat", padx=10, pady=5).pack(side=tk.LEFT, padx=6)
        tk.Button(btns_bottom, text="Save JSON", command=save_combo, bg="#315c36", fg="white", relief="flat", padx=10, pady=5).pack(side=tk.LEFT, padx=6)
        tk.Button(btns_bottom, text="Open Export Folder", command=open_export_dir, bg="#263f67", fg="white", relief="flat", padx=10, pady=5).pack(side=tk.LEFT)
        return panel

    def build_weakness_click_panel(self, parent, side_state, candidates, side_label, header_color, combo_window=None):
        panel = tk.Frame(parent, bg=self.C["panel"], padx=8, pady=8)
        counts = side_state.get("opponent_point_counts", {})
        display_side = self.ui_en_text(side_label) or side_label
        header = tk.Frame(panel, bg=header_color, padx=8, pady=5)
        header.pack(fill=tk.X)
        tk.Label(
            header,
            text=f"{display_side} Weaknesses",
            bg=header_color,
            fg="#ffffff",
            font=("Microsoft YaHei UI", 12, "bold"),
        ).pack(side=tk.LEFT)
        tk.Label(
            header,
            text=f"Arguments {counts.get('arguments', 0)} / Evidence {counts.get('evidence', 0)} / Weaknesses {len(candidates)}",
            bg=header_color,
            fg="#d7f7ff",
            font=("Microsoft YaHei UI", 9),
        ).pack(side=tk.RIGHT)

        canvas = tk.Canvas(panel, bg=self.C["entry"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(panel, orient=tk.VERTICAL, command=canvas.yview)
        list_frame = tk.Frame(canvas, bg=self.C["entry"])
        list_window = canvas.create_window((0, 0), window=list_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=(8, 0))
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=(8, 0))

        def sync_scroll(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def sync_width(event):
            canvas.itemconfigure(list_window, width=event.width)

        list_frame.bind("<Configure>", sync_scroll)
        canvas.bind("<Configure>", sync_width)
        self.bind_local_scroll(canvas)
        list_frame.bind("<MouseWheel>", lambda event, w=canvas: self._on_local_widget_mousewheel(w, event))
        list_frame.bind("<Button-4>", lambda event, w=canvas: (w.yview_scroll(-1, "units"), "break")[-1])
        list_frame.bind("<Button-5>", lambda event, w=canvas: (w.yview_scroll(1, "units"), "break")[-1])

        if not candidates:
            tk.Label(
                list_frame,
                text="No weaknesses yet.",
                bg=self.C["entry"],
                fg=self.C["muted"],
                font=("Microsoft YaHei UI", 11),
                pady=16,
            ).pack(fill=tk.X)
            return panel

        for candidate in candidates:
            self.add_weakness_click_card(list_frame, candidate, display_side, header_color, canvas, combo_window=combo_window)
        return panel

    def reorder_weakness_card_at_pointer(self, card, parent):
        try:
            pointer_y = self.root.winfo_pointery()
            siblings = [
                child for child in parent.winfo_children()
                if getattr(child, "_weakness_candidate", None) is not None
            ]
            if card not in siblings or len(siblings) < 2:
                return
            target = None
            for sibling in siblings:
                if sibling is card:
                    continue
                midpoint = sibling.winfo_rooty() + sibling.winfo_height() / 2
                if pointer_y < midpoint:
                    target = sibling
                    break
            if target is not None:
                current_index = siblings.index(card)
                target_index = siblings.index(target)
                if current_index != target_index - 1:
                    card.pack_configure(before=target)
            elif siblings[-1] is not card:
                card.pack_configure(after=siblings[-1])
            parent.update_idletasks()

            ordered = [
                child._weakness_candidate for child in parent.winfo_children()
                if getattr(child, "_weakness_candidate", None) is not None
            ]
            side = str(getattr(card, "_weakness_candidate", {}).get("side") or "")
            state = getattr(self, "last_weakness_state", None)
            if isinstance(state, dict) and side in ("positive", "negative"):
                state[f"{side}_weaknesses"] = ordered
                state["weakness_candidates"] = (
                    (state.get("positive_weaknesses") or [])
                    + (state.get("negative_weaknesses") or [])
                )
                self.weakness_candidates = state["weakness_candidates"]
        except (tk.TclError, AttributeError, ValueError):
            return

    def add_weakness_click_card(self, parent, candidate, side_label, accent, scroll_widget, combo_window=None):
        card = tk.Frame(parent, bg="#111827", highlightthickness=1, highlightbackground="#344054", padx=8, pady=7)
        card._weakness_candidate = candidate
        card.pack(fill=tk.X, padx=6, pady=5)
        kind = candidate.get("opponent_point_kind", "argument/evidence")
        index = candidate.get("opponent_point_index", "")
        kind_en = self.candidate_kind_en(candidate) or "argument/evidence"
        guide = self.weakness_plain_guide(candidate)
        candidate["plain_guide"] = guide
        surface = self.weakness_surface_conclusion(candidate, guide)
        header_row = tk.Frame(card, bg="#111827")
        header_row.pack(fill=tk.X)
        title_label = tk.Label(
            header_row,
            text=surface["title"],
            bg="#111827",
            fg=accent,
            font=("Microsoft YaHei UI", 11, "bold"),
            anchor="w",
            justify=tk.LEFT,
            wraplength=440,
        )
        title_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        drag_handle = tk.Label(
            header_row,
            text="DRAG",
            bg="#1f6feb",
            fg="white",
            font=("Microsoft YaHei UI", 8, "bold"),
            padx=8,
            pady=2,
        )
        drag_handle.pack(side=tk.RIGHT)
        source_widget = None
        synthetic_source = str(candidate.get("synthetic_source_case") or "").strip()
        if synthetic_source:
            source_widget = tk.Label(
                card,
                text=f"Fictional source: {synthetic_source}",
                bg="#111827",
                fg=self.C["muted"],
                font=("Microsoft YaHei UI", 8),
                anchor="w",
                justify=tk.LEFT,
                wraplength=520,
            )
            source_widget.pack(fill=tk.X, pady=(4, 0))
        attack_label = tk.Label(
            card,
            text=surface["reason"],
            bg="#111827",
            fg=self.C["text"],
            font=("Microsoft YaHei UI", 10),
            anchor="w",
            justify=tk.LEFT,
            wraplength=520,
        )
        if surface["reason"]:
            attack_label.pack(fill=tk.X, pady=(5, 0))

        def set_sorting_view(active):
            if active:
                if source_widget is not None:
                    source_widget.pack_forget()
                attack_label.pack_forget()
                card.pack_configure(fill=tk.X, padx=58, pady=2)
                card.configure(padx=5, pady=3, highlightthickness=2, highlightbackground="#22c55e")
                title_label.configure(font=("Microsoft YaHei UI", 9, "bold"), wraplength=320)
                drag_handle.configure(bg="#22c55e", fg="#052e16", text="MOVING")
            else:
                card.pack_configure(fill=tk.X, padx=6, pady=5)
                card.configure(padx=8, pady=7, highlightthickness=1, highlightbackground="#344054")
                title_label.configure(font=("Microsoft YaHei UI", 11, "bold"), wraplength=440)
                drag_handle.configure(bg="#1f6feb", fg="white", text="DRAG")
                if source_widget is not None:
                    source_widget.pack(fill=tk.X, pady=(4, 0))
                if surface["reason"]:
                    attack_label.pack(fill=tk.X, pady=(5, 0))
            card.update_idletasks()

        def on_sort_press(_event=None):
            card._sorting_active = True
            card._external_drag_active = False
            set_sorting_view(True)
            self.status_var.set("Status: moving weakness card within this side")
            return "break"

        def on_sort_motion(_event=None):
            if not getattr(card, "_sorting_active", False):
                return "break"
            pointer_x = self.root.winfo_pointerx()
            pointer_y = self.root.winfo_pointery()
            left = scroll_widget.winfo_rootx()
            right = left + scroll_widget.winfo_width()
            top = scroll_widget.winfo_rooty()
            bottom = top + scroll_widget.winfo_height()
            if pointer_x < left - 12 or pointer_x > right + 12 or pointer_y < top - 12 or pointer_y > bottom + 12:
                card._sorting_active = False
                card._external_drag_active = True
                set_sorting_view(False)
                on_press()
                self.status_var.set("Status: drag to a main-case argument box; release to confirm the entire weakness")
                return "break"
            if pointer_y < top + 34:
                scroll_widget.yview_scroll(-1, "units")
            elif pointer_y > bottom - 34:
                scroll_widget.yview_scroll(1, "units")
            self.reorder_weakness_card_at_pointer(card, parent)
            return "break"

        def on_sort_release(_event=None):
            if getattr(card, "_external_drag_active", False):
                card._external_drag_active = False
                on_release()
                return "break"
            if getattr(card, "_sorting_active", False):
                card._sorting_active = False
                set_sorting_view(False)
                self.status_var.set("Status: weakness card order updated")
            return "break"
        def set_card_bg(color):
            card.configure(bg=color)
            for child in card.winfo_children():
                if child is drag_handle:
                    continue
                child.configure(bg=color)
                for grand in child.winfo_children():
                    try:
                        if grand is drag_handle:
                            continue
                        grand.configure(bg=color)
                    except Exception:
                        pass
            drag_handle.configure(bg="#1f6feb", fg="white")

        def set_pressed(value):
            if value:
                card.pack_configure(fill=tk.X, padx=16, pady=10)
                card.configure(highlightthickness=2, highlightbackground="#1f6feb")
                set_card_bg("#0b1220")
                drag_handle.configure(bg="#22c55e", fg="#052e16", text="DRAGGING")
            else:
                card.pack_configure(fill=tk.X, padx=6, pady=5)
                card.configure(highlightthickness=1, highlightbackground="#344054")
                set_card_bg("#111827")
                drag_handle.configure(bg="#1f6feb", fg="white", text="DRAG")
            try:
                card.update_idletasks()
            except Exception:
                pass

        def on_enter(_event):
            if getattr(card, "_sorting_active", False):
                return
            card.configure(bg="#172033", highlightbackground=accent)
            for child in card.winfo_children():
                if child is drag_handle:
                    continue
                child.configure(bg="#172033")
                for grand in child.winfo_children():
                    try:
                        if grand is drag_handle:
                            continue
                        grand.configure(bg="#172033")
                    except Exception:
                        pass
            drag_handle.configure(bg="#1f6feb", fg="white")

        def on_leave(_event):
            if getattr(card, "_sorting_active", False):
                return
            card.configure(bg="#111827", highlightbackground="#344054")
            for child in card.winfo_children():
                if child is drag_handle:
                    continue
                child.configure(bg="#111827")
                for grand in child.winfo_children():
                    try:
                        if grand is drag_handle:
                            continue
                        grand.configure(bg="#111827")
                    except Exception:
                        pass
            drag_handle.configure(bg="#1f6feb", fg="white")

        def on_click(_event=None):
            card.configure(highlightbackground=accent)

        def on_double_click(_event=None):
            self.open_point_rebuttal_for_weakness(candidate, combo_window=combo_window)
            return "break"

        def on_press(_event=None):
            self.dragging_weakness_candidate = candidate
            self._pressed_weakness_card = card
            self._weakness_drag_started = False
            self._weakness_drag_start_xy = (self.root.winfo_pointerx(), self.root.winfo_pointery())
            set_pressed(True)
            self.status_var.set("Status: dragging weakness card; release on a side argument box or Tactic Combo")
            if combo_window is not None:
                combo_window.dragging_weakness_candidate = candidate
            self.show_weakness_drag_ghost(candidate)
            self.start_weakness_drag_poll(combo_window=combo_window)
            try:
                if getattr(self, "_weakness_drag_release_bind", None):
                    self.root.unbind_all("<ButtonRelease-1>")
                if getattr(self, "_weakness_drag_motion_bind", None):
                    self.root.unbind_all("<B1-Motion>")
                self.root.bind_all(
                    "<B1-Motion>",
                    self.move_weakness_drag_ghost,
                    add="+",
                )
                self._weakness_drag_motion_bind = True
                self.root.bind_all(
                    "<ButtonRelease-1>",
                    lambda event, cw=combo_window: self.finish_weakness_card_drag(combo_window=cw),
                    add="+",
                )
                self._weakness_drag_release_bind = True
            except Exception:
                pass

        def on_release(_event=None):
            set_pressed(False)
            self.finish_weakness_card_drag(combo_window=combo_window)

        content_widgets = [card, header_row, title_label, attack_label]
        if source_widget is not None:
            content_widgets.append(source_widget)
        for widget in content_widgets:
            widget.bind("<Enter>", on_enter)
            widget.bind("<Leave>", on_leave)
            widget.bind("<Button-1>", on_click)
            widget.bind("<Double-Button-1>", on_double_click)
            widget.bind("<MouseWheel>", lambda event, w=scroll_widget: self._on_local_widget_mousewheel(w, event))
            widget.bind("<Button-4>", lambda event, w=scroll_widget: (w.yview_scroll(-1, "units"), "break")[-1])
            widget.bind("<Button-5>", lambda event, w=scroll_widget: (w.yview_scroll(1, "units"), "break")[-1])
            widget.configure(cursor="hand2")

        drag_handle.bind("<Enter>", on_enter)
        drag_handle.bind("<Leave>", on_leave)
        drag_handle.bind("<ButtonPress-1>", on_sort_press)
        drag_handle.bind("<B1-Motion>", on_sort_motion)
        drag_handle.bind("<ButtonRelease-1>", on_sort_release)
        drag_handle.bind("<MouseWheel>", lambda event, w=scroll_widget: self._on_local_widget_mousewheel(w, event))
        drag_handle.bind("<Button-4>", lambda event, w=scroll_widget: (w.yview_scroll(-1, "units"), "break")[-1])
        drag_handle.bind("<Button-5>", lambda event, w=scroll_widget: (w.yview_scroll(1, "units"), "break")[-1])
        drag_handle.configure(cursor="fleur")

    def render_weakness_candidates(self, state):
        if "positive_weaknesses" in state or "negative_weaknesses" in state:
            return "\n\n".join([
                self.render_weakness_side(state.get("positive_state", state), state.get("positive_weaknesses", []), "正方"),
                self.render_weakness_side(state.get("negative_state", state), state.get("negative_weaknesses", []), "反方"),
            ])
        return self.render_weakness_side(state, state.get("weakness_candidates", []), "对方")

    def render_weakness_side(self, state, candidates, side_label):
        counts = state.get("opponent_point_counts", {})
        side_label = self.ui_en_text(side_label) or side_label
        lines = [
            f"[[TITLE]]# {side_label} Weaknesses",
            "",
            f"{side_label} arguments: {counts.get('arguments', 0)}; {side_label} evidence: {counts.get('evidence', 0)}.",
            "",
        ]
        for c in candidates:
            lines.extend([
                f"[[SECTION]]## {side_label} Weakness {c.get('display_id', '')}",
            ])
            kind = self.candidate_kind_en(c)
            index = c.get("opponent_point_index", "")
            target = self.ui_en_text(c.get('opponent_point') or c.get('targeting', ''))
            if self.bad_ui_text(target):
                target = "the targeted argument or evidence"
            lines.append(f"[[LABEL]]Targeting {side_label} {kind} {index}: {target}")
            if c.get("risk_tags"):
                tags = [self.ui_en_text(x) for x in c.get("risk_tags", [])]
                lines.append(f"Tags: {', '.join(x for x in tags if not self.bad_ui_text(x))}")
            if c.get("source_label") or c.get("priority_reason"):
                lines.append(f"Source/ranking: {self.weakness_source_en(c)}; {self.weakness_reason_en(c)}")
            lines.append("Weaknesses:")
            lines.append(f"- {self.weakness_text_en(c)}")
            lines.append("")
        return self.clean_weakness_scan_text("\n".join(lines))

    def tactic_candidate_block(self, item, idx=1):
        target = self.ui_en_text(item.get("opponent_point") or item.get("targeting") or "")
        if self.bad_ui_text(target):
            target = "the targeted argument or evidence"
        return "\n".join([
            f"{idx}. [{self.ui_en_text(item.get('dimension', '')) or 'Fact Challenge'}] Target: {target}",
            f"   - {self.weakness_text_en(item)}",
        ])

    def weakness_candidate_key(self, candidate):
        """Stable identity across card reordering and repeated scans."""
        side = str(candidate.get("side") or "").strip().lower()
        guide = self.weakness_plain_guide(candidate)
        core = "\n".join([
            str(guide.get("one_sentence_summary") or candidate.get("weakness") or ""),
            str(guide.get("core_problem") or ""),
            str(candidate.get("opponent_point") or candidate.get("targeting") or ""),
        ])
        normalized = re.sub(r"\s+", " ", core).strip().lower()
        return f"{side}:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()}"

    def tactic_combo_sections(self, state, items):
        positive_lines = []
        negative_lines = []
        for idx, item in enumerate(items, 1):
            block = self.tactic_candidate_block(item, idx)
            if item.get("side") == "positive":
                negative_lines.append(block)
            else:
                positive_lines.append(block)
        return "\n".join(positive_lines), "\n".join(negative_lines)

    def render_tactic_combo_text(self, state, items):
        positive_text, negative_text = self.tactic_combo_sections(state, items)
        return "\n".join([
            "## Nido Tactic Package",
            "",
            "Auto assignment: positive-side weaknesses are assigned to the negative side; negative-side weaknesses are assigned to the positive side.",
            "",
            "## Tactics For Positive Side",
            positive_text or "None.",
            "",
            "## Tactics For Negative Side",
            negative_text or "None.",
        ])

    def apply_tactic_combo_to_current_case(self, state, items):
        if not items:
            messagebox.showwarning("No Tactic Items", "Please add or drag at least one weakness into the Tactic Combo Window first.")
            return False
        positive_text, negative_text = self.tactic_combo_sections(state, items)
        if positive_text:
            self.append_text_to_widget(
                self.t_pos_args,
                "Tactic Package: for attacking negative-side weaknesses",
                positive_text,
            )
        if negative_text:
            self.append_text_to_widget(
                self.t_neg_args,
                "Tactic Package: for attacking positive-side weaknesses",
                negative_text,
            )
        return bool(positive_text or negative_text)

    def apply_weakness_candidate_to_current_case(self, candidate, forced_panel=None):
        if not candidate:
            return False
        text = self.tactic_candidate_block(candidate, 1)
        if forced_panel == "positive":
            self.append_text_to_widget(self.t_pos_args, "Tactic from dragged weakness", text)
            self.status_var.set("Status: dragged weakness appended to Positive arguments")
            return True
        if forced_panel == "negative":
            self.append_text_to_widget(self.t_neg_args, "Tactic from dragged weakness", text)
            self.status_var.set("Status: dragged weakness appended to Negative arguments")
            return True
        if candidate.get("side") == "positive":
            self.append_text_to_widget(self.t_neg_args, "Tactic Package: for attacking positive-side weaknesses", text)
            self.status_var.set("Status: positive-side weakness appended to Negative arguments")
        else:
            self.append_text_to_widget(self.t_pos_args, "Tactic Package: for attacking negative-side weaknesses", text)
            self.status_var.set("Status: negative-side weakness appended to Positive arguments")
        return True

    def weakness_full_text_for_current_case(self, candidate):
        """Return the complete readable card, without display-only color markers."""
        rendered = self.render_weakness_brief_report(candidate)
        rendered = re.sub(r"\[\[(?:TITLE|SECTION|LABEL|NEG_BLOCK|POS_BLOCK|END_BLOCK)\]\]", "", str(rendered or ""))
        return re.sub(r"\n{3,}", "\n\n", rendered).strip()

    def confirm_and_apply_dragged_weakness(self, candidate, forced_panel):
        if not candidate:
            return False
        side_name = "Positive arguments" if forced_panel == "positive" else "Negative arguments"
        surface = self.weakness_surface_conclusion(candidate, self.weakness_plain_guide(candidate))
        title = self.compact(surface.get("title") or self.weakness_text_en(candidate), 180)
        text = self.weakness_full_text_for_current_case(candidate)
        widget = self.t_pos_args if forced_panel == "positive" else self.t_neg_args
        existing = re.sub(r"\s+", " ", self.get_text(widget)).strip()
        incoming = re.sub(r"\s+", " ", text).strip()
        if incoming and incoming in existing:
            messagebox.showinfo(
                "Weakness Already Added",
                f"This weakness card already exists in {side_name} and was not added again.",
                parent=self.root,
            )
            self.status_var.set("Status: duplicate weakness was not added")
            return False
        confirmed = messagebox.askyesno(
            "Add Entire Weakness",
            f"Add the entire weakness card to {side_name}?\n\n{title}\n\n"
            "The full explanation, questions, and response preparation will be added.",
            parent=self.root,
        )
        if not confirmed:
            self.status_var.set("Status: weakness drop cancelled")
            return False
        self.append_text_to_widget(widget, "Entire Weakness Card", text)
        self.status_var.set(f"Status: entire weakness card appended to {side_name}")
        return True

    def apply_dragged_weakness_to_current_case(self, forced_panel):
        candidate = getattr(self, "dragging_weakness_candidate", None)
        if not candidate:
            return
        self.apply_weakness_candidate_to_current_case(candidate, forced_panel=forced_panel)
        self.dragging_weakness_candidate = None

    def show_weakness_drag_ghost(self, candidate):
        self.hide_weakness_drag_ghost()
        try:
            ghost = tk.Toplevel(self.root)
            ghost.overrideredirect(True)
            ghost.attributes("-topmost", True)
            ghost.configure(bg="#1f6feb")
            text = self.compact(self.weakness_text_en(candidate), 80)
            tk.Label(
                ghost,
                text=f"Drop weakness: {text}",
                bg="#1f6feb",
                fg="white",
                font=("Microsoft YaHei UI", 9, "bold"),
                padx=10,
                pady=5,
            ).pack()
            self._weakness_drag_ghost = ghost
            self.move_weakness_drag_ghost()
        except Exception:
            self._weakness_drag_ghost = None

    def move_weakness_drag_ghost(self, _event=None):
        self._weakness_drag_started = True
        ghost = getattr(self, "_weakness_drag_ghost", None)
        if not ghost:
            return
        try:
            ghost.geometry(f"+{self.root.winfo_pointerx() + 14}+{self.root.winfo_pointery() + 12}")
        except Exception:
            pass

    def left_mouse_is_down(self):
        try:
            return bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)
        except Exception:
            return False

    def start_weakness_drag_poll(self, combo_window=None):
        self._weakness_drag_polling = True

        def poll():
            if not getattr(self, "_weakness_drag_polling", False):
                return
            candidate = getattr(self, "dragging_weakness_candidate", None)
            if not candidate:
                self._weakness_drag_polling = False
                return
            try:
                sx, sy = getattr(self, "_weakness_drag_start_xy", (self.root.winfo_pointerx(), self.root.winfo_pointery()))
                px, py = self.root.winfo_pointerx(), self.root.winfo_pointery()
                if abs(px - sx) + abs(py - sy) >= 4:
                    self._weakness_drag_started = True
                    self.move_weakness_drag_ghost()
            except Exception:
                pass
            if not self.left_mouse_is_down():
                self._weakness_drag_polling = False
                self.finish_weakness_card_drag(combo_window=combo_window)
                return
            try:
                self.root.after(40, poll)
            except Exception:
                self._weakness_drag_polling = False

        try:
            self.root.after(40, poll)
        except Exception:
            self._weakness_drag_polling = False

    def hide_weakness_drag_ghost(self):
        ghost = getattr(self, "_weakness_drag_ghost", None)
        self._weakness_drag_ghost = None
        if ghost:
            try:
                ghost.destroy()
            except Exception:
                pass

    def finish_weakness_card_drag(self, combo_window=None):
        self._weakness_drag_polling = False
        candidate = getattr(self, "dragging_weakness_candidate", None)
        drag_started = bool(getattr(self, "_weakness_drag_started", False))
        self._weakness_drag_started = False
        pressed_card = getattr(self, "_pressed_weakness_card", None)
        self._pressed_weakness_card = None
        if pressed_card:
            try:
                pressed_card.pack_configure(fill=tk.X, padx=6, pady=5)
                pressed_card.configure(bg="#111827", highlightthickness=1, highlightbackground="#344054")
                for child in pressed_card.winfo_children():
                    child.configure(bg="#111827")
                    for grand in child.winfo_children():
                        try:
                            if isinstance(grand, tk.Label) and grand.cget("text") in {"DRAG", "DRAGGING"}:
                                grand.configure(bg="#1f6feb", fg="white", text="DRAG")
                        except Exception:
                            pass
            except Exception:
                pass
        bind_id = getattr(self, "_weakness_drag_release_bind", None)
        if bind_id:
            try:
                self.root.unbind_all("<ButtonRelease-1>")
            except Exception:
                pass
            self._weakness_drag_release_bind = None
        motion_bind_id = getattr(self, "_weakness_drag_motion_bind", None)
        if motion_bind_id:
            try:
                self.root.unbind_all("<B1-Motion>")
            except Exception:
                pass
            self._weakness_drag_motion_bind = None
        self.hide_weakness_drag_ghost()
        if not candidate:
            return False
        if not drag_started:
            self.dragging_weakness_candidate = None
            if combo_window is not None:
                combo_window.dragging_weakness_candidate = None
            return False
        try:
            if self.apply_dragged_weakness_by_pointer(candidate):
                return True
            if combo_window is not None and getattr(combo_window, "dragging_weakness_candidate", None):
                before = len(getattr(combo_window, "tactic_combo_items", []) or [])
                combo_window.finish_tactic_combo_drop()
                after = len(getattr(combo_window, "tactic_combo_items", []) or [])
                if after > before:
                    return True
            self.show_weakness_drop_menu(candidate, combo_window=combo_window)
            self.status_var.set("Status: choose where to place the dragged weakness")
            return False
        finally:
            self.dragging_weakness_candidate = None
            if combo_window is not None:
                combo_window.dragging_weakness_candidate = None

    def show_weakness_drop_menu(self, candidate, combo_window=None):
        if not candidate:
            return
        menu = tk.Menu(self.root, tearoff=0, bg="#111827", fg=self.C["text"], activebackground="#1f6feb", activeforeground="white")

        def add_positive():
            self.apply_weakness_candidate_to_current_case(candidate, forced_panel="positive")

        def add_negative():
            self.apply_weakness_candidate_to_current_case(candidate, forced_panel="negative")

        def add_combo():
            if combo_window is not None:
                try:
                    combo_window.deiconify()
                    combo_window.lift()
                    combo_window.add_tactic_candidate(candidate)
                    return
                except Exception:
                    pass
            self.status_var.set("Status: Tactic Combo window is not available for this card")

        menu.add_command(label="Add to Positive arguments", command=add_positive)
        menu.add_command(label="Add to Negative arguments", command=add_negative)
        menu.add_command(label="Add to Tactic Combo", command=add_combo)
        try:
            menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass

    def pointer_inside_widget(self, widget):
        try:
            px, py = self.root.winfo_pointerx(), self.root.winfo_pointery()
            wx, wy = widget.winfo_rootx(), widget.winfo_rooty()
            return 0 <= px - wx <= widget.winfo_width() and 0 <= py - wy <= widget.winfo_height()
        except Exception:
            return False

    def apply_dragged_weakness_by_pointer(self, candidate):
        if not candidate:
            return False
        # A weakness belongs to the opposing advocate: a positive-side weakness
        # becomes a negative-side argument and vice versa. Accept a drop anywhere
        # on the main case window so the user does not need to target a text box.
        try:
            px, py = self.root.winfo_pointerx(), self.root.winfo_pointery()
            widget = self.root.winfo_containing(px, py)
            if widget is not None and widget.winfo_toplevel() == self.root:
                forced_panel = "negative" if candidate.get("side") == "positive" else "positive"
                return self.confirm_and_apply_dragged_weakness(candidate, forced_panel=forced_panel)
        except Exception:
            pass
        return False

    def save_tactic_combo_package(self, state, items):
        positive_text, negative_text = self.tactic_combo_sections(state, items)
        structured = state.get("options", {}).get("structured_case", {}) if isinstance(state, dict) else {}
        pos_append = "\n\n[Tactic Package: for attacking negative-side weaknesses]\n" + positive_text if positive_text else ""
        neg_append = "\n\n[Tactic Package: for attacking positive-side weaknesses]\n" + negative_text if negative_text else ""
        payload = {
            "nido_tactic_combo_package": True,
            "version": "0.1",
            "case_name": state.get("options", {}).get("case_name") or self.case_name_var.get().strip(),
            "jurisdiction": state.get("jurisdiction") or self.jur_var.get().strip(),
            "background": self.get_text(self.t_bg),
            "case_text": self.get_text(self.t_bg),
            "pos_args": (structured.get("pos_args") or self.get_text(self.t_pos_args) + pos_append).strip(),
            "pos_ev": structured.get("pos_ev") or self.get_text(self.t_pos_ev),
            "neg_args": (structured.get("neg_args") or self.get_text(self.t_neg_args) + neg_append).strip(),
            "neg_ev": structured.get("neg_ev") or self.get_text(self.t_neg_ev),
            "tactic_combo": {
                "assignment_rule": "positive_weakness_to_negative; negative_weakness_to_positive",
                "for_positive": positive_text,
                "for_negative": negative_text,
                "selected": items,
            },
        }
        if pos_append and pos_append not in payload["pos_args"]:
            payload["pos_args"] = (payload["pos_args"] + pos_append).strip()
        if neg_append and neg_append not in payload["neg_args"]:
            payload["neg_args"] = (payload["neg_args"] + neg_append).strip()
        safe = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]+", "_", payload.get("case_name") or "tactic_combo").strip("_")
        default_dir = HERE / "tactic_combo_exports"
        default_dir.mkdir(parents=True, exist_ok=True)
        chosen = filedialog.asksaveasfilename(
            title="Save Tactic Package JSON",
            initialdir=str(default_dir),
            initialfile=f"{safe}_tactic_combo.json",
            defaultextension=".json",
            filetypes=[("Tactic Package JSON", "*.json"), ("All files", "*.*")],
        )
        if not chosen:
            return None
        path = Path(chosen)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")
        return path

    def selected_weakness_ids(self):
        raw = self.weakness_select_var.get().strip()
        if not raw:
            return [c.get("select_id") or c["id"] for c in self.weakness_candidates[:6]]
        ids = []
        for part in re.split(r"[,，\s;；]+", raw):
            part = part.strip().upper()
            if not part:
                continue
            part = part.replace("正方", "正").replace("反方", "反")
            if part.isdigit():
                part = f"正{int(part)}"
            elif part.startswith("正") and part[1:].isdigit():
                part = f"正{int(part[1:])}"
            elif part.startswith("反") and part[1:].isdigit():
                part = f"反{int(part[1:])}"
            ids.append(part)
        return ids

    def open_point_rebuttal_for_weakness(self, candidate, combo_window=None):
        target = self.ui_en_text(candidate.get("opponent_point") or candidate.get("targeting") or "")
        if self.bad_ui_text(target):
            target = "the targeted argument or evidence"
        weakness = self.weakness_text_en(candidate)
        side = candidate.get("side", "positive")
        side_label = "Positive side" if side == "positive" else "Negative side"
        attacker = "Negative side" if side == "positive" else "Positive side"
        kind = self.candidate_kind_en(candidate)
        tags = [self.ui_en_text(x) for x in (candidate.get("risk_tags") or [])]
        tags = ", ".join(x for x in tags if not self.bad_ui_text(x)) or "General weakness"
        point = "\n".join([
            f"Target object: {side_label} {kind} {candidate.get('opponent_point_index', '')}",
            f"Object content: {target}",
            f"Attackable weakness: {weakness}",
            f"Weakness tags: {tags}",
            f"Weakness source: {self.weakness_source_en(candidate)}",
            f"Attack direction: {attacker} attacks this weakness; {side_label} defends it.",
        ]).strip()
        report = self.generate_single_point_brief_report(
            candidate,
            point,
            "My New Argument/Evidence",
            candidate.get("dimension") or (DIMENSIONS[0][0] if DIMENSIONS else "Fact Challenge"),
        )
        self.open_weakness_brief_result_window(candidate, report, combo_window=combo_window)

    def generate_single_point_brief_report(self, candidate, point, point_mode, dimension):
        full_report = self.generate_single_point_two_rounds(point, point_mode, dimension)
        raw_r1 = self.extract_report_field(full_report, "攻击")
        raw_r2 = self.extract_report_field(full_report, "回应")
        tactic_names = self.extract_report_field(full_report, "识别招式")
        side_label = "Positive-side Weakness" if candidate.get("side", "positive") == "positive" else "Negative-side Weakness"
        attacker = "Negative side" if candidate.get("side", "positive") == "positive" else "Positive side"
        defender = "Positive side" if candidate.get("side", "positive") == "positive" else "Negative side"
        weakness = self.weakness_text_en(candidate)
        target = self.ui_en_text(candidate.get("opponent_point") or candidate.get("targeting") or "")
        if self.bad_ui_text(target):
            target = "the targeted argument or evidence"
        guide = self.weakness_plain_guide(candidate)
        return {
            "side_label": side_label,
            "attacker": attacker,
            "defender": defender,
            "side": candidate.get("side", "positive"),
            "dimension": candidate.get("dimension", dimension),
            "opponent_point_kind": candidate.get("opponent_point_kind", "argument"),
            "opponent_point_index": candidate.get("opponent_point_index", ""),
            "opponent_point": candidate.get("opponent_point", target),
            "target": target,
            "weakness": weakness,
            "plain_guide": guide,
            "risk_tags": candidate.get("risk_tags") or [],
            "source_label": candidate.get("source_label", ""),
            "priority_reason": candidate.get("priority_reason", ""),
            "tactic_names": tactic_names,
            "raw_r1": raw_r1,
            "raw_r2": raw_r2,
            "r1": self.court_attack_from_brief(raw_r1, attacker, defender, target, weakness, candidate.get("risk_tags") or []),
            "r2": self.court_defense_from_brief(raw_r2, attacker, defender, target, weakness, candidate.get("risk_tags") or []),
            "moves": self.extract_report_field(full_report, "可用后招"),
            "needed": self.extract_report_section(full_report, "需要补强材料"),
        }

    def court_attack_from_brief(self, raw, attacker, defender, target, weakness, tags=None):
        target = self.compact(self.ui_en_text(target), 100)
        weakness_en = self.compact(self.ui_en_text(weakness), 180)
        tags = set(tags or [])
        if target or weakness_en:
            return (
                f"The attacking side should press {defender} on {target or 'this point'}. "
                f"The gap is: {weakness_en or 'the factual basis, evidence source, rule application, or causal chain is not closed'}. "
                "Require the opponent to identify the exact fact proved, the source of the evidence, the applicable rule, and the proof burden before the conclusion can advance."
            )
        if "取证合法性" in tags:
            return (
                f"{defender}，你方不能只说材料内容对你有利。"
                "请先说明这份材料如何取得、由谁取得、是否经过授权，取得过程是否违反隐私、平台规则或其他强制性边界；"
                "如果取得方式站不住，内容本身就不能直接支撑你方主张。"
            )
        if "证据可采性" in tags:
            return (
                f"{defender}，这份材料要先过证据使用门槛。"
                "请说明原始来源、提交路径、完整链条和上下文是否齐全；"
                "不能把一份未经完整说明的材料直接当成已被法院接受的事实。"
            )
        if any(x in target + weakness for x in ["页面截图", "课程页面", "平台页面", "网页", "页面缓存", "宣传页面", "广告页面", "动态页面", "后台原始数据", "完整滚动截屏"]):
            return (
                f"{defender}，你方提交的课程或平台页面截图，首先要证明它是完整、未经篡改的交易当时页面。"
                "请提交后台原始配置、页面发布时间、版本记录或展示日志；"
                "线上平台可能存在动态页面、缓存差异或不同用户展示版本，单张截图不能当然证明这就是购买时所见的最终页面。"
                "如果页面下方或折叠部分存在课程可调整、退款限制或免责声明，而你方没有提交完整滚动截屏，就属于选择性呈现。"
            )
        if "责任倒置" in tags:
            return (
                f"{defender}，你方现在是在要求我方证明自己没有责任。"
                "请先回到证明责任：是哪一方提出这个主张，哪一方掌握关键事实，哪一方应当先完成证明门槛？"
            )
        if "反向法律责任" in tags:
            return (
                f"{defender}，你方这种取证、投诉或施压方式本身可能引出反向责任。"
                "请说明你方行为的合法边界在哪里，为什么它不是越权取证、不当施压或把民事争议包装成外部压力。"
            )
        if any(x in tags for x in ("跨界", "跨Jurisdiction", "平台/监管规则", "隐私/商业秘密")):
            return (
                f"{defender}，你方引用的平台、监管或外部规则，不能自动变成本案法律依据。"
                "请明确它在本Jurisdiction、本交易、本证据中的适用入口；"
                "如果只是谈判压力或参考材料，就不能替代本案构成要件。"
            )
        if any(x in weakness for x in ["时间", "日期", "起算", "寄出", "送达", "版本", "当时"]):
            return (
                f"{defender}，你方这份材料只能说明后来有这个说法，不能证明关键时点已经适用。"
                f"请你方明确：每一个关键动作发生在什么日期、什么时间、依据的是哪个当时版本？"
            )
        if any(x in weakness for x in ["连续", "原始", "时间戳", "封条", "视频", "影像"]):
            return (
                f"{defender}，你方证据缺少连续过程和原始来源，不能直接证明完整事实链。"
                "请说明原始文件在哪里、时间戳是否连续、是否能排除中间被剪辑或选择性提交。"
            )
        if any(x in weakness for x in ["因果", "导致", "原因", "介入"]):
            return (
                f"{defender}，即使你方说的结果存在，也不能自动推出就是我方行为导致。"
                "请说明你方如何排除了其他原因、第三方因素和自身行为影响。"
            )
        if any(x in weakness for x in ["金额", "费用", "损失", "商誉", "量化"]):
            return (
                f"{defender}，你方请求仍缺少金额计算和直接因果。"
                "请说明金额怎么来、为什么必要、与被指行为之间的直接连接在哪里。"
            )
        if any(x in weakness for x in ["法律", "规则", "适用", "条件", "证明责任"]):
            return (
                f"{defender}，你方不能只引用规则名称就跳到结论。"
                "请逐项说明适用条件、例外限制、补救范围和证明责任是否已经完成。"
            )
        return (
            f"{defender}，围绕“{target}”，你方还没有把事实前提、证据来源和证明责任闭合。"
            f"请先回答这个缺口：{weakness}"
        )

    def court_defense_from_brief(self, raw, attacker, defender, target, weakness, tags=None):
        target = self.compact(self.ui_en_text(target), 100)
        weakness_en = self.compact(self.ui_en_text(weakness), 180)
        tags = set(tags or [])
        if target or weakness_en:
            return (
                f"The defending side should keep the response limited to {target or 'this point'}. "
                f"Answer the alleged gap directly: {weakness_en or 'the opponent says the proof path is incomplete'}. "
                "Separate admissibility, factual weight, legal application, and remedy scope; concede any narrow evidentiary supplement without weakening the overall position."
            )
        if "取证合法性" in tags:
            return (
                f"{attacker}攻击的是取得过程，本方就把问题限定在合法来源和使用范围。"
                "本方将说明材料取得主体、授权基础、保存链条和提交目的；"
                "即使个别使用范围需要限缩，也不等于本方核心事实当然不存在。"
            )
        if "证据可采性" in tags:
            return (
                f"{attacker}质疑可采性，本方会先补足原始来源、完整上下文和提交路径。"
                "但对方不能把形式审查直接扩大成事实不存在；"
                "该材料至少可以与其他证据相互印证，证明力范围由法院判断。"
            )
        if "责任倒置" in tags:
            return (
                f"{attacker}提出证明责任问题，本方接受先分配证明对象。"
                "本方只证明本方应证明的事实；"
                "对方若主张排除、替代原因或免责事实，也必须拿出自己的反证基础。"
            )
        if "反向法律责任" in tags:
            return (
                f"{attacker}把问题转向反向责任，本方先限定行为目的和合法边界。"
                "本方不会把外部投诉或平台材料当作当然裁判依据，只把其中可核验事实用于本案证明；"
                "超出部分可以限缩，不影响可证明部分。"
            )
        if any(x in tags for x in ("跨界", "跨Jurisdiction", "平台/监管规则", "隐私/商业秘密")):
            return (
                f"{attacker}要求区分Jurisdiction和规则来源，本方接受这个边界。"
                "本方将把本Jurisdiction强制规则作为主依据，把平台、监管或外Jurisdiction材料只作为解释、行业背景或补强材料；"
                "对方不能因为辅助材料需要限缩，就否定本方在本Jurisdiction下的核心请求。"
            )
        if any(x in weakness for x in ["时间", "日期", "起算", "寄出", "送达", "版本", "当时"]):
            return (
                f"{attacker}把问题扩大了。本方只需要在这一条上说明关键时点和规则来源。"
                "本方将用节点表、当时版本材料和形成时间说明该证据与主张之间的对应关系；"
                "即使个别节点需要补充，也不影响本方总立场。"
            )
        if any(x in weakness for x in ["连续", "原始", "时间戳", "封条", "视频", "影像"]):
            return (
                f"{attacker}质疑的是证明力范围，不是事实当然不存在。"
                "本方会用原始文件、连续时间戳、提交记录和其他材料交叉印证该证据；"
                "不能因为对方提出抽象质疑，就否定该证据的全部价值。"
            )
        if any(x in weakness for x in ["因果", "导致", "原因", "介入"]):
            return (
                f"{attacker}提出替代原因，应当说明替代原因的事实基础。"
                "本方会把行为、结果和损失之间的时间顺序及关联材料固定下来；"
                "对方不能只用可能性切断本方因果链。"
            )
        if any(x in weakness for x in ["金额", "费用", "损失", "商誉", "量化"]):
            return (
                f"{attacker}针对金额的质疑，本方可以把请求限缩到已能证明的范围。"
                "本方将提交金额明细、计算依据和必要性说明；未完全量化的部分保留补证或替代请求。"
            )
        if any(x in weakness for x in ["法律", "规则", "适用", "条件", "证明责任"]):
            return (
                f"{attacker}要求逐项适用，本方接受这个框架。"
                "本方会把规则条件、事实对应和补救请求分开说明；对方不能把需要解释的适用问题直接说成请求不成立。"
            )
        return (
            f"{attacker}的攻击只能限于这一条Weakness。本方会围绕“{target}”补足事实前提、证据来源和对应关系；"
            "该Weakness至多影响证明范围，不当然推翻本方总立场。"
        )

    def extract_report_field(self, report, label):
        pattern = rf"^{re.escape(label)}[:：](.+)$"
        for line in report.splitlines():
            m = re.match(pattern, line.strip())
            if m:
                return m.group(1).strip()
        return ""

    def extract_report_section(self, report, title):
        marker = f"## {title}"
        pos = report.find(marker)
        if pos < 0:
            return ""
        rest = report[pos + len(marker):].strip()
        next_pos = rest.find("\n[[")
        if next_pos >= 0:
            rest = rest[:next_pos].strip()
        return rest

    def ai_full_card_explanation_prompt(self, report):
        guide = report.get("plain_guide") or {}
        surface = self.weakness_surface_conclusion(report, guide)
        missing = guide.get("missing_evidence_or_step") or []
        if isinstance(missing, str):
            missing = [missing]
        source = guide.get("source") or report.get("source_label") or "Local weakness scan"
        context = "\n".join([
            f"Existing weakness explanation: {guide.get('one_sentence_summary') or guide.get('summary') or report.get('weakness', '')}",
            f"Currently identified missing link or material: {'; '.join(str(x) for x in missing[:5])}",
        ])
        case_facts = self.get_text(self.t_bg)[:6000]
        return f'''You are a senior legal weakness reviewer. Read the complete matter and the identified weakness together from the named review dimension. Diagnose only the weakness that exists in the material and explain why it exists.

Weakness conclusion:
{surface['title']}

Original statement or evidence being examined:
{surface['target']}

Existing local analysis:
{context}

Case facts:
{case_facts}

Target side:
{report.get('defender', 'Positive side')}

Weakness source:
{source}

Internal analysis dimension:
{report.get('dimension', 'Fact Challenge')}

Constraints:
- Write natural connected prose in English. Do not return JSON.
- Do not fill a template, checklist, card schema, or fixed series of headings.
- Do not begin with "This card means" and do not mechanically insert labels such as "What the material proves", "What it does not prove", "A simple example", "Questions a lawyer can ask", or "To answer this point".
- Explain the weakness in the order that best fits this particular matter. Identify the precise vulnerable claim, evidence, inference, omission, or contradiction; explain the supplied facts that expose it; and state its significance and limits.
- Use headings only when they naturally improve this particular explanation; choose the headings yourself.
- Bind the analysis to concrete facts actually supplied in the case material.
- Never use internal labels such as Evidence angle, Mapping-back, Frame, Cross-Boundary, Argument 1, or model-routing terminology as substantive content.
- Do not invent a name, date, amount, document, clause, statute, or event. If the case does not supply a date or amount, say that no specific date or amount is supplied and make that absence part of the question where relevant.
- Do not say a claim is false merely because its source document has not yet been shown. Explain the narrower proof limitation accurately.
- Stay focused on this one weakness. Do not introduce unrelated weaknesses.
- It is acceptable to conclude that the point is limited, uncertain, curable, or not decisive.
- Do not provide lawyer questions, attack scripts, recommendations, cures, response language, preparation steps, strategy, or everyday examples. The lawyer will decide what to do with the diagnosis.

Return only the finished internal analysis, with no preface about these instructions.'''

    def render_ai_full_card_explanation(self, result):
        if isinstance(result, str):
            text = result.strip()
            text = re.sub(r"^```(?:markdown|md|text)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
            return text.strip() or "No explanation was returned."
        if not isinstance(result, dict):
            return str(result or "").strip() or "No explanation was returned."

        # Old saved records may contain advisory fields. Preserve only their
        # diagnostic content so they do not recreate the retired template.
        parts = []
        for key in (
            "one_sentence_summary", "full_analysis", "analysis",
            "plain_explanation", "core_problem", "relevant_facts",
            "what_it_proves", "what_it_does_not_prove", "source_explanation",
        ):
            value = result.get(key)
            if isinstance(value, (list, tuple)):
                value = "\n".join(str(item).strip() for item in value if str(item).strip())
            value = str(value or "").strip()
            if value and value not in parts:
                parts.append(value)
        return "\n\n".join(parts) or "No diagnostic explanation was returned."

    def open_weakness_brief_result_window(self, candidate, report, combo_window=None):
        win = tk.Toplevel(self.root)
        win.title("Single-Point Weakness Opposition")
        win.geometry("900x640")
        win.configure(bg=self.C["panel"])

        top = tk.Frame(win, bg=self.C["panel"], padx=12, pady=10)
        top.pack(fill=tk.X)
        tk.Label(
            top,
            text=self.ui_en_text(report.get("side_label", "Weakness")),
            bg=self.C["panel"],
            fg=self.C["gold"],
            font=("Microsoft YaHei UI", 14, "bold"),
        ).pack(anchor="w")
        tk.Label(
            top,
            text=self.compact(self.ui_en_text(report.get("target", "")), 180),
            bg=self.C["panel"],
            fg=self.C["muted"],
            font=("Microsoft YaHei UI", 10),
            anchor="w",
            justify=tk.LEFT,
            wraplength=820,
        ).pack(fill=tk.X, pady=(4, 0))

        t = scrolledtext.ScrolledText(win, bg=self.C["entry"], fg=self.C["text"], font=("Microsoft YaHei UI", 11), wrap=tk.WORD, relief="flat")
        self.bind_local_scroll(t)
        t.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        self.configure_output_tags(t)
        self.insert_colored(t, self.render_weakness_brief_report(report))
        t.config(state=tk.DISABLED)

        controls = tk.Frame(win, bg=self.C["panel"], padx=12, pady=(0, 12))
        controls.pack(fill=tk.X)

        def add_positive():
            self.apply_weakness_candidate_to_current_case(candidate, forced_panel="positive")
            win.lift()

        def add_negative():
            self.apply_weakness_candidate_to_current_case(candidate, forced_panel="negative")
            win.lift()

        def add_combo():
            if combo_window is not None:
                try:
                    combo_window.deiconify()
                    combo_window.lift()
                    combo_window.add_tactic_candidate(candidate)
                    return
                except Exception:
                    pass
            self.status_var.set("Status: Tactic Combo window is not available for this detail window")

        def explain_with_model():
            if not self.has_verified_external_provider():
                messagebox.showwarning("No Verified Model", "Please verify a model provider before requesting an AI plain-language explanation.")
                return
            if self.confidential_var.get() == "Local-only confidentiality":
                messagebox.showinfo(
                    "Local Confidentiality Mode",
                    "This card is currently local-only. Switch to External aid after redaction or Authorized cloud expert before sending this single-card excerpt to a model provider.",
                )
                return
            if not self.ensure_real_case_external_privacy_gate("AI Full Card Explanation"):
                return
            ai_btn.config(state=tk.DISABLED, text="Explaining...")
            self.status_var.set("Status: generating plain-language full weakness card...")

            def worker():
                try:
                    result = self.call_cloud_text(self.ai_full_card_explanation_prompt(report), max_tokens=4500)
                    rendered = self.render_ai_full_card_explanation(result)

                    def apply_result():
                        t.config(state=tk.NORMAL)
                        t.delete("1.0", tk.END)
                        self.insert_colored(t, rendered)
                        t.config(state=tk.DISABLED)
                        ai_btn.config(state=tk.NORMAL, text="Refresh AI Explanation")
                        self.status_var.set("Status: AI plain-language full card complete")
                        win.lift()

                    self.root.after(0, apply_result)
                except Exception as exc:
                    error = str(exc)[:800]

                    def show_error():
                        ai_btn.config(state=tk.NORMAL, text="Explain With Verified Model")
                        self.status_var.set("Status: AI full-card explanation failed")
                        messagebox.showerror("AI Explanation Failed", error)

                    self.root.after(0, show_error)

            threading.Thread(target=worker, daemon=True).start()

        tk.Button(controls, text="Add to Positive", command=add_positive, bg="#114b5f", fg="white", relief="flat", padx=16, pady=7).pack(side=tk.LEFT)
        tk.Button(controls, text="Add to Negative", command=add_negative, bg="#6f1d3b", fg="white", relief="flat", padx=16, pady=7).pack(side=tk.LEFT, padx=8)
        tk.Button(controls, text="Add to Tactic Combo", command=add_combo, bg="#8a5a13", fg="white", relief="flat", padx=16, pady=7).pack(side=tk.LEFT)
        ai_btn = tk.Button(controls, text="Explain With Verified Model", command=explain_with_model, bg="#315c8c", fg="white", relief="flat", padx=16, pady=7)
        ai_btn.pack(side=tk.LEFT, padx=8)
        tk.Button(controls, text="Close", command=win.destroy, bg="#333", fg=self.C["text"], relief="flat", padx=16, pady=7).pack(side=tk.RIGHT)
        if (
            not candidate.get("whole_case_model_scan")
            and self.has_verified_external_provider()
            and self.confidential_var.get() in ("External aid after redaction", "Authorized cloud expert")
        ):
            win.after(200, explain_with_model)

    def standard_weakness_brief_markdown(self, report, original_content):
        provider = str(report.get("provider") or (report.get("plain_guide") or {}).get("provider") or "Offline local workflow")
        model = str(report.get("model") or (report.get("plain_guide") or {}).get("model") or "No external model recorded")
        needed = report.get("needed") or (report.get("plain_guide") or {}).get("missing_evidence_or_step") or []
        if isinstance(needed, str):
            needed = [line.strip("- ") for line in needed.splitlines() if line.strip()]
        standard = build_standard_report(
            "single_point_review",
            "single_point_weakness_review",
            self.case_name_var.get().strip() or "Current matter",
            self.jur_var.get(),
            findings=[{
                "id": report.get("id") or "SP-001",
                "dimension": self.dim_label(report.get("dimension", "")),
                "title": report.get("weakness") or report.get("side_label") or "Single-point weakness",
                "finding": report.get("weakness") or original_content,
                "affected_side": report.get("side_label") or report.get("side") or "Not assigned",
                "factual_basis": report.get("target") or report.get("opponent_point") or "",
                "evidence_references": [report.get("source_label")] if report.get("source_label") else [],
                "significance": report.get("priority_reason") or "Materiality requires lawyer assessment",
                "confidence": report.get("confidence") or "Not independently scored",
                "provider": provider,
                "model": model,
                "source_reference": report.get("source_label") or "Single-point weakness result",
                "review_status": "ai_generated_unverified",
            }],
            provider_runs=[{"provider": provider, "model": model, "engine_source": "Single-point review", "run_reference": report.get("dimension")}],
            input_scope={"target_point": report.get("target") or report.get("opponent_point"), "dimension": self.dim_label(report.get("dimension", ""))},
            sections={
                "attack_response_matrix": [{
                    "attack": report.get("r1") or report.get("raw_r1") or "Not separately recorded",
                    "response": report.get("r2") or report.get("raw_r2") or "Not separately recorded",
                    "lawyer_status": "ai_generated_unverified",
                }],
                "original_analysis": original_content,
            },
            missing_material=needed,
            synthetic=bool(report.get("synthetic") or report.get("synthetic_analogue")),
        )
        return render_standard_markdown(standard)

    def render_weakness_brief_report(self, report):
        attacker = self.ui_en_text(report.get("attacker", "Negative side")) or "Negative side"
        defender = self.ui_en_text(report.get("defender", "Positive side")) or "Positive side"
        guide = report.get("plain_guide") or {}
        full_dimension_report = str(guide.get("full_dimension_report") or report.get("full_dimension_report") or "").strip()
        if full_dimension_report:
            return self.standard_weakness_brief_markdown(report, full_dimension_report)
        if isinstance(guide.get("model_full_card"), dict):
            content = self.render_ai_full_card_explanation(guide["model_full_card"])
            return self.standard_weakness_brief_markdown(report, content)
        tags = [self.ui_en_text(x) for x in (report.get("risk_tags") or [])]
        tags = ", ".join(x for x in tags if not self.bad_ui_text(x)) or "General weakness"
        source = self.ui_en_text(report.get("source_label", ""))
        if self.bad_ui_text(source) or source.strip(" []/;,:") == "":
            source = "Local weakness scan"
        ranking = self.ui_en_text(report.get("priority_reason", ""))
        if self.bad_ui_text(ranking) or ranking.strip(" []/;,:") == "":
            ranking = "Prioritized by proof, evidence, and rule-application risk"
        weakness = self.ui_en_text(report.get("weakness", ""))
        if self.bad_ui_text(weakness) or weakness.strip(" []/;,:") == "":
            weakness = "This point leaves an attackable gap in proof, rule application, or causation."
        name = guide.get("name") or "Attackable weakness"
        summary = guide.get("one_sentence_summary") or guide.get("summary") or weakness
        strategy = guide.get("strategy") or "Turn the broad assertion into specific questions about facts, evidence, rules, and the link between them."
        hit = guide.get("signal_of_success") or guide.get("hit") or "The other side cannot give a precise answer and falls back to broad conclusions."
        defense = guide.get("defense") or ""
        target = guide.get("target") or self.ui_en_text(report.get("target", "")) or "the targeted point"
        target_claim = guide.get("target_claim_or_element") or target
        mapping_checklist = guide.get("mapping_checklist") or {}
        missing_items = guide.get("missing_evidence_or_step") or []
        attack_script = guide.get("attack_script") or []
        severity = guide.get("severity") or "Medium"
        source_line = guide.get("source") or source
        reason_line = guide.get("reason") or ranking
        surface = self.weakness_surface_conclusion(report, guide)
        missing_text = "\n".join(missing_items) or "The supporting material or intermediate proof step identified by this card still needs to be checked."
        questions_text = "\n".join(attack_script)
        source_explanation = (
            "This point was identified by comparing the selected statement or evidence with the proof questions generated during the local weakness scan. "
            "It remains a preparation point until the original record and surrounding context are checked."
        )
        question_lines = []
        for line in attack_script:
            clean = re.sub(r"^\s*\d+[.)]\s*", "", str(line).strip())
            if clean:
                question_lines.append(f"- {clean}")
        low_target = surface["target"].lower()
        if any(word in low_target for word in ("renovation contract", "contract", "agreement")):
            plain_opening = (
                "The case summary records a renovation contract but does not identify its exact parties, work scope, price, payment terms, or variation procedure."
            )
            plain_problem = (
                "If a party wants to rely on the contract to claim payment or resist payment, the signed contract and its actual terms matter. "
                "Without them, the summary can describe the dispute, but it cannot settle the scope of the work, the payment obligation, or responsibility for changes requested by the new owner."
            )
            question_lines = [
                "- Is there a signed copy of the renovation contract?",
                "- Who are the parties named in it, and who is required to pay?",
                "- What does it say about the original work scope and price?",
                "- How does it require variations or additional work to be approved?",
                "- Did the original owner approve, know about, or later accept the changes requested by the new owner?",
            ]
            answer_text = (
                "The party relying on the contract should produce the signed agreement, the relevant payment and variation clauses, and any messages or conduct showing that the later changes were authorised or accepted."
            )
            closing_text = "In short, the issue is not simply whether a contract was mentioned. The issue is what the contract actually required and whether the later work and payment claim fit those terms."
        else:
            plain_opening = self.ui_en_text(
                guide.get("plain_explanation") or guide.get("one_sentence_summary")
                or guide.get("summary") or weakness
            )
            plain_problem = self.ui_en_text(
                guide.get("core_problem") or guide.get("reason")
                or "The available material does not yet supply the specific fact, source record, or legal link required for this conclusion."
            )
            if not surface["target"]:
                question_lines = [
                    "- Which specific case assertion is being relied on?",
                    "- What source document or witness evidence directly supports that assertion?",
                    "- Which legal element does that evidence establish?",
                    "- What further step connects that evidence to the requested result?",
                ]
            answer_text = (
                defense if defense else "The party relying on this point should produce the source record and explain clearly how it supports the larger conclusion."
            )
            closing_text = "Use this point only after checking the original record and the missing evidentiary or legal link identified above."
        original_content = "\n".join([
            f"[[TITLE]]# {surface['title']}",
            "",
            plain_opening,
            "",
            plain_problem,
            "",
            "[[NEG_BLOCK]]Questions that can be asked:",
            "\n".join(question_lines),
            "[[END_BLOCK]]",
            "",
            f"[[POS_BLOCK]]How this point can be answered: {answer_text}",
            "[[END_BLOCK]]",
            "",
            closing_text,
        ])
        return self.standard_weakness_brief_markdown(report, original_content)

    def full_card_passes_specificity_check(self, summary, target_claim, missing_items, attack_script, mapping_checklist):
        fields = [
            str(summary or ""),
            str(target_claim or ""),
            "\n".join(missing_items or []),
            "\n".join(attack_script or []),
            str((mapping_checklist or {}).get("case_specific_missing_evidence", "")),
        ]
        if any(self.is_placeholder_case_target(field) for field in fields):
            return False
        summary_ok = self.has_case_specific_marker(fields[0]) or self.has_case_specific_marker(fields[1])
        attack_ok = any(self.has_case_specific_marker(line) for line in (attack_script or []))
        missing_ok = any(self.has_case_specific_marker(line) for line in (missing_items or []))
        checklist_ok = self.has_case_specific_marker(str((mapping_checklist or {}).get("case_specific_missing_evidence", "")))
        return bool(summary_ok and attack_ok and missing_ok and checklist_ok)

    def simulate_selected_weaknesses(self):
        if not self.last_weakness_state or not self.weakness_candidates:
            messagebox.showwarning("No Weakness Scan", 'Please click "Scan Weaknesses" first.')
            return
        ids = set(self.selected_weakness_ids())
        chosen = [c for c in self.weakness_candidates if (c.get("select_id") or c.get("id")) in ids or c.get("id") in ids]
        if not chosen:
            messagebox.showwarning("Weakness Number Not Found", "No matching weakness number was found. Examples: P1, N2.")
            return
        if len(chosen) == 1:
            self.open_point_rebuttal_for_weakness(chosen[0])
            return
        first_side = chosen[0].get("side", "positive")
        if isinstance(self.last_weakness_state, dict) and first_side == "negative" and self.last_weakness_state.get("negative_state"):
            state = copy.deepcopy(self.last_weakness_state["negative_state"])
        elif isinstance(self.last_weakness_state, dict) and self.last_weakness_state.get("positive_state"):
            state = copy.deepcopy(self.last_weakness_state["positive_state"])
        else:
            state = copy.deepcopy(self.last_weakness_state)
        chosen = [c for c in chosen if c.get("side", first_side) == first_side]
        dims = {c["dimension"] for c in chosen}
        state["workflow_mode"] = "selected_weakness_simulation"
        state["lawyer_selected_weaknesses"] = chosen
        state["selected_dimensions"] = [d for d in state.get("selected_dimensions", []) if d in dims]
        rounds = state.get("rounds", {})
        for key in ("round1_opponent_attack", "round2_my_rebuttal"):
            rounds[key] = [x for x in rounds.get(key, []) if x.get("dimension") in dims]
        rounds.pop("round3_opponent_response", None)
        rounds.pop("round4_my_final", None)
        self.last_state = state
        self.save_run_artifacts(state)
        self.render_state(state)
        self.status_var.set("Status: offline simulation completed for selected weaknesses")

    def _offline_advanced_model_call(self, route, prompt, temperature=0.68, max_tokens=4200, **_kwargs):
        provider = str(route.get("name") or "custom").strip().lower()
        api_key = str(route.get("key") or "").strip()
        base_url = str(route.get("base_url") or "").strip().rstrip("/")
        model = str(route.get("model") or "").strip()
        if not api_key or not base_url or not model:
            raise RuntimeError(f"{provider or 'provider'} is missing its key, endpoint, or model name")

        preset = PROVIDER_PRESETS.get(provider, PROVIDER_PRESETS.get("deepseek", {}))
        kind = preset.get("kind", "openai")
        if kind == "anthropic":
            url = base_url + "/messages"
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            payload = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            }
            data = self.http_json(url, headers, payload)
            return "\n".join(
                block.get("text", "") for block in data.get("content", [])
                if isinstance(block, dict)
            ).strip()

        if kind == "gemini_native":
            url = f"{base_url}/models/{model}:generateContent?key={urllib.parse.quote(api_key)}"
            payload = {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                },
            }
            data = self.http_json(url, {"Content-Type": "application/json"}, payload)
            return "\n".join(
                part.get("text", "")
                for candidate in data.get("candidates", [])
                for part in candidate.get("content", {}).get("parts", [])
                if isinstance(part, dict) and part.get("text")
            ).strip()

        url = base_url if base_url.endswith("/chat/completions") else base_url + "/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        data = self.http_json(
            url,
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            payload,
        )
        return str(data.get("choices", [{}])[0].get("message", {}).get("content", "")).strip()

    def _prepared_full_matter_for_advanced_opposition(self):
        sections = [
            ("CASE NAME", self.case_name_var.get().strip()),
            ("JURISDICTION", self.jur_var.get().strip()),
            ("FULL CASE BACKGROUND", self.get_text(self.t_bg)),
            ("POSITIVE-SIDE ARGUMENTS", self.get_text(self.t_pos_args)),
            ("POSITIVE-SIDE EVIDENCE", self.get_text(self.t_pos_ev)),
            ("NEGATIVE-SIDE ARGUMENTS", self.get_text(self.t_neg_args)),
            ("NEGATIVE-SIDE EVIDENCE", self.get_text(self.t_neg_ev)),
        ]
        matter = "\n\n".join(f"===== {title} =====\n{text}" for title, text in sections if text)
        if self.confidential_var.get() == "External aid after redaction":
            matter = self._redact_external_matter(matter)
        return matter

    def choose_offline_opposition_mode(self):
        if self.running:
            return
        from Nido_Advanced_Main_Opposition_2R_EN import show_main_opposition_mode_dialog
        show_main_opposition_mode_dialog(
            self.root,
            self.run_attack,
            self.open_offline_advanced_main_opposition,
        )

    def open_offline_advanced_main_opposition(self):
        from Nido_Advanced_Main_Opposition_2R_EN import open_advanced_main_opposition_review

        mode = self.confidential_var.get()
        all_routes = self.verified_provider_snapshots()
        routes = self.verified_private_provider_snapshots() if mode == "Local-only confidentiality" else all_routes
        if not routes:
            if mode == "Local-only confidentiality":
                self.show_local_model_required_dialog(
                    public_model_detected=bool(all_routes),
                    on_redacted_continue=self.open_offline_advanced_main_opposition,
                )
            else:
                messagebox.showwarning(
                    "Verified Model Required",
                    "Verify at least one model provider before starting Advanced Main Opposition 2R.",
                    parent=self.root,
                )
            return
        if not self.get_text(self.t_bg):
            messagebox.showwarning("Missing Case Background", "Please enter or import the case background.")
            return
        if not self.ensure_real_case_external_privacy_gate("Advanced Main Opposition 2R"):
            return
        mode = self.confidential_var.get()
        routes = self.verified_private_provider_snapshots() if mode == "Local-only confidentiality" else self.verified_provider_snapshots()
        if not routes:
            messagebox.showwarning("Verified Model Required", "No provider is available under the selected confidentiality boundary.")
            return
        privacy = {
            "Local-only confidentiality": "Only verified local or private-model endpoints receive the complete prepared matter.",
            "External aid after redaction": "The prepared matter is redacted before every external model call.",
            "Authorized cloud expert": "Authorized original-text assistance is active for all 36 calls.",
        }.get(mode, mode)
        open_advanced_main_opposition_review(
            self.root,
            self._prepared_full_matter_for_advanced_opposition(),
            routes,
            self.case_name_var.get().strip() or "Current Matter",
            privacy,
            model_caller=self._offline_advanced_model_call,
        )

    def run_attack(self):
        if self.running:
            return
        selected = self.selected_dimensions()
        if not selected:
            messagebox.showwarning("No Dimension Selected", "Please select at least one opposition dimension.")
            return
        case_text = self.get_text(self.t_bg)
        if not case_text:
            messagebox.showwarning("Missing Case Background", "Please enter or import the case background.")
            return
        if not self.ensure_real_case_external_privacy_gate("Start Opposition"):
            return

        self.running = True
        self.set_weakness_scan_controls_locked(True)
        self.status_var.set("Status: running local opposition...")
        self.clear_outputs()
        threading.Thread(target=self._run_attack_thread, args=(selected,), daemon=True).start()

    def _run_attack_thread(self, selected):
        try:
            self.log("Starting local opposition. Full case text is not uploaded.")
            self.log(
                "Offline side model route: positive -> "
                f"{self.positive_provider_route_var.get()}; negative -> {self.negative_provider_route_var.get()}"
            )
            state = self.run_nido_local_state(selected, workflow_mode="full_attack")
            self.last_state = state
            self.save_run_artifacts(state)
            self.root.after(0, lambda: self.render_state(state))
            self.root.after(0, lambda: self.status_var.set("Status: opposition complete"))
        except Exception as exc:
            self.root.after(0, lambda: messagebox.showerror("Opposition Failed", str(exc)))
            self.root.after(0, lambda: self.status_var.set("Status: opposition failed"))
        finally:
            self.running = False
            self.root.after(0, lambda: (
                self.set_weakness_scan_controls_locked(False),
                self.progress.stop(), self.progress.pack_forget(),
                self.run_btn.config(state=tk.NORMAL),
            ))

    def clear_outputs(self):
        for w in self.outputs.values():
            w.delete("1.0", tk.END)

    def log(self, text):
        stamp = _dt.datetime.now().strftime("%H:%M:%S")
        if "log" in self.outputs:
            self.outputs["log"].insert(tk.END, f"[{stamp}] {text}\n")
            self.outputs["log"].see(tk.END)
        else:
            self.status_var.set(f"Status: {text}")

    def render_state(self, state):
        self.clear_outputs()
        self.insert_colored(self.outputs["attacks"], self.render_attack_details(state))
        self.outputs["json"].insert(tk.END, json.dumps(self.display_state_for_json(state), ensure_ascii=False, indent=2))
        self.nb.select(self.output_tabs.get("attacks", self.nb.tabs()[0]))

    def display_state_for_json(self, state):
        def clean_display_string(text):
            raw = str(text or "")
            dim = self.dim_label(raw)
            if dim != raw:
                return dim
            cleaned = self.ui_en_text(raw)
            cleaned = re.sub(r"[^A-Za-z0-9_ .,:;\-/\[\]\(\)\{\}'\"|]+", " ", cleaned)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            if re.search(r"[\u4e00-\u9fff]", raw) and len(re.findall(r"[A-Za-z]", cleaned)) < 3:
                return "[internal non-English text hidden in display JSON]"
            return cleaned or raw

        def convert(value):
            if isinstance(value, dict):
                return {str(k): convert(v) for k, v in value.items()}
            if isinstance(value, list):
                return [convert(v) for v in value]
            if isinstance(value, str):
                return clean_display_string(value)
            return value
        display = convert(copy.deepcopy(state))
        if isinstance(display, dict):
            display["display_note"] = "Safe English display copy. Raw internal runtime state is preserved separately as raw_internal_state.json."
            if isinstance(display.get("selected_dimensions"), list):
                display["selected_dimensions"] = [self.dim_label(x) for x in state.get("selected_dimensions", [])]
        return display

    def build_standard_two_round_report(self, state):
        rounds = state.get("rounds") or {}
        attacks = [item for item in (rounds.get("round1_opponent_attack") or []) if isinstance(item, dict)]
        responses = [item for item in (rounds.get("round2_my_rebuttal") or []) if isinstance(item, dict)]
        response_by_dimension = {str(item.get("dimension") or ""): item for item in responses}
        findings = []
        matrix = []
        missing = []
        for index, attack in enumerate(attacks, 1):
            raw_dimension = str(attack.get("dimension") or "")
            response = response_by_dimension.get(raw_dimension, {})
            needed = response.get("needed_material") or []
            if isinstance(needed, str):
                needed = [needed]
            missing.extend(str(value).strip() for value in needed if str(value).strip())
            attack_text = attack.get("finding") or attack.get("attack") or attack.get("question") or ""
            response_text = response.get("response") or response.get("answer_to") or ""
            findings.append({
                "id": f"OP-{index:03d}",
                "analysis_stage": "two_round_opposition",
                "dimension": self.dim_label(raw_dimension),
                "title": self.english_detail_or_empty(attack_text) or f"Opposition issue {index}",
                "finding": str(attack_text),
                "affected_side": "Positive side",
                "factual_basis": attack.get("targeting") or attack.get("relevant_facts") or "",
                "evidence_references": [],
                "significance": "Review the attack and response together; materiality requires lawyer assessment",
                "confidence": attack.get("confidence") or "Not independently scored",
                "provider": attack.get("provider") or "Offline local workflow",
                "model": attack.get("model") or "No external model recorded",
                "source_reference": "Round 1 opposition state",
                "review_status": "ai_generated_unverified",
            })
            matrix.append({
                "issue_id": f"OP-{index:03d}",
                "dimension": self.dim_label(raw_dimension),
                "original_position_or_target": attack.get("targeting") or "Not separately recorded",
                "opposing_attack": str(attack_text),
                "response": str(response_text),
                "needed_material": needed,
                "remaining_risk": "Requires lawyer assessment",
                "lawyer_status": "ai_generated_unverified",
            })
        counts = ((state.get("execution_trace") or {}).get("counts") or {})
        external_calls = int(counts.get("cloud_calls_for_case_text") or 0)
        provider_runs = []
        if external_calls:
            preset = PROVIDER_PRESETS.get(self.cloud_provider_var.get(), {})
            provider_runs.append({
                "provider": preset.get("label") or self.cloud_provider_var.get(),
                "model": self.cloud_model_var.get() or "Not recorded",
                "engine_source": "Execution trace recorded full-case model calls",
                "run_reference": f"{external_calls} full-case call(s)",
            })
        return build_standard_report(
            "two_round_opposition",
            state.get("workflow_mode") or "two_round_opposition",
            self.case_name_var.get().strip() or state.get("case_key") or "Current matter",
            state.get("jurisdiction") or self.jur_var.get(),
            findings=findings,
            provider_runs=provider_runs,
            input_scope={
                "selected_dimensions": [self.dim_label(value) for value in (state.get("selected_dimensions") or [])],
                "round_1_records": len(attacks),
                "round_2_records": len(responses),
                "full_case_external_calls": external_calls,
            },
            sections={
                "attack_response_matrix": matrix,
                "case_summary": self.strip_markers(self.render_summary(state)),
                "legacy_opposition_details": self.strip_markers(self.render_attack_details(state)),
            },
            missing_material=list(dict.fromkeys(missing)),
        )

    def save_run_artifacts(self, state):
        run_dir = HERE / "runs" / state.get("run_id", _dt.datetime.now().strftime("nido_strikeover_%Y%m%d_%H%M%S"))
        run_dir.mkdir(parents=True, exist_ok=True)
        tactic_frames = self.suggest_tactic_frames(state)
        raw_state = json.dumps(state, ensure_ascii=False, indent=2)
        safe_state = json.dumps(self.display_state_for_json(state), ensure_ascii=False, indent=2)
        (run_dir / "raw_internal_state.json").write_text(raw_state, encoding="utf-8-sig")
        (run_dir / "safe_display_state_en.json").write_text(safe_state, encoding="utf-8-sig")
        (run_dir / "state_object.json").write_text(raw_state, encoding="utf-8-sig")
        (run_dir / "state_display_en.json").write_text(safe_state, encoding="utf-8-sig")
        (run_dir / "STATE_FILES_README.txt").write_text(
            "raw_internal_state.json: internal runtime state; may contain local language, private placeholders, and debug fields.\n"
            "safe_display_state_en.json: English safe display/export copy for inspection.\n"
            "state_object.json and state_display_en.json are kept for backward compatibility.\n",
            encoding="utf-8",
        )
        (run_dir / "report.md").write_text(
            "\n\n".join([
                self.strip_markers(self.render_summary(state)),
                self.strip_markers(self.render_attack_details(state)),
            ]),
            encoding="utf-8-sig",
        )
        (run_dir / "execution_trace.json").write_text(
            json.dumps(state.get("execution_trace", {}), ensure_ascii=False, indent=2),
            encoding="utf-8-sig",
        )
        (run_dir / "customer_showcase_note.md").write_text(
            self.render_customer_showcase_note(state),
            encoding="utf-8-sig",
        )
        (run_dir / "tactic_frame_suggestions.json").write_text(
            json.dumps(tactic_frames, ensure_ascii=False, indent=2),
            encoding="utf-8-sig",
        )
        (run_dir / "tactic_frame_suggestions.md").write_text(
            self.render_tactic_frame_report(tactic_frames),
            encoding="utf-8-sig",
        )
        write_standard_companions(
            run_dir,
            "tactic-frame-suggestions",
            self.build_standard_tactic_frame_report(state, tactic_frames),
        )
        write_standard_companions(run_dir, "two-round-opposition", self.build_standard_two_round_report(state))
        self.last_run_dir = run_dir
        self.log(f"Saved本轮记录：{run_dir}")

    def case_slug(self):
        raw = self.case_name_var.get().strip() or "nido_case"
        raw = re.sub(r"[\\/:*?\"<>|]+", "_", raw)
        raw = re.sub(r"\s+", "_", raw)
        return raw[:80] or "nido_case"

    def state_text_for_tactics(self, state):
        rounds = state.get("rounds", {})
        useful = {
            "round1_opponent_attack": rounds.get("round1_opponent_attack", []),
            "round2_my_rebuttal": rounds.get("round2_my_rebuttal", []),
            "structured_case": state.get("options", {}).get("structured_case", {}),
            "selected_dimensions": state.get("selected_dimensions", []),
        }
        return json.dumps(useful, ensure_ascii=False)

    def collect_tactic_snippets(self, text, keywords, limit=3):
        snippets = []
        clean = re.sub(r"\s+", " ", text)
        for kw in keywords:
            pos = clean.find(kw)
            if pos < 0:
                continue
            start = max(0, pos - 55)
            end = min(len(clean), pos + len(kw) + 80)
            snippet = clean[start:end].strip()
            if snippet and snippet not in snippets:
                snippets.append(snippet)
            if len(snippets) >= limit:
                break
        return snippets

    def suggest_tactic_frames(self, state):
        text = self.state_text_for_tactics(state)
        selected = []
        now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for item in TACTIC_FRAME_CATALOG:
            hits = [kw for kw in item["trigger_keywords"] if kw and kw in text]
            if not hits:
                continue
            score = len(hits)
            frame = {
                "frame_type": "opponent_tactic_counter_frame",
                "tactic_name": item["name"],
                "family": item["family"],
                "score": score,
                "matched_keywords": hits,
                "opponent_move": item["opponent_move"],
                "counter_principle": item["counter_principle"],
                "counter_moves": item["counter_moves"],
                "follow_up_questions": item["follow_up_questions"],
                "valid_when": "对方正在使用同类攻击套路，且本案事实或证据链能支持相应反制。",
                "invalid_when": "案件事实不支持该反制，或该套路只是表面相似、实质争点不同。",
                "case_name": self.case_name_var.get().strip() or state.get("case_key", ""),
                "source_run_id": state.get("run_id", ""),
                "created_at": now,
                "example_snippets": self.collect_tactic_snippets(text, item["trigger_keywords"]),
                "use_note": "先识别对方招数，再调用对应后招；用于律师准备和追问，不替代最终法律判断。",
            }
            selected.append(frame)
        selected.sort(key=lambda x: (-x["score"], x["tactic_name"]))
        return selected[:10]

    def tactic_frame_text_en(self, text, fallback="General tactic"):
        text = str(text or "")
        mapping = {
            "结果倒推": "Causation Backfill",
            "因果链攻击": "Causation Attack",
            "法条压迫": "Legal Element Pressure",
            "Legal Application攻击": "Legal Application Attack",
            "证据完整性压迫": "Evidence Completeness Pressure",
            "证据链攻击": "Evidence Chain Attack",
            "时间线模糊": "Timeline Ambiguity",
            "事实基础攻击": "Fact Foundation Attack",
            "情绪叙事包装": "Emotional Narrative Framing",
            "比例过度": "Proportionality Overreach",
            "补救范围攻击": "Remedy Scope Attack",
            "Burden of Proof转移": "Burden-of-Proof Shift",
            "证明责任攻击": "Burden of Proof Attack",
            "跨Jurisdiction施压": "Cross-Jurisdiction Pressure",
            "策略施压": "Strategic Pressure",
            "对方把后出现的结果直接倒推成我方原因。": "The opponent backfills causation from a later result.",
            "切断因果链，要求对方排除物流、使用、第三方行为和时间线介入因素。": "Break the causal chain and require exclusion of logistics, use, third-party conduct, and timeline interventions.",
            "对方用一个宽泛法条制造压迫感，跳过构成要件和本案事实前提。": "The opponent uses a broad rule to create pressure while skipping legal elements and case facts.",
            "把法条拆成构成要件，逐项要求对方证明前提成立。": "Break the rule into elements and require proof for each premise.",
            "对方提交局部材料，试图让局部材料承担完整证明责任。": "The opponent uses partial material as if it proves the whole chain.",
            "追问原始性、连续性、完整性和缺失证据，逼对方补足证据链。": "Press originality, continuity, completeness, and missing evidence.",
            "对方模糊关键时间点，把迟延、使用后发现或程序缺口包装成及时维权。": "The opponent blurs timing and repackages delay or procedural gaps as timely action.",
            "把时间线拆成节点，区分下单、签收、开箱、使用、发现、通知和申请。": "Split the timeline into order, receipt, opening, use, discovery, notice, and application.",
            "对方把证据问题包装成道德叙事，诱导裁判先接受身份框架。": "The opponent converts an evidence issue into a moral narrative.",
            "拆掉标签和情绪词，回到证据、前提、时间线和责任分配。": "Strip labels and emotion; return to evidence, premises, timeline, and responsibility.",
            "对方从一个有限瑕疵或有限争议跳到最大化补救。": "The opponent jumps from a limited dispute to maximum relief.",
            "把损害程度、功能影响、替代补救和成本拆开，压回相称补救。": "Separate harm, functional impact, alternatives, and cost; return to proportionate relief.",
            "对方用质疑代替证明，要求我方证明对方主张不成立。": "The opponent substitutes doubt for proof and tries to shift the burden.",
            "把证明责任压回主张方，区分初步反证和最终证明门槛。": "Return the burden to the asserting party and separate rebuttal from final proof.",
            "对方引入本案之外的监管、平台或其他Jurisdiction材料制造压力。": "The opponent imports regulatory, platform, or external-jurisdiction material to create pressure.",
            "区分诉讼内法律依据和诉讼外策略材料，避免被无关威胁带偏。": "Separate legal authority inside the case from external pressure material.",
        }
        for old, new in mapping.items():
            text = text.replace(old, new)
        text = self.ui_en_text(text)
        text = re.sub(r"[\u4e00-\u9fff]+", "", text)
        text = re.sub(r"\s+", " ", text).strip(" ;,，。")
        if self.bad_ui_text(text) or not re.search(r"[A-Za-z]", text):
            return fallback
        return text

    def render_tactic_frame_report(self, frames):
        lines = ["# Tactic Frame Suggestions", ""]
        if not frames:
            lines.append("No clearly reusable tactic frame was detected in this run.")
            return "\n".join(lines)
        for idx, frame in enumerate(frames, 1):
            lines.extend([
                f"## {idx}. {self.tactic_frame_text_en(frame['tactic_name'], 'Reusable Tactic')} ({self.tactic_frame_text_en(frame['family'], 'Attack Family')})",
                "",
                f"- Hit strength: {frame['score']}",
                f"- Opponent move: {self.tactic_frame_text_en(frame['opponent_move'], 'The opponent is using a reusable pressure pattern.')}",
                f"- Counter principle: {self.tactic_frame_text_en(frame['counter_principle'], 'Return the issue to proof, elements, causation, and scope.')}",
                "- Available counters: " + "; ".join(self.tactic_frame_text_en(x, 'counter move') for x in frame["counter_moves"]),
                "- Follow-up questions:",
            ])
            for q in frame["follow_up_questions"]:
                lines.append(f"  - {self.tactic_frame_text_en(q, 'Which fact, evidence source, legal element, or causal link supports this point?')}")
            if frame.get("example_snippets"):
                lines.append("- Trigger snippets:")
                for snip in frame["example_snippets"]:
                    clean = self.tactic_frame_text_en(snip, "")
                    if clean:
                        lines.append(f"  - {clean}")
            lines.append("")
        return "\n".join(lines)

    def build_standard_tactic_frame_report(self, state, frames):
        findings = []
        for idx, frame in enumerate(frames or [], 1):
            counter_moves = frame.get("counter_moves") or []
            if isinstance(counter_moves, str):
                counter_moves = [counter_moves]
            findings.append({
                "id": f"TACTIC-{idx:03d}",
                "analysis_stage": "tactic_frame_suggestions",
                "dimension": self.tactic_frame_text_en(frame.get("family"), "Attack Family"),
                "title": self.tactic_frame_text_en(frame.get("tactic_name"), "Reusable Tactic"),
                "finding": self.tactic_frame_text_en(frame.get("opponent_move"), "Potential opponent tactic pattern."),
                "affected_side": "Lawyer to assign",
                "factual_basis": "; ".join(
                    self.tactic_frame_text_en(value, "") for value in (frame.get("example_snippets") or [])
                    if self.tactic_frame_text_en(value, "")
                ),
                "significance": self.tactic_frame_text_en(frame.get("counter_principle"), "Requires matter-specific assessment."),
                "confidence": f"Rule-match score {frame.get('score', 0)}; not independently validated",
                "provider": "Offline local workflow",
                "model": "Deterministic tactic catalogue",
                "source_reference": frame.get("source_run_id") or state.get("run_id") or "Current opposition state",
                "review_status": "ai_generated_unverified",
                "lawyer_note": "Confirm applicability before using any counter move: " + "; ".join(
                    self.tactic_frame_text_en(value, "counter move") for value in counter_moves
                ),
            })
        return build_standard_report(
            "tactic_frame_suggestions",
            "tactic_frame_suggestions",
            self.case_name_var.get().strip() or state.get("case_key") or "Current matter",
            state.get("jurisdiction") or self.jur_var.get(),
            findings=findings,
            input_scope={
                "source_run_id": state.get("run_id") or "",
                "frame_count": len(frames or []),
                "derivation": "Local deterministic pattern catalogue applied to current opposition state",
            },
            sections={"legacy_tactic_report": self.render_tactic_frame_report(frames)},
            missing_material=["Matter-specific facts and evidence supporting each suggested tactic must be verified."],
        )

    def archive_tactic_frames(self):
        if not self.last_state:
            messagebox.showwarning("No Opposition Record", "Please run opposition once before archiving tactic frames.")
            return
        frames = self.suggest_tactic_frames(self.last_state)
        if not frames:
            messagebox.showinfo("No Tactic Frames Found", "No clearly reusable tactic frames were detected in this run.")
            return
        archive_dir = HERE / "sop_frames" / "opponent_tactic_frames"
        archive_dir.mkdir(parents=True, exist_ok=True)
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        base = f"{stamp}_{self.case_slug()}"
        payload = {
            "case_name": self.case_name_var.get().strip(),
            "run_id": self.last_state.get("run_id", ""),
            "created_at": _dt.datetime.now().isoformat(timespec="seconds"),
            "frames": frames,
        }
        json_path = archive_dir / f"{base}.json"
        md_path = archive_dir / f"{base}.md"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")
        md_path.write_text(self.render_tactic_frame_report(frames), encoding="utf-8-sig")
        write_standard_companions(
            archive_dir,
            base + "-tactic-frames",
            self.build_standard_tactic_frame_report(self.last_state, frames),
        )
        index_path = archive_dir / "tactic_frame_index.jsonl"
        with index_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "created_at": payload["created_at"],
                "case_name": payload["case_name"],
                "run_id": payload["run_id"],
                "frame_count": len(frames),
                "json_path": str(json_path),
                "md_path": str(md_path),
                "tactics": [x["tactic_name"] for x in frames],
            }, ensure_ascii=False) + "\n")
        self.status_var.set(f"Status: archived {len(frames)} tactic frames")
        messagebox.showinfo("Tactic Frames Archived", f"Archived {len(frames)} tactic frames:\n{md_path}")

    def load_personal_sop_candidates(self):
        return []

    def save_personal_sop_candidates(self, items):
        return None

    def refresh_sop_badge(self):
        if hasattr(self, "sop_new_count_var"):
            self.sop_new_count_var.set("0")

    def classify_personal_sop(self, item):
        return "disabled_competition_feature"

    def filter_personal_sop_rule(self, rule):
        clean_rule = re.sub(r"\s+", " ", str(rule or "")).strip()
        return {"ok": False, "status": "disabled", "warnings": ["Competition build does not store reusable SOP/training rules."], "clean_rule": clean_rule}

    def render_sop_filter_status(self, item):
        return "Filter: disabled in competition build"

    def append_personal_sop_candidate(self, *args, **kwargs):
        return None

    def approve_personal_sop_candidate(self, candidate):
        return False, "SOP storage is disabled in the competition build."

    def personal_sop_rule_key(self, rule):
        return re.sub(r"\s+", "", str(rule or ""))

    def find_existing_personal_sop(self, *args, **kwargs):
        return None

    def find_covering_personal_sop(self, *args, **kwargs):
        return None

    def load_personal_sop_jsonl(self, path):
        return []

    def is_usable_sop_item(self, item):
        return False

    def active_personal_sops(self, category=None):
        return []

    def append_personal_sop_jsonl(self, path, item):
        return None

    def personal_sop_call_counts(self):
        return {}

    def log_personal_sop_call(self, item, context="manual"):
        return None

    def rewrite_personal_sop_jsonl(self, path, rows):
        return None

    def set_personal_sop_disabled(self, item, disabled=True):
        return False

    def save_sop_snapshot(self):
        return None

    def restore_sop_snapshot(self, path):
        return None

    def open_personal_sop_candidates(self):
        messagebox.showinfo("Competition Build", "Reusable SOP/training storage is disabled in this competition copy.")
    def render_customer_showcase_note(self, state):
        trace = state.get("execution_trace", {})
        counts = trace.get("counts", {})
        tactic_frames = self.suggest_tactic_frames(state)
        return "\n".join([
            "# Nido 律师攻防Client demo记录",
            "",
            f"- 案件：{self.case_name_var.get() or state.get('case_key', '')}",
            f"- Mode：{state.get('mode')}",
            f"- 本地Confidentiality：{state.get('options', {}).get('confidentiality_mode', self.confidential_var.get())}",
            f"- 策略增强：{'on' if state.get('options', {}).get('strategy_enhanced') else 'off'}",
            f"- SOP/画像命中：{counts.get('sop_or_profile_hits', 0)}",
            f"- 现场计算路径：{counts.get('field_compute_routes', 0)}",
            f"- 案件全文云端调用：{counts.get('cloud_calls_for_case_text', 0)}",
            f"- 可Archive Tactic Frames：{len(tactic_frames)}",
            "",
            "## 可对客户说明",
            "本系统Local by default案件材料，不把案件全文发送给外部模型。",
            "系统会先检查本地案件画像、证据缺口模板和攻防画框；命中后优先复用本地经验。",
            "随着使用增加，本地案件经验库会沉淀常见争点、证据缺口、追问方式和反驳路径，从而提高准备效率。",
            "该系统用于律师准备和攻防推演，不替代律师对当地法律和客户目标的最终判断。",
            "",
            "## 本轮可归档招式",
            "；".join(x["tactic_name"] for x in tactic_frames) if tactic_frames else "本轮未检测到明确可归档招式。",
        ])

    def strip_markers(self, text):
        for marker in ["[[TITLE]]", "[[SECTION]]", "[[NEG]]", "[[POS]]", "[[LABEL]]", "[[WARN]]", "[[MUTED]]", "[[NEG_BLOCK]]", "[[POS_BLOCK]]", "[[END_BLOCK]]"]:
            text = text.replace(marker, "")
        return text

    def report_html_from_text(self, title, plain_text):
        import html
        raw = str(plain_text or "")
        parts = re.split(r"(?=^## R[12] .*$)", raw, flags=re.M)
        body_parts = []
        for part in parts:
            if not part:
                continue
            safe = html.escape(part)
            if part.startswith("## R1 Negative"):
                body_parts.append(f'<section class="negative"><pre>{safe}</pre></section>')
            elif part.startswith("## R2 Positive"):
                body_parts.append(f'<section class="positive"><pre>{safe}</pre></section>')
            else:
                body_parts.append(f'<pre>{safe}</pre>')
        body = "\n".join(body_parts)
        return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(title or "AI Lawyer Opposition Report")}</title>
<style>
body {{ margin: 32px; background: #111827; color: #e5e7eb; font-family: Arial, sans-serif; }}
pre {{ white-space: pre-wrap; font-family: Consolas, "Courier New", monospace; line-height: 1.45; margin: 0; }}
.negative {{ border-left: 6px solid #ef4444; background: #2a151b; padding: 18px 20px; margin: 22px 0; }}
.positive {{ border-left: 6px solid #3b82f6; background: #111f35; padding: 18px 20px; margin: 22px 0; }}
</style>
</head>
<body>
{body}
</body>
</html>"""

    def insert_colored(self, widget, content):
        marker_tags = {
            "[[TITLE]]": "title",
            "[[SECTION]]": "section",
            "[[NEG]]": "neg",
            "[[POS]]": "pos",
            "[[LABEL]]": "label",
            "[[WARN]]": "warn",
            "[[MUTED]]": "muted",
        }
        active_side = None
        for line in content.splitlines(True):
            if line.startswith("[[NEG_BLOCK]]"):
                active_side = "neg"
                line = line.replace("[[NEG_BLOCK]]", "", 1)
                if not line.strip():
                    continue
            elif line.startswith("[[POS_BLOCK]]"):
                active_side = "pos"
                line = line.replace("[[POS_BLOCK]]", "", 1)
                if not line.strip():
                    continue
            elif line.startswith("[[END_BLOCK]]"):
                active_side = None
                line = line.replace("[[END_BLOCK]]", "", 1)
                if not line.strip():
                    continue
            tag = None
            for marker, marker_tag in marker_tags.items():
                if line.startswith(marker):
                    tag = marker_tag
                    line = line.replace(marker, "", 1)
                    break
            if active_side:
                if tag == "section":
                    tag = "neg_header" if active_side == "neg" else "pos_header"
                elif tag in (None, "label"):
                    tag = active_side
            widget.insert(tk.END, line, tag if tag else ())

    def collect_local_law_references(self, state):
        refs = []
        jurisdiction = state.get("jurisdiction") or self.jur_var.get()
        selected = set(state.get("selected_dimensions", []))
        pack_key = self.match_framework_pack_key(jurisdiction)
        pack = LEGAL_FRAMEWORK_PACKS.get(pack_key) or LEGAL_FRAMEWORK_PACKS.get("Custom / User Provided", {})

        def add(label, source, note):
            row = f"{label}｜{source}｜{note}"
            if row not in refs:
                refs.append(row)

        if pack_key == "Australia / AU":
            add("Australian Consumer Law / consumer guarantees", "本地Jurisdiction模板", "消费者保证、误导行为、合理通知和补救比例需律师核验具体 Act/section。")
            add("Contract formation and terms notice", "本地Jurisdiction模板", "合同成立、条款提示、接受和交易当时版本是本轮基础规则。")
        elif pack_key == "United States / US":
            add("State contract / UCC / consumer protection", "本地Jurisdiction模板", "美国规则高度州法化，必须确认具体州法和适用条款。")
        elif pack_key == "United Kingdom / UK":
            add("Consumer Rights Act / contract formation", "本地Jurisdiction模板", "需核验消费者权利、misrepresentation、unfair terms 和 remedies。")
        elif pack_key == "European Union / EU":
            add("EU consumer / platform / data rules", "本地Jurisdiction模板", "需继续确认成员国实施规则和本案事实连接。")
        elif pack_key == "China / CN":
            add("合同/消费者权益/电子数据规则", "本地Jurisdiction模板", "需律师核验最新法律法规、司法解释和地方裁判尺度。")
        else:
            if pack.get("case_text"):
                add("Custom jurisdiction rules", "用户提供Jurisdiction模板", "当前Jurisdiction需用户或律所资料库补充具体法律依据。")

        if selected & {"Legal Application", "Legal Text Interpretation", "Procedural Defect", "Proportionality Test"}:
            add("本Jurisdiction构成要件与程序规则", "本地规则清单", "本轮需核验构成要件、提示/通知程序、期限、救济比例。")
        if selected & {"跨Jurisdiction武器", "Reverse Thinking"}:
            add("跨Jurisdiction/平台/监管材料", "跨界维度引用边界", "只能作为比较、压力或辅助解释；核心仍须落回本Jurisdiction规则和本案事实。")
        if selected & {"Precedent Attack", "Public Policy", "Systemic Risk Amplification"}:
            add("判例/Public Policy/系统风险材料", "复查维度引用边界", "不得编造案例；Public Policy和系统风险必须有事实、行业或制度依据。")

        context = state.get("case_search_context", {})
        if context.get("enabled"):
            if context.get("verified"):
                for dim, result in (context.get("results_by_dimension") or {}).items():
                    if result.get("verified"):
                        titles = "；".join(x.get("title", "") for x in result.get("results", [])[:3] if x.get("title"))
                        if titles:
                            add(f"{dim} 判例参照", result.get("source", "case search"), titles)
            else:
                add("判例参照", "在线检索未取得已验证结果", "不得编造案例名称，只能用一般法律原则或律师确认材料。")

        for source in OFFICIAL_LEGAL_SOURCE_PACKS.get(pack_key, [])[:3]:
            add(source.get("name", "官方来源"), "官方法律资料入口", source.get("note", "需律师复核当前版本。"))

        return refs[:10]

    def render_summary(self, state):
        review = state["rounds"].get("final_reviewer", {})
        trace = state.get("execution_trace", {})
        counts = trace.get("counts", {})
        strategy_on = "on" if state.get("options", {}).get("strategy_enhanced") else "off"
        attacks = state.get("rounds", {}).get("round1_opponent_attack", [])
        rebuttals = state.get("rounds", {}).get("round2_my_rebuttal", [])
        top_attacks = []
        for item in attacks[:3]:
            dim = self.dim_label(item.get("dimension", ""))
            finding = item.get("finding") or item.get("attack") or item.get("question") or ""
            detail = self.english_detail_or_empty(finding)
            top_attacks.append(f"- {dim}: {detail or 'Attack path generated in Attack Details.'}")
        materials = []
        for item in rebuttals:
            needed = item.get("needed_material") or []
            if isinstance(needed, str):
                needed = [needed]
            materials.extend(str(x) for x in needed if x)
        materials = list(dict.fromkeys(materials))[:6]
        law_refs = self.collect_local_law_references(state)
        return "\n".join([
            "[[TITLE]]# Summary",
            "",
            f"Case: {self.sanitize_case_name(self.case_name_var.get() or state.get('case_key', ''))}",
            f"Mode：{state.get('mode')}",
            f"Confidentiality：{state.get('options', {}).get('confidentiality_mode', self.confidential_var.get())}",
            f"Strategy boost: {strategy_on}",
            f"Two-round dimensions: {len(state.get('selected_dimensions', []))}",
            f"Case-law reference: {state.get('case_search_context', {}).get('region', 'unspecified')} / {'on' if state.get('case_search_context', {}).get('enabled') else 'off'}",
            f"Cloud calls using full case text: {counts.get('cloud_calls_for_case_text', 0)}",
            "",
            "[[SECTION]]## Attack Points Worth Reading",
            "\n".join(top_attacks) if top_attacks else "No clear attack point generated.",
            "",
            "[[SECTION]]## Materials To Prepare",
            "\n".join(f"- {self.english_detail_or_empty(x) or 'Review supporting material for this point.'}" for x in materials) if materials else "- Counsel should decide supporting materials by case theory.",
            "",
            "[[SECTION]]## Local Law / Rule References",
            "\n".join(f"- {self.english_detail_or_empty(x) or 'Verify the governing law and current version.'}" for x in law_refs) if law_refs else "- No verified local rule reference yet; counsel should add the governing basis.",
            "",
            "[[SECTION]]## Next Step",
            self.english_detail_or_empty(review.get("next_step", "")) or "Choose one or two high-value weaknesses and polish them in Single-Point 2R.",
        ])

    def render_attack_details(self, state):
        parts = ["[[TITLE]]# Two-Round Opposition Details\n"]
        chosen = state.get("lawyer_selected_weaknesses") or []
        if chosen:
            parts.append("\n[[SECTION]]## Lawyer-Selected Weaknesses\n")
            for c in chosen:
                parts.append(
                    f"{c.get('id', '')} [{self.dim_label(c.get('dimension', ''))}] "
                    f"{c.get('weakness', '')}\n"
                )
        for title, key in [
            ("R1 Negative Side Attack", "round1_opponent_attack"),
            ("R2 Positive Side Rebuttal", "round2_my_rebuttal"),
        ]:
            block_tag = "[[NEG_BLOCK]]" if title.startswith("R1") else "[[POS_BLOCK]]"
            parts.append(f"\n{block_tag}[[SECTION]]## {title}\n")
            for idx, item in enumerate(state["rounds"].get(key, []), 1):
                dim = self.dim_label(item.get("dimension", f"Dimension {idx}"))
                parts.append(f"[[SECTION]][{dim}]\n")
                if key == "round1_opponent_attack":
                    parts.extend(self.render_round1_item(item))
                elif key == "round2_my_rebuttal":
                    parts.extend(self.render_round2_item(item))
                parts.append("\n")
            parts.append("[[END_BLOCK]]")
        return "".join(parts)

    def render_round1_item(self, item):
        finding = item.get("finding") or item.get("attack") or ""
        speech = self.frontstage_round_speech(
            finding,
            role="attack",
            dimension=item.get("dimension", ""),
            item=item,
        )
        return [f"[[LABEL]]  Negative: {speech}\n"] if speech else []

    def render_round2_item(self, item):
        response = item.get("response") or item.get("rebuttal") or ""
        speech = self.frontstage_round_speech(
            response,
            role="rebuttal",
            dimension=item.get("dimension", ""),
            item=item,
        )
        return [f"[[LABEL]]  Positive: {speech}\n"] if speech else []

    def frontstage_round_speech(self, text, max_len=420, role=None, dimension="", item=None):
        text = re.sub(r"\s+", " ", str(text or "")).strip()
        if not text:
            return ""
        cut_markers = [
            "策略增强：",
            "策略层：",
            "反制策略：",
            "需要补强材料：",
            "维度防守落点：",
            "攻击落点应",
            "先锁定证明对象",
            "继续追问",
            "回应不得削弱",
            "回应时不得削弱",
            "同时保留限缩",
            "先限定对方攻击范围",
        ]
        for marker in cut_markers:
            pos = text.find(marker)
            if pos > 0:
                text = text[:pos].rstrip(" ；;，,。")
        text = self.strip_backend_tone(text)
        if role == "attack":
            text = self.render_court_attack_speech(text, dimension, item=item)
        elif role == "rebuttal":
            text = self.render_court_rebuttal_speech(text, dimension, item=item)
        return self.compact(text, max_len)

    def legacy_target_label(self, item=None, fallback="the claim"):
        item = item or {}
        for key in ("targeting", "answer_to", "target", "object"):
            val = re.sub(r"\s+", " ", str(item.get(key, "")).strip())
            if val:
                cleaned = self.clean_frontstage_target_label(self.ui_en_text(val) or val)
                if cleaned:
                    return self.compact(cleaned, 90)
        return fallback

    def clean_frontstage_target_label(self, text):
        text = self.ui_en_text(text)
        text = re.sub(r"[`´‘’“”\"']", " ", str(text or ""))
        text = re.sub(r"\\+", " ", text)
        text = re.sub(r"\b(evidence|argument|claim|point)\b(?:\s*[,.;:])?\s*\b\1\b", r"\1", text, flags=re.I)
        text = re.sub(r"[^A-Za-z0-9][^A-Za-z0-9]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip(" ,.;:-_/|")
        if len(re.findall(r"[A-Za-z0-9]", text)) < 4:
            return ""
        if text.lower() in {"evidence", "argument", "claim", "point"}:
            return f"the selected {text.lower()}"
        if not re.search(r"\b(the|a|an|this|that|opponent|positive|negative|evidence|argument|claim|point|attack)\b", text, re.I):
            return f"the selected point ({text})"
        return text

    def strip_backend_tone(self, text):
        text = str(text or "").strip()
        replacements = [
            ("攻击重点是", ""),
            ("攻击方向是", ""),
            ("核心攻击是", ""),
            ("程序攻击集中在", "问题集中在"),
            ("量化攻击要求", "应要求"),
            ("Public Policy攻击把", "不能把"),
            ("逆向攻击承认风险：", ""),
            ("跨Jurisdiction攻击只作为策略提示，", ""),
            ("反事实攻击用", "应当用"),
            ("比例攻击把", "应当把"),
            ("叙事攻击拆掉", "不能接受"),
            ("系统性攻击把", "不能把"),
            ("Missing Evidence攻击不是说", "不是说"),
            ("攻击因果链：", ""),
            ("攻击点是", ""),
        ]
        for old, new in replacements:
            text = text.replace(old, new)
        text = self.guard_unproven_frontstage_terms(text)
        text = re.sub(r"\s+", " ", text).strip(" ：:，,。")
        return text

    def guard_unproven_frontstage_terms(self, text):
        case_blob = ""
        try:
            case_blob = "\n".join([
                self.get_text(self.t_bg) if hasattr(self, "t_bg") else "",
                self.get_text(self.t_pos_args) if hasattr(self, "t_pos_args") else "",
                self.get_text(self.t_pos_ev) if hasattr(self, "t_pos_ev") else "",
                self.get_text(self.t_neg_args) if hasattr(self, "t_neg_args") else "",
                self.get_text(self.t_neg_ev) if hasattr(self, "t_neg_ev") else "",
            ])
        except Exception:
            case_blob = ""
        guarded = str(text or "")
        if "点击同意" in guarded and "点击同意" not in case_blob:
            guarded = guarded.replace("点击同意", "是否有明确接受记录")
        if "页面提示" in guarded and "页面提示" not in case_blob:
            guarded = guarded.replace("页面提示", "交易当时的提示材料")
        if "下单确认" in guarded and "下单确认" not in case_blob:
            guarded = guarded.replace("下单确认", "交易确认记录")
        if "页面截图" in guarded and "页面截图" not in case_blob and "截图" not in case_blob:
            guarded = guarded.replace("页面截图", "交易页面或规则材料")
        return guarded

    def render_court_attack_speech(self, text, dimension, item=None):
        if not text:
            return ""
        target = self.legacy_target_label(item, "the positive-side claim")
        dim = self.dim_label(dimension)
        lead = {
            "Fact Challenge": "The negative side does not accept isolated fragments as complete fact proof.",
            "Legal Application": "The negative side objects to jumping straight from facts to a legal conclusion.",
            "Precedent Attack": "The negative side requires any cited rule or precedent to match this fact pattern.",
            "Burden of Proof": "The burden remains on the positive side; the negative side does not have to fill the gap.",
            "Logic Gap": "This argument has a visible inferential gap.",
            "Damage Causation": "Liability, causation, and loss must be separated.",
            "Quantum Dispute": "The claimed amount must be proved, not merely asserted.",
            "Cross-Jurisdiction Weapon": "External rules may be used as boundary checks only, not as binding law.",
            "Counterfactual Reasoning": "An alternative factual path must be tested.",
            "Proportionality Test": "Even if some facts are accepted, the remedy cannot automatically expand.",
            "Narrative Deconstruction": "A story cannot replace elements, evidence, and causation.",
            "Missing Evidence": "The point is not to prove the opponent's case for them; it is to expose missing proof.",
        }.get(dim, "The negative side's position is that the proof path remains incomplete.")
        tail = {
            "Fact Challenge": "Until those facts are closed, the court should not accept the conclusion.",
            "Legal Application": "If the preconditions are not met, the legal consequence cannot follow.",
            "Precedent Attack": "A general rule cannot substitute for proof in this case.",
            "Burden of Proof": "Without meeting the proof threshold, the claim cannot move forward.",
            "Logic Gap": "If the gap is not repaired, the requested outcome has no stable base.",
            "Damage Causation": "Where the causal chain breaks, responsibility should stop.",
            "Quantum Dispute": "Without particulars and method, the amount remains unproved.",
            "Cross-Jurisdiction Weapon": "External rules cannot replace this jurisdiction's facts and law.",
            "Counterfactual Reasoning": "If the alternative path cannot be excluded, sole causation is not proved.",
            "Proportionality Test": "The remedy must stay proportionate to proved loss, risk, and responsibility.",
            "Narrative Deconstruction": "The positive side must return to evidence, terms, and causation.",
            "Missing Evidence": "The absence of key materials should reduce the probative value of the claim.",
        }.get(dim, "The positive side must identify the factual premise, evidence source, and proof burden first.")
        detail = self.english_detail_or_empty(text)
        middle = f" {detail}" if detail else ""
        return f"As to {target}, {lead}{middle} {tail}"

    def render_court_rebuttal_speech(self, text, dimension, item=None):
        if not text:
            return ""
        target = self.clean_frontstage_target_label(self.legacy_target_label(item, "")) or "the selected negative-side attack"
        dim = self.dim_label(dimension)
        lead = {
            "Fact Challenge": "The positive side answers that the factual record should be read as a whole.",
            "Legal Application": "The positive side does not avoid the legal framework, but the negative side must apply it to the correct premises.",
            "Burden of Proof": "The positive side maintains that the burden cannot be reversed by broad suspicion.",
            "Logic Gap": "The positive side breaks the causal chain back into its proved links.",
            "Damage Causation": "The positive side separates liability from the scope of loss.",
            "Quantum Dispute": "The positive side returns the amount to particulars and calculation method.",
            "Cross-Jurisdiction Weapon": "The positive side does not allow external rules to override the governing jurisdiction.",
            "Counterfactual Reasoning": "The positive side uses the broader factual record to answer the alternative path.",
            "Proportionality Test": "The positive side keeps the remedy tied to the proved responsibility.",
            "Narrative Deconstruction": "The positive side pulls both stories back to provable facts.",
            "Missing Evidence": "The positive side answers each alleged missing material by relevance and proof value.",
        }.get(dim, "The positive side answers as follows.")
        tail = {
            "Legal Application": "The negative side cannot defeat the positive path with an abstract rule alone.",
            "Burden of Proof": "The party making an assertion must prove it; generalized doubt is not a substitute for contrary proof.",
            "Logic Gap": "Once each link is tied to evidence, the broad denial loses force.",
            "Damage Causation": "Liability and amount can be reviewed separately without collapsing the whole claim.",
            "Quantum Dispute": "Unparticularized components may be limited, but that does not disprove the underlying facts.",
            "Proportionality Test": "That preserves the positive side's position while keeping room for alternative relief.",
        }.get(dim, "The negative side cannot expand the attack beyond the point actually made.")
        detail = self.english_detail_or_empty(text)
        middle = f" {detail}" if detail else ""
        return f"In response to {target}, {lead}{middle} {tail}"

    def english_detail_or_empty(self, text):
        text = re.sub(r"\s+", " ", str(text or "")).strip()
        if not text:
            return ""
        cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
        ascii_letters = len(re.findall(r"[A-Za-z]", text))
        if cjk and cjk > ascii_letters:
            return ""
        return self.compact(text, 180)

    def open_single_point_popup(self):
        self.open_point_rebuttal_assistant()
        return
        point = simpledialog.askstring(
            "Single-Point 2R",
            "Enter one argument, evidence item, attack point, or question:",
            parent=self.root,
        )
        if not point or not point.strip():
            return
        report = self.generate_simple_single_point_report(point.strip())
        win = tk.Toplevel(self.root)
        win.title("Single-Point 2R Result")
        win.geometry("820x560")
        win.configure(bg=self.C["panel"])
        t = scrolledtext.ScrolledText(win, bg=self.C["entry"], fg=self.C["text"], insertbackground=self.C["text"], font=("Microsoft YaHei UI", 11), wrap=tk.WORD)
        self.bind_local_scroll(t)
        t.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 6))
        self.configure_output_tags(t)
        self.insert_colored(t, report)
        controls = tk.Frame(win, bg=self.C["panel"], padx=10, pady=8)
        controls.pack(fill=tk.X)

        def copy_result():
            self.root.clipboard_clear()
            self.root.clipboard_append(self.strip_markers(report))

        def save_result():
            out_dir = HERE / "single_point_runs"
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}_{self.case_slug()}_single_point.md"
            path.write_text(self.strip_markers(report), encoding="utf-8-sig")
            messagebox.showinfo("Saved", str(path))

        tk.Button(controls, text="Copy", command=copy_result, bg="#333", fg=self.C["text"], relief="flat", padx=14, pady=6).pack(side=tk.LEFT)
        tk.Button(controls, text="Save", command=save_result, bg="#1a3a1a", fg="white", relief="flat", padx=14, pady=6).pack(side=tk.LEFT, padx=8)

    def simple_single_point_dimension(self, point):
        text = str(point or "").lower()
        checks = [
            ("duty of care", ["duty of care", "non-delegable", "non delegable", "civil liability act", "common law", "lawful entrant", "lawful entrants", "reasonable care"]),
            ("Legal Application", ["duty", "breach", "rule", "law", "legal", "element", "liability", "statute", "act", "section"]),
            ("Missing Evidence", ["missing", "absence", "no record", "inspection log", "not shown", "unavailable"]),
            ("Damage Causation", ["cause", "causation", "caused", "injury", "medical", "impairment", "recovery", "earning capacity", "damage", "loss"]),
            ("Quantum Dispute", ["amount", "quantum", "future earning", "cost", "money", "damages"]),
            ("Procedural Defect", ["notice", "time", "date", "deadline", "service", "inspection"]),
            ("Fact Challenge", ["evidence", "proof", "prove", "record", "witness", "fact"]),
        ]
        for dim, needles in checks:
            if any(x in text for x in needles):
                return dim
        return "Logic Gap"

    def generate_simple_single_point_report(self, point):
        point_en = (self.ui_en_text(point) or str(point or "").strip()).strip()
        point_en = point_en.rstrip()
        if self.bad_ui_text(point_en):
            point_en = str(point or "").strip()
        dimension = self.simple_single_point_dimension(point_en)
        case_name = self.case_name_var.get().strip() or "Current case"
        attack = self.simple_single_point_attack(point_en, dimension)
        defence = self.simple_single_point_defence(point_en, dimension)
        materials = self.simple_single_point_materials(dimension)
        original = "\n".join([
            "[[TITLE]]# Evidence Assistant - Single Point",
            "",
            "[[MUTED]]Provider: local offline",
            f"[[MUTED]]Case: {case_name}",
            f"[[MUTED]]Point: {point_en}",
            f"[[MUTED]]Focus: {dimension}",
            "",
            "[[NEG_BLOCK]][[SECTION]]## R1 Negative Attack",
            attack,
            "[[END_BLOCK]]",
            "",
            "[[POS_BLOCK]][[SECTION]]## R2 Positive Defence",
            defence,
            "[[END_BLOCK]]",
            "",
            "[[LABEL]]Materials to Check",
            *[f"- {x}" for x in materials],
        ])
        standard = build_standard_report(
            "single_point_2r",
            "local_single_point_2r",
            case_name,
            self.jur_var.get(),
            findings=[{
                "id": "SP-001",
                "dimension": dimension,
                "title": point_en,
                "finding": attack,
                "affected_side": "Positive side",
                "factual_basis": point_en,
                "significance": "Materiality requires lawyer assessment",
                "provider": "Offline local workflow",
                "model": "No external model recorded",
                "source_reference": "User-selected single point",
                "review_status": "ai_generated_unverified",
            }],
            input_scope={"selected_point": point_en, "dimension": dimension},
            sections={
                "attack_response_matrix": [{"attack": attack, "response": defence, "lawyer_status": "ai_generated_unverified"}],
                "legacy_output": self.strip_markers(original),
            },
            missing_material=materials,
        )
        return render_standard_markdown(standard)

    def simple_single_point_attack(self, point, dimension):
        base = f"The negative side should attack this point directly: \"{point}\". "
        if dimension == "duty of care":
            return base + "Accepting a duty in general does not prove breach or scope. Require the positive side to identify the precise statutory or common-law element, the class of entrant, the foreseeable risk, the reasonable precaution, and why the duty extends to this exact condition."
        if dimension == "Missing Evidence":
            return base + "The point depends on material that should have a source record. Require the positive side to identify the original document, when it was created, who controlled it, and why any missing record should not reduce weight."
        if dimension == "Damage Causation":
            return base + "Separate breach, causation, and loss. The positive side must show that this point caused the claimed outcome and must exclude alternative causes, pre-existing conditions, third-party conduct, and ordinary background risk."
        if dimension == "Quantum Dispute":
            return base + "The amount cannot be asserted as a conclusion. Require particulars, calculation method, time period, assumptions, mitigation, and a direct link between the point and each claimed dollar."
        if dimension == "Procedural Defect":
            return base + "Turn it into a timing and record-path issue. Ask when the step occurred, who recorded it, whether notice or inspection was complete, and whether the procedure was followed at the relevant time."
        if dimension == "Legal Application":
            return base + "Do not let the positive side jump from a general duty or rule to liability. Break the rule into elements and require a proved fact for each element before the legal conclusion follows."
        if dimension == "Fact Challenge":
            return base + "Press for direct proof. Identify whether this is a fact, inference, opinion, or conclusion; then ask for the source, continuity, reliability, and whether the record proves exactly what is alleged."
        return base + "The inference is not closed. Force the positive side to state the factual premise, the evidence source, the rule applied, and the causal step linking the point to the requested result."

    def simple_single_point_defence(self, point, dimension):
        base = f"The positive side should keep the answer narrow and defend only this point: \"{point}\". "
        if dimension == "duty of care":
            return base + "Frame the duty as a premises-safety obligation owed to lawful entrants, then connect it to the concrete risk, the defendant's control of the premises, the reasonable precautions available, and the evidence showing why the warning or maintenance response was inadequate."
        if dimension == "Missing Evidence":
            return base + "Answer by identifying what records already exist, why any absent material is not essential, and how the available evidence still proves the relevant fact on the required standard."
        if dimension == "Damage Causation":
            return base + "Tie the point to the pleaded chain: duty or obligation, breach or event, resulting harm, and loss. If causation is contested, isolate the strongest link and reserve alternative support."
        if dimension == "Quantum Dispute":
            return base + "Defend the amount by separating liability from quantum, then provide the calculation path, assumptions, supporting documents, and any fallback amount if the court narrows the claim."
        if dimension == "Procedural Defect":
            return base + "Respond with the timeline, notice or inspection record, responsible person, and why any procedural criticism does not change the substantive proof."
        if dimension == "Legal Application":
            return base + "Map each legal element to a concrete fact and an evidence source. Do not argue fairness in the abstract; show how this point satisfies the rule in this case."
        if dimension == "Fact Challenge":
            return base + "Anchor the answer in source evidence: who observed it, where it appears in the record, why it is reliable, and how it fits the other facts."
        return base + "Close the logical path step by step: premise, evidence, rule, causation, and remedy. Concede only narrow proof gaps and preserve the main position."

    def simple_single_point_materials(self, dimension):
        mapping = {
            "duty of care": ["Civil Liability Act or applicable statute sections", "Common-law duty and scope materials", "Premises control and lawful entrant evidence", "Warning, cleaning, inspection, or maintenance records"],
            "Missing Evidence": ["Original source record", "Reason missing material is unavailable or unnecessary", "Alternative corroborating evidence"],
            "Damage Causation": ["Causation timeline", "Alternative cause checklist", "Support for the causal link"],
            "Quantum Dispute": ["Calculation schedule", "Invoices or loss records", "Mitigation and fallback amount"],
            "Procedural Defect": ["Notice, service, inspection, or submission record", "Timeline of relevant steps", "Authority or responsibility record"],
            "Legal Application": ["Element-by-element table", "Fact-to-rule mapping", "Exceptions or limits check"],
            "Fact Challenge": ["Original record", "Witness/source reliability", "Continuity and completeness check"],
        }
        return mapping.get(dimension, ["Factual premise", "Evidence source", "Rule application", "Causal link"])

    def open_point_rebuttal_assistant(self, initial_point=None, initial_mode=None, initial_dimension=None, autorun=False):
        win = tk.Toplevel(self.root)
        win.title("Nido Single-Point 2R")
        win.geometry("1120x760")
        win.configure(bg=self.C["panel"])

        top = tk.Frame(win, bg=self.C["panel"], padx=10, pady=8)
        top.pack(fill=tk.X)
        tk.Label(
            top,
            text="Single-Point 2R: one side attacks this point and the other gives defence language and evidence paths.",
            bg=self.C["panel"],
            fg=self.C["gold"],
            font=("Microsoft YaHei UI", 12, "bold"),
        ).pack(anchor="w")

        cfg = tk.Frame(win, bg=self.C["panel"], padx=10, pady=4)
        cfg.pack(fill=tk.X)
        mode_var = tk.StringVar(value=initial_mode or "My New Argument/Evidence")
        tk.Label(cfg, text="Single-Point Type:", bg=self.C["panel"], fg=self.C["text"]).pack(side=tk.LEFT)
        ttk.Combobox(cfg, textvariable=mode_var, values=["My New Argument/Evidence", "对方攻击点"], width=18, state="readonly").pack(side=tk.LEFT, padx=(0, 12))
        mode_combo = cfg.winfo_children()[-1]
        mode_combo.configure(values=["My New Argument/Evidence", "Opponent Attack Point"], width=24)
        tk.Label(cfg, text="Review Single Point Across 18 Dimensions", bg=self.C["panel"], fg=self.C["gold"], font=("Microsoft YaHei UI", 10, "bold")).pack(side=tk.LEFT)

        dim_panel = tk.Frame(win, bg=self.C["panel"], padx=10, pady=4)
        dim_panel.pack(fill=tk.X)
        point_dim_vars = {name: tk.BooleanVar(value=(not initial_dimension or name == initial_dimension)) for name, _desc in DIMENSIONS}
        tk.Label(dim_panel, text="Opposition Dimensions:", bg=self.C["panel"], fg=self.C["text"]).grid(row=0, column=0, sticky="w", padx=(0, 8))
        tk.Button(dim_panel, text="Select All", command=lambda: [v.set(True) for v in point_dim_vars.values()], bg="#333", fg="white", relief="flat", padx=10).grid(row=0, column=1, sticky="w", padx=(0, 4))
        tk.Button(dim_panel, text="Clear", command=lambda: [v.set(False) for v in point_dim_vars.values()], bg="#333", fg="white", relief="flat", padx=10).grid(row=0, column=2, sticky="w", padx=(0, 8))
        grid = tk.Frame(dim_panel, bg=self.C["panel"])
        grid.grid(row=1, column=0, columnspan=8, sticky="we", pady=(4, 0))
        for idx, (name, _desc) in enumerate(DIMENSIONS):
            tk.Checkbutton(
                grid,
                text=name,
                variable=point_dim_vars[name],
                bg=self.C["panel"],
                fg=self.C["text"],
                selectcolor=self.C["entry"],
                activebackground=self.C["panel"],
                activeforeground=self.C["text"],
            ).grid(row=idx // 6, column=idx % 6, sticky="w", padx=6, pady=1)

        body = tk.PanedWindow(win, orient=tk.HORIZONTAL, bg=self.C["panel"], sashwidth=5)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        left = tk.Frame(body, bg=self.C["panel"])
        right = tk.Frame(body, bg=self.C["panel"])
        body.add(left, minsize=420)
        body.add(right, minsize=560)

        tk.Label(left, text="Single-Point Content", bg=self.C["panel"], fg=self.C["text"], font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w")
        point_text = scrolledtext.ScrolledText(left, bg=self.C["entry"], fg=self.C["text"], font=("Microsoft YaHei UI", 11), wrap=tk.WORD, height=16)
        self.bind_local_scroll(point_text)
        point_text.pack(fill=tk.BOTH, expand=True, pady=(4, 8))
        point_text.insert(tk.END, initial_point or self.default_point_focus_text())

        tk.Label(left, text="Usage Notes", bg=self.C["panel"], fg=self.C["muted"], font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")
        help_text = tk.Text(left, bg=self.C["entry"], fg=self.C["muted"], font=("Microsoft YaHei UI", 10), height=8, wrap=tk.WORD, relief="flat")
        self.bind_local_scroll(help_text)
        help_text.pack(fill=tk.X, pady=(4, 0))
        help_text.insert(tk.END, "用法一：律师想到一条新证据或新论点，选择“My New Argument/Evidence”，看对方会怎么打、我方怎么守。\n")
        help_text.insert(tk.END, "用法二：看到对方某条攻击，选择“对方攻击点”，直接围绕这一条生成我方反驳。\n")
        help_text.insert(tk.END, "这个窗口把单点当作一个小主案，用18个维度一起审，但不改变主案件画框。适合庭审前逐条打磨。")
        help_text.delete("1.0", tk.END)
        help_text.insert(tk.END, "Use My New Argument/Evidence to test how the opposing side may attack a new point and how your side can answer.\n\n")
        help_text.insert(tk.END, "Use Opponent Attack Point to generate a focused rebuttal to one identified opposing attack.\n\n")
        help_text.insert(tk.END, "The selected point is reviewed as a focused sub-matter across the chosen dimensions. This does not alter the main case fields.")
        help_text.config(state=tk.DISABLED)

        tk.Label(right, text="Single-Point 2R Result", bg=self.C["panel"], fg=self.C["text"], font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w")
        result_text = scrolledtext.ScrolledText(right, bg=self.C["entry"], fg=self.C["text"], font=("Microsoft YaHei UI", 11), wrap=tk.WORD)
        self.bind_local_scroll(result_text)
        result_text.pack(fill=tk.BOTH, expand=True, pady=(4, 8))
        self.configure_output_tags(result_text)

        controls = tk.Frame(win, bg=self.C["panel"], padx=10, pady=8)
        controls.pack(fill=tk.X, before=body)

        def run_point():
            point = point_text.get("1.0", tk.END).strip()
            if not point:
                messagebox.showwarning("Missing Single-Point Content", "Please enter one argument, evidence item, follow-up question, or rebuttal first.")
                return
            selected_dims = [name for name, var in point_dim_vars.items() if var.get()]
            if not selected_dims:
                messagebox.showwarning("No Dimension Selected", "Please select at least one single-point review dimension.")
                return
            report = self.generate_single_point_multi_dimension_report(point, mode_var.get(), selected_dims)
            result_text.delete("1.0", tk.END)
            self.insert_colored(result_text, report)

        def copy_result():
            self.root.clipboard_clear()
            self.root.clipboard_append(result_text.get("1.0", tk.END).strip())

        def save_result():
            content = result_text.get("1.0", tk.END).strip()
            if not content:
                messagebox.showwarning("No Result", "Please run Single-Point 2R first.")
                return
            out_dir = HERE / "single_point_runs"
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}_{self.case_slug()}_single_point.md"
            path.write_text(content, encoding="utf-8-sig")
            selected_dims = [name for name, var in point_dim_vars.items() if var.get()]
            standard = build_standard_report(
                "single_point_2r",
                "single_point_result_export",
                self.case_name_var.get().strip() or "Current matter",
                self.jur_var.get(),
                findings=[{
                    "id": f"SP-{index:03d}",
                    "dimension": self.dim_label(dimension),
                    "title": self.compact(point_text.get("1.0", tk.END).strip(), 140),
                    "finding": "See the standardised single-point analysis section.",
                    "factual_basis": point_text.get("1.0", tk.END).strip(),
                    "provider": "Offline local workflow",
                    "model": "No external model recorded",
                    "source_reference": "Single-point result window",
                    "review_status": "ai_generated_unverified",
                } for index, dimension in enumerate(selected_dims, 1)],
                input_scope={"selected_point": point_text.get("1.0", tk.END).strip(), "selected_dimensions": [self.dim_label(value) for value in selected_dims]},
                sections={"standardised_analysis": content},
            )
            write_standard_companions(out_dir, path.stem, standard)
            messagebox.showinfo("Saved", str(path))

        tk.Button(controls, text="Run Single-Point 2R", command=run_point, bg=self.C["accent"], fg="white", relief="flat", padx=18, pady=7, font=("Microsoft YaHei UI", 11, "bold")).pack(side=tk.LEFT)
        tk.Button(controls, text="Copy Result", command=copy_result, bg="#333", fg=self.C["text"], relief="flat", padx=14, pady=7).pack(side=tk.LEFT, padx=8)
        tk.Button(controls, text="Save Single-Point Report", command=save_result, bg="#1a3a1a", fg="white", relief="flat", padx=14, pady=7).pack(side=tk.LEFT, padx=8)
        if autorun:
            win.after(80, run_point)

    def generate_single_point_multi_dimension_report(self, point, point_mode, dimensions):
        dimensions = dimensions or [DIMENSIONS[0][0]]
        parts = [
            "[[TITLE]]# 单点18维攻防",
            "",
            f"案件：{self.case_name_var.get() or '未命名案件'}",
            f"Single-Point Type:{point_mode}",
            f"审查维度：{len(dimensions)} 个",
            "",
        ]
        for idx, dimension in enumerate(dimensions, 1):
            sub = self.generate_single_point_two_rounds(point, point_mode, dimension)
            sub = re.sub(r"^\[\[TITLE\]\]# Single-Point 2R\s*", "", sub).strip()
            parts.extend([
                f"[[SECTION]]## D{idx:02d} {dimension}",
                sub,
                "",
            ])
        parts.append("[[MUTED]]提示：本报告把一个单点当作小主案，用选中的攻防维度逐项审查。")
        legacy = "\n".join(parts)
        findings = [{
            "id": f"SP-{index:03d}",
            "dimension": self.dim_label(dimension),
            "title": self.compact(self.ui_en_text(point) or point, 140),
            "finding": f"Single-point review completed through {self.dim_label(dimension)}; see the dimension analysis section.",
            "affected_side": "Depends on selected point type",
            "factual_basis": point,
            "significance": "Materiality requires lawyer assessment",
            "provider": "Offline local workflow",
            "model": "No external model recorded",
            "source_reference": f"Single-point dimension {index}",
            "review_status": "ai_generated_unverified",
        } for index, dimension in enumerate(dimensions, 1)]
        standard = build_standard_report(
            "single_point_2r",
            "multi_dimension_single_point_2r",
            self.case_name_var.get().strip() or "Current matter",
            self.jur_var.get(),
            findings=findings,
            input_scope={
                "selected_point": point,
                "point_type": point_mode,
                "selected_dimensions": [self.dim_label(value) for value in dimensions],
            },
            sections={"dimension_analysis": self.strip_markers(legacy)},
            limitations=[
                "Each selected dimension reviews the same user-selected point; duplication does not increase legal certainty.",
                "All attack and response language requires lawyer verification before use.",
            ],
        )
        return render_standard_markdown(standard)

    def default_point_focus_text(self):
        if not self.last_state:
            return "Enter one argument, evidence item, opposing attack point, or proposed rebuttal here."
        if self.last_state:
            attacks = self.last_state.get("rounds", {}).get("round1_opponent_attack", [])
            for item in attacks:
                target = item.get("targeting") or item.get("target") or ""
                finding = item.get("finding") or item.get("attack") or ""
                question = item.get("question") or ""
                text = "\n".join(x for x in [target, finding, question] if x).strip()
                if text:
                    return text
        return "在这里输入单条新论点、新证据、对方攻击点或我方反驳。"

    def generate_single_point_two_rounds(self, point, point_mode, dimension):
        case_text = self.get_text(self.t_bg) if hasattr(self, "t_bg") else ""
        my_position = self.get_text(self.t_pos_args) if hasattr(self, "t_pos_args") else ""
        my_evidence = self.get_text(self.t_pos_ev) if hasattr(self, "t_pos_ev") else ""
        opponent_position = self.get_text(self.t_neg_args) if hasattr(self, "t_neg_args") else ""
        opponent_evidence = self.get_text(self.t_neg_ev) if hasattr(self, "t_neg_ev") else ""
        attacker_label = "Negative side"
        defender_label = "Positive side"
        if "Attack direction: Positive side" in point or "攻防方向：正方围绕" in point:
            attacker_label = "Positive side"
            defender_label = "Negative side"
        elif "Attack direction: Negative side" in point or "攻防方向：反方围绕" in point:
            attacker_label = "Negative side"
            defender_label = "Positive side"
        state = {
            "rounds": {"round1_opponent_attack": [{"dimension": dimension, "finding": point, "question": point}]},
            "options": {"structured_case": {"pos_args": my_position, "pos_ev": my_evidence, "neg_args": opponent_position, "neg_ev": opponent_evidence}},
        }
        frames = self.suggest_tactic_frames(state)
        tactic_names = "; ".join(self.ui_en_text(x["tactic_name"]) for x in frames[:5]) if frames else "No clear tactic hit"
        counter_moves = []
        for frame in frames[:3]:
            counter_moves.extend(frame.get("counter_moves", [])[:3])
        counter_moves = list(dict.fromkeys(counter_moves))[:8]
        if not counter_moves:
            counter_moves = ["Limit the attack scope", "Split facts, rules, evidence, and causation", "Return to burden of proof", "List missing materials"]
        target_match = re.search(r"(?:被攻击对象|Target object)[:：]\s*(.+)", point)
        point_target_label = target_match.group(1).strip() if target_match else "New single point"

        if point_mode == "My New Argument/Evidence":
            r1_target = point_target_label
            r1_attack = self.compose_single_point_attack(
                point, dimension, frames,
                my_position, my_evidence, opponent_position, opponent_evidence,
            )
            r2_rebuttal = self.compose_single_point_rebuttal(
                point, r1_attack, counter_moves, my_position, my_evidence, dimension,
                opponent_position, opponent_evidence,
            )
        else:
            r1_target = "opposing single-point attack"
            r1_attack = point
            r2_rebuttal = self.compose_single_point_rebuttal(
                point, point, counter_moves, my_position, my_evidence, dimension,
                opponent_position, opponent_evidence,
            )
        r1_attack = self.polish_single_point_language_sop(r1_attack, role="attack")
        r2_rebuttal = self.polish_single_point_language_sop(r2_rebuttal, role="rebuttal")
        r1_item = {
            "dimension": dimension,
            "targeting": r1_target,
            "legacy_lawyer_frame": self.legacy_lawyer_frame(attacker_label, "单点攻击", 18),
        }
        r2_item = {
            "dimension": dimension,
            "answer_to": r1_attack,
            "legacy_lawyer_frame": self.legacy_lawyer_frame(defender_label, "单点反驳", 18),
        }

        needed = self.single_point_needed_materials(point, frames, dimension)
        return "\n".join([
            "[[TITLE]]# Single-Point 2R",
            "",
            f"案件：{self.case_name_var.get() or '未命名案件'}",
            f"Single-Point Type:{point_mode}",
            f"重点维度：{dimension}",
            "",
            f"[[NEG_BLOCK]][[SECTION]]## R1 {attacker_label}攻击",
            self.frontstage_round_speech(r1_attack, max_len=560, role="attack", dimension=dimension, item=r1_item),
            "[[END_BLOCK]]",
            "",
            f"[[POS_BLOCK]][[SECTION]]## R2 {defender_label}逐条反驳",
            self.frontstage_round_speech(r2_rebuttal, max_len=560, role="rebuttal", dimension=dimension, item=r2_item),
            "[[END_BLOCK]]",
        ])

    def polish_single_point_language_sop(self, text, role="attack"):
        text = re.sub(r"\s+", " ", str(text or "")).strip()
        if not text:
            return text
        replacements = [
            ("存在适用边界或证明缺口", "尚未完成适用条件与证明责任"),
            ("说明该单点", "逐项说明该单点"),
            ("事实基础", "事实前提"),
            ("证明来源", "证据来源"),
            ("适用边界", "适用条件和范围"),
            ("对本案结论的必要性", "对本案请求或抗辩的必要性"),
            ("要求说明", "要求逐项说明"),
            ("只是事后解释", "仍停留在事后解释"),
            ("硬撑结论", "直接硬推结论"),
            ("不能", "不能"),
        ]
        for old, new in replacements:
            text = text.replace(old, new)
        if role == "attack":
            text = text.replace("会追问：", "追问焦点：")
            if "证明责任" not in text and any(x in text for x in ["证据", "事实", "规则", "条款", "时间"]):
                text += " Burden of Proof在对方，不能由本方替对方补全事实。"
        else:
            text = text.replace("先把", "先将")
            text = text.replace("逐项回应", "逐项回应并固定可证明范围")
            text = text.replace("不得削弱我方总立场", "不得削弱本方总立场")
            if "保留" not in text:
                text += " 同时保留限缩、补证和替代论证空间。"
        active_rules = self.active_personal_sops("language_rhetoric")[:2]
        for item in active_rules:
            rule = re.sub(r"\s+", " ", str(item.get("rule", "")).strip())
            if not rule:
                continue
            self.log_personal_sop_call(item, context=f"single_point_{role}")
            if role == "attack":
                if "证明对象" in rule and "证明对象" not in text:
                    text += " 先锁定证明对象，再压回事实前提、证据来源和证明责任。"
                elif "追问" in rule and "追问" not in text:
                    text += " 追问应聚焦事实前提、证据来源和证明责任。"
            else:
                if "总立场" in rule and "总立场" not in text:
                    text += " 回应时不得削弱本方总立场。"
                elif "单点" in rule and "单点" not in text:
                    text += " 回应范围应限定在被攻击单点。"
        return text

    def single_point_voice_vars(self, point):
        target_match = re.search(r"(?:被攻击对象|Target object)[:：]\s*(.+)", point)
        target = target_match.group(1).strip() if target_match else "this single point"
        content_match = re.search(r"(?:Single-Point Content|Object content)[:：]\s*(.+)", point)
        content = content_match.group(1).strip() if content_match else self.compact(point, 160)
        direction_match = re.search(r"(?:攻击方向|Attack direction)[:：]\s*(.+)", point)
        direction = direction_match.group(1).strip() if direction_match else ""
        weak_match = re.search(r"(?:可攻击Weakness|Attackable weakness)[:：]\s*(.+)", point)
        weakness = weak_match.group(1).strip() if weak_match else ""
        names = []
        for name in re.findall(r"\b[A-Z][a-zA-Z]{1,30}\b", point):
            if name not in names and name.lower() not in {"pdf", "word", "json", "txt"}:
                names.append(name)
        opponent = "opponent"
        for pattern in [
            r"\b([A-Z][a-zA-Z]{1,30})\s*(?:主张|认为|声称|要求|依赖)",
            r"(?:请|要求)\s*([A-Z][a-zA-Z]{1,30})\s*(?:说明|回答|证明)",
        ]:
            match = re.search(pattern, point)
            if match:
                opponent = match.group(1)
                break
        client = "client"
        for name in names:
            if name != opponent:
                client = name
                break
        claim = content
        claim = re.sub(rf"^{re.escape(opponent)}\s*(?:主张|认为|声称|要求)\s*", "", claim).strip(" ：:，。")
        if not claim:
            claim = "this single point supports the conclusion"
        return {
            "target": target,
            "content": content,
            "direction": direction,
            "weakness": weakness,
            "opponent": opponent,
            "client": client,
            "claim": claim,
        }

    def single_point_voice_anchor(self, v):
        client_label = f"{v['client']}一方" if v.get("client") and v.get("client") != "本方" else "本方当事人"
        return (
            f"审判长，本方只维护{client_label}的合法利益，"
            "不接受以推测替代证明，也不接受任何削弱本方立场的不利妥协。"
        )

    def render_single_point_skeleton_attack(self, skeleton, v, frame_tail=""):
        anchor = self.single_point_voice_anchor(v)
        target = v["target"]
        opponent = v["opponent"]
        client = v["client"]
        claim = self.compact(v["claim"], 100)
        direction = v.get("direction", "")
        direction_line = ""
        if direction:
            direction_line = f"具体说，{direction}这些问题都必须由{opponent}证明。"
        if skeleton == "proof":
            recipient_label = v["client"] if v.get("client") and v.get("client") != "本方" else "相对方"
            return (
                f"{anchor}{opponent}现在依赖【{target}】，主张“{claim}”。"
                "但这份材料本身并不能自动证明其结论。"
                f"请{opponent}先回答：原始来源是什么？形成时间是否清楚？记录是否完整连续？"
                f"签收或接收主体是否具有权限？{recipient_label}何时实际知悉？"
                f"{direction_line}"
                f"如果这些基础问题不能闭合，【{target}】就仍然只是一个待证明材料，不能直接替代合同成立、责任成立或请求成立的证明。"
                f"{frame_tail}"
            )
        if skeleton == "legal":
            return (
                f"{anchor}{opponent}不能只把【{target}】贴上法律标签就跳到结论。"
                f"请{opponent}逐项说明：适用的具体规则是什么，构成要件是什么，"
                f"【{target}】分别对应哪一个事实前提和哪一个法律条件。"
                f"如果事实、规则和结论之间的映射不能闭合，所谓“{claim}”就不能成立。"
                f"{frame_tail}"
            )
        if skeleton == "counterfactual":
            return (
                f"{anchor}Counterfactual Reasoning：如果{opponent}按照正常路径及时完成必要动作，"
                f"并且【{target}】能够证明关键事实在合理时间内到达{client}并被实际知悉，"
                f"那么“{claim}”才有讨论空间。"
                f"但现在的问题是，【{target}】本身仍存在来源、时间、接收主体或知悉节点缺口。"
                f"这些前提没有发生或没有被证明，问题根源就不能转嫁给{client}。"
                f"{opponent}不能用自己的不作为或证明缺口来主张权利。"
                f"{frame_tail}"
            )
        if skeleton == "proportionality":
            return (
                f"{anchor}即使假设{opponent}最有利的前提成立（本方否认），"
                f"{opponent}也不能要求{client}承担全部责任或全部后果。"
                f"围绕【{target}】的时间、接收、知悉和证明缺口，至少说明{opponent}自身存在风险控制问题。"
                "即便法院认为需要处理责任，也应按证明程度、因果关系和损害范围进行限缩，"
                f"不能让{client}替{opponent}承担未被证明部分的后果。"
                f"{frame_tail}"
            )
        if skeleton == "cross_domain":
            return (
                f"{anchor}虽然本案主要围绕当前争议规则审查，但也可以从诚信交易、注意义务或外部规则边界重新观察。"
                f"如果{opponent}处在交易相对人的位置，其同样应当遵守及时、清楚、可核验的交易表达义务。"
                f"其依赖【{target}】却不能补足来源、时间和接收链条，本身就削弱其诚信交易立场。"
                "此外，如果该交易入口来自公开信息、平台页面、广告或第三方规则，还必须先区分要约、要约邀请和辅助规则，"
                f"不能直接把外部信息当成{opponent}可当然承诺或当然主张权利的基础。"
                f"{frame_tail}"
            )
        if skeleton == "narrative":
            return (
                f"{anchor}对方试图构建一个“自己已经完成关键动作、{client}却拒绝承担后果”的叙事。"
                f"但这个叙事选择性呈现事实：它隐去了【{target}】是否足以证明及时、有效、可知悉这一核心问题，"
                "也淡化了对方自己的证明责任。"
                f"对方不能把证明缺口包装成对{client}的不利评价。"
                f"拆穿这个叙事后，真正的问题仍然是：{opponent}是否已经完成其主张成立所需的证明。"
                f"{frame_tail}"
            )
        return (
            f"{anchor}{opponent}围绕【{target}】提出“{claim}”，但本方不接受这种跳跃。"
            f"请{opponent}回到事实前提、证据来源、适用条件和证明责任，逐项说明该单点如何支撑其结论。"
            f"{frame_tail}"
        )

    def skeleton_for_dimension(self, dimension):
        if dimension in ("证据完整性", "Fact Challenge", "Burden of Proof", "Procedural Defect", "Missing Evidence"):
            return "proof"
        if dimension in ("Legal Application", "Legal Text Interpretation", "Precedent Attack"):
            return "legal"
        if dimension in ("Logic Gap", "Counterfactual Reasoning", "Reverse Thinking"):
            return "counterfactual"
        if dimension in ("Damage Causation", "Quantum Dispute", "Proportionality Test", "Comparative Fault"):
            return "proportionality"
        if dimension in ("跨Jurisdiction武器",):
            return "cross_domain"
        if dimension in ("Narrative Deconstruction", "Public Policy", "Systemic Risk Amplification"):
            return "narrative"
        return "default"

    def single_point_related_materials(self, point, *sources, limit=2):
        keywords = set(re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}", str(point or "").lower()))
        keywords -= {"this", "that", "with", "from", "into", "point", "argument", "evidence"}
        ranked = []
        for source in sources:
            for raw in re.split(r"[\r\n]+", str(source or "")):
                line = re.sub(r"\s+", " ", raw).strip(" -\t")
                if len(line) < 12:
                    continue
                words = set(re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}", line.lower()))
                score = len(keywords & words)
                ranked.append((score, len(line), line))
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        selected = []
        for _score, _length, line in ranked:
            if line not in selected:
                selected.append(line)
            if len(selected) >= limit:
                break
        return selected

    def compose_single_point_attack(self, point, dimension, frames,
                                    positive_arguments="", positive_evidence="",
                                    negative_arguments="", negative_evidence=""):
        v = self.single_point_voice_vars(point)
        frame_tail = ""
        if frames:
            frame = frames[0]
            frame_tail = f" 请对方进一步说明：{frame['follow_up_questions'][0]}"
        skeleton = self.skeleton_for_dimension(dimension)
        if v.get("weakness") and skeleton == "default":
            v["claim"] = f"{v['claim']}；该点存在Weakness：{v['weakness']}"
        attack = self.render_single_point_skeleton_attack(skeleton, v, frame_tail)
        positive_context = self.single_point_related_materials(
            point, positive_arguments, positive_evidence, limit=2
        )
        negative_context = self.single_point_related_materials(
            point, negative_arguments, negative_evidence, limit=2
        )
        context_parts = []
        if positive_context:
            context_parts.append("Positive-side material to test: " + " | ".join(positive_context))
        if negative_context:
            context_parts.append("Negative-side material to test: " + " | ".join(negative_context))
        if context_parts:
            attack += " Main-case cross-check: " + " ".join(context_parts)
        return attack

    def compose_single_point_rebuttal(self, point, attack, counter_moves, my_position,
                                      my_evidence, dimension=None,
                                      opponent_position="", opponent_evidence=""):
        base = [
            "先把对方攻击限定在这一条单点上，避免对方扩大成全案否定。",
        ]
        dimension_moves = {
            "Fact Challenge": "回应时先固定事实来源、形成时间和可验证材料；对方若只做概括怀疑，应要求其指出具体矛盾或缺口。",
            "Legal Application": "回应时先列明适用规则、构成要件和本案事实对应点；不泛称法律存在，只证明本条单点满足对应前提。",
            "Precedent Attack": "回应时说明引用规则或案例与本案在主体、交易结构、争点和救济上的同构点，同时切开不相干差异。",
            "Logic Gap": "回应时把结论拆回事实前提、推理步骤和因果节点；对方若提出替代解释，应要求其说明替代解释的证据基础。",
            "Procedural Defect": "回应时按时间线列出通知、送达、确认、提交和回复节点；把程序攻击压回具体期限和具体记录。",
            "Damage Causation": "回应时分别处理责任来源、损害发生、因果连接和救济范围，避免把结果直接当成责任。",
            "Quantum Dispute": "回应时把金额、范围、计算口径和替代救济分开说明；不让对方用金额不确定否定全部基础事实。",
            "Burden of Proof": "回应时先确认本方只证明自己应证明的部分，再把对方反驳所需事实和反证责任压回对方。",
            "Legal Text Interpretation": "回应时回到条款原文、上下文、目的和交易当时版本，防止对方用抽象公平感改写文本。",
            "Comparative Fault": "回应时区分双方各自注意义务、控制能力和风险节点；只承认可证明的比例，不扩大为全盘责任。",
            "Public Policy": "回应时把个案救济和规则外溢区分开；对方若放大系统风险，应要求其给出行业事实或制度依据。",
            "Reverse Thinking": "回应时反向检查没有该单点时本方主张是否仍有其他支撑，并把该单点定位为主证据、辅证据或补强证据。",
            "跨Jurisdiction武器": "回应时说明外Jurisdiction材料只作为解释或比较辅助，核心仍落在本Jurisdiction规则和本案事实。",
            "Counterfactual Reasoning": "回应时建立反事实边界：没有该事实时结果如何，有该事实时链条如何变化，并说明替代原因为何不足。",
            "Proportionality Test": "回应时证明本方请求和风险、损害、履行成本之间相称；同时预留维修、折价、部分补偿等次级路径。",
            "Narrative Deconstruction": "回应时把叙事标签拆成可证明事实，避免情绪化表达；让本方故事服务证据链，不代替证据链。",
            "Systemic Risk Amplification": "回应时承认规则需要边界，但强调本案只处理已证明的具体事实，不把个案无限扩张。",
            "Missing Evidence": "回应时解释沉默、缺失或未提交材料的合理原因；同时说明现有积极证据为何仍能支撑该单点。",
        }
        if dimension in dimension_moves:
            base.append(dimension_moves[dimension])
        else:
            base.append("把该单点拆成事实、规则、证据、因果和补救五个层面逐项回应。")
        if counter_moves:
            base.append("针对本条可采用：" + "；".join(counter_moves[:5]) + "。")
        if my_evidence:
            base.append("我方现有证据应优先用于证明该单点的来源、时间线和与核心主张的关联。")
        else:
            base.append("若现有证据不足，应把该单点标记为需补证，而不是在庭审中硬撑结论。")
        if my_position:
            base.append("反驳时不得削弱我方总立场，只能把该单点纳入我方既有诉求或抗辩路径。")
        own_context = self.single_point_related_materials(point, my_position, my_evidence, limit=2)
        opposing_context = self.single_point_related_materials(
            point, opponent_position, opponent_evidence, limit=2
        )
        if own_context:
            base.append(" Existing positive-side support to use or verify: " + " | ".join(own_context) + ".")
        if opposing_context:
            base.append(" Existing negative-side material requiring an answer: " + " | ".join(opposing_context) + ".")
        return "".join(base)

    def compose_single_point_counter_response(self, rebuttal, frames):
        if frames:
            frame = frames[0]
            return (
                f"对方会继续说：我方后招仍未解决【{frame['opponent_move']}】的核心问题。"
                "如果我方不能拿出对应原始材料，对方会主张该反驳只是事后解释。"
            )
        return "对方会继续攻击我方反驳过于概括，要求我方把证据、时间线、法律依据和因果链逐项落到具体材料上。"

    def compose_single_point_final(self, point, r1_attack, r2_rebuttal, r3_response, my_position):
        return (
            "最终应把该单点收束为一个可证明、可追问、可补证的问题："
            "对方若不能完成自己的证明责任，该单点不能推翻我方总立场；"
            "我方若材料不足，则把它降级为辅助论点，并用主证据链维持核心路径。"
        )

    def single_point_needed_materials(self, point, frames, dimension=None):
        materials = ["单点对应的原始材料", "形成时间或来源说明", "与核心争点的关联说明"]
        dimension_materials = {
            "Fact Challenge": ["原始记录", "形成过程说明", "可核验来源", "与其他材料的对应表"],
            "Legal Application": ["法条构成要件表", "本案事实对应表", "适用前提说明", "例外条款排除说明"],
            "Precedent Attack": ["引用案例或规则全文", "相同点/不同点对照表", "争点同构说明", "Jurisdiction适用说明"],
            "Logic Gap": ["推理链条图", "替代解释排除表", "因果节点说明", "结论依赖关系表"],
            "Procedural Defect": ["通知记录", "送达或提交记录", "关键期限表", "对方回复或确认记录"],
            "Damage Causation": ["损害发生记录", "责任节点说明", "因果链材料", "介入因素排除表"],
            "Quantum Dispute": ["金额明细", "计算口径", "损失范围说明", "替代补救方案"],
            "Burden of Proof": ["证明对象列表", "证明责任分配表", "已提交证据清单", "对方反证缺口"],
            "Legal Text Interpretation": ["交易当时条款版本", "条款上下文", "提示或接受记录", "文本目的说明"],
            "Comparative Fault": ["双方控制能力说明", "注意义务节点表", "风险分担材料", "比例责任说明"],
            "Public Policy": ["规则边界说明", "行业惯例材料", "公共利益影响说明", "个案事实限制条件"],
            "Reverse Thinking": ["主备证据链", "去除该单点后的支撑表", "替代论证路径", "风险开关表", "本Jurisdiction强制规则清单", "比较法/平台规则边界"],
            "跨Jurisdiction武器": ["本Jurisdiction规则依据", "外Jurisdiction材料全文", "比较法适用边界", "监管/平台规则适用范围", "本案事实落点"],
            "Counterfactual Reasoning": ["反事实条件表", "结果变化说明", "替代原因材料", "必要性证明"],
            "Proportionality Test": ["请求范围说明", "救济比例说明", "替代方案清单", "成本或影响材料"],
            "Narrative Deconstruction": ["事实标签对照表", "证据支撑清单", "叙事顺序时间线", "选择性呈现排查"],
            "Systemic Risk Amplification": ["规则外溢边界", "系统风险依据", "个案限制条件", "反向Public Policy材料"],
            "Missing Evidence": ["未提交原因说明", "现有积极证据清单", "缺失材料影响评估", "补交或调取路径"],
        }
        materials.extend(dimension_materials.get(dimension, []))
        names = {f["tactic_name"] for f in frames}
        if "证据完整性压迫" in names:
            materials.extend(["原始视频/照片/文件", "连续时间戳", "第三方或平台记录", "封条/签收/外包装状态"])
        if "结果倒推" in names:
            materials.extend(["替代原因列表", "介入因素排除表", "关键时间线"])
        if "法条压迫" in names:
            materials.extend(["法条构成要件表", "本案事实对应表", "对方适用前提缺口"])
        if "比例过度" in names:
            materials.extend(["金额明细", "替代补救方案", "功能影响或损害程度说明"])
        return list(dict.fromkeys(materials))

    def open_tactic_suggestions(self):
        if not self.last_state:
            messagebox.showwarning("No Opposition Record", "Please run opposition once first.")
            return
        frames = self.suggest_tactic_frames(self.last_state)
        win = tk.Toplevel(self.root)
        win.title("Tactic Suggestions")
        win.geometry("980x700")
        t = scrolledtext.ScrolledText(win, bg=self.C["entry"], fg=self.C["text"], font=("Microsoft YaHei UI", 11), wrap=tk.WORD)
        self.bind_local_scroll(t)
        t.pack(fill=tk.BOTH, expand=True)
        t.insert(tk.END, self.render_tactic_frame_report(frames))

    def open_summary_window(self):
        if not self.last_state:
            messagebox.showwarning("No Summary", "Please scan weaknesses or run two-round opposition first.")
            return
        win = tk.Toplevel(self.root)
        win.title("Case Summary")
        win.geometry("760x460")
        win.configure(bg=self.C["panel"])
        t = scrolledtext.ScrolledText(
            win,
            bg=self.C["entry"],
            fg=self.C["text"],
            font=("Microsoft YaHei UI", 11),
            wrap=tk.WORD,
            relief="flat",
        )
        self.bind_local_scroll(t)
        t.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.configure_output_tags(t)
        self.insert_colored(t, self.render_summary(self.last_state))
        t.config(state=tk.DISABLED)

    def render_reviews(self, state):
        lines = ["[[TITLE]]# Stance Continuity Review\n"]
        for review in state.get("stance_reviews", []):
            lines.append(f"- {review.get('stage', 'stage')}: {review.get('status', '')} {review.get('note', '')}")
        lines.append("\n\n[[TITLE]]# Lawyer-Team Persona Anchors\n")
        for name, anchor in state.get("persona_anchors", {}).items():
            lines.append(f"[[SECTION]]## {name}\n")
            lines.append(f"- Prior statement: {anchor.get('past_statement', '')}\n")
            lines.append(f"- Attack habit: {anchor.get('attack_habit', '')}\n")
            lines.append(f"- Boundary: {anchor.get('red_line', '')}\n")
        return "\n".join(lines)

    def swap_sides(self):
        pos_args, pos_ev = self.get_text(self.t_pos_args), self.get_text(self.t_pos_ev)
        neg_args, neg_ev = self.get_text(self.t_neg_args), self.get_text(self.t_neg_ev)
        self.set_text(self.t_pos_args, neg_args)
        self.set_text(self.t_pos_ev, neg_ev)
        self.set_text(self.t_neg_args, pos_args)
        self.set_text(self.t_neg_ev, pos_ev)

    def _professional_report_key(self):
        selected = self.professional_report_type_var.get().strip()
        for key, label in PROFESSIONAL_REPORT_TYPES.items():
            if selected == label:
                return key
        return "lawyer_working_paper"

    def _professional_chronology(self, case_text):
        month = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        date_pattern = re.compile(
            rf"\b(?:\d{{4}}-\d{{1,2}}-\d{{1,2}}|\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}}|\d{{1,2}}\s+{month}\s+\d{{4}}|{month}\s+\d{{1,2}},?\s+\d{{4}})\b",
            re.I,
        )
        rows = []
        for line in str(case_text or "").splitlines():
            clean = line.strip()
            match = date_pattern.search(clean)
            if clean and match:
                rows.append({
                    "date": match.group(0),
                    "event": clean,
                    "source_reference": "Supplied case background",
                    "status": "Extracted from supplied text; lawyer verification required",
                })
        return rows[:100]

    def _professional_evidence_index(self):
        rows = []
        for side, text in (
            ("Positive", self.get_text(self.t_pos_ev)),
            ("Negative", self.get_text(self.t_neg_ev)),
        ):
            current = None
            for line in str(text or "").splitlines():
                clean = line.strip()
                if not clean:
                    continue
                tag = re.match(r"^\[([A-Za-z]+\d+)\]\s*(.*)$", clean)
                if tag:
                    current = {
                        "item": tag.group(1).upper(),
                        "side": side,
                        "document_or_evidence": tag.group(2).strip() or "Description not supplied",
                        "source_reference": "User-entered evidence frame",
                        "status": "Supplied or indexed; authenticity and admissibility unverified",
                    }
                    rows.append(current)
                elif current is not None:
                    current["document_or_evidence"] += " " + clean
                else:
                    rows.append({
                        "item": f"{side[0]}-{len(rows) + 1:02d}",
                        "side": side,
                        "document_or_evidence": clean,
                        "source_reference": "User-entered evidence frame",
                        "status": "Supplied or indexed; authenticity and admissibility unverified",
                    })
        return rows

    def build_offline_professional_record(self):
        if not self.last_state:
            raise RuntimeError("Run a weakness scan or opposition before creating a professional report.")
        state = self.last_state
        rounds = state.get("rounds") or {}
        attacks = [item for item in (rounds.get("round1_opponent_attack") or []) if isinstance(item, dict)]
        rebuttals = [item for item in (rounds.get("round2_my_rebuttal") or []) if isinstance(item, dict)]
        issues = []
        risk_notes = []
        for index, item in enumerate(attacks, 1):
            dimension = self.dim_label(item.get("dimension", "")) or f"Dimension {index}"
            issue = item.get("finding") or item.get("attack") or item.get("question") or ""
            if issue:
                issues.append({
                    "id": f"W-{index:02d}",
                    "dimension": dimension,
                    "issue": self.english_detail_or_empty(issue) or str(issue),
                    "source_reference": "Round 1 opposition state",
                    "review_status": "Requires lawyer verification",
                })
            risk_notes.append({
                "dimension": dimension,
                "confidence": str(item.get("confidence") or "Not independently scored"),
                "note": "System-generated diagnostic output; materiality and legal significance require lawyer review.",
            })
        dimension_rows = []
        for raw_dimension in state.get("selected_dimensions") or []:
            attack = next((item for item in attacks if item.get("dimension") == raw_dimension), {})
            rebuttal = next((item for item in rebuttals if item.get("dimension") == raw_dimension), {})
            dimension_rows.append({
                "dimension": self.dim_label(raw_dimension),
                "identified_issue": self.english_detail_or_empty(attack.get("finding") or attack.get("attack") or "") or "No material issue recorded.",
                "response_or_counterpoint": self.english_detail_or_empty(rebuttal.get("response") or rebuttal.get("answer_to") or "") or "No response recorded.",
                "needed_material": "; ".join(str(value) for value in (rebuttal.get("needed_material") or []) if str(value).strip()) or "No specific material recorded.",
            })
        missing = []
        for item in rebuttals:
            needed = item.get("needed_material") or []
            if isinstance(needed, str):
                needed = [needed]
            missing.extend(str(value).strip() for value in needed if str(value).strip())
        missing = list(dict.fromkeys(missing))
        counts = ((state.get("execution_trace") or {}).get("counts") or {})
        external_calls = int(counts.get("cloud_calls_for_case_text") or 0)
        if external_calls:
            preset = PROVIDER_PRESETS.get(self.cloud_provider_var.get(), {})
            provider = preset.get("label") or self.cloud_provider_var.get() or "Configured provider"
            model = self.cloud_model_var.get().strip() or "Configured model not recorded"
            engine_source = f"External model route recorded by execution trace ({external_calls} full-case call(s))"
        else:
            provider = "Offline local workflow"
            model = "No external model recorded"
            engine_source = "Local application state"
        return {
            "report_type": self._professional_report_key(),
            "matter_name": self.case_name_var.get().strip() or state.get("case_key") or "Current matter",
            "jurisdiction": self.jur_var.get().strip() or state.get("jurisdiction") or "Not specified",
            "generated_at_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "engine_metadata": {"provider": provider, "model": model, "source": engine_source},
            "executive_summary": self.strip_markers(self.render_summary(state)),
            "case_profile": {
                "workflow_mode": state.get("workflow_mode") or state.get("mode") or "Not recorded",
                "confidentiality": state.get("options", {}).get("confidentiality_mode", self.confidential_var.get()),
                "selected_dimensions": len(state.get("selected_dimensions") or []),
                "full_case_external_calls": external_calls,
            },
            "chronology": self._professional_chronology(self.get_text(self.t_bg)),
            "positions": {
                "positive_side_arguments": self.get_text(self.t_pos_args) or "Not supplied",
                "negative_side_arguments": self.get_text(self.t_neg_args) or "Not supplied",
            },
            "evidence_index": self._professional_evidence_index(),
            "issues_and_weaknesses": issues,
            "dimension_analysis": dimension_rows,
            "missing_information": missing,
            "risk_and_confidence": risk_notes,
            "lawyer_verification_tasks": [
                "Verify the factual record against original source material.",
                "Verify the governing law, jurisdiction, current authorities, deadlines and procedural requirements.",
                "Decide which identified issues are material and approve all wording before client or external use.",
                "Check whether the selected court, regulator or recipient requires an official form or template.",
            ],
            "scope_and_limits": [
                "This report organises and presents supplied software state; it does not establish that a fact or allegation is true.",
                "No court, regulator, filing rule, authority or citation is treated as verified unless counsel independently confirms it.",
                "This is AI-assisted lawyer reference material, not legal advice or a final legal opinion.",
            ],
            "include_contents": bool(self.professional_include_contents_var.get()),
            "include_page_numbers": bool(self.professional_include_pages_var.get()),
            "include_source_references": bool(self.professional_include_sources_var.get()),
            "include_evidence_index": bool(self.professional_include_evidence_var.get()),
        }

    def export_professional_report(self):
        try:
            record = self.build_offline_professional_record()
        except Exception as exc:
            messagebox.showwarning("Professional Report Not Ready", str(exc), parent=self.root)
            return
        output_dir = filedialog.askdirectory(title="Choose Professional Report Folder")
        if not output_dir:
            return
        report_key = self._professional_report_key().replace("_", "-")
        base = Path(output_dir) / f"{self.case_slug()}-{report_key}"
        selected_format = self.professional_output_format_var.get().strip()
        created = []
        try:
            json_path = base.with_suffix(".structured.json")
            json_path.write_text(record_as_json(record), encoding="utf-8-sig")
            created.append(json_path)
            final_standard = build_standard_report(
                "final_lawyer_pack",
                "professional_report_export",
                record.get("matter_name"),
                record.get("jurisdiction"),
                findings=record.get("issues_and_weaknesses") or [],
                provider_runs=[record.get("engine_metadata") or {}],
                input_scope=record.get("case_profile") or {},
                sections={
                    "chronology": record.get("chronology") or [],
                    "positions": record.get("positions") or {},
                    "evidence_index": record.get("evidence_index") or [],
                    "dimension_analysis": record.get("dimension_analysis") or [],
                    "risk_and_confidence": record.get("risk_and_confidence") or [],
                },
                missing_material=record.get("missing_information") or [],
                limitations=record.get("scope_and_limits") or [],
            )
            final_paths = write_standard_companions(output_dir, f"{self.case_slug()}-final-lawyer-pack", final_standard)
            created.extend(Path(path) for path in final_paths.values())
            evidence_standard = build_standard_report(
                "evidence_index", "evidence_index_export", record.get("matter_name"), record.get("jurisdiction"),
                provider_runs=[record.get("engine_metadata") or {}],
                input_scope={"evidence_items": len(record.get("evidence_index") or [])},
                sections={"evidence_index": record.get("evidence_index") or []},
                missing_material=record.get("missing_information") or [],
            )
            evidence_paths = write_standard_companions(output_dir, f"{self.case_slug()}-evidence-index", evidence_standard)
            created.extend(Path(path) for path in evidence_paths.values())
            chronology_standard = build_standard_report(
                "chronology", "chronology_export", record.get("matter_name"), record.get("jurisdiction"),
                provider_runs=[record.get("engine_metadata") or {}],
                input_scope={"chronology_entries": len(record.get("chronology") or [])},
                sections={"chronology": record.get("chronology") or []},
                limitations=["Dates and events are extracted from supplied text and require verification against original source material."],
            )
            chronology_paths = write_standard_companions(output_dir, f"{self.case_slug()}-chronology", chronology_standard)
            created.extend(Path(path) for path in chronology_paths.values())
            if selected_format == "Markdown + JSON":
                markdown_path = base.with_suffix(".md")
                markdown_path.write_text(build_professional_markdown(record), encoding="utf-8-sig")
                created.append(markdown_path)
            if selected_format in {"Word + PDF", "Editable Word"}:
                word_path = base.with_suffix(".docx")
                word_path.write_bytes(build_professional_docx(record))
                created.append(word_path)
            if selected_format in {"Word + PDF", "PDF"}:
                pdf_path = base.with_suffix(".pdf")
                pdf_path.write_bytes(build_professional_pdf(record))
                created.append(pdf_path)
        except Exception as exc:
            messagebox.showerror("Professional Export Failed", str(exc), parent=self.root)
            return
        self.status_var.set(f"Status: professional report exported ({len(created)} files)")
        messagebox.showinfo(
            "Professional Report Exported",
            "Created:\n" + "\n".join(str(path) for path in created),
            parent=self.root,
        )

    def export_report(self):
        if not self.last_state:
            messagebox.showwarning("No Report", "Please run opposition once first.")
            return
        default = (self.case_name_var.get() or "nido_strikeover_report").replace(" ", "_") + ".md"
        path = filedialog.asksaveasfilename(title="Export Report", defaultextension=".md", initialfile=default, filetypes=[("Markdown", "*.md"), ("Text", "*.txt")])
        if not path:
            return
        standard_report = self.build_standard_two_round_report(self.last_state)
        content = render_standard_markdown(standard_report)
        Path(path).write_text(content, encoding="utf-8-sig")
        Path(path).with_suffix(".professional.json").write_text(
            json.dumps(standard_report, ensure_ascii=False, indent=2), encoding="utf-8-sig"
        )
        html_path = Path(path).with_suffix(".html")
        html_path.write_text(self.report_html_from_text(self.case_name_var.get(), content), encoding="utf-8")
        messagebox.showinfo("Exported", path)

    def open_run_dir(self):
        path = self.last_run_dir or (HERE / "runs")
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(str(path))

    def save_case(self):
        data = {
            "case_name": self.case_name_var.get(),
            "jurisdiction": self.jur_var.get(),
            "case_text": self.get_text(self.t_bg),
            "pos_args": self.get_text(self.t_pos_args),
            "pos_ev": self.get_text(self.t_pos_ev),
            "neg_args": self.get_text(self.t_neg_args),
            "neg_ev": self.get_text(self.t_neg_ev),
            "local_law_region": self.current_law_region()["label"],
            "case_search_enabled": bool(self.case_search_var.get()),
            "professional_report_settings": {
                "report_type": self._professional_report_key(),
                "output_format": self.professional_output_format_var.get(),
                "include_contents": bool(self.professional_include_contents_var.get()),
                "include_page_numbers": bool(self.professional_include_pages_var.get()),
                "include_source_references": bool(self.professional_include_sources_var.get()),
                "include_evidence_index": bool(self.professional_include_evidence_var.get()),
            },
        }
        default = (data["case_name"] or "nido_case").replace(" ", "_") + ".json"
        path = filedialog.asksaveasfilename(title="Save Case File", defaultextension=".json", initialfile=default, filetypes=[("JSON", "*.json")])
        if not path:
            return
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8-sig")
        messagebox.showinfo("Saved", path)

    def load_case(self):
        path = filedialog.askopenfilename(title="Load Case File", filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if path:
            self.load_case_path(path)

    def open_fullscreen(self):
        win = tk.Toplevel(self.root)
        win.title("Nido StrikeOver - Fullscreen Opposition Results")
        win.state("zoomed")
        win.configure(bg=self.C["panel"])
        nb = ttk.Notebook(win)
        nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        for key, title in [("attacks", "Attack Details"), ("json", "Safe Display State")]:
            f = ttk.Frame(nb)
            nb.add(f, text=title)
            t = scrolledtext.ScrolledText(f, bg=self.C["entry"], fg=self.C["text"], font=("Microsoft YaHei UI", 12), wrap=tk.WORD)
            self.bind_local_scroll(t)
            t.pack(fill=tk.BOTH, expand=True)
            self.configure_output_tags(t)
            if key == "attacks" and self.last_state:
                self.insert_colored(t, self.render_attack_details(self.last_state))
            elif key == "json" and self.last_state:
                self.set_text(t, json.dumps(self.display_state_for_json(self.last_state), ensure_ascii=False, indent=2))
            else:
                self.insert_colored(t, self.outputs[key].get("1.0", tk.END))
            t.config(state=tk.DISABLED)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    NidoOldSkinApp().run()




