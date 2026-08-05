#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StrikeOver v2.12 - 对称攻防诉讼策略预演系统
专利 AU 2026202656

v2.12 改进 (Patent 5 辩论模式):
- 每轮 prompt 改造为"调节器告知"模式 (告知用户身份 + 已做工作 + 对方现状)
- 删除强制立场禁令, 改为自然对齐 (告知 AI 已做了什么, 比强迫虚假立场更有效)
- 内部分析模块: 静默扫描每轮输出, 检测立场弱化信号
- 报告增强: 自动提炼"庭审重点准备"——对方攻击奏效点提示

v2.11 改进：
- 维度精简：17→18维度（删3合2重定义2新增5）
- "历史判例搜索"从攻击维度改为独立搜索开关
- "当事人适格"并入"程序瑕疵"
- "损害可预见性"+"减损义务"并入"量化争议"
- "合同解释"→"法律文本解释"（扩展适用范围）
- 新增5个元维度：反事实推演/比例原则检验/叙事解构/系统性风险放大/沉默证据

v2.10 改进：
- 首次运行时弹窗提醒开启数据脱敏

v2.9 改进：
- 逐轮脱敏：每轮辩论发送前对完整prompt脱敏，防止前轮输出泄露新PII
- 还原逻辑不变：所有轮次结束后一次性还原
- v2.8改进：
  - 新增数据脱敏功能（PIIAnonymizer）：发送到云大模型前自动替换姓名/日期/地址/金额等敏感信息
  - 返回结果后自动还原脱敏数据
  - GUI 新增「🔒 数据脱敏」checkbox，默认关闭，用户自行启用
  - 辩论流程改为4轮交替（反方先攻，正方后守）
  - 证据反驳助手：针对单条证据生成精准反驳（点攻击）
  - 法官叠加画框：接收所有人的陈述，独立分析双方弱点
  - 画框隔离 + 叠加系统双轨运行

辩论流程（4轮交替）：
 Round 1: 反方攻击正方（只看正方初始论点）
 Round 2: 正方反驳（看到反方攻击）
   法官: 叠加所有人的陈述，独立分析

核心架构：
- M×N并行（多家模型 × 15维度）
- 画框隔离（正反方各自独立认知空间）
- 叠加系统（法官画框接收所有陈述）
- 证据反驳助手（点攻击：针对单条证据精准反驳）
- 真实案例搜索引擎（自动降级）
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog, simpledialog
import json, os, sys, threading, time, hashlib, re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

USER_SITE_CANDIDATES = [
    os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Python", f"Python{sys.version_info.major}{sys.version_info.minor}", "site-packages"),
    os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Python", f"python{sys.version_info.major}{sys.version_info.minor}", "site-packages"),
]
for user_site in USER_SITE_CANDIDATES:
    if user_site not in sys.path:
        sys.path.append(user_site)

try:
    from tkinterdnd2 import TkinterDnD
except Exception:
    TkinterDnD = None

# 自动安装依赖
try:
    import requests
except ImportError as exc:
    raise RuntimeError("在线版缺少 requests，请使用 START_在线版.bat 或安装 requests。") from exc
import urllib.parse
import webbrowser
import difflib
from google_cloud_backend import get_backend

# ========== 搜索缓存 ==========
SEARCH_CACHE = {}

# ========== 配置文件安全处理 ==========
APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(APP_DIR, "api_profiles.local.json")
SESSION_FILE = os.path.join(APP_DIR, "cloud_session.local.json")
DRAFT_FILE = os.path.join(APP_DIR, "online_user_data", "draft.local.json")
CASES_DIR = os.path.join(APP_DIR, "online_user_data", "cases")
AUTO_SAVE_CASE_CONTENT = False

os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
os.makedirs(CASES_DIR, exist_ok=True)

gitignore_path = os.path.join(os.path.dirname(CONFIG_FILE), ".gitignore")
if not os.path.exists(gitignore_path):
    with open(gitignore_path, "w") as f:
        f.write("# API Keys - DO NOT COMMIT\n*.json\n")

# ========== 18个攻击维度 ==========
ALL_DIMENSIONS = [
    # ── 核心维度 ──
    ("事实质疑", "证据真实性、完整性、来源可靠性"),
    ("法律适用", "法条引用是否准确、是否过时、是否适用本管辖区"),
    ("先例对抗", "搜索反面先例、类似案件败诉判例、区分有利先例；利用搜索结果构建先例论证"),
    ("逻辑漏洞", "因果链断裂、以偏概全、循环论证、滑坡谬误"),
    ("程序瑕疵", "取证程序、时效问题、管辖权、诉讼资格、当事人适格"),
    ("损害因果关系", "因果关系是否成立、介入因素、贡献度"),
    ("量化争议", "赔偿金额合理性、计算方法、市场对标；含损害可预见性（远端损害排除）、减损义务（扩大损失自担）"),
    # ── 战术维度 ──
    ("举证责任", "举证责任分配、证明标准是否达到、间接证据效力"),
    ("法律文本解释", "条款歧义利用、行业惯例对抗、格式条款无效；适用于合同、法规、判决书等所有法律文本"),
    ("过失比较", "原告是否有过错、共同过失、贡献性过失"),
    ("公共政策", "裁决是否违背公共利益、道德考量、示范效应"),
    # ── 元维度：换框架攻击 ──
    ("逆向思维", "从我方理想结局倒推：法官必须采信什么事实、需要什么证据、现有证据缺什么、对方最可能的突破口、最大风险路径"),
    ("跨法域武器", "本案虽属X法域，但其他法域（刑法/反不正当竞争法/消费者权益保护法/行政法/宪法）可否作为辅助武器；用刑事报案/行政投诉施压的可能性"),
    ("反事实推演", "如果关键事实未发生，结果会怎样？攻击因果关系的必要性——去掉某环后结论是否还成立"),
    ("比例原则检验", "即使权利主张成立，诉求的幅度是否合乎比例？'就算你全对，500万不合理'"),
    ("叙事解构", "不打证据/法律，打叙事结构：选择性呈现、时序操纵、因果跳跃、情感绑架——人对叙事漏洞敏感度远高于逻辑漏洞"),
    ("系统性风险放大", "如果法院支持对方，会创造什么坏先例？对行业/社会/司法体系的影响？给法官超越本案的理由"),
    ("沉默证据", "不在对方提交的证据里找漏洞，在缺失的证据里找——'如果有口头协议，为什么没有邮件记录？'"),
]

DIMENSION_LABELS_EN = {
    "事实质疑": "Fact Challenge",
    "法律适用": "Legal Application",
    "先例对抗": "Precedent Resistance",
    "逻辑漏洞": "Logic Gap",
    "程序瑕疵": "Procedural Defect",
    "损害因果关系": "Causation and Damage",
    "量化争议": "Quantum Dispute",
    "举证责任": "Burden of Proof",
    "法律文本解释": "Legal Text Interpretation",
    "过失比较": "Comparative Fault",
    "公共政策": "Public Policy",
    "逆向思维": "Reverse Reasoning",
    "跨法域武器": "Cross-Domain Weapon",
    "反事实推演": "Counterfactual Test",
    "比例原则检验": "Proportionality Test",
    "叙事解构": "Narrative Deconstruction",
    "系统性风险放大": "Systemic Risk Amplification",
    "沉默证据": "Silent Evidence",
}

DIMENSION_DESC_EN = {
    "事实质疑": "Authenticity, completeness, and source reliability of evidence.",
    "法律适用": "Whether the rule is current, accurate, and applicable to this jurisdiction.",
    "先例对抗": "Adverse authorities, failed analogies, and distinguishing favorable precedent.",
    "逻辑漏洞": "Broken causal chains, over-generalization, circular reasoning, and non sequitur.",
    "程序瑕疵": "Collection procedure, limitation, jurisdiction, standing, and party capacity.",
    "损害因果关系": "Causation, intervening factors, and contribution to loss.",
    "量化争议": "Quantum, calculation method, comparators, foreseeability, and mitigation.",
    "举证责任": "Burden allocation, proof standard, and indirect evidence sufficiency.",
    "法律文本解释": "Ambiguity, usage, unfair terms, and textual interpretation.",
    "过失比较": "Opponent fault, shared responsibility, and contributory negligence.",
    "公共政策": "Public interest, morality, precedent effect, and systemic incentives.",
    "逆向思维": "Reason backward from our desired outcome to required facts and proof.",
    "跨法域武器": "Use adjacent legal domains as pressure tools.",
    "反事实推演": "Remove or alter key facts and test whether causation survives.",
    "比例原则检验": "Test whether the remedy is excessive even if the right exists.",
    "叙事解构": "Attack selective story framing, chronology, causation, and emotion.",
    "系统性风险放大": "Show harmful precedent, industry risk, or judicial-management risk.",
    "沉默证据": "Attack missing documents, records, logs, emails, and third-party proof.",
}

# ========== 律师人格模板 ==========
LAWYER_PERSONALITIES = [
    {"name": "激进型", "style": "攻击性强，善于抓住对方漏洞，言辞犀利"},
    {"name": "稳健型", "style": "注重证据链完整性，论证严密，步步为营"},
    {"name": "技术型", "style": "擅长法律技术细节，善于运用程序规则"},
    {"name": "策略型", "style": "全局观强，善于权衡利弊，考虑多种可能"},
]

# ========== API提供商预设 ==========
PROVIDER_PRESETS = {
    "deepseek": {"name": "DeepSeek", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat", "rate_input": 0.001, "rate_output": 0.002},
    "openai": {"name": "OpenAI", "base_url": "https://api.openai.com/v1", "model": "gpt-4o", "rate_input": 0.005, "rate_output": 0.015},
    "anthropic": {"name": "Anthropic", "base_url": "https://api.anthropic.com/v1", "model": "claude-sonnet-4-20250514", "rate_input": 0.003, "rate_output": 0.015},
    "gemini": {"name": "Google Gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta", "model": "gemini-2.5-flash", "rate_input": 0.001, "rate_output": 0.002},
    "moonshot": {"name": "Moonshot", "base_url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-8k", "rate_input": 0.012, "rate_output": 0.012},
    "zhipu": {"name": "智谱AI", "base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4", "rate_input": 0.05, "rate_output": 0.05},
    "azure-au": {"name": "Azure Australia", "base_url": "https://australiaeast.api.cognitive.microsoft.com/openai/deployments", "model": "gpt-4o", "rate_input": 0.005, "rate_output": 0.015},
}

# 别名映射：输入 claude/claoud → anthropic，输入 gpt/chatgpt → openai，等等
PROVIDER_ALIASES = {
    "claude": "anthropic", "claoud": "anthropic", "anthropic": "anthropic",
    "gpt": "openai", "chatgpt": "openai", "openai": "openai",
    "deepseek": "deepseek", "ds": "deepseek",
    "gemini": "gemini", "google": "gemini", "bard": "gemini",
    "moonshot": "moonshot", "kimi": "moonshot",
    "zhipu": "zhipu", "glm": "zhipu",
}

# ========== 案例搜索引擎（专业法律数据库优先） ==========
class CaseSearchEngine:
    SOURCES = [
        {"name": "AustLII", "url": "https://www.austlii.edu.au", "parse": "austlii", "type": "legal_db"},
        {"name": "DuckDuckGo", "url": "https://duckduckgo.com/html/?q=", "parse": "ddg", "type": "search_engine"},
        {"name": "Bing", "url": "https://www.bing.com/search?q=", "parse": "bing", "type": "search_engine"},
    ]

    def __init__(self):
        self.log = []
        self.keys = {} # 存储 API keys

    def _austlii(self, query):
        """搜索 AustLII 澳大利亚法律数据库"""
        # AustLII 搜索接口
        search_url = "https://www.austlii.edu.au/cgi-bin/searchdb.pl"
        params = {
            "method": "auto",
            "query": query,
            "meta": "/au",
            "results": "10"
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
        }

        try:
            r = requests.get(search_url, params=params, headers=headers, timeout=15)
            r.raise_for_status()

            results = []
            # 解析 AustLII 搜索结果页面
            # AustLII 返回格式：<li><a href="/au/cases/...">Case Name</a> - Court Year</li>
            for m in re.finditer(r'<li>\s*<a\s+href="([^"]+)"[^>]*>([^<]+)</a>\s*-?\s*([^<]{0,100})', r.text):
                url = "https://www.austlii.edu.au" + m.group(1)
                title = m.group(2).strip()
                snippet = m.group(3).strip()
                results.append({
                    "title": title,
                    "snippet": snippet[:200] if snippet else "",
                    "url": url
                })

            if not results:
                # 备用解析模式1: 更宽松的 li + a 标签
                for m in re.finditer(r'<li[^>]*>\s*<a\s+href="(/au/[^"]+)"[^>]*>([^<]{5,})</a>', r.text, re.I):
                    url = "https://www.austlii.edu.au" + m.group(1)
                    title = m.group(2).strip()
                    results.append({"title": title, "snippet": "", "url": url})

            if not results:
                # 备用解析模式2: search-db 结果链接
                for m in re.finditer(r'<a\s+href="(/cgi-bin/searchdb\.pl[^"]*)"[^>]*>([^<]{5,})</a>', r.text):
                    url = "https://www.austlii.edu.au" + m.group(1)
                    title = m.group(2).strip()
                    results.append({"title": title, "snippet": "", "url": url})


            if results:
                self.log.append(f"✓ AustLII 返回 {len(results)} 条结果")
                return {"results": results[:10]}
            raise ValueError("AustLII 无结果")

        except Exception as e:
            self.log.append(f"⚠ AustLII 搜索失败: {str(e)[:50]}")
            raise

    def _ddg(self, query):
        r = requests.get("https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
            headers={"User-Agent": "LegalBattle/2.2"},
            timeout=15)
        r.raise_for_status()
        data = r.json()
        results = []
        if data.get("Abstract"):
            results.append({"title": data.get("Heading", ""), "snippet": data["Abstract"], "url": data.get("AbstractURL", "")})
        for topic in data.get("RelatedTopics", [])[:6]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({"title": topic.get("Text", "")[:80], "snippet": topic.get("Text", ""), "url": topic.get("FirstURL", "")})
        if not results:
            raise ValueError("no results")
        return {"results": results}

    def _bing(self, query):
        key = self.keys.get("bing", "")
        if not key:
            raise ValueError("no key")
        r = requests.get("https://api.bing.microsoft.com/v7.0/search",
            headers={"Ocp-Apim-Subscription-Key": key},
            params={"q": query, "count": 10, "mkt": "en-AU"},
            timeout=15)
        r.raise_for_status()
        data = r.json()
        results = []
        for item in data.get("webPages", {}).get("value", [])[:8]:
            results.append({"title": item.get("name", ""), "snippet": item.get("snippet", ""), "url": item.get("url", "")})
        return {"results": results}


    def search(self, query, jurisdiction=""):
        """搜索真实法律案例，专业数据库优先"""
        full_query = f"{query} {jurisdiction} case law judgment court".strip()
        cache_key = hashlib.md5(full_query.encode()).hexdigest()

        if cache_key in SEARCH_CACHE:
            return SEARCH_CACHE[cache_key]

        self.log = []

        # 专业数据库优先（针对澳大利亚案件）
        if "australia" in jurisdiction.lower() or "australi" in jurisdiction.lower() or "nsw" in jurisdiction.lower():
            engines = [
                ("AustLII（澳大利亚法律研究院）", self._austlii),
            ]
        else:
            engines = []

        # 通用搜索引擎作为备选
        engines.extend([
            ("DuckDuckGo", self._ddg),
            ("Bing", self._bing),
        ])

        for name, fn in engines:
            try:
                result = fn(full_query)
                if result and result.get("results"):
                    result["source"] = name
                    result["verified"] = True
                    result["query"] = full_query
                    SEARCH_CACHE[cache_key] = result
                    self.log.append(f"✓ [{name}] 找到 {len(result['results'])} 条案例")
                    return result
            except Exception as e:
                self.log.append(f"✗ [{name}] {str(e)[:50]}")
                continue

        # 降级到LLM知识库
        return {"results": [], "source": "LLM知识库", "verified": False, "query": full_query}


    @staticmethod
    def format_for_prompt(search_result):
        if not search_result.get("verified") or not search_result.get("results"):
            return "⚠ 无法获取真实搜索结果。重要约束：你只能引用你有高度把握真实存在的案例，必须注明案件年份和法院。"

        lines = [
            f"以下是来自{search_result.get('source', '')}的真实搜索结果：",
            "═" * 50,
            "⚠ 关键约束：你只能引用以下搜索结果中明确出现的案例名称。",
            "═" * 50,
        ]
        for i, r in enumerate(search_result["results"][:8], 1):
            lines.append(f"\n[{i}] {r.get('title', '')}")
            lines.append(f" {r.get('snippet', '')}")
            if r.get("url"):
                lines.append(f" 来源: {r['url']}")
        return "\n".join(lines)

    @staticmethod
    def verify_citations(llm_output, search_result):
        if not search_result.get("verified"):
            return {"verified": [], "unverified": [], "skipped": True}

        all_text = " ".join(f"{r.get('title', '')} {r.get('snippet', '')}" for r in search_result.get("results", [])).lower()
        patterns = [r'[A-Z][a-z]+ v\.? [A-Z][a-z]+', r'\[\d{4}\] [A-Z]{2,}']
        cited = set()
        for pat in patterns:
            for m in re.finditer(pat, llm_output):
                cited.add(m.group())

        return {"verified": [c for c in cited if c.lower() in all_text], "unverified": [c for c in cited if c.lower() not in all_text]}

# ========== PII脱敏模块 ==========
class PIIAnonymizer:
    """案件数据脱敏/还原模块——发送前替换PII，返回后还原"""

    # 预定义PII类别与占位符
    CATEGORIES = {
        "人名": "[Person{}]",
        "公司/机构": "[Organization{}]",
        "日期": "[Date{}]",
        "地址": "[Address{}]",
        "金额": "[Amount{}]",
        "身份证/护照": "[ID{}]",
        "电话": "[Phone{}]",
        "邮箱": "[Email{}]",
        "银行账号": "[Account{}]",
    }
    CATEGORY_LABELS_EN = {
        "人名": "Person",
        "公司/机构": "Organization",
        "日期": "Date",
        "地址": "Address",
        "金额": "Amount",
        "身份证/护照": "ID / Passport",
        "电话": "Phone",
        "邮箱": "Email",
        "银行账号": "Bank Account",
    }

    # 正则规则：按优先级排列（先匹配长模式再匹配短模式）
    RULES = [
        # 邮箱
        (r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', "邮箱"),
        # 澳洲手机号 04XX XXX XXX 或 +61 4XX XXX XXX
        (r'\+61\s*4\d{2}\s*\d{3}\s*\d{3}|04\d{2}\s*\d{3}\s*\d{3}', "电话"),
        # 澳洲固定电话 (0X) XXXX XXXX
        (r'\(0[2-8]\)\s*\d{4}\s*\d{4}', "电话"),
        # 金额：$前缀 / A$前缀 / AUD前缀 / 中文万/百万单位 / 英文million/billion / X美元/X澳元
        (r'A?\$[\d,]+(?:\.\d{1,2})?|AUD\s*[\d,]+(?:\.\d{1,2})?|\d+(?:,\d{3})*(?:\.\d{1,2})?\s*(?:万美元|万澳元|澳元|美元|million\s*dollars?|billion\s*dollars?)', "金额"),
        # 日期 YYYY年M月D日 / DD/MM/YYYY / YYYY-MM-DD / M月D日
        (r'\d{4}年\d{1,2}月\d{1,2}日|\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}月\d{1,2}日', "日期"),
        # 澳洲地址（粗略匹配：数字+街道名+NSW/VIC/QLD等+邮编）
        (r'\d+[\w\s]+(?:Street|St|Road|Rd|Avenue|Ave|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct|Place|Pl|Way|Circuit|Cct)[\w\s]*(?:,|\\s)*(?:NSW|VIC|QLD|SA|WA|TAS|ACT|NT)?\s*\d{4}?', "地址"),
        # 护照/身份证号
        (r'[A-Z]\d{7,8}|\d{17}[\dXx]', "身份证/护照"),
        # 银行账号 BSB XXX-XXX + Account XXXXXXXX
        (r'(?:BSB\s*)?\d{3}-\d{3}\s+\d{4,10}|BSB\s*\d{3}-\d{3}', "银行账号"),
    ]

    def __init__(self):
        self.map_forward = {}   # 原文 → 占位符
        self.map_backward = {}  # 占位符 → 原文
        self.counters = {}      # 每类计数器
        self._cn_surnames = ""  # 百家姓，由外部调用 set_cn_surnames 设置

    def _get_placeholder(self, category, original):
        """获取或创建占位符"""
        if original in self.map_forward:
            return self.map_forward[original]
        idx = self.counters.get(category, 0) + 1
        self.counters[category] = idx
        placeholder = self.CATEGORIES[category].format(idx)
        self.map_forward[original] = placeholder
        self.map_backward[placeholder] = original
        return placeholder

    def anonymize(self, text):
        """脱敏：替换所有PII为占位符"""
        if not text:
            return text
        result = text
        # 第一步：中文人名发现（必须在正则之前，用原始文本扫描）
        self._scan_cn_names(result)
        # 第二步：正则规则扫描
        for pattern, category in self.RULES:
            matches = set(re.findall(pattern, result))
            for match in sorted(matches, key=len, reverse=True):
                if len(match) < 2:
                    continue
                placeholder = self._get_placeholder(category, match)
                result = result.replace(match, placeholder)
        # 第三步：替换映射表中的手动条目（人名等）
        # 安全规则：只替换不含'['的原始文本，避免在占位符内二次替换
        for original in sorted(self.map_forward.keys(), key=len, reverse=True):
            placeholder = self.map_forward[original]
            if original in result and placeholder not in result and '[' not in original:
                result = result.replace(original, placeholder)
        return result

    def _scan_cn_names(self, text):
        """扫描文本发现中文人名，加入映射表（不替换）"""
        if not hasattr(self, '_cn_surnames') or not self._cn_surnames:
            return
        cn_stop = set("的了在和是有不为于与也从这就而着被将让把向给很已还能只又即更最该其但如因由此")
        cn_exclude = {
            "案件", "法院", "被告", "原告", "证人", "律师", "法官",
            "当事人", "被害人", "申请人", "被申请人",
            "上诉人", "被上诉人",
            "金额", "人名", "机构", "日期", "地址", "电话",
            "邮箱", "银行", "金融", "金属", "金利", "金库",
            "万元", "百万", "千万", "亿万",
            "费用", "费率", "费时",
            "行政", "协议", "合同", "判决", "裁定", "执行", "审结",
            "法定", "法规", "法律", "法庭", "法务", "法人",
            "商标", "商业", "商议",
            "税务", "税额", "税收",
            "账户", "账号", "账目",
            "证据", "证件", "证券", "证书",
            "公司", "公诉",
            "敏感", "任何", "任何敏",
        }
        for m in re.finditer(r'[' + self._cn_surnames + r'][一-鿿]{1,2}', text):
            name = m.group()
            # 如果末字是停用词，尝试截短一位
            if len(name) >= 3 and name[-1] in cn_stop:
                name = name[:-1]
            if (len(name) >= 2
                and name[-1] not in cn_stop
                and name not in cn_exclude):
                self.add_manual(name, "人名")


    def deanonymize(self, text):
        """还原：将占位符替换回原始PII"""
        if not text:
            return text
        result = text
        # 按占位符长度降序替换（避免短占位符破坏长占位符）
        for placeholder in sorted(self.map_backward.keys(), key=len, reverse=True):
            result = result.replace(placeholder, self.map_backward[placeholder])
        return result

    def add_manual(self, original, category="人名"):
        """手动添加一个PII映射（用于正则没覆盖的情况，如中文人名）"""
        if original and original not in self.map_forward:
            self._get_placeholder(category, original)

    def reset(self):
        """清空映射表（每次新案件前调用）"""
        self.map_forward.clear()
        self.map_backward.clear()
        self.counters.clear()

    def set_cn_surnames(self, surnames):
        """设置百家姓字符串，启用中文人名自动发现"""
        self._cn_surnames = surnames

    def get_report(self):
        """返回脱敏报告（供日志输出）"""
        if not self.map_forward:
            return "No PII was redacted"
        lines = []
        for category in self.CATEGORIES:
            items = {k: v for k, v in self.map_forward.items()
                     if v.startswith(self.CATEGORIES[category].split("{")[0])}
            if items:
                label = self.CATEGORY_LABELS_EN.get(category, category)
                lines.append(f"  {label}: {len(items)} item(s)")
                for idx, (_, ph) in enumerate(items.items(), 1):
                    lines.append(f"    Source item {idx} -> {ph}")
        return "\n".join(lines) if lines else "No PII was redacted"


def is_non_material_weakness_display_record(record):
    """Identify explicit no-finding cards at the final presentation boundary only."""
    if not isinstance(record, dict):
        return False
    fields = (
        "conclusion", "weakness", "reason", "plain_explanation", "core_problem",
        "one_sentence_summary", "source_explanation", "targeting", "priority_reason",
    )
    parts = [str(record.get(field) or "") for field in fields]
    # Surface titles and the provider's final no-finding explanation may live
    # inside plain_guide even when the outer candidate looks substantive.
    plain_guide = record.get("plain_guide") or {}
    if isinstance(plain_guide, dict):
        for field in (
            "name", "summary", "one_sentence_summary", "plain_explanation",
            "core_problem", "source_explanation", "reason",
        ):
            parts.append(str(plain_guide.get(field) or ""))
        model_full_card = plain_guide.get("model_full_card") or {}
        if isinstance(model_full_card, dict):
            for field in (
                "one_sentence_summary", "plain_explanation", "core_problem",
                "source_explanation",
            ):
                parts.append(str(model_full_card.get(field) or ""))
    weakness_lines = record.get("weakness_lines") or []
    if isinstance(weakness_lines, (list, tuple)):
        parts.extend(str(value or "") for value in weakness_lines)
    elif weakness_lines:
        parts.append(str(weakness_lines))
    text = re.sub(r"\s+", " ", " ".join(parts)).strip().lower()
    if not text:
        return True
    no_finding_patterns = (
        r"\bno\s+(?:material\s+|supported\s+|usable\s+|actual\s+)?(?:finding|weakness)(?:es)?\s+(?:is|are|was|were|can\s+be|could\s+be)\s+(?:warranted|identified|found|available|present|supported)\b",
        r"\b(?:none|nothing)\s+(?:is|are|was|were)\s+(?:present|provided|supplied|available)\b.{0,100}\bno\s+(?:finding|weakness)\b.{0,30}\b(?:warranted|identified|found)\b",
        r"\bno\s+(?:material\s+|supported\s+|identifiable\s+|procedural\s+|actual\s+)?weakness(?:es)?\b",
        r"\bweakness(?:es)?\b.{0,50}\b(?:not|cannot|can't)\b.{0,40}\b(?:identified|found|assessed|evaluated)\b",
        r"\bno\b.{0,80}\b(?:issue|basis|context|material|information|facts?|figures?|language|precedent|allegation)\b.{0,90}\b(?:to|can be)\s*(?:analys(?:e|ed)|analyz(?:e|ed)|assess(?:ed)?|evaluat(?:e|ed)|interpret(?:ed)?)\b",
        r"\b(?:cannot|can't|unable to)\s+(?:be\s+)?(?:assess|assessed|evaluate|evaluated|analyse|analyze)\b.{0,70}\b(?:from|because|without|given)\b",
        r"\b(?:analysis|assessment|evaluation)\b.{0,30}\b(?:is\s+)?(?:impossible|not possible|unavailable)\b",
        r"\b(?:this (?:angle|dimension|issue)|comparative fault|precedent analysis|textual analysis)\b.{0,60}\b(?:irrelevant|not applicable)\b",
        r"\b(?:irrelevant|not applicable)\b.{0,60}\b(?:this (?:matter|case|angle|dimension)|the case facts)\b",
        r"\bno\b.{0,35}\b(?:fault|negligence)\b.{0,35}\b(?:alleged|present|identified)\b.{0,70}\bcomparative fault\b.{0,30}\birrelevant\b",
        r"\bno\b.{0,35}\b(?:cross[- ]jurisdictional|cross[- ]border|jurisdictional)\b.{0,45}\b(?:issue|element|conflict)\b.{0,35}\b(?:present|raised|identified|exists?|available)\b",
    )
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in no_finding_patterns)


# ========== 卡死检测器 (Patent 5 辩论模式核心机制) ==========
class CapitulationDetector:
    """
    检测 AI 输出中的"立场松动"信号。
    不拦截输出, 不强制重试, 只标记。
    卡死本身是有价值的情报: 标记位置往往是对方最致命的攻击点。
    """

    # 接受词词表 (按风险等级分类)
    EXPLICIT_CONCESSION = [
        "对方说得对", "对方说的对", "对方有道理", "对方确实有道理",
        "对方的论点不无道理", "对方的观点有道理", "对方说得没错",
        "对方所言有理", "对方主张确实", "对方的反驳有效",
        "我们必须承认", "不得不承认", "我承认", "我方承认",
        "你说得对", "您说得对", "确实如此", "确实有道理",
        "确实需要承认", "实在难以反驳", "无法否认",
    ]

    CONCESSION_PATTERN = [
        "虽然...但是", "尽管...但", "诚然", "固然",
        "不可否认", "无可争辩", "客观来说", "公允地讲",
        "辩证地看", "需要承认的是",
    ]

    NEUTRALIZATION = [
        "需要权衡", "需要综合考虑", "两边都有道理", "两方都有",
        "平衡双方", "中立来看", "客观分析",
        "也有其合理性", "也并非完全错误", "有其道理",
    ]

    MORAL_RETREAT = [
        "出于伦理", "从道德角度", "考虑到公正", "公平地说",
        "为了真相", "本着客观",
    ]

    @classmethod
    def scan(cls, text):
        """
        扫描文本是否含接受词。
        返回: {
            "capitulated": bool,
            "level": "explicit|pattern|neutralization|moral|none",
            "triggers": [触发的具体词列表],
            "severity": "fatal|high|medium|none"
        }
        """
        if not text:
            return {"capitulated": False, "level": "none", "triggers": [], "severity": "none"}

        if not isinstance(text, str):
            try:
                text = str(text)
            except:
                return {"capitulated": False, "level": "none", "triggers": [], "severity": "none"}

        triggers = []
        levels_found = []

        for phrase in cls.EXPLICIT_CONCESSION:
            if phrase in text:
                triggers.append(phrase)
                levels_found.append("explicit")

        for phrase in cls.CONCESSION_PATTERN:
            if "..." in phrase:
                parts = phrase.split("...")
                if all(p in text for p in parts if p):
                    triggers.append(phrase)
                    levels_found.append("pattern")
            elif phrase in text:
                triggers.append(phrase)
                levels_found.append("pattern")

        for phrase in cls.NEUTRALIZATION:
            if phrase in text:
                triggers.append(phrase)
                levels_found.append("neutralization")

        for phrase in cls.MORAL_RETREAT:
            if phrase in text:
                triggers.append(phrase)
                levels_found.append("moral")

        if not triggers:
            return {"capitulated": False, "level": "none", "triggers": [], "severity": "none"}

        if "explicit" in levels_found:
            severity = "fatal"
            level = "explicit"
        elif "pattern" in levels_found:
            severity = "high"
            level = "pattern"
        elif "neutralization" in levels_found:
            severity = "medium"
            level = "neutralization"
        else:
            severity = "medium"
            level = "moral"

        return {
            "capitulated": True,
            "level": level,
            "triggers": triggers[:5],
            "severity": severity
        }

    @classmethod
    def scan_round(cls, results, content_keys=None):
        """
        扫描一轮所有 LLM 输出。
        results: [{...}, ...] 每个是一个 LLM 的输出
        content_keys: 要扫描的字段名列表 (例如 ["rebuttal", "response", "attack"])
        返回每条结果加上 _capitulation 标记
        """
        if not content_keys:
            content_keys = ["rebuttal", "response", "attack", "final_position",
                           "kill_shot", "why_fails", "key_points", "summary"]

        for r in results:
            collected_text = []
            cls._collect_text(r, content_keys, collected_text)
            full_text = " ".join(collected_text)
            r["_capitulation"] = cls.scan(full_text)

        return results

    @classmethod
    def _collect_text(cls, obj, keys, acc):
        """递归收集所有指定字段的文本"""
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in keys and isinstance(v, str):
                    acc.append(v)
                elif isinstance(v, (dict, list)):
                    cls._collect_text(v, keys, acc)
        elif isinstance(obj, list):
            for item in obj:
                cls._collect_text(item, keys, acc)

    @classmethod
    def format_warning(cls, capitulation_info):
        """格式化卡死警报供显示"""
        if not capitulation_info or not capitulation_info.get("capitulated"):
            return ""

        sev = capitulation_info.get("severity", "")
        triggers = capitulation_info.get("triggers", [])

        icons = {"fatal": "🔴", "high": "🟠", "medium": "🟡"}
        icon = icons.get(sev, "⚠️")

        msg = f"{icon} 立场松动 ({sev})"
        if triggers:
            msg += f" | 触发词: {', '.join(triggers[:3])}"
        msg += "\n   ⚡ 此为对方攻击奏效点, 庭审重点准备"
        return msg


# ========== LLM客户端 ==========
class FunctionItemAuditor:
    """Local per-item audit for model output before display/export.

    This audit does not decide legal truth. It flags output that needs lawyer
    review before it is treated as usable advice.
    """

    CASE_PATTERNS = [
        r"\b[A-Z][A-Za-z'&.-]+(?:[ \t]+[A-Z][A-Za-z'&.-]+){0,5}[ \t]+v\.?[ \t]+[A-Z][A-Za-z'&.-]+(?:[ \t]+[A-Z][A-Za-z'&.-]+){0,5}\b",
        r"\[\d{4}\][ \t]+[A-Z]{2,}[ \t]+\d+",
    ]
    STATUTE_PATTERNS = [
        r"\b[A-Z][A-Za-z& ]{2,80}[ \t]+(?:Act|Regulation|Rules|Code)[ \t]+\d{4}\b",
        r"\b(?:s|ss|section|sections)\s*\d+[A-Za-z0-9()\-]*(?:\s*[-,]\s*\d+[A-Za-z0-9()\-]*)?",
    ]
    GENERIC_TARGETS = {
        "opponent's argument/evidence",
        "opposing argument or evidence",
        "which attack is being answered",
        "which opposing argument",
        "the opposing side's evidence",
        "the opponent's evidence",
        "?",
    }
    ODD_PUNCT_RE = re.compile(r"(?:[`'\u2018\u2019\u201c\u201d,，、。]\s*){4,}")

    @classmethod
    def audit_attack(cls, item, target_context="", verified_cases=None):
        return cls._audit_item(
            item=item,
            kind="R1 attack",
            side="negative",
            main_keys=("attack", "kill_shot", "legal_basis"),
            target_key="targeting",
            target_context=target_context,
            verified_cases=verified_cases,
        )

    @classmethod
    def audit_rebuttal(cls, item, target_context="", verified_cases=None):
        return cls._audit_item(
            item=item,
            kind="R2 rebuttal",
            side="positive",
            main_keys=("rebuttal", "why_fails"),
            target_key="targeting",
            target_context=target_context,
            verified_cases=verified_cases,
        )

    @classmethod
    def summarize(cls, audit):
        if not audit:
            return "not audited"
        status = audit.get("status", "review").upper()
        risk = audit.get("risk", "medium")
        reasons = audit.get("reasons") or []
        if not reasons:
            return f"{status} ({risk})"
        return f"{status} ({risk}) - " + "; ".join(reasons[:3])

    @classmethod
    def _audit_item(cls, item, kind, side, main_keys, target_key, target_context, verified_cases):
        item = item if isinstance(item, dict) else {"text": str(item)}
        verified_lookup = {str(x).strip().lower() for x in (verified_cases or []) if str(x).strip()}
        target_context = str(target_context or "")
        target = str(item.get(target_key, "") or "").strip()
        text_parts = [target]
        for key in main_keys:
            text_parts.append(str(item.get(key, "") or ""))
        text = "\n".join(text_parts).strip()

        issues = []
        main_text = " ".join(str(item.get(k, "") or "") for k in main_keys).strip()
        if len(main_text) < 40:
            issues.append(("high", "substantive text is too short"))
        if re.search(r"[\u4e00-\u9fff]", text):
            issues.append(("high", "Chinese text remains in user-visible output"))
        if cls.ODD_PUNCT_RE.search(text):
            issues.append(("medium", "punctuation artifact detected"))

        target_l = target.lower()
        if not target or target_l in cls.GENERIC_TARGETS or len(target) < 8:
            issues.append(("medium", "target is generic or missing"))
        elif target_context and not cls._target_is_grounded(target, target_context):
            issues.append(("medium", "target is not clearly grounded in the supplied side material"))

        for case in cls._extract_patterns(text, cls.CASE_PATTERNS):
            if verified_lookup and case.lower() in verified_lookup:
                continue
            issues.append(("high", f"unverified case/citation: {case[:80]}"))
        for statute in cls._extract_patterns(text, cls.STATUTE_PATTERNS):
            issues.append(("medium", f"statute/section requires lawyer review: {statute[:80]}"))

        lowered = text.lower()
        if side == "negative":
            drift_terms = [
                "the positive side is right",
                "the claimant is clearly entitled",
                "we concede",
                "cannot dispute the positive side",
                "balanced view",
            ]
            if any(term in lowered for term in drift_terms):
                issues.append(("high", "possible negative-side stance drift"))
        elif side == "positive":
            drift_terms = [
                "the negative side is right",
                "the defendant is clearly not liable",
                "we concede",
                "cannot dispute the attack",
                "balanced view",
            ]
            if any(term in lowered for term in drift_terms):
                issues.append(("high", "possible positive-side stance drift"))

        if "as to the opponent's argument/evidence" in lowered:
            issues.append(("low", "template phrase may be too generic"))
        if "must be proved, not merely asserted" in lowered and len(main_text) < 120:
            issues.append(("low", "generic proof-burden phrase needs case-specific support"))

        risk_order = {"none": 0, "low": 1, "medium": 2, "high": 3}
        max_risk = "none"
        for risk, _ in issues:
            if risk_order.get(risk, 0) > risk_order.get(max_risk, 0):
                max_risk = risk
        status = "pass" if not issues else ("review" if max_risk == "high" else "caution")
        return {
            "kind": kind,
            "side": side,
            "status": status,
            "risk": max_risk,
            "reasons": [reason for _, reason in issues],
            "note": "Local function audit only; lawyer must verify legal correctness.",
        }

    @classmethod
    def _extract_patterns(cls, text, patterns):
        found = []
        for pattern in patterns:
            found.extend(re.findall(pattern, text, flags=re.I))
        return cls._unique_keep_order([cls._clean(x) for x in found])

    @staticmethod
    def _clean(text):
        return re.sub(r"\s+", " ", str(text or "")).strip(" .,:;")

    @staticmethod
    def _unique_keep_order(items):
        seen = set()
        out = []
        for item in items:
            key = str(item or "").strip().lower()
            if key and key not in seen:
                seen.add(key)
                out.append(str(item).strip())
        return out

    @staticmethod
    def _target_is_grounded(target, context):
        target_l = re.sub(r"\s+", " ", target.lower()).strip()
        context_l = re.sub(r"\s+", " ", context.lower())
        if target_l and target_l in context_l:
            return True
        words = re.findall(r"[a-zA-Z][a-zA-Z0-9'-]{3,}", target_l)
        stop = {
            "that", "this", "with", "from", "have", "been", "their", "there",
            "argument", "evidence", "opposing", "positive", "negative", "side",
            "claim", "case", "point", "target",
        }
        words = [w for w in words if w not in stop]
        if not words:
            return False
        hits = sum(1 for w in words[:8] if w in context_l)
        return hits >= max(1, min(3, len(words)))


class LLMClient:
    def __init__(self, provider_key, api_key, personality_idx=0):
        # 别名转换：claude/claoud → anthropic, gpt → openai, etc.
        resolved_key = PROVIDER_ALIASES.get(provider_key.strip().lower(), provider_key.strip().lower())
        # ★ 支持自定义URL（http开头或含 ://）
        if provider_key.strip().lower().startswith("http") or "://" in provider_key:
            self.provider = {"base_url": provider_key.rstrip("/"), "model": "local-qwen2.5-7b",
                "rate_input": 0.0, "rate_output": 0.0}
            self.provider_key = "custom-local"
        else:
            self.provider = PROVIDER_PRESETS.get(resolved_key, {})
            self.provider_key = resolved_key
        self.api_key = api_key
        self.total_cost = 0.0
        self.total_tokens_in = 0
        self.total_tokens_out = 0
        self.personality = LAWYER_PERSONALITIES[personality_idx % len(LAWYER_PERSONALITIES)]
        self.personality_idx = personality_idx
        self.failed = False

    @staticmethod
    def _extract_balanced_json(text):
        text = str(text or "").strip()
        if not text:
            raise json.JSONDecodeError("empty response", text, 0)
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        starts = [idx for idx in (text.find("{"), text.find("[")) if idx >= 0]
        if not starts:
            raise json.JSONDecodeError("no json object found", text, 0)
        start = min(starts)
        opener = text[start]
        closer = "}" if opener == "{" else "]"
        depth = 0
        in_string = False
        escaped = False
        for idx in range(start, len(text)):
            ch = text[idx]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    return json.loads(text[start:idx + 1])
        raise json.JSONDecodeError("unbalanced json object", text, start)

    def _chat_json_gemini(self, prompt, system_guard, temperature=0.75, max_tokens=4000):
        try:
            base_url = self.provider.get("base_url", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
            model = self.provider.get("model", "gemini-2.5-flash") or "gemini-2.5-flash"
            url = f"{base_url}/models/{urllib.parse.quote(model, safe='')}:generateContent"
            def call_gemini(user_prompt, temp, out_tokens):
                payload = {
                    "systemInstruction": {"parts": [{"text": system_guard}]},
                    "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                    "generationConfig": {
                        "temperature": temp,
                        "maxOutputTokens": out_tokens,
                        "responseMimeType": "application/json",
                    },
                }
                r = requests.post(
                    url,
                    params={"key": self.api_key},
                    headers={"Content-Type": "application/json"},
                    json=payload,
                    timeout=(30, 270),
                )
                r.raise_for_status()
                data = r.json()
                parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                text = "".join(str(p.get("text", "")) for p in parts).strip()
                usage = data.get("usageMetadata", {})
                tok_in = usage.get("promptTokenCount", 0)
                tok_out = usage.get("candidatesTokenCount", 0)
                cost = (tok_in * self.provider.get("rate_input", 1) +
                        tok_out * self.provider.get("rate_output", 1)) / 1000
                self.total_cost += cost
                self.total_tokens_in += tok_in
                self.total_tokens_out += tok_out
                return text

            content = call_gemini(prompt, temperature, max_tokens)
            try:
                return self._extract_balanced_json(content)
            except json.JSONDecodeError:
                repair_prompt = (
                    "Repair the following model output into valid strict JSON only. "
                    "Do not add markdown, comments, or explanation. Preserve the intended legal content. "
                    "The required top-level object is either {\"results\": [...]} or the object requested by the original task.\n\n"
                    "BROKEN OUTPUT:\n"
                    f"{content[:12000]}"
                )
                repaired = call_gemini(repair_prompt, 0.05, min(max_tokens, 6000))
                return self._extract_balanced_json(repaired)
        except json.JSONDecodeError:
            return {"_raw": content if "content" in locals() else "", "_error": "parse_failed"}
        except Exception as e:
            self.failed = True
            return {"_error": str(e)}

    def chat_json(self, prompt, temperature=0.75, max_tokens=4000):
        if self.failed:
            return {"_error": "model_marked_failed"}

        base_url = self.provider.get("base_url", "")
        model = self.provider.get("model", "")

        if not base_url or not self.api_key:
            self.failed = True
            return {"_error": f"not_configured: {self.provider_key}"}

        try:
            system_guard = (
                "You are running inside the English commercial edition of StrikeOver. "
                "All user-visible legal analysis, summaries, targets, attacks, rebuttals, reasons, fixes, comments, "
                "and every JSON string value must be written in English. "
                "Preserve proper names, court names, dates, monetary amounts, and legal citations exactly where possible. "
                "If the user prompt contains Chinese instructions, follow the task but produce English output. "
                "When strict JSON is requested, return JSON only."
            )
            if self.provider_key == "gemini":
                return self._chat_json_gemini(prompt, system_guard, temperature, max_tokens)
            r = requests.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [
                    {"role": "system", "content": system_guard},
                    {"role": "user", "content": prompt},
                ], "max_tokens": max_tokens, "temperature": temperature},
                timeout=(30, 270))
            r.raise_for_status()
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            tok_in  = usage.get("prompt_tokens", 0)
            tok_out = usage.get("completion_tokens", 0)
            cost = (tok_in  * self.provider.get("rate_input",  1) +
                    tok_out * self.provider.get("rate_output", 1)) / 1000
            self.total_cost       += cost
            self.total_tokens_in  += tok_in
            self.total_tokens_out += tok_out

            return self._extract_balanced_json(content)
        except json.JSONDecodeError:
            return {"_raw": content, "_error": "parse_failed"}
        except Exception as e:
            self.failed = True
            return {"_error": str(e)}

    def chat_text(self, prompt, temperature=0.65, max_tokens=5000):
        """Return natural-language analysis without forcing a JSON schema."""
        if self.failed:
            raise RuntimeError("model_marked_failed")

        base_url = self.provider.get("base_url", "")
        model = self.provider.get("model", "")
        if not base_url or not self.api_key:
            raise RuntimeError(f"not_configured: {self.provider_key}")

        system_guard = (
            "You are working inside the English commercial edition of StrikeOver as senior litigation counsel. "
            "Write all user-visible analysis in clear professional English. Preserve proper names, dates, amounts, "
            "document references, and legal citations. Do not return JSON. Do not force the analysis into a preset "
            "field template. Reason from the complete record, distinguish facts from inferences, and never invent "
            "missing facts or authorities. The output assists a lawyer and is not a final legal conclusion."
        )

        if self.provider_key == "gemini":
            url = f"{base_url.rstrip('/')}/models/{urllib.parse.quote(model, safe='')}:generateContent"
            payload = {
                "systemInstruction": {"parts": [{"text": system_guard}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                },
            }
            response = requests.post(
                url,
                params={"key": self.api_key},
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=(30, 270),
            )
            response.raise_for_status()
            data = response.json()
            parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            content = "".join(str(part.get("text", "")) for part in parts).strip()
            usage = data.get("usageMetadata", {})
            tok_in = usage.get("promptTokenCount", 0)
            tok_out = usage.get("candidatesTokenCount", 0)
        else:
            response = requests.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_guard},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
                timeout=(30, 270),
            )
            response.raise_for_status()
            data = response.json()
            content = str(data["choices"][0]["message"]["content"] or "").strip()
            usage = data.get("usage", {})
            tok_in = usage.get("prompt_tokens", 0)
            tok_out = usage.get("completion_tokens", 0)

        if not content:
            raise RuntimeError("empty model response")
        self.total_tokens_in += tok_in
        self.total_tokens_out += tok_out
        self.total_cost += (
            tok_in * self.provider.get("rate_input", 1)
            + tok_out * self.provider.get("rate_output", 1)
        ) / 1000
        return content

# ========== M×N并行攻防引擎 ==========
class MxNEngine:
    def __init__(self, max_workers=16, use_search=True):
        self.max_workers = max_workers
        self.search_engine = CaseSearchEngine() if use_search else None

    def run(self, providers, dimensions, case_bg, my_side, opp_side, jurisdiction="", log_cb=None, side_label="正方"):
        # 每维度单独搜索，结果更精准
        dim_search_ctx = {}
        last_sr = {"source": "none", "verified": False}
        display_side = {"反方": "negative side", "正方": "positive side"}.get(side_label, side_label)
        if self.search_engine:
            if log_cb:
                log_cb(f"Authority search [{display_side}]: searching each dimension separately ({len(dimensions)} dimension(s))...")
            for dim, desc in dimensions:
                sr = self.search_engine.search(dim + " " + case_bg[:100], jurisdiction)
                dim_search_ctx[dim] = CaseSearchEngine.format_for_prompt(sr)
                last_sr = sr # 保存最后一个搜索结果用于验证
            for msg in self.search_engine.log[-1:]:
                if log_cb: log_cb(" [" + dim + "] " + msg)
            self.search_engine.log.clear()
        all_search_ctx = "\n\n".join(f"【{dim}】\n{ctx}" for dim, ctx in dim_search_ctx.items()) if dim_search_ctx else ""

        frames_text = "\n".join([
            f"=== Frame {str(i+1)}: {DIMENSION_LABELS_EN.get(dim, dim)} lawyer ===\n"
            f"Assigned dimension: {DIMENSION_LABELS_EN.get(dim, dim)}\nDescription: {DIMENSION_DESC_EN.get(dim, desc)}\n"
            f"Persona: {providers[i % len(providers)].personality['name']}\n"
            for i, (dim, desc) in enumerate(dimensions)
        ])

        base_len = len(case_bg) + len(my_side) + len(opp_side) + len(all_search_ctx)
        max_tokens = min(max(4000, base_len // 4 + len(dimensions) * 500), 16000)

        prompt = (
            f"## Regulator Notice\n"
            f"Your client is the {display_side}. You are the {display_side}'s legal team.\n"
            f"The client has already set out its position and evidence. Your job is to advance that side's position through focused attacks.\n"
            f"Each attack dimension is handled by an independent lawyer frame. Do not let frames contaminate each other.\n\n"
            f"## Role\n"
            f"- You work for the {display_side}; your output serves that side's interests.\n"
            f"- Your goal is to persuade the judge to accept the {display_side}'s position.\n"
            f"- Truth-finding is the judge's job, not yours.\n"
            f"- Do not write a neutral balanced essay.\n\n"
            f"## Case Background\n{case_bg[:2500]}\n\n"
            f"## Your Side's Arguments and Evidence\n{my_side[:2000]}\n\n"
            f"## Opposing Side's Arguments and Evidence (attack target)\n{opp_side[:2000]}\n\n"
            + (f"## Verified Authority Search Results\n{all_search_ctx}\n\n" if all_search_ctx else "") +
            ("\nCritical constraints:\n"
            "1. You may cite only authorities that appear explicitly in the verified authority search results above.\n"
            "2. Do not invent case names, legislation, section numbers, regulations, or rule numbers.\n"
            "3. If no verified authority is available, argue from general legal principles only.\n"
            "4. Every JSON string value must be in English. Preserve proper names, court names, dates, monetary amounts, and citations.\n\n" if all_search_ctx else
            "\nCritical constraints:\n"
            "1. No verified authority search result is available. Do not cite any case name.\n"
            "2. Do not invent legislation, section numbers, regulations, or rule numbers.\n"
            "3. Argue from general legal principles only.\n"
            "4. Every JSON string value must be in English. Preserve proper names, court names, dates, monetary amounts, and citations.\n\n") +
            f"## Lawyer Frame Definitions\n{frames_text}\n\n"
            "Return strict JSON only: {\"results\": [{\"dimension\": \"dimension name in English\", "
            "\"attacks\": [{\"targeting\": \"which opposing argument or evidence item is targeted\", \"attack\": \"attack content in English\", "
            "\"legal_basis\": \"legal basis in English\", \"is_fatal\": false, \"kill_shot\": \"one most damaging sentence in English\", "
            "\"strength\": \"high|medium|low\"}], \"summary\": \"frame assessment in English\"}]}"
        )

        results = []
        done = [0]
        total = len(providers)
        success_providers = []

        def call_one_model(client):
            if client.failed:
                if log_cb: log_cb(f"Warning: [{client.provider_key}] is marked failed; skipped")
                return []

            if log_cb: log_cb(f" -> [{display_side}] calling {client.provider_key}...")
            res = client.chat_json(prompt, temperature=0.8, max_tokens=max_tokens)
            done[0] += 1

            if res.get("_error"):
                if log_cb: log_cb(f"Warning: [{done[0]}/{total}] {client.provider_key} failed: {res['_error'][:50]}")
                return []

            if log_cb: log_cb(f"✓ [{done[0]}/{total}] {client.provider_key} returned")

            expanded = []
            for dim_result in res.get("results", []):
                dim_result["_provider"] = client.provider_key
                dim_result["_dimension"] = dim_result.get("dimension", "?")
                dim_result["_personality"] = client.personality["name"]
                dim_result["_search_source"] = last_sr.get("source", "none") if self.search_engine else "off"
                dim_result["_search_verified"] = bool(all_search_ctx)
                # 验证引用
                raw = json.dumps(dim_result.get("attacks", []), ensure_ascii=False)
                check = CaseSearchEngine.verify_citations(raw,
                    last_sr if self.search_engine else {"verified": False})
                dim_result["_verified_cases"] = check.get("verified", [])
                dim_result["_unverified_cases"] = check.get("unverified", [])
                expanded.append(dim_result)

            if expanded:
                success_providers.append(client)
            return expanded

        if log_cb:
            log_cb(f"⚡ [{display_side}] {total} provider(s) in parallel...")

        with ThreadPoolExecutor(max_workers=min(self.max_workers, total)) as pool:
            futures = {pool.submit(call_one_model, c): c for c in providers}
            for future in as_completed(futures):
                results.extend(future.result())

        return results, success_providers

# ========== GUI ==========
class StrikeOverGUI:
    def __init__(self):
        self.root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
        self.root.title("StrikeOver v2.11 - Online Opposition System")
        self.root.geometry("1400x950")

        self.providers = []
        self.dim_vars = {}
        self.draft_timer = None
        self.loading_config = False
        self.running = False # 全局运行状态标志
        self.fast_scroll = False
        self.help_mode = False
        self.help_button = None
        self.v_search = tk.BooleanVar(value=False)  # 案例搜索开关（默认关闭，防止LLM虚构案例）
        self.v_positive_provider_route = tk.StringVar(value="Full verified providers")
        self.v_negative_provider_route = tk.StringVar(value="Full verified providers")
        self.side_provider_allocation = {"positive": [], "negative": []}
        self.v_side_allocation_summary = tk.StringVar(value="Side allocation: Full verified providers for both sides")
        self.cloud_backend = get_backend()
        self._analysis_ui_snapshot = {}

        self.C = {"bg": "#1e1e2e", "panel": "#2a2a3e", "accent": "#89b4fa", "gold": "#f9e2af", "red": "#f38ba8",
            "teal": "#94e2d5", "green": "#a6e3a1", "text": "#cdd6f4", "muted": "#a6adc8", "entry": "#1e1e2e",
            "salmon": "#fab387"}
        self.root.configure(bg=self.C["bg"])

        self._build_ui()
        self._load_config()
        self._refresh_side_provider_routes()
        self._load_draft()
        self.cloud_backend.run_async(
            self.cloud_backend.record_event,
            "online_application_opened",
            {"version": "google-cloud-online"},
        )
        self.root.after_idle(self._setup_global_drag_drop)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _walk_analysis_widgets(self, widget):
        for child in widget.winfo_children():
            if isinstance(child, tk.Toplevel):
                continue
            yield child
            yield from self._walk_analysis_widgets(child)

    def _set_analysis_ui_locked(self, locked):
        """Disable and visibly dim the main UI without adding a progress panel."""
        muted = "#667085"
        if locked:
            if self._analysis_ui_snapshot:
                return
            snapshot = {}
            for widget in self._walk_analysis_widgets(self.root):
                saved = {}
                for option in ("state", "foreground", "disabledforeground", "insertbackground"):
                    try:
                        saved[option] = widget.cget(option)
                    except (tk.TclError, AttributeError):
                        pass
                if not saved:
                    continue
                snapshot[widget] = saved
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
            self._analysis_ui_snapshot = snapshot
            try:
                self.root.configure(cursor="watch")
            except tk.TclError:
                pass
            return

        snapshot = self._analysis_ui_snapshot
        self._analysis_ui_snapshot = {}
        for widget, saved in reversed(list(snapshot.items())):
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
        try:
            self.root.configure(cursor="")
        except tk.TclError:
            pass

    def _ask_enable_data_redaction(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Data Security Review")
        dialog.configure(bg="#111827")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        result = {"enable": False}

        shell = tk.Frame(dialog, bg="#111827", padx=24, pady=22)
        shell.pack(fill=tk.BOTH, expand=True)
        tk.Label(
            shell,
            text="Data Security Review",
            bg="#111827",
            fg=self.C["gold"],
            font=("Microsoft YaHei UI", 17, "bold"),
        ).pack(anchor="w")
        tk.Label(
            shell,
            text="This action may send matter content to verified external model providers.",
            bg="#111827",
            fg="#cbd5e1",
            wraplength=640,
            justify=tk.LEFT,
            font=("Microsoft YaHei UI", 10),
        ).pack(anchor="w", pady=(6, 18))

        body = tk.Frame(shell, bg="#1f2937", padx=16, pady=14, highlightthickness=1, highlightbackground="#374151")
        body.pack(fill=tk.X)
        notices = [
            ("Recommended default", "Enable Data Redaction before sending case facts, arguments, evidence, names, dates, or private identifiers to external providers."),
            ("If you continue without redaction", "The original text will be sent to the selected verified provider for this run. Use this only for low-sensitivity matters or already-redacted material."),
            ("Local workflow", "API/provider settings can remain saved, but matter content is not auto-saved by default in this competition copy."),
        ]
        for title, text in notices:
            item = tk.Frame(body, bg="#1f2937")
            item.pack(fill=tk.X, pady=(0, 10))
            title_color = "#f87171" if title == "If you continue without redaction" else "#f8fafc"
            tk.Label(
                item,
                text=title,
                bg="#1f2937",
                fg=title_color,
                font=("Microsoft YaHei UI", 10, "bold"),
            ).pack(anchor="w")
            tk.Label(
                item,
                text=text,
                bg="#1f2937",
                fg="#cbd5e1",
                wraplength=610,
                justify=tk.LEFT,
                font=("Microsoft YaHei UI", 9),
            ).pack(anchor="w", pady=(2, 0))

        actions = tk.Frame(shell, bg="#111827")
        actions.pack(fill=tk.X, pady=(18, 0))

        def choose(value):
            result["enable"] = value
            dialog.destroy()

        def confirm_original_text():
            confirmed = messagebox.askyesno(
                "Final Warning - Original Matter Will Be Sent",
                "You are about to send the complete original matter without redaction.\n\n"
                "Names, dates, identifiers, facts, arguments, and evidence may be "
                "transmitted to the selected external model provider.\n\n"
                "Continue only if you are authorized to send this material.\n\n"
                "Send the complete original text now?",
                parent=dialog,
                icon="warning",
                default="no",
            )
            if confirmed:
                choose(False)

        tk.Button(
            actions,
            text="Enable Redaction",
            command=lambda: choose(True),
            bg="#2563eb",
            fg="#ffffff",
            activebackground="#3b82f6",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            padx=20,
            pady=8,
            cursor="hand2",
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(side=tk.RIGHT)
        tk.Button(
            actions,
            text="Send Original Text (No Redaction)",
            command=confirm_original_text,
            bg="#b91c1c",
            fg="#ffffff",
            activebackground="#dc2626",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            padx=18,
            pady=8,
            cursor="hand2",
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(side=tk.RIGHT, padx=(0, 8))

        dialog.update_idletasks()
        width = dialog.winfo_reqwidth()
        height = dialog.winfo_reqheight()
        x = self.root.winfo_rootx() + max(0, self.root.winfo_width() // 2 - width // 2)
        y = self.root.winfo_rooty() + max(0, self.root.winfo_height() // 2 - height // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.lift()
        dialog.focus_force()
        dialog.protocol("WM_DELETE_WINDOW", lambda: choose(True))
        self.root.wait_window(dialog)
        return result["enable"]

    def _build_ui(self):
        top = tk.Frame(self.root, bg=self.C["bg"], pady=8)
        top.pack(fill=tk.X, padx=14)
        self.help_button = tk.Button(
            top,
            text="?",
            command=self.enable_help_mode,
            bg="#2f3b52",
            fg=self.C["gold"],
            activebackground="#3d4a66",
            activeforeground=self.C["gold"],
            relief="flat",
            width=3,
            cursor="question_arrow",
            font=("Helvetica", 12, "bold"),
        )
        self.help_button.pack(side=tk.RIGHT, padx=(8, 0))
        self.set_help(self.help_button, "Help mode: click the question mark, then click any area to see what it does.")
        tk.Label(top, text="⚖ StrikeOver v2.11", bg=self.C["bg"], fg=self.C["gold"], font=("Helvetica", 18, "bold")).pack(side=tk.LEFT)
        tk.Label(top, text=" 2-round opposition + evidence assistant + judge review + redaction", bg=self.C["bg"], fg=self.C["muted"], font=("Helvetica", 14)).pack(side=tk.LEFT, pady=5)

        cv = tk.Canvas(self.root, bg=self.C["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(self.root, orient="vertical", command=cv.yview)
        self.sf = tk.Frame(cv, bg=self.C["bg"])
        self.sf.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        self.sf_window = cv.create_window((0, 0), window=self.sf, anchor="nw")
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        cv.pack(fill=tk.BOTH, expand=True)
        self.main_canvas = cv
        cv.bind("<Configure>", self._sync_main_canvas_width)
        cv.bind("<MouseWheel>", lambda e: self._scroll_widget(cv, e))
        self.sf.bind("<MouseWheel>", lambda e: self._scroll_widget(cv, e))
        self.root.bind_all("<MouseWheel>", self._scroll_main_canvas, add="+")
        self.root.bind_all("<ButtonPress-3>", lambda e: self._set_fast_scroll(True), add="+")
        self.root.bind_all("<ButtonRelease-3>", lambda e: self._set_fast_scroll(False), add="+")

        self._build_providers()
        self._build_dimensions()
        self._build_case()
        self._build_side_panels()
        self._build_controls()
        self._build_output()
        self.root.bind_all("<Button-1>", self._handle_help_click, add="+")
        self._setup_drag_drop(self.root)
        self._setup_drag_drop(cv)
        self._setup_drag_drop(self.sf)

    def _sync_main_canvas_width(self, event):
        try:
            self.main_canvas.itemconfigure(self.sf_window, width=event.width)
            self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all"))
        except Exception:
            pass

    def _scroll_widget(self, widget, event):
        delta = -1 * (event.delta // 120) if getattr(event, "delta", 0) else 0
        if delta:
            if self.fast_scroll:
                delta *= 6
            widget.yview_scroll(delta, "units")
        return "break"

    def _scroll_main_canvas(self, event):
        if event.widget.winfo_toplevel() is not self.root:
            return None
        if event.widget.winfo_class() in {"Text", "Entry", "TEntry", "TCombobox", "Listbox"}:
            return None
        return self._scroll_widget(self.main_canvas, event)

    def _bind_local_scroll(self, widget):
        widget.bind("<MouseWheel>", lambda e, w=widget: self._scroll_widget(w, e))
        widget.bind("<ButtonPress-3>", lambda e: self._set_fast_scroll(True))
        widget.bind("<ButtonRelease-3>", lambda e: self._set_fast_scroll(False))
        widget.bind("<Button-4>", lambda e, w=widget: (w.yview_scroll(-1, "units"), "break")[-1])
        widget.bind("<Button-5>", lambda e, w=widget: (w.yview_scroll(1, "units"), "break")[-1])

    def _set_fast_scroll(self, value):
        self.fast_scroll = bool(value)
        return "break"

    def _provider_config_data(self):
        saved_providers = []
        for r in self.providers:
            pname = r["name"].get()
            preset = PROVIDER_PRESETS.get(pname, {})
            saved_providers.append({
                "name": pname,
                "key": r["key"].get(),
                "base_url": preset.get("base_url", ""),
                "model": preset.get("model", ""),
                "enabled": r["enabled"].get(),
                "verified": r.get("verified", tk.BooleanVar(value=False)).get(),
                "lawyers": r.get("lawyers", tk.IntVar(value=1)).get(),
            })
        return {
            "providers": saved_providers,
            "anon_reminder_shown": self._anon_reminder_shown,
            "positive_provider_route": self.v_positive_provider_route.get(),
            "negative_provider_route": self.v_negative_provider_route.get(),
            "side_provider_allocation": self.side_provider_allocation,
        }

    def _provider_session_active(self):
        try:
            with open(SESSION_FILE, encoding="utf-8") as f:
                data = json.load(f)
            return bool(data.get("signed_in"))
        except Exception:
            return False

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
            self.status_label.config(text="Help mode: click an area to inspect")
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
            help_text = "这个位置暂时没有单独说明。一般空白区域只是布局，不影响案件分析。"
            messagebox.showinfo("What this area does", help_text)
        try:
            self.status_label.config(text="Status: Ready")
        except Exception:
            pass
        return "break"

    def _build_providers(self):
        p = tk.Frame(self.sf, bg=self.C["panel"], padx=10, pady=8)
        p.pack(fill=tk.X, padx=10, pady=(10, 5))
        self.set_help(p, "Model providers: add and verify external or private model endpoints. The online version only uses verified rows.")
        tk.Label(p, text="🔑 Model Providers", bg=self.C["panel"], fg=self.C["text"], font=("Helvetica", 12, "bold")).pack(anchor=tk.W)

        self.prov_frame = tk.Frame(p, bg=self.C["panel"])
        self.prov_frame.pack(fill=tk.X)
        # 默认行由_load_config统一加载，不在这里加

        br = tk.Frame(p, bg=self.C["panel"])
        br.pack(fill=tk.X, pady=(8, 0))
        tk.Button(br, text="+ Add", command=self._add_empty_row, bg="#1a3a1a", fg="white", relief="flat", padx=12, pady=3).pack(side=tk.LEFT)
        self.prov_count_lbl = tk.Label(br, text="", bg=self.C["panel"], fg=self.C["gold"], font=("Helvetica", 11, "bold"))
        self.prov_count_lbl.pack(side=tk.LEFT, padx=12)

        route = tk.Frame(p, bg=self.C["panel"])
        route.pack(fill=tk.X, pady=(8, 0))
        tk.Button(
            route,
            text="Side Allocation...",
            command=self.open_side_allocation_dialog,
            bg="#243b5a",
            fg="white",
            relief="flat",
            padx=12,
            pady=4,
        ).pack(side=tk.LEFT)
        tk.Label(route, textvariable=self.v_side_allocation_summary, bg=self.C["panel"], fg=self.C["muted"], font=("Helvetica", 10)).pack(side=tk.LEFT, padx=12)
        tk.Label(
            route,
            text="No checked provider on a side = Full verified providers for that side.",
            bg=self.C["panel"],
            fg=self.C["muted"],
            font=("Helvetica", 10),
        ).pack(side=tk.LEFT)

    def _add_provider_row(self, name="", key="", enabled=True, verified=False):
        row = tk.Frame(self.prov_frame, bg=self.C["panel"])
        row.pack(fill=tk.X, pady=2)

        name_var = tk.StringVar(value=name)
        key_var = tk.StringVar(value=key)
        verified_var = tk.BooleanVar(value=verified)

        # 大模型名称输入框
        name_entry = tk.Entry(row, textvariable=name_var, width=18,
            bg=self.C["entry"], fg=self.C["text"],
            insertbackground=self.C["text"], relief="flat",
            font=("Helvetica", 14), bd=3)
        name_entry.pack(side=tk.LEFT, padx=2)

        # API Key 输入框
        key_entry = tk.Entry(row, textvariable=key_var, width=32, show="*",
            bg=self.C["entry"], fg=self.C["text"],
            insertbackground=self.C["text"], relief="flat",
            font=("Helvetica", 14), bd=3)
        key_entry.pack(side=tk.LEFT, padx=2)

        # 预设下拉框
        preset_var = tk.StringVar(value=name if name else "")
        cb = ttk.Combobox(row, textvariable=preset_var,
            values=list(PROVIDER_PRESETS.keys()), width=14)
        cb.pack(side=tk.LEFT, padx=2)

        # 如果已认证,恢复锁定状态
        if verified and key:
            name_entry.config(state="disabled", disabledbackground="#1a1a1a",
                disabledforeground=self.C["muted"])
            key_entry.config(state="disabled", disabledbackground="#1a1a1a",
                disabledforeground=self.C["muted"])

        # 认证逻辑
        def do_verify():
            n = name_var.get().strip()
            k = key_var.get().strip()
            if not n:
                messagebox.showerror("Error", "Please enter a model provider name first.")
                return
            if not k:
                resolved = PROVIDER_ALIASES.get(n.lower(), n.lower())
                preset = PROVIDER_PRESETS.get(resolved, {})
                if not preset or n.lower().startswith("http") or "://" in n:
                    inferred = discover_provider_with_gemini(n, preset_var.get().strip(), False)
                    if inferred.get("provider_name"):
                        name_var.set(inferred["provider_name"])
                        preset_var.set(inferred["provider_name"])
                        cb["values"] = list(PROVIDER_PRESETS.keys())
                        suggestion_lbl.config(text="found; enter key to verify")
                        messagebox.showinfo("Provider Found", "Provider profile was found. Enter its API key, then click Verify again.")
                        return
                messagebox.showerror("Error", "Please enter an API key first.")
                return
            verify_btn.config(text="Verifying...", state="disabled")
            row.update()
            discovered_profile = {}

            def test():
                try:
                    # 别名转换：claude -> anthropic, gpt -> openai 等
                    real_key = PROVIDER_ALIASES.get(n.lower(), n.lower())
                    preset = PROVIDER_PRESETS.get(real_key, {})
                    typed_is_url = n.lower().startswith("http") or "://" in n
                    if real_key != "gemini" and (not preset or typed_is_url):
                        inferred = discover_provider_with_gemini(n, preset_var.get().strip(), bool(k))
                        if inferred:
                            discovered_profile.update(inferred)
                            n2 = inferred.get("provider_name", n).strip().lower()
                            real_key = PROVIDER_ALIASES.get(n2, n2)
                            preset = PROVIDER_PRESETS.get(real_key, {})
                            effective_name = n2
                        else:
                            effective_name = n
                    else:
                        effective_name = n
                    # ★ 支持自定义URL：如果输入包含 http，直接作为base_url
                    if effective_name.lower().startswith("http") or "://" in effective_name:
                        base_url = preset.get("base_url") or discovered_profile.get("base_url") or effective_name.rstrip("/")
                        model = preset.get("model") or discovered_profile.get("model") or "local-qwen2.5-7b"
                        # 保存自定义URL到provider（供后续chat_json使用）
                        custom_provider = {"base_url": base_url, "model": model,
                            "rate_input": 0.0, "rate_output": 0.0}
                        PROVIDER_PRESETS["__custom__"] = custom_provider
                    else:
                        base_url = preset.get("base_url", f"https://api.{real_key}.com/v1")
                        model = preset.get("model", f"{real_key}-chat")
                    if real_key == "gemini":
                        gemini_url = (
                            base_url.rstrip("/") +
                            f"/models/{urllib.parse.quote(model, safe='')}:generateContent"
                        )
                        r = requests.post(
                            gemini_url,
                            params={"key": k},
                            headers={"Content-Type": "application/json"},
                            json={"contents": [{"role": "user", "parts": [{"text": "Return JSON only: {\"ok\": true}"}]}]},
                            timeout=15,
                        )
                        if r.status_code == 200:
                            return True, None
                        elif r.status_code in (400, 422):
                            return True, None
                        elif r.status_code == 429:
                            return True, "Gemini connection recognized, but the current account quota or request-rate limit has been reached. Other verified providers can continue."
                        elif r.status_code in (401, 403):
                            return False, "Invalid Gemini API key or permission denied"
                        else:
                            return False, "HTTP " + str(r.status_code)
                    r = requests.post(
                        base_url.rstrip("/") + "/chat/completions",
                        headers={"Authorization": "Bearer " + k,
                        "Content-Type": "application/json"},
                        json={"model": model,
                        "messages": [{"role": "user", "content": "hi"}],
                        "max_tokens": 1},
                        timeout=15)
                    if r.status_code in (200, 400, 422):
                        return True, None
                    elif r.status_code == 401:
                        return False, "Invalid API key"
                    else:
                        return False, "HTTP " + str(r.status_code)
                except Exception as e:
                    return False, str(e)[:40]

            def run_test():
                ok, err = test()
                if ok:
                    if discovered_profile.get("provider_name"):
                        name_var.set(discovered_profile["provider_name"])
                        preset_var.set(discovered_profile["provider_name"])
                        cb["values"] = list(PROVIDER_PRESETS.keys())
                        suggestion_lbl.config(text="saved to library")
                    verified_var.set(True)
                    name_entry.config(state="disabled",
                        disabledbackground="#1a1a1a",
                        disabledforeground=self.C["muted"])
                    key_entry.config(state="disabled",
                        disabledbackground="#1a1a1a",
                        disabledforeground=self.C["muted"])
                    if err:
                        self.root.after(0, lambda msg=err: messagebox.showwarning("Provider Verified - Quota Limited", msg))
                    verify_btn.config(text="✓ Verified", command=do_unlock,
                        bg=self.C["green"], state="normal")
                    update_lawyer_count()
                    self._update_count_label()
                    self._refresh_side_provider_routes()
                    self._save_config()
                else:
                    verify_btn.config(text="✔ Verify", state="normal")
                    messagebox.showerror("Verification Failed", err or "Please check the API key and model name.")

            threading.Thread(target=run_test, daemon=True).start()

        def do_unlock():
            verified_var.set(False)
            name_entry.config(state="normal",
                bg=self.C["entry"], fg=self.C["text"])
            key_entry.config(state="normal",
                bg=self.C["entry"], fg=self.C["text"])
            verify_btn.config(text="✔ Verify", command=do_verify,
                bg=self.C["accent"])
            update_lawyer_count()
            self._update_count_label()
            self._refresh_side_provider_routes()

        # 认证按钮
        verify_btn = tk.Button(row,
            text="✓ Verified" if (verified and key) else "✔ Verify",
            command=do_unlock if (verified and key) else do_verify,
            bg=self.C["green"] if (verified and key) else self.C["accent"],
            fg="white", relief="flat", padx=8, pady=2, cursor="hand2")
        verify_btn.pack(side=tk.LEFT, padx=2)

        # 删除按钮
        def del_row():
            self.providers = [r for r in self.providers if r["_frame"] is not row]
            row.destroy()
            self._update_count_label()
            self._refresh_side_provider_routes()

        tk.Button(row, text="✕", command=del_row,
            bg=self.C["red"], fg="white", relief="flat",
            padx=6, pady=2, cursor="hand2").pack(side=tk.LEFT, padx=2)

        # ===== 智能自动补全:删除按钮后面显示灰色箭头+建议 =====
        suggestion_lbl = tk.Label(row, text="", bg=self.C["panel"],
            fg=self.C["muted"], font=("Helvetica", 14))
        suggestion_lbl.pack(side=tk.LEFT, padx=4)

        def get_best_match(typed):
            typed = typed.strip().lower()
            if not typed:
                return ""
            # 1. 先完全匹配别名
            resolved = PROVIDER_ALIASES.get(typed)
            if resolved and resolved in PROVIDER_PRESETS:
                return resolved
            # 2. 别名包含匹配(如输入 c → 匹配 claude)
            matched_aliases = [a for a in PROVIDER_ALIASES.keys() if typed in a.lower()]
            if matched_aliases:
                best_alias = min(matched_aliases, key=len)
                return best_alias
            # 3. 预设包含匹配
            all_keys = list(PROVIDER_PRESETS.keys())
            matched = [k for k in all_keys if typed in k.lower()]
            if matched:
                return matched[0]
            return ""

        def on_name_input(evt=None):
            typed = name_var.get()
            best = get_best_match(typed)
            if best and best.lower() != typed.lower():
                suggestion_lbl.config(text=f"→ {best}")
            else:
                suggestion_lbl.config(text="")

            # 如果输入看起来像 URL,尝试反向查找软件名
            if "http" in typed.lower() or "api." in typed.lower() or ".com" in typed.lower():
                matched_key = None
                for key, config in PROVIDER_PRESETS.items():
                    base_url = config.get("base_url", "")
                    if base_url and typed.lower() in base_url.lower():
                        matched_key = key
                        break
                preset_var.set(matched_key if matched_key else "未知")
            else:
                # 正常同步下拉框
                preset_var.set(typed)

            # 更新下拉框选项
            if typed:
                matches = [k for k in PROVIDER_PRESETS.keys() if typed.lower() in k.lower()]
                cb["values"] = matches if matches else list(PROVIDER_PRESETS.keys())
            else:
                cb["values"] = list(PROVIDER_PRESETS.keys())

        def on_focus_out(evt=None):
            suggestion_lbl.config(text="")

        def apply_suggestion():
            typed = name_var.get().strip()
            if not typed:
                return
            best = get_best_match(typed)
            if best and best.lower() != typed.lower():
                name_var.set(best)
                preset_var.set(best) # 同步下拉框
                for p in self.providers:
                    if p.get("name").get() == best and p.get("key").get():
                        key_var.set(p.get("key").get())
                        break
            suggestion_lbl.config(text="")

        def get_verified_gemini_key():
            for p in self.providers:
                pname = (p.get("name").get() or "").strip().lower()
                resolved = PROVIDER_ALIASES.get(pname, pname)
                if resolved == "gemini" and p.get("verified").get() and p.get("key").get().strip():
                    return p.get("key").get().strip()
            return ""

        def discover_provider_with_gemini(typed_name, selected, target_key_hint):
            gemini_key = get_verified_gemini_key()
            if not gemini_key or not typed_name:
                return {}
            prompt = (
                "You help configure AI model API providers for a desktop legal-assistance app.\n"
                "The app can call OpenAI-compatible /chat/completions endpoints and Google Gemini native generateContent endpoints.\n"
                "Given the user's rough provider name, URL, or model hint, infer the best configuration.\n"
                "Return strict JSON only with these keys:\n"
                "{"
                "\"provider_name\":\"short lowercase provider id\","
                "\"adapter\":\"openai_compatible|gemini_native|unknown\","
                "\"base_url\":\"base API URL without trailing slash\","
                "\"model\":\"recommended model id\","
                "\"confidence\":\"high|medium|low\","
                "\"note\":\"short English note\""
                "}\n"
                "Rules:\n"
                "- If it is Google Gemini or generativelanguage.googleapis.com, provider_name must be gemini, adapter gemini_native, base_url https://generativelanguage.googleapis.com/v1beta.\n"
                "- If the URL looks like /v1, /openai/v1, OpenRouter, DeepSeek, Groq, Together, Fireworks, LM Studio, Ollama OpenAI bridge, or a private Cloud Run OpenAI gateway, use openai_compatible.\n"
                "- If unsure, use adapter unknown and keep provider_name close to the user's input.\n\n"
                f"User typed provider/name/url: {typed_name!r}\n"
                f"Current dropdown value: {selected!r}\n"
                f"User entered an API key: {bool(target_key_hint)}\n"
            )
            client = LLMClient("gemini", gemini_key)
            result = client.chat_json(prompt, temperature=0.1, max_tokens=900)
            if result.get("_error"):
                return {}

            provider_name = str(result.get("provider_name") or typed_name or selected).strip().lower()
            adapter = str(result.get("adapter") or "unknown").strip().lower()
            base_url = str(result.get("base_url") or "").strip().rstrip("/")
            model = str(result.get("model") or "").strip()
            confidence = str(result.get("confidence") or "low").strip()

            if adapter == "gemini_native":
                provider_name = "gemini"
                base_url = base_url or "https://generativelanguage.googleapis.com/v1beta"
                model = model or "gemini-2.5-flash"
            elif adapter == "openai_compatible":
                provider_name = provider_name or typed_name.strip().lower()
                model = model or provider_name
            if not provider_name:
                return {}

            if base_url or model:
                PROVIDER_PRESETS[provider_name] = {
                    "name": provider_name,
                    "base_url": base_url,
                    "model": model or provider_name,
                    "rate_input": 0.0,
                    "rate_output": 0.0,
                }
            PROVIDER_ALIASES[provider_name] = provider_name
            return {
                "provider_name": provider_name,
                "adapter": adapter,
                "base_url": base_url,
                "model": model,
                "confidence": confidence,
            }

        name_entry.bind("<KeyRelease>", on_name_input)
        name_entry.bind("<FocusOut>", on_focus_out)
        name_entry.bind("<Return>", lambda e: apply_suggestion())


        # 下拉框选择时自动填充
        def on_preset_select(evt=None):
            selected = preset_var.get().strip()
            if selected in PROVIDER_PRESETS:
                name_var.set(selected)
                for p in self.providers:
                    if p.get("name").get() == selected and p.get("key").get() and p is not self.providers[-1]:
                        key_var.set(p.get("key").get())
                        break

        cb.bind("<<ComboboxSelected>>", on_preset_select)
        cb.bind("<Return>", on_preset_select)

        self.providers.append({
            "_frame": row, "enabled": tk.BooleanVar(value=True),
            "name": name_var, "key": key_var,
            "verified": verified_var,
        })

        # ===== 黄色律师数量标签 =====
        lawyer_count_lbl = tk.Label(row, text="", bg=self.C["panel"], fg=self.C["gold"],
            font=("Helvetica", 12, "bold"))
        lawyer_count_lbl.pack(side=tk.LEFT, padx=8)

        def update_lawyer_count(*args):
            n_dim = sum(1 for v in self.dim_vars.values() if v.get()) if hasattr(self, "dim_vars") else 15
            if verified_var.get():
                lawyer_count_lbl.config(text=f"{n_dim * 2} frames")
            else:
                lawyer_count_lbl.config(text="")

        # 绑定维度变化更新律师数量
        for v in self.dim_vars.values():
            v.trace_add("write", update_lawyer_count)
        update_lawyer_count()

    def _add_empty_row(self):
        self._add_provider_row()
        self._update_count_label()

    def _set_dims(self, val):
        for v in self.dim_vars.values():
            v.set(val)
        self._update_count_label()

    def _verified_provider_route_names(self):
        names = []
        for r in self.providers:
            try:
                if r["key"].get().strip() and r.get("verified", tk.BooleanVar(value=False)).get():
                    name = r["name"].get().strip()
                    if name and name not in names:
                        names.append(name)
            except Exception:
                pass
        return names

    def _refresh_side_provider_routes(self):
        names = self._verified_provider_route_names()
        valid = set(names)
        for side in ("positive", "negative"):
            selected = [x for x in self.side_provider_allocation.get(side, []) if x in valid]
            self.side_provider_allocation[side] = selected
        self._update_side_allocation_summary()

    def _update_side_allocation_summary(self):
        pos = self.side_provider_allocation.get("positive", [])
        neg = self.side_provider_allocation.get("negative", [])
        pos_text = ", ".join(pos) if pos else "Full"
        neg_text = ", ".join(neg) if neg else "Full"
        self.v_positive_provider_route.set(pos_text if pos else "Full verified providers")
        self.v_negative_provider_route.set(neg_text if neg else "Full verified providers")
        self.v_side_allocation_summary.set(f"Side allocation: Positive -> {pos_text}; Negative -> {neg_text}")

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
            font=("Helvetica", 11, "bold"),
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
            btn = tk.Button(parent, relief="flat", width=11, padx=4, pady=2, font=("Helvetica", 9, "bold"))

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
            self._save_config()
            win.destroy()

        tk.Button(buttons, text="Cancel", command=win.destroy, bg="#333", fg="white", relief="flat", padx=14, pady=5).pack(side=tk.RIGHT, padx=(8, 0))
        tk.Button(buttons, text="Apply", command=save_and_close, bg=self.C["accent"], fg="#111827", relief="flat", padx=16, pady=5).pack(side=tk.RIGHT)

    def _select_provider_clients_for_side(self, all_clients, route_value, side_label):
        selected_names = self.side_provider_allocation.get("positive" if side_label.lower().startswith("positive") else "negative", [])
        if not selected_names:
            return list(all_clients)
        wanted_names = {x.lower() for x in selected_names}
        wanted_aliases = {PROVIDER_ALIASES.get(x.lower(), x.lower()) for x in selected_names}
        selected = [
            c for c in all_clients
            if c.provider_key in wanted_aliases or getattr(c, "source_name", "").lower() in wanted_names
        ]
        if not selected:
            available = ", ".join(getattr(c, "source_name", c.provider_key) for c in all_clients) or "none"
            wanted_text = ", ".join(selected_names)
            raise RuntimeError(f"{side_label} selected providers are not verified or available: {wanted_text}. Available verified providers: {available}")
        return selected

    def _update_count_label(self):
        verified_count = sum(1 for r in self.providers if r.get("verified") and r["verified"].get())
        n_dim = sum(1 for v in self.dim_vars.values() if v.get()) if hasattr(self, "dim_vars") else 15
        if verified_count == 0:
            self.prov_count_lbl.config(text="")
        else:
            total_frames = verified_count * n_dim * 2
            self.prov_count_lbl.config(
                text=f"⚡ {verified_count} provider(s) x {n_dim} dimension(s) x 2 = {total_frames} frames",
                fg=self.C["gold"])

    def _build_dimensions(self):
        p = tk.Frame(self.sf, bg=self.C["panel"], padx=10, pady=8)
        p.pack(fill=tk.X, padx=10, pady=5)
        self.set_help(p, "Attack dimensions: choose which lawyer frames join this online opposition run. Selected dimensions run with verified model rows.")
        # 标题行：标题 + 按钮在同一行
        title_row = tk.Frame(p, bg=self.C["panel"])
        title_row.pack(fill=tk.X)
        tk.Label(title_row, text="⚔️ Step 2 — Attack Dimensions (all selected by default)", bg=self.C["panel"], fg=self.C["text"], font=("Helvetica", 10, "bold")).pack(side=tk.LEFT)

        # 按钮行内嵌到标题右侧
        tk.Button(title_row, text="📖 Explain", command=self._show_dim_explanations, bg="#2a3a4a", fg=self.C["text"], relief="flat", padx=10, pady=2, cursor="hand2").pack(side=tk.LEFT, padx=(16, 0))
        tk.Button(title_row, text="✅ All", command=lambda: self._set_dims(True), bg="#1a3a1a", fg="white", relief="flat", padx=10, pady=2, cursor="hand2").pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(title_row, text="☐ None", command=lambda: self._set_dims(False), bg="#333", fg=self.C["text"], relief="flat", padx=10, pady=2, cursor="hand2").pack(side=tk.LEFT, padx=5)
        self.status_label = tk.Label(title_row, text="Status: Ready", bg=self.C["panel"], fg=self.C["muted"], font=("Helvetica", 12))
        self.status_label.pack(side=tk.RIGHT, padx=8)


        grid = tk.Frame(p, bg=self.C["panel"])
        grid.pack(fill=tk.X)
        cols = 5
        for i, (dim, _desc) in enumerate(ALL_DIMENSIONS):
            default_val = True  # 所有维度默认开启
            v = tk.BooleanVar(value=default_val)
            self.dim_vars[dim] = v
            color = self.C["text"]
            cmd = lambda d=dim: self._on_dim_toggle(d)
            tk.Checkbutton(grid, text=DIMENSION_LABELS_EN.get(dim, dim), variable=v, bg=self.C["panel"], fg=color, selectcolor="#3e1a1a", activeforeground="#f38ba8", activebackground="#3e1a1a", font=("Helvetica", 13), command=cmd).grid(row=i // cols, column=i % cols, sticky="w", padx=12, pady=3)
        # 判例参照 — 独立于维度，放在沉默证据右侧
        search_row = 16 // cols  # 沉默证据的行
        search_col = 16 % cols + 1  # 沉默证据右侧
        tk.Checkbutton(grid, text="🔍 Case Authority Search", variable=self.v_search, bg=self.C["panel"], fg=self.C["gold"], selectcolor="#3e1a1a", activeforeground="#f9e2af", activebackground="#3e1a1a", font=("Helvetica", 13), command=self._on_search_toggle).grid(row=search_row, column=search_col, sticky="w", padx=12, pady=3)

    def _on_dim_toggle(self, dim):
        """维度勾选回调"""
        self._update_count_label()

    def _on_search_toggle(self):
        """案例搜索开关回调"""
        if self.v_search.get():
            # 用户开启搜索，弹警告
            ok = messagebox.askokcancel(
                "⚠️ Case Search Risk Notice",
                "When case search is enabled, the system will use an online search engine to retrieve real authorities.\n\n"
                "Please note:\n"
                "• The model may still invent non-existent citations\n"
                "• Search results must be checked manually\n"
                "• Any cited authority should be verified before filing\n\n"
                "Enable case search?"
            )
            if not ok:
                self.v_search.set(False)
            else:
                self._log("[✓] Case search enabled - please verify all citations")
        else:
            self._log("[!] Case search disabled - model citations may be unreliable")

    def _show_dim_explanations(self):
        """弹窗显示全部攻击维度的详细解释"""
        win = tk.Toplevel(self.root)
        win.title("📖 18 Attack Dimensions - Details")
        win.geometry("820x680")
        win.configure(bg=self.C["bg"])
        win.transient(self.root)
        win.grab_set()

        # 标题
        tk.Label(win, text="⚔️ 18 Attack Dimensions", bg=self.C["bg"], fg=self.C["gold"], font=("Helvetica", 15, "bold")).pack(pady=(16, 10))

        # 可滚动区域
        canvas = tk.Canvas(win, bg=self.C["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=self.C["bg"])
        scroll_frame.bind("<Configure>", lambda e: (canvas.configure(scrollregion=canvas.bbox("all")), canvas.configure(width=e.width)))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw", width=780)
        canvas.configure(yscrollcommand=scrollbar.set)

        # 鼠标滚轮绑定
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"
        canvas.bind("<MouseWheel>", _on_mousewheel)
        scroll_frame.bind("<MouseWheel>", _on_mousewheel)

        # 分类标题
        categories = [
            ("-- Core Dimensions --", self.C["teal"]),
            ("-- Tactical Dimensions --", self.C["gold"]),
            ("-- Meta Dimensions: Frame Shift Attacks --", self.C["salmon"]),
        ]
        cat_idx = 0
        for idx, (dim, desc) in enumerate(ALL_DIMENSIONS):
            # 插入分类标题
            if idx in (6, 11):  # 战术维度从第7个开始(idx=6)，元维度从第12个开始(idx=11)
                if cat_idx < len(categories):
                    lbl = tk.Label(scroll_frame, text=categories[cat_idx][0], bg=self.C["bg"], fg=categories[cat_idx][1], font=("Helvetica", 12, "bold"), anchor="w")
                    lbl.pack(fill=tk.X, padx=24, pady=(14, 4))
                    cat_idx += 1

            row = tk.Frame(scroll_frame, bg=self.C["bg"])
            row.pack(fill=tk.X, padx=18, pady=3)
            # 维度名（加粗）
            tk.Label(row, text=f"▸ {DIMENSION_LABELS_EN.get(dim, dim)}", bg=self.C["bg"], fg=self.C["text"], font=("Helvetica", 12, "bold"), anchor="w", width=26).pack(side=tk.LEFT)
            # 解释文字
            tk.Label(row, text=DIMENSION_DESC_EN.get(dim, desc), bg=self.C["bg"], fg=self.C["muted"], font=("Helvetica", 11), anchor="w", justify=tk.LEFT, wraplength=700).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 关闭按钮
        btn_row = tk.Frame(win, bg=self.C["bg"])
        btn_row.pack(fill=tk.X, pady=(12, 16))
        tk.Button(btn_row, text="Close", command=win.destroy, bg="#333", fg="white", relief="flat", padx=30, pady=5, cursor="hand2").pack()

        # 布局
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(16, 0))
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=(0, 16), padx=(0, 16))

        # 关闭时解绑滚轮
        def _cleanup():
            pass
        win.protocol("WM_DELETE_WINDOW", lambda: (_cleanup(), win.destroy()))

    def _build_case(self):
        p = tk.Frame(self.sf, bg=self.C["panel"], padx=10, pady=8)
        p.pack(fill=tk.X, padx=10, pady=5)
        self.set_help(p, "Case information: import or paste the full matter. The online model combines the case with both side frames.")

        # 标题行 + 拖入按钮
        title_row = tk.Frame(p, bg=self.C["panel"])
        title_row.pack(fill=tk.X)
        tk.Label(title_row, text="📋 Step 3 — Case Information", bg=self.C["panel"], fg=self.C["text"],
                 font=("Helvetica", 12, "bold")).pack(side=tk.LEFT)
        tk.Button(title_row, text="📂 Import Case File (PDF/Word/TXT)",
                  command=self._import_case_file,
                  bg="#1a3a5a", fg="white", relief="flat",
                  padx=12, pady=3, font=("Helvetica", 13), cursor="hand2").pack(side=tk.RIGHT)

        r = tk.Frame(p, bg=self.C["panel"])
        r.pack(fill=tk.X, pady=4)
        tk.Label(r, text="Case Name:", bg=self.C["panel"], fg=self.C["muted"]).pack(side=tk.LEFT)
        self.v_name = tk.StringVar()
        tk.Entry(r, textvariable=self.v_name, width=40, bg=self.C["entry"], fg=self.C["text"], relief="flat").pack(side=tk.LEFT, padx=5)
        tk.Label(r, text=" Jurisdiction:", bg=self.C["panel"], fg=self.C["muted"]).pack(side=tk.LEFT)
        self.v_jur = tk.StringVar(value="Australia / New South Wales")
        tk.Entry(r, textvariable=self.v_jur, width=30, bg=self.C["entry"], fg=self.C["text"], relief="flat").pack(side=tk.LEFT, padx=5)
        tk.Button(r, text="Add Jurisdiction Frame", command=self._add_online_jurisdiction_frame, bg="#31547a", fg="white", relief="flat", padx=10, pady=3).pack(side=tk.LEFT, padx=5)
        tk.Button(r, text="Official Law Pack", command=self._open_online_official_law_pack, bg="#7a531f", fg="white", relief="flat", padx=10, pady=3).pack(side=tk.LEFT, padx=3)

        # Drag/drop hint area.
        self.drop_label = tk.Label(p,
            text="💡 Drop a PDF / Word / TXT file here for automatic parsing",
            bg="#0d2137", fg=self.C["muted"],
            font=("Helvetica", 13), pady=6, relief="flat", cursor="hand2")
        self.drop_label.pack(fill=tk.X, pady=(4, 2))
        self.drop_label.bind("<Button-1>", lambda e: self._import_case_file())
        self._setup_drag_drop(self.drop_label)

        tk.Label(p, text="Full Case Background:", bg=self.C["panel"], fg=self.C["muted"]).pack(anchor=tk.W, pady=(6, 2))
        self.t_bg = scrolledtext.ScrolledText(p, height=6, bg=self.C["entry"], fg=self.C["text"], relief="flat")
        self._bind_local_scroll(self.t_bg)
        self.t_bg.pack(fill=tk.X)

    def _jurisdiction_family(self):
        value = self.v_jur.get().strip().lower()
        if any(x in value for x in ("australia", "nsw", "vic", "qld", "queensland", "wa", "tas", "act", "nt")):
            return "AU"
        if any(x in value for x in ("united kingdom", "uk", "england", "wales", "scotland")):
            return "UK"
        if any(x in value for x in ("united states", "usa", " u.s.", "california", "new york", "texas", "florida")):
            return "US"
        if any(x in value for x in ("european union", " eu", "europe")):
            return "EU"
        if any(x in value for x in ("china", " cn", "prc")):
            return "CN"
        return "CUSTOM"

    def _add_online_jurisdiction_frame(self):
        family = self._jurisdiction_family()
        jurisdiction = self.v_jur.get().strip() or "Unspecified jurisdiction"
        frames = {
            "AU": {
                "positive": "Identify the applicable Commonwealth and State or Territory law. Map contract formation, Australian Consumer Law or other pleaded duties, breach, causation, loss, notice, and proportionate remedy to the actual facts.",
                "negative": "Test whether the claimant has selected the correct Commonwealth and State or Territory rule, proved each element, preserved original evidence, excluded alternative causes, and sought a proportionate remedy.",
                "evidence": "Current legislation and applicable State or Territory provisions; signed contract and terms; notices and communications; payment, delivery, inspection, expert, loss, and mitigation records.",
            },
            "UK": {
                "positive": "Map the facts to the governing contract rules and, where applicable, the Consumer Rights Act 2015, misrepresentation, unfair-terms, notice, causation, and remedy requirements.",
                "negative": "Test formation, incorporation and clarity of terms, statutory preconditions, timely notice, evidence authenticity, causation, mitigation, and proportionality of the remedy.",
                "evidence": "Signed contract and incorporated terms; communications and notices; delivery or performance records; expert material; payment, loss, and mitigation records.",
            },
            "US": {
                "positive": "Identify the governing State and whether common-law contract, UCC, consumer-protection, warranty, tort, or procedural rules apply. Map every required element to the record.",
                "negative": "Challenge choice of law, formation, warranty or notice preconditions, authentication, hearsay or reliability issues, causation, mitigation, and damages methodology.",
                "evidence": "Governing State statutes and rules; signed agreement and disclosures; notices; performance and inspection records; authentication material; damages calculations and alternative-cause evidence.",
            },
            "EU": {
                "positive": "Separate EU-level rules from Member State implementation. Identify the specific consumer, data, platform, contract, evidence, and remedy rules that enter this dispute.",
                "negative": "Test whether the relied-on EU rule is directly applicable or requires Member State implementation, and challenge the factual, evidentiary, causation, and proportionality links.",
                "evidence": "EUR-Lex source text; relevant Member State implementation; contract or platform terms; consent and notice records; process logs; loss and remedy evidence.",
            },
            "CN": {
                "positive": "Identify the applicable national law, judicial interpretation, local procedural rule, and cause of action. Map formation, performance, breach or infringement, evidence, causation, loss, and remedy.",
                "negative": "Challenge the selected cause of action, element-to-fact mapping, electronic-data authenticity and completeness, burden of proof, alternative causation, fault allocation, and proportionality.",
                "evidence": "Current official legislation and judicial interpretations; contract or order records; communications and platform records; payment and delivery records; inspection, expert, loss, and causation material.",
            },
            "CUSTOM": {
                "positive": "Identify the governing legislation, cause of action, required elements, burden of proof, procedure, available remedies, and any mandatory local rules before relying on a conclusion.",
                "negative": "Test jurisdiction and choice of law, each required element, procedural preconditions, evidence admissibility and weight, causation, loss, mitigation, and remedy limits.",
                "evidence": "Official local legislation and court rules; controlling authorities; original transaction records; notices; witness, expert, causation, loss, and remedy material.",
            },
        }
        frame = frames[family]
        marker = f"Jurisdiction frame: {jurisdiction}"
        combined = self._gt(self.t_pos_args) + self._gt(self.t_neg_args)
        if marker.lower() in combined.lower():
            messagebox.showinfo("Jurisdiction Frame", "This jurisdiction frame is already present.")
            return
        self._append_text_to_widget(self.t_pos_args, marker, frame["positive"])
        self._append_text_to_widget(self.t_neg_args, marker, frame["negative"])
        self._append_text_to_widget(self.t_pos_ev, f"Official and local materials for {jurisdiction}", frame["evidence"])
        self._append_text_to_widget(self.t_neg_ev, f"Official and local materials for {jurisdiction}", frame["evidence"])
        self.status_label.config(text=f"Jurisdiction frame added: {jurisdiction}")

    def _open_online_official_law_pack(self):
        family = self._jurisdiction_family()
        jurisdiction = self.v_jur.get().strip() or "Unspecified jurisdiction"
        sources = {
            "AU": [
                ("Federal Register of Legislation", "https://www.legislation.gov.au/"),
                ("Federal Register API", "https://api.prod.legislation.gov.au/swagger/v1/swagger.json"),
                ("Australian Consumer Law", "https://consumer.gov.au/australian-consumer-law/legislation"),
                ("AustLII", "https://www.austlii.edu.au/"),
                ("NSW Legislation", "https://legislation.nsw.gov.au/"),
            ],
            "UK": [("UK Legislation", "https://www.legislation.gov.uk/"), ("BAILII", "https://www.bailii.org/")],
            "US": [("U.S. Code", "https://uscode.house.gov/"), ("GovInfo", "https://www.govinfo.gov/"), ("Congress.gov", "https://www.congress.gov/")],
            "EU": [("EUR-Lex", "https://eur-lex.europa.eu/"), ("CURIA", "https://curia.europa.eu/")],
            "CN": [("National Laws and Regulations Database", "https://flk.npc.gov.cn/"), ("Supreme People's Court", "https://www.court.gov.cn/")],
            "CUSTOM": [],
        }
        win = tk.Toplevel(self.root)
        win.title("Official Law Pack")
        win.geometry("760x520")
        win.configure(bg=self.C["bg"])
        shell = tk.Frame(win, bg=self.C["bg"], padx=18, pady=16)
        shell.pack(fill=tk.BOTH, expand=True)
        tk.Label(shell, text=f"Official Law Pack - {jurisdiction}", bg=self.C["bg"], fg=self.C["gold"], font=("Helvetica", 16, "bold")).pack(anchor="w")
        tk.Label(shell, text="Opening an official source does not upload case content. Verify currency, amendments, territorial application, and relevance before use.", bg=self.C["bg"], fg=self.C["muted"], wraplength=710, justify=tk.LEFT).pack(anchor="w", pady=(6, 14))
        entries = sources.get(family, [])
        if not entries:
            tk.Label(shell, text="No built-in official source directory is available for this custom jurisdiction. The law firm or user should supply the official legislation and court sources.", bg=self.C["panel"], fg=self.C["text"], wraplength=690, justify=tk.LEFT, padx=14, pady=14).pack(fill=tk.X)
        for name, url in entries:
            row = tk.Frame(shell, bg=self.C["panel"], padx=12, pady=8)
            row.pack(fill=tk.X, pady=3)
            tk.Label(row, text=name, bg=self.C["panel"], fg=self.C["text"], font=("Helvetica", 10, "bold")).pack(side=tk.LEFT)
            tk.Button(row, text="Open Official Source", command=lambda target=url: webbrowser.open(target), bg="#31547a", fg="white", relief="flat", padx=12, pady=4).pack(side=tk.RIGHT)

    def _setup_drag_drop(self, widget):
        """Register one widget as a file drop target when tkinterdnd2 is available."""
        try:
            widget.drop_target_register('DND_Files')
            widget.dnd_bind('<<Drop>>', lambda e: self._on_file_drop(e.data))
            widget._nido_drop_enabled = True
        except Exception:
            pass

    def _setup_global_drag_drop(self):
        """Allow dropping a case file anywhere inside the main window."""
        if not TkinterDnD:
            return

        def walk(widget):
            self._setup_drag_drop(widget)
            try:
                children = widget.winfo_children()
            except Exception:
                children = []
            for child in children:
                walk(child)

        walk(self.root)

    def _drop_paths_from_data(self, data):
        raw = str(data or "").strip()
        if not raw:
            return []
        try:
            paths = list(self.root.tk.splitlist(raw))
        except Exception:
            paths = re.findall(r"\{([^}]+)\}|(\S+)", raw)
            paths = [a or b for a, b in paths]
        return [str(p).strip().strip("{}") for p in paths if str(p).strip()]

    def _on_file_drop(self, data):
        """Handle a dropped PDF / Word / TXT / JSON case file."""
        paths = self._drop_paths_from_data(data)
        supported = {".pdf", ".docx", ".doc", ".txt", ".json"}
        for path in paths:
            if os.path.splitext(path)[1].lower() in supported:
                self._parse_case_file(path)
                return "break"
        messagebox.showerror("Unsupported Format", "Please drop a PDF, Word, TXT, or JSON file.")
        return "break"

    def _import_case_file(self):
        """弹出文件选择对话框"""
        path = filedialog.askopenfilename(
            title="Select Case File",
            filetypes=[
                ("Supported files", "*.pdf *.docx *.doc *.txt *.json"),
                ("PDF files", "*.pdf"),
                ("Word files", "*.docx *.doc"),
                ("Text files", "*.txt"),
                ("JSON files", "*.json"),
                ("All files", "*.*"),
            ]
        )
        if path:
            self._parse_case_file(path)

    def _parse_case_file(self, path):
        """读取文件内容，调用AI分析并填入各输入框"""
        import os
        ext = os.path.splitext(path)[1].lower()

        self.drop_label.config(text="⏳ Reading file...", fg=self.C["gold"])
        self.root.update()

        # 1. 提取文本
        try:
            if ext == '.json':
                with open(path, encoding='utf-8-sig') as f:
                    data = json.load(f)
                if data.get("nido_tactic_combo_package") or any(k in data for k in ("pos_args", "neg_args", "background", "case_text")):
                    if data.get("case_name"):
                        self.v_name.set(data.get("case_name", ""))
                    if data.get("jurisdiction"):
                        self.v_jur.set(data.get("jurisdiction", ""))
                    fields = [
                        (self.t_bg, data.get("background") or data.get("case_text") or ""),
                        (self.t_pos_args, data.get("pos_args") or ""),
                        (self.t_pos_ev, data.get("pos_ev") or ""),
                        (self.t_neg_args, data.get("neg_args") or ""),
                        (self.t_neg_ev, data.get("neg_ev") or ""),
                    ]
                    package_text = "\n\n".join(str(value or "") for _widget, value in fields)
                    if not re.search(r"[\u4e00-\u9fff]", package_text):
                        for widget, value in fields:
                            if value:
                                widget.delete("1.0", tk.END)
                                widget.insert("1.0", self._clean_system_labels(value))
                        self.drop_label.config(
                            text=f"✅ Tactic package imported: {data.get('case_name', os.path.basename(path))}",
                            fg=self.C["green"],
                        )
                        return
                    raw_text = package_text
                raw_text = json.dumps(data, ensure_ascii=False, indent=2)

            elif ext == '.txt':
                with open(path, encoding='utf-8', errors='ignore') as f:
                    raw_text = f.read()

            elif ext == '.pdf':
                try:
                    import pdfplumber
                    with pdfplumber.open(path) as pdf:
                        raw_text = '\n'.join(p.extract_text() or '' for p in pdf.pages)
                except ImportError:
                    try:
                        import PyPDF2
                        with open(path, 'rb') as f:
                            reader = PyPDF2.PdfReader(f)
                            raw_text = '\n'.join(p.extract_text() or '' for p in reader.pages)
                    except ImportError:
                        messagebox.showerror("Missing Dependency", "Please install a PDF parser:\npip install pdfplumber")
                        self.drop_label.config(text="❌ Missing PDF parser", fg=self.C["red"])
                        return

            elif ext in ('.docx', '.doc'):
                try:
                    import docx
                    doc = docx.Document(path)
                    raw_text = '\n'.join(p.text for p in doc.paragraphs)
                except ImportError:
                    messagebox.showerror("Missing Dependency", "Please install the Word parser:\npip install python-docx")
                    self.drop_label.config(text="❌ Missing Word parser", fg=self.C["red"])
                    return
            else:
                messagebox.showerror("Unsupported Format", f"Unsupported file format: {ext}")
                return

            if not raw_text.strip():
                messagebox.showerror("Empty File", "No text could be extracted from this file.")
                self.drop_label.config(text="❌ File content is empty", fg=self.C["red"])
                return

            raw_text = re.sub(r"^\s*\[(?:Imported file|Read mode|Language note)[^\]]*\].*$", "", raw_text, flags=re.MULTILINE | re.IGNORECASE)
            raw_text = re.sub(r"^\s*(?:好的[，,].*英文.*|以下是.*英文.*|这是.*英文.*)\s*$", "", raw_text, flags=re.MULTILINE)
            raw_text = re.sub(r"\n{3,}", "\n\n", raw_text).strip()

            if self._is_tactic_combo_text(raw_text):
                self._apply_tactic_combo_text(raw_text)
                self.drop_label.config(
                    text="✅ Tactic package appended to the current side panels; case background was not overwritten",
                    fg=self.C["green"],
                )
                return

        except Exception as e:
            messagebox.showerror("Read Failed", str(e)[:100])
            self.drop_label.config(text="❌ File read failed", fg=self.C["red"])
            return

        # 2. 用AI分析
        self.drop_label.config(text="⏳ AI is analyzing the case...", fg=self.C["gold"])
        self.root.update()
        use_redaction = self.v_anonymize.get()
        if not use_redaction:
            use_redaction = self._ask_enable_data_redaction()
            if use_redaction:
                self.v_anonymize.set(True)
        import_anonymizer = PIIAnonymizer() if use_redaction else None
        raw_for_model = import_anonymizer.anonymize(raw_text) if import_anonymizer else raw_text

        def do_parse():
            # 找第一个已认证的模型
            verified = [r for r in self.providers
                        if r["key"].get().strip() and r.get("verified", tk.BooleanVar(value=False)).get()]
            if not verified:
                self.root.after(0, lambda: messagebox.showerror("Error", "Please verify at least one model first."))
                self.root.after(0, lambda: self.drop_label.config(text="No verified model", fg=self.C["red"]))
                return

            prompt = (
                f"You are a legal assistant extracting structured case inputs for an English UI.\n\n"
                f"Read the case file carefully and extract the key information.\n"
                f"All JSON values must be written in English. If the source text is not English, translate the extracted content into English.\n"
                f"Preserve party names, case names, court names, dates, amounts, and legal citations exactly where possible.\n"
                f"Do not add legal analysis beyond what can be inferred from the file.\n\n"
                f"Case file content (first 8000 characters):\n{raw_for_model[:8000]}\n\n"
                f"Return strict JSON only, with this exact shape:\n"
                f'{{"case_name": "short case name", '
                f'"jurisdiction": "court or jurisdiction", '
                f'"background": "factual background, within 300 English words", '
                f'"pos_args": ["positive/plaintiff/applicant core argument 1", "core argument 2"], '
                f'"pos_ev": ["positive evidence item 1", "positive evidence item 2"], '
                f'"neg_args": ["negative/defendant/respondent core argument 1", "core argument 2"], '
                f'"neg_ev": ["negative evidence item 1", "negative evidence item 2"]}}'
            )

            res = {"_error": "all_verified_providers_failed"}
            errors = []
            for row in verified:
                client = LLMClient(row["name"].get(), row["key"].get().strip())
                attempt = client.chat_json(prompt, temperature=0.3, max_tokens=3000)
                if isinstance(attempt, dict) and not attempt.get("_error"):
                    res = attempt
                    break
                errors.append(f"{row['name'].get()}: {attempt.get('_error', 'invalid response') if isinstance(attempt, dict) else 'invalid response'}")

            if res.get("_error"):
                detail = "; ".join(errors)[:300] or str(res.get("_error", ""))[:100]
                self.root.after(0, lambda msg=detail: messagebox.showerror("AI Analysis Failed", msg))
                self.root.after(0, lambda: self.drop_label.config(text="❌ AI analysis failed", fg=self.C["red"]))
                return

            if import_anonymizer:
                res = json.loads(import_anonymizer.deanonymize(json.dumps(res, ensure_ascii=False)))

            # 填入各输入框
            def fill_fields():
                def as_items(value):
                    if isinstance(value, list):
                        raw_items = value
                    else:
                        text = str(value or "").strip()
                        text = re.sub(r"}\s*{", "\n", text)
                        raw_items = re.split(r"\r?\n|(?<=\.)\s+(?=\{)|\s*;\s*", text)
                    items = []
                    for raw in raw_items:
                        item = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", str(raw or "")).strip(" {}[]\t\r\n")
                        item = re.sub(r"\s+", " ", item).strip()
                        if item and item.lower() not in {x.lower() for x in items}:
                            items.append(item)
                    return items

                def numbered(value):
                    return "\n".join(f"{idx}. {item}" for idx, item in enumerate(as_items(value), 1))

                def evidence(value, prefix):
                    return "\n".join(f"[{prefix}{idx}] {item}" for idx, item in enumerate(as_items(value), 1))

                if res.get("case_name"):
                    self.v_name.set(res["case_name"])
                if res.get("jurisdiction"):
                    self.v_jur.set(res["jurisdiction"])
                formatted = [
                    (self.t_bg, str(res.get("background") or "").strip()),
                    (self.t_pos_args, numbered(res.get("pos_args"))),
                    (self.t_pos_ev, evidence(res.get("pos_ev"), "P")),
                    (self.t_neg_args, numbered(res.get("neg_args"))),
                    (self.t_neg_ev, evidence(res.get("neg_ev"), "D")),
                ]
                for widget, value in formatted:
                    if value:
                        widget.delete("1.0", tk.END)
                        widget.insert("1.0", value)
                self.drop_label.config(
                    text=f"✅ Case parsed: {res.get('case_name', 'Unknown')}  |  Click to import again",
                    fg=self.C["green"])

            self.root.after(0, fill_fields)

        threading.Thread(target=do_parse, daemon=True).start()

    def _is_tactic_combo_text(self, text):
        text = str(text or "")
        return "## Nido 战术组合包" in text and "## 给正方使用的战术" in text and "## 给反方使用的战术" in text

    def _extract_tactic_combo_section(self, text, heading, next_headings):
        start = text.find(heading)
        if start < 0:
            return ""
        start += len(heading)
        ends = [text.find(h, start) for h in next_headings if text.find(h, start) >= 0]
        end = min(ends) if ends else len(text)
        return text[start:end].strip()

    def _append_text_to_widget(self, widget, title, text):
        title = self._clean_system_labels(title)
        text = self._clean_system_labels(text).strip()
        if not text:
            return
        existing = widget.get("1.0", tk.END).strip()
        addition = f"\n\n【{title}】\n{text}"
        widget.delete("1.0", tk.END)
        widget.insert("1.0", (existing + addition).strip() if existing else addition.strip())

    def _build_insert_header(self, parent, label_text, color, target_widget_getter, insert_title):
        row = tk.Frame(parent, bg=self.C["panel"])
        row.pack(fill=tk.X, pady=(0, 2))
        tk.Label(row, text=label_text, bg=self.C["panel"], fg=color).pack(side=tk.LEFT)
        tk.Button(
            row,
            text="+ Insert",
            command=lambda: self._open_manual_insert(target_widget_getter(), insert_title),
            bg="#24324a",
            fg=self.C["gold"],
            activebackground="#2f4264",
            activeforeground=self.C["gold"],
            relief="flat",
            padx=8,
            pady=1,
            cursor="hand2",
            font=("Helvetica", 9, "bold"),
        ).pack(side=tk.RIGHT)
        self.set_help(row, f"Insert manually found {insert_title.lower()} into this field.")
        return row

    def _open_manual_insert(self, target_widget, title):
        win = tk.Toplevel(self.root)
        win.title(f"Insert {title}")
        win.geometry("620x360")
        win.configure(bg=self.C["panel"])
        tk.Label(
            win,
            text=f"Insert {title}",
            bg=self.C["panel"],
            fg=self.C["gold"],
            font=("Helvetica", 13, "bold"),
        ).pack(anchor="w", padx=12, pady=(12, 4))
        box = scrolledtext.ScrolledText(
            win,
            height=10,
            bg=self.C["entry"],
            fg=self.C["text"],
            insertbackground=self.C["text"],
            relief="flat",
            wrap=tk.WORD,
        )
        self._bind_local_scroll(box)
        box.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)
        controls = tk.Frame(win, bg=self.C["panel"])
        controls.pack(fill=tk.X, padx=12, pady=(4, 12))

        def apply_insert():
            value = box.get("1.0", tk.END).strip()
            if not value:
                messagebox.showwarning("Nothing to insert", "Please enter an argument or evidence item.", parent=win)
                return
            existing = target_widget.get("1.0", tk.END).strip()
            target_widget.delete("1.0", tk.END)
            target_widget.insert("1.0", (existing + "\n" + value).strip() if existing else value)
            target_widget.see(tk.END)
            win.destroy()

        tk.Button(controls, text="Insert", command=apply_insert, bg="#1a4a42", fg="white", relief="flat", padx=16, pady=6).pack(side=tk.RIGHT)
        tk.Button(controls, text="Cancel", command=win.destroy, bg="#333", fg="white", relief="flat", padx=16, pady=6).pack(side=tk.RIGHT, padx=(0, 8))

    def _apply_tactic_combo_text(self, text):
        positive_text = self._extract_tactic_combo_section(
            text,
            "## 给正方使用的战术",
            ["## 给反方使用的战术", "## 原始选中弱点", "## 使用方式"],
        )
        negative_text = self._extract_tactic_combo_section(
            text,
            "## 给反方使用的战术",
            ["## 原始选中弱点", "## 使用方式"],
        )
        positive_text = positive_text.replace("暂无。", "").strip()
        negative_text = negative_text.replace("暂无。", "").strip()
        self._append_text_to_widget(self.t_pos_args, "Tactic package for attacking negative-side weaknesses", positive_text)
        self._append_text_to_widget(self.t_neg_args, "Tactic package for attacking positive-side weaknesses", negative_text)

    def _build_side_panels(self):
        outer = tk.Frame(self.sf, bg=self.C["bg"])
        outer.pack(fill=tk.X, padx=10, pady=8)
        self.set_help(outer, "Side frames: left is the positive side, right is the negative side. Arguments and evidence define what each side protects or attacks.")

        # 正方
        lf = tk.Frame(outer, bg=self.C["bg"])
        lf.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        tk.Label(lf, text="⚖ Positive Frame - Arguments and Evidence", bg="#0a3d1f", fg="#56d364", font=("Helvetica", 13, "bold")).pack(fill=tk.X)
        lb = tk.Frame(lf, bg=self.C["panel"], padx=10, pady=10)
        lb.pack(fill=tk.BOTH, expand=True)
        self._build_insert_header(lb, "Arguments:", "#56d364", lambda: self.t_pos_args, "Positive Argument")
        self.t_pos_args = scrolledtext.ScrolledText(lb, height=6, bg=self.C["entry"], fg=self.C["text"], relief="flat")
        self._bind_local_scroll(self.t_pos_args)
        self.t_pos_args.pack(fill=tk.X, pady=(2, 8))
        self._build_insert_header(lb, "Evidence (optional labels: [P1], [P2]):", "#56d364", lambda: self.t_pos_ev, "Positive Evidence")
        self.t_pos_ev = scrolledtext.ScrolledText(lb, height=4, bg=self.C["entry"], fg=self.C["text"], relief="flat")
        self._bind_local_scroll(self.t_pos_ev)
        self.t_pos_ev.pack(fill=tk.X)

        swap_mid = tk.Frame(outer, bg=self.C["bg"], width=34)
        swap_mid.pack(side=tk.LEFT, fill=tk.Y, padx=2)
        swap_mid.pack_propagate(False)
        tk.Frame(swap_mid, bg=self.C["bg"]).pack(fill=tk.BOTH, expand=True)
        tk.Button(
            swap_mid,
            text="↔\nS\nW\nA\nP",
            command=self._swap_sides,
            bg="#24324a",
            fg=self.C["gold"],
            activebackground="#2f4264",
            activeforeground=self.C["gold"],
            relief="flat",
            padx=2,
            pady=6,
            font=("Helvetica", 9, "bold"),
            cursor="hand2",
        ).pack(fill=tk.X, pady=8)
        tk.Frame(swap_mid, bg=self.C["bg"]).pack(fill=tk.BOTH, expand=True)

        # 反方
        rf = tk.Frame(outer, bg=self.C["bg"])
        rf.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        tk.Label(rf, text="⚖ Negative Frame - Arguments and Evidence", bg="#3d1a1a", fg="#f85149", font=("Helvetica", 13, "bold")).pack(fill=tk.X)
        rb = tk.Frame(rf, bg=self.C["panel"], padx=10, pady=10)
        rb.pack(fill=tk.BOTH, expand=True)
        self._build_insert_header(rb, "Arguments:", "#f85149", lambda: self.t_neg_args, "Negative Argument")
        self.t_neg_args = scrolledtext.ScrolledText(rb, height=6, bg=self.C["entry"], fg=self.C["text"], relief="flat")
        self._bind_local_scroll(self.t_neg_args)
        self.t_neg_args.pack(fill=tk.X, pady=(2, 8))
        self._build_insert_header(rb, "Evidence (optional labels: [D1], [D2]):", "#f85149", lambda: self.t_neg_ev, "Negative Evidence")
        self.t_neg_ev = scrolledtext.ScrolledText(rb, height=4, bg=self.C["entry"], fg=self.C["text"], relief="flat")
        self._bind_local_scroll(self.t_neg_ev)
        self.t_neg_ev.pack(fill=tk.X)

    def _build_controls(self):
        p = tk.Frame(self.sf, bg=self.C["panel"], padx=10, pady=8)
        p.pack(fill=tk.X, padx=10, pady=5)
        self.set_help(p, "Main controls: start online opposition, open the evidence assistant, swap sides, export, save/load, and run blind tests.")

        tk.Button(p, text="▶ Start Opposition", command=self._choose_main_opposition_mode, bg=self.C["accent"], fg="white", relief="flat", padx=20, pady=8, font=("Helvetica", 12, "bold")).pack(side=tk.LEFT)
        self.stop_btn = tk.Button(p, text="Stop", command=self._stop, bg=self.C["red"], fg="white", relief="flat", padx=14, pady=8, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=8)
        tk.Button(p, text="Evidence Assistant", command=self._open_evidence_assistant, bg="#3d1a5a", fg="white", relief="flat", padx=14, pady=8).pack(side=tk.LEFT, padx=8)
        tk.Button(p, text="Single-Point AI Review", command=self._open_single_point_ai_review, bg="#5b2c83", fg="white", relief="flat", padx=14, pady=8).pack(side=tk.LEFT, padx=8)
        tk.Button(p, text="📄 Export", command=self._export_report, bg="#1a3a1a", fg="white", relief="flat", padx=14, pady=8).pack(side=tk.LEFT)
        tk.Button(p, text="💾 Save", command=self._save_case, bg="#1a3a1a", fg="white", relief="flat", padx=14, pady=8).pack(side=tk.LEFT)
        tk.Button(p, text="📂 Load", command=self._load_case, bg="#1a3a1a", fg="white", relief="flat", padx=14, pady=8).pack(side=tk.LEFT)
        tk.Button(p, text="🔬 Blind Test", command=self._run_blind, bg="#2d1b69", fg="white", relief="flat", padx=14, pady=8).pack(side=tk.LEFT, padx=8)

        self.v_anonymize = tk.BooleanVar(value=False)
        self._anon_reminder_shown = False  # 每次启动只弹一次脱敏提醒
        tk.Checkbutton(p, text="Data Redaction", variable=self.v_anonymize,
            bg=self.C["panel"], fg=self.C["teal"], selectcolor="#3e1a1a",
            activeforeground=self.C["teal"], activebackground="#3e1a1a",
            font=("Helvetica", 12, "bold"),
            cursor="hand2").pack(side=tk.LEFT, padx=8)
        self.weakness_status_var = tk.StringVar(value="Weakness scan ready")
        self.weakness_scan_btn = tk.Button(
            p, text="AI Weakness Scan", command=self._open_online_weakness_scan,
            bg="#14635b", fg="white", relief="flat", padx=14, pady=8,
        )
        self.weakness_scan_btn.pack(side=tk.LEFT, padx=(8, 6))
        self.weakness_status_label = tk.Label(
            p, textvariable=self.weakness_status_var, bg=self.C["panel"], fg=self.C["teal"],
            anchor="w", width=28,
        )
        self.weakness_status_label.pack(side=tk.LEFT, padx=(6, 4))
        self.progress = ttk.Progressbar(p, mode="indeterminate", length=150)

    def _open_online_weakness_scan(self):
        from Nido_Advanced_18D_Review_EN import show_scan_mode_dialog

        show_scan_mode_dialog(
            self.root,
            self._open_standard_online_weakness_scan,
            self._open_advanced_18d_review,
            self._open_contextual_advanced_18d_review,
        )

    def _open_contextual_advanced_18d_review(self):
        self._open_advanced_18d_review(contextual_positions=True)

    def _open_advanced_18d_review(self, contextual_positions=False):
        from Nido_Advanced_18D_Review_EN import open_advanced_review

        full_case = self.t_bg.get("1.0", tk.END).strip()
        if contextual_positions:
            case_text = (
                f"ORIGINAL COMPLETE CASE:\n{full_case}\n\n"
                f"CURRENT POSITIVE-SIDE ARGUMENTS:\n{self._gt(self.t_pos_args)}\n\n"
                f"CURRENT POSITIVE-SIDE EVIDENCE:\n{self._gt(self.t_pos_ev)}\n\n"
                f"CURRENT NEGATIVE-SIDE ARGUMENTS:\n{self._gt(self.t_neg_args)}\n\n"
                f"CURRENT NEGATIVE-SIDE EVIDENCE:\n{self._gt(self.t_neg_ev)}"
            ).strip()
        else:
            case_text = full_case
        privacy_label = "Original matter mode is active. Confirm that external processing is authorized."
        if self.v_anonymize.get() and case_text:
            anonymizer = PIIAnonymizer()
            case_text = anonymizer.anonymize(case_text)
            privacy_label = (
                "Data Redaction is enabled; the prepared redacted complete matter and side frames will be used for all 18 calls."
                if contextual_positions
                else "Data Redaction is enabled; the prepared redacted matter will be used for all 18 calls."
            )
        elif contextual_positions:
            privacy_label = (
                "Contextual mode is active. The original complete matter and both sides' current argument and evidence "
                "frames will be used for all 18 calls after explicit authorization."
            )
        routes = []
        for row in self.providers:
            try:
                if row["verified"].get() and row["key"].get().strip():
                    routes.append({"name": row["name"].get().strip() or "custom", "key": row["key"].get().strip()})
            except Exception:
                continue

        def add_advanced_weakness(item, affected_side):
            target = self.t_neg_args if affected_side == "positive" else self.t_pos_args
            target_name = "Negative arguments" if affected_side == "positive" else "Positive arguments"
            questions = "\n".join(f"- {value}" for value in (item.get("questions_for_lawyer") or []))
            cures = "\n".join(f"- {value}" for value in (item.get("response_or_cure") or []))
            text = "\n\n".join(part for part in [
                str(item.get("conclusion") or "Weakness identified").strip(),
                f"Why this matters\n{str(item.get('why_material') or '').strip()}",
                f"Supporting case facts\n{str(item.get('supporting_case_facts') or '').strip()}",
                f"What the material proves\n{str(item.get('what_the_material_proves') or '').strip()}",
                f"What it does not prove\n{str(item.get('what_it_does_not_prove') or '').strip()}",
                f"Questions for counsel\n{questions}",
                f"Response or cure\n{cures}",
                f"Review dimension\n{str(item.get('dimension') or '').strip()}",
                f"Source model\n{str(item.get('provider') or '').strip()}",
            ] if part.split("\n", 1)[-1].strip())
            existing = re.sub(r"\s+", " ", self._gt(target)).strip().lower()
            incoming = re.sub(r"\s+", " ", text).strip().lower()
            if incoming and incoming in existing:
                messagebox.showinfo(
                    "Weakness Already Added",
                    f"This entire weakness already exists in {target_name} and was not added again.",
                    parent=self.root,
                )
                return False
            conclusion = str(item.get("conclusion") or "Weakness identified").strip()
            if not messagebox.askyesno(
                "Add Entire Advanced Weakness",
                f"This is a weakness of the {affected_side} side.\n\n"
                f"Add the entire weakness to {target_name}?\n\n{conclusion}",
                parent=self.root,
            ):
                return False
            self._append_text_to_widget(target, "Advanced 18-Dimension Weakness", text)
            return True

        open_advanced_review(
            self.root,
            case_text,
            routes,
            self.v_name.get().strip() or "Current Matter",
            privacy_label,
            add_advanced_weakness,
            review_mode="contextual_positions" if contextual_positions else "whole_matter",
        )

    def _open_standard_online_weakness_scan(self):
        win = tk.Toplevel(self.root)
        win.title("Online AI Weakness Scan")
        win.geometry("1180x820")
        win.configure(bg=self.C["bg"])
        win.withdraw()

        header = tk.Frame(win, bg=self.C["bg"], padx=14, pady=10)
        header.pack(fill=tk.X)
        tk.Label(header, text="AI Weakness Scan", bg=self.C["bg"], fg=self.C["gold"], font=("Helvetica", 17, "bold")).pack(side=tk.LEFT)
        status_var = tk.StringVar(value="Ready - the full matter and both side frames will be reviewed")
        tk.Label(header, textvariable=status_var, bg=self.C["bg"], fg=self.C["muted"]).pack(side=tk.LEFT, padx=14)

        columns = tk.PanedWindow(win, orient=tk.HORIZONTAL, bg=self.C["bg"], sashwidth=6)
        columns.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 10))
        pos_frame = tk.Frame(columns, bg=self.C["panel"], padx=10, pady=10)
        neg_frame = tk.Frame(columns, bg=self.C["panel"], padx=10, pady=10)
        columns.add(pos_frame, minsize=520)
        columns.add(neg_frame, minsize=520)
        tk.Label(pos_frame, text="Positive Side Weaknesses", bg="#0d4f57", fg="#42d4ca", font=("Helvetica", 13, "bold"), pady=8).pack(fill=tk.X)
        tk.Label(neg_frame, text="Negative Side Weaknesses", bg="#6b233e", fg="#ff9dbb", font=("Helvetica", 13, "bold"), pady=8).pack(fill=tk.X)
        def make_card_column(parent):
            shell = tk.Frame(parent, bg=self.C["entry"])
            shell.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
            canvas = tk.Canvas(shell, bg=self.C["entry"], highlightthickness=0)
            scrollbar = ttk.Scrollbar(shell, orient=tk.VERTICAL, command=canvas.yview)
            inner = tk.Frame(canvas, bg=self.C["entry"])
            window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))
            canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))
            inner._scroll_canvas = canvas
            return inner

        pos_cards = make_card_column(pos_frame)
        neg_cards = make_card_column(neg_frame)
        result_store = {"positive": [], "negative": []}

        actions = tk.Frame(win, bg=self.C["panel"], padx=14, pady=10)
        actions.pack(fill=tk.X)
        run_btn = tk.Button(actions, text="Run Full-Matter Weakness Scan", bg=self.C["accent"], fg="white", relief="flat", padx=18, pady=8)
        run_btn.pack(side=tk.LEFT)
        scan_cancelled = {"value": False}
        scan_progress = ttk.Progressbar(actions, mode="indeterminate", length=170)
        stop_scan_btn = tk.Button(
            actions, text="Stop Scan", bg="#b8324b", fg="white", relief="flat",
            padx=14, pady=8, state=tk.DISABLED,
        )
        stop_scan_btn.pack(side=tk.LEFT, padx=(0, 8))
        action_status_var = tk.StringVar(value="Ready")
        tk.Label(
            actions, textvariable=action_status_var, bg=self.C["panel"], fg=self.C["teal"],
            font=("Helvetica", 11, "bold"), anchor="w",
        ).pack(side=tk.LEFT, padx=(8, 0))

        def stop_scan():
            scan_cancelled["value"] = True
            stop_scan_btn.config(state=tk.DISABLED)
            status_var.set("Stopping after the current model call...")
            action_status_var.set("Stopping...")
            self.weakness_status_var.set("Stopping after current call...")
            self.weakness_scan_btn.config(state=tk.DISABLED)

        stop_scan_btn.config(command=stop_scan)

        drag_state = {"item": None, "card": None, "side": None, "ghost": None, "external": False}

        def weakness_text(item):
            return (
                f"{item.get('conclusion', '')}\n\n"
                f"Reason: {item.get('reason', '')}\n"
                f"Dimension: {self._dim_en(item.get('dimension', ''))}\n"
                f"Source model: {item.get('provider', '')}"
            ).strip()

        def confirm_dragged_weakness(item, side):
            target = self.t_neg_args if side == "positive" else self.t_pos_args
            target_name = "Negative arguments" if side == "positive" else "Positive arguments"
            text = weakness_text(item)
            normalized_existing = re.sub(r"\s+", " ", self._gt(target)).strip().lower()
            normalized_incoming = re.sub(r"\s+", " ", text).strip().lower()
            if normalized_incoming and normalized_incoming in normalized_existing:
                messagebox.showinfo(
                    "Weakness Already Added",
                    f"This weakness card already exists in {target_name} and was not added again.",
                    parent=self.root,
                )
                status_var.set("Duplicate weakness was not added")
                return False
            conclusion = str(item.get("conclusion") or "Weakness identified").strip()
            confirmed = messagebox.askyesno(
                "Add Entire Weakness",
                f"Add the entire weakness card to {target_name}?\n\n{conclusion}\n\n"
                "The conclusion, reason, dimension, and source model will be added.",
                parent=self.root,
            )
            if not confirmed:
                status_var.set("Weakness drop cancelled")
                return False
            self._append_text_to_widget(target, "Entire AI Weakness Card", text)
            status_var.set(f"Entire weakness card added to {target_name}")
            return True

        def open_weakness_detail(item, side):
            detail = tk.Toplevel(win)
            detail.title("Positive-Side Weakness" if side == "positive" else "Negative-Side Weakness")
            detail.geometry("900x650")
            detail.configure(bg=self.C["bg"])
            accent = "#42d4ca" if side == "positive" else "#ff9dbb"
            tk.Label(
                detail,
                text="Positive-Side Weakness" if side == "positive" else "Negative-Side Weakness",
                bg=self.C["panel"], fg=accent, anchor="w", padx=18, pady=12,
                font=("Helvetica", 16, "bold"),
            ).pack(fill=tk.X)
            body = scrolledtext.ScrolledText(
                detail, bg=self.C["entry"], fg=self.C["text"], relief="flat",
                wrap=tk.WORD, padx=18, pady=16, font=("Helvetica", 12),
            )
            body.pack(fill=tk.BOTH, expand=True, padx=14, pady=(12, 8))
            body.tag_configure("heading", foreground=accent, font=("Helvetica", 13, "bold"), spacing1=8, spacing3=4)
            def add_section(title, value):
                if isinstance(value, list):
                    value = "\n".join(f"- {entry}" for entry in value if str(entry).strip())
                value = str(value or "").strip()
                if not value:
                    return
                body.insert(tk.END, f"{title}\n", "heading")
                body.insert(tk.END, f"{value}\n\n")

            conclusion = item.get("conclusion", "")
            reason = item.get("reason", "")
            add_section("Weakness", conclusion)
            diagnostic_parts = []
            for value in (
                item.get("full_analysis"), item.get("analysis"),
                item.get("plain_explanation"), item.get("core_problem"), reason,
                item.get("relevant_facts"), item.get("what_it_proves"),
                item.get("what_it_does_not_prove"), item.get("source_explanation"),
            ):
                value = str(value or "").strip()
                if value and value not in diagnostic_parts and value != conclusion:
                    diagnostic_parts.append(value)
            add_section("Analysis", "\n\n".join(diagnostic_parts))
            add_section("Review Dimension", self._dim_en(item.get("dimension", "")))
            add_section("Source Model", item.get("provider", ""))
            body.config(state=tk.DISABLED)
            tk.Button(
                detail, text="Close", command=detail.destroy, bg="#334155", fg="white",
                relief="flat", padx=22, pady=8,
            ).pack(side=tk.RIGHT, padx=14, pady=(0, 12))
            detail.transient(win)
            detail.lift()
            detail.focus_force()

        def hide_drag_ghost():
            ghost = drag_state.get("ghost")
            drag_state["ghost"] = None
            if ghost:
                try:
                    ghost.destroy()
                except tk.TclError:
                    pass

        def show_drag_ghost(item):
            hide_drag_ghost()
            ghost = tk.Toplevel(self.root)
            ghost.overrideredirect(True)
            ghost.attributes("-topmost", True)
            ghost.configure(bg="#1f6feb")
            conclusion = str(item.get("conclusion") or "Weakness identified").strip()
            if len(conclusion) > 90:
                conclusion = conclusion[:87].rstrip() + "..."
            tk.Label(
                ghost, text=f"Drop weakness: {conclusion}", bg="#1f6feb", fg="white",
                font=("Helvetica", 9, "bold"), padx=10, pady=5,
            ).pack()
            drag_state["ghost"] = ghost

        def move_drag_ghost():
            ghost = drag_state.get("ghost")
            if ghost:
                ghost.geometry(f"+{self.root.winfo_pointerx() + 14}+{self.root.winfo_pointery() + 12}")

        def reorder_card(card, parent):
            pointer_y = self.root.winfo_pointery()
            siblings = [child for child in parent.winfo_children() if hasattr(child, "_weakness_item")]
            target = None
            for sibling in siblings:
                if sibling is card:
                    continue
                if pointer_y < sibling.winfo_rooty() + sibling.winfo_height() / 2:
                    target = sibling
                    break
            if target is not None:
                card.pack_configure(before=target)
            elif siblings and siblings[-1] is not card:
                card.pack_configure(after=siblings[-1])
            parent.update_idletasks()

        def finish_card_drag():
            item, card, side = drag_state.get("item"), drag_state.get("card"), drag_state.get("side")
            external = drag_state.get("external", False)
            hide_drag_ghost()
            if card:
                card.pack_configure(fill=tk.X, padx=5, pady=5)
                card.configure(highlightthickness=1, highlightbackground="#334155")
            drag_state.update({"item": None, "card": None, "side": None, "external": False})
            if not item or not external:
                if side in result_store and card is not None:
                    parent = card.master
                    result_store[side] = [
                        child._weakness_item for child in parent.winfo_children()
                        if hasattr(child, "_weakness_item")
                    ]
                status_var.set("Weakness card order updated")
                return
            try:
                px, py = self.root.winfo_pointerx(), self.root.winfo_pointery()
                widget = self.root.winfo_containing(px, py)
                if widget is not None and widget.winfo_toplevel() == self.root:
                    confirm_dragged_weakness(item, side)
                else:
                    status_var.set("Drop the card anywhere inside the main case window")
            except tk.TclError:
                status_var.set("Weakness drop cancelled")

        def render_cards(container, items, side):
            for child in container.winfo_children():
                child.destroy()
            accent = "#42d4ca" if side == "positive" else "#ff9dbb"
            for item in items:
                card = tk.Frame(container, bg="#111827", highlightthickness=1, highlightbackground="#334155", padx=12, pady=10)
                card.pack(fill=tk.X, padx=5, pady=5)
                top = tk.Frame(card, bg="#111827")
                top.pack(fill=tk.X)
                card._weakness_item = item
                conclusion = str(item.get("conclusion") or "Weakness identified").strip()
                reason = str(item.get("reason") or "").strip()
                conclusion_label = tk.Label(top, text=conclusion, bg="#111827", fg=accent, wraplength=410, justify=tk.LEFT, anchor="w", font=("Helvetica", 11, "bold"))
                conclusion_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
                drag_handle = tk.Label(top, text="DRAG", bg="#1f6feb", fg="white", font=("Helvetica", 8, "bold"), padx=10, pady=5, cursor="fleur")
                drag_handle.pack(side=tk.RIGHT, padx=(8, 0))
                if reason:
                    reason_label = tk.Label(card, text=reason, bg="#111827", fg="#dbe7f5", wraplength=480, justify=tk.LEFT, anchor="w")
                    reason_label.pack(fill=tk.X, pady=(7, 4))
                else:
                    reason_label = None
                meta_label = tk.Label(card, text=f"{self._dim_en(item.get('dimension', ''))}  |  {item.get('provider', '')}", bg="#111827", fg=self.C["muted"], anchor="w")
                meta_label.pack(fill=tk.X)
                for detail_widget in (card, top, conclusion_label, reason_label, meta_label):
                    if detail_widget is not None:
                        detail_widget.bind("<Double-Button-1>", lambda _e, record=item, record_side=side: open_weakness_detail(record, record_side))

                def drag_press(_event, record=item, widget=card, record_side=side, handle=drag_handle):
                    drag_state.update({"item": record, "card": widget, "side": record_side, "external": False})
                    widget.pack_configure(fill=tk.X, padx=55, pady=2)
                    widget.configure(highlightthickness=2, highlightbackground="#22c55e")
                    handle.configure(text="MOVING", bg="#22c55e", fg="#052e16")
                    status_var.set("Moving card - drag outside this list to add it to the main case")
                    return "break"

                def drag_motion(_event, widget=card, parent=container, handle=drag_handle):
                    canvas = getattr(parent, "_scroll_canvas", None)
                    if canvas is None:
                        return "break"
                    px, py = self.root.winfo_pointerx(), self.root.winfo_pointery()
                    left, top = canvas.winfo_rootx(), canvas.winfo_rooty()
                    right, bottom = left + canvas.winfo_width(), top + canvas.winfo_height()
                    outside = px < left - 12 or px > right + 12 or py < top - 12 or py > bottom + 12
                    if outside:
                        if not drag_state.get("external"):
                            drag_state["external"] = True
                            widget.pack_configure(fill=tk.X, padx=16, pady=10)
                            handle.configure(text="DRAGGING", bg="#22c55e", fg="#052e16")
                            show_drag_ghost(drag_state["item"])
                        move_drag_ghost()
                    else:
                        if py < top + 34:
                            canvas.yview_scroll(-1, "units")
                        elif py > bottom - 34:
                            canvas.yview_scroll(1, "units")
                        reorder_card(widget, parent)
                    return "break"

                def drag_release(_event, handle=drag_handle):
                    handle.configure(text="DRAG", bg="#1f6feb", fg="white")
                    finish_card_drag()
                    return "break"

                drag_handle.bind("<ButtonPress-1>", drag_press)
                drag_handle.bind("<B1-Motion>", drag_motion)
                drag_handle.bind("<ButtonRelease-1>", drag_release)
            if not items:
                tk.Label(container, text="No material weaknesses returned.", bg=self.C["entry"], fg=self.C["muted"], pady=30).pack(fill=tk.X)

        def start_scan():
            win.withdraw()
            rows = [r for r in self.providers if r["key"].get().strip() and r.get("verified") and r["verified"].get()]
            if not rows:
                messagebox.showerror("No Verified Provider", "Verify at least one model provider first.", parent=self.root)
                win.destroy()
                return
            if not self._gt(self.t_bg):
                messagebox.showwarning("Missing Matter", "Enter or import the matter before scanning.", parent=self.root)
                win.destroy()
                return
            use_redaction = self.v_anonymize.get()
            if not use_redaction:
                use_redaction = self._ask_enable_data_redaction()
                if use_redaction:
                    self.v_anonymize.set(True)
            dims = [DIMENSION_LABELS_EN.get(d, d) for d, _desc in ALL_DIMENSIONS if self.dim_vars.get(d, tk.BooleanVar()).get()]
            context = (
                f"CASE NAME: {self._gt(self.v_name)}\nJURISDICTION: {self._gt(self.v_jur)}\n\n"
                f"FULL CASE:\n{self._gt(self.t_bg)}\n\n"
                f"POSITIVE ARGUMENTS:\n{self._gt(self.t_pos_args)}\n\nPOSITIVE EVIDENCE:\n{self._gt(self.t_pos_ev)}\n\n"
                f"NEGATIVE ARGUMENTS:\n{self._gt(self.t_neg_args)}\n\nNEGATIVE EVIDENCE:\n{self._gt(self.t_neg_ev)}"
            )
            anonymizer = PIIAnonymizer() if use_redaction else None
            send_context = anonymizer.anonymize(context) if anonymizer else context
            def build_dimension_prompt(batch):
                return f'''Read the complete legal matter and both side frames directly before analysing it. Do not use sentence-by-sentence extraction, pre-built templates, or internal software labels.

Act as one independent legal weakness reviewer for each listed dimension. Diagnose the matter only from that dimension's professional perspective. For every dimension, identify zero or more genuinely material weaknesses across the whole matter. Return no finding when that dimension reveals no useful weakness. Do not force equal counts.

Every value must be English. Each finding must state the weakness and explain why it exists by reference to the supplied case facts. Diagnose only. Do not provide lawyer questions, attack scripts, strategy, recommendations, cures, response language, preparation steps, or everyday examples. Do not invent facts, dates, amounts, documents, clauses, approvals, authorities, or quotations.

DIMENSIONS FOR THIS BATCH:
{json.dumps(batch, ensure_ascii=False)}

COMPLETE MATTER AND SIDE FRAMES:
{send_context}

Return strict JSON only:
{{
  "dimensions": [
    {{
      "dimension": "one listed English dimension",
      "findings": [
        {{
          "conclusion": "short plain-language surface-card conclusion",
          "analysis": "natural connected explanation of the weakness, its factual basis, significance, and limits from this dimension's perspective",
          "relevant_facts": "specific supplied facts",
          "affected_side": "positive, negative, or both",
          "confidence": "high, medium, or low"
        }}
      ]
    }}
  ]
}}'''
            run_btn.config(state=tk.DISABLED)
            stop_scan_btn.config(state=tk.NORMAL)
            scan_cancelled["value"] = False
            action_status_var.set("Scanning...")
            status_var.set(f"Preparing one case across {len(dims)} dimensions...")
            self.weakness_status_var.set(f"Preparing one case / {len(dims)} dimensions...")
            self.weakness_scan_btn.config(
                text="Analysis Running", command=stop_scan, bg="#374151", state=tk.DISABLED,
            )
            result_store["positive"] = []
            result_store["negative"] = []
            for child in pos_cards.winfo_children():
                child.destroy()
            for child in neg_cards.winfo_children():
                child.destroy()
            self._set_analysis_ui_locked(True)

            def worker():
                positive_items, negative_items = [], []
                for idx, row in enumerate(rows):
                    if scan_cancelled["value"]:
                        break
                    provider_name = row["name"].get()
                    client = LLMClient(provider_name, row["key"].get().strip(), personality_idx=idx)
                    pending_batches = [list(dims)]
                    call_no = 0
                    while pending_batches and not scan_cancelled["value"]:
                        batch = pending_batches.pop(0)
                        call_no += 1
                        self.root.after(
                            0,
                            lambda name=provider_name, count=len(batch), number=call_no: (
                                status_var.set(f"{name}: reviewing {count} dimensions, call {number}..."),
                                self.weakness_status_var.set(f"{name}: {count} dimensions, call {number}..."),
                            ),
                        )
                        try:
                            data = client.chat_json(build_dimension_prompt(batch), temperature=0.3, max_tokens=6500)
                            if not isinstance(data, dict) or data.get("_error"):
                                raise RuntimeError("invalid structured response")
                            dimension_results = [entry for entry in (data.get("dimensions") or []) if isinstance(entry, dict)]
                            if not dimension_results:
                                raise RuntimeError("no dimension results returned")
                        except Exception as exc:
                            error_text = str(exc).lower()
                            rate_limited = "429" in error_text or "too many requests" in error_text or "resource_exhausted" in error_text
                            if len(batch) > 1 and not rate_limited:
                                midpoint = (len(batch) + 1) // 2
                                pending_batches = [batch[:midpoint], batch[midpoint:]] + pending_batches
                                self.root.after(0, lambda count=len(batch): status_var.set(f"Output capacity reached; splitting {count} dimensions..."))
                            if rate_limited:
                                break
                            continue
                        if anonymizer:
                            data = json.loads(anonymizer.deanonymize(json.dumps(data, ensure_ascii=False)))
                            dimension_results = [entry for entry in (data.get("dimensions") or []) if isinstance(entry, dict)]
                        for dimension_result in dimension_results:
                            dimension = self._dim_en(dimension_result.get("dimension", "Whole-Case Review"))
                            for finding in dimension_result.get("findings") or []:
                                if not isinstance(finding, dict):
                                    continue
                                conclusion = str(finding.get("conclusion") or finding.get("one_sentence_summary") or "").strip()
                                if not conclusion:
                                    continue
                                analysis = str(
                                    finding.get("analysis") or finding.get("full_analysis")
                                    or finding.get("plain_explanation") or finding.get("core_problem")
                                    or finding.get("source_explanation") or ""
                                ).strip()
                                record = dict(finding)
                                record.update({
                                    "conclusion": conclusion,
                                    "analysis": analysis,
                                    "full_analysis": analysis,
                                    "reason": analysis,
                                    "dimension": dimension,
                                    "provider": provider_name,
                                })
                                affected = str(finding.get("affected_side") or "both").strip().lower()
                                if affected not in ("positive", "negative", "both"):
                                    affected = "both"
                                if affected in ("positive", "both"):
                                    positive_items.append(dict(record))
                                if affected in ("negative", "both"):
                                    negative_items.append(dict(record))
                def finish():
                    # Preserve the complete provider output. Remove explicit
                    # no-finding records only from the final visible cards.
                    display_positive_items = [
                        item for item in positive_items
                        if not is_non_material_weakness_display_record(item)
                    ]
                    display_negative_items = [
                        item for item in negative_items
                        if not is_non_material_weakness_display_record(item)
                    ]
                    self._set_analysis_ui_locked(False)
                    result_store["positive"] = display_positive_items
                    result_store["negative"] = display_negative_items
                    render_cards(pos_cards, display_positive_items, "positive")
                    render_cards(neg_cards, display_negative_items, "negative")
                    scan_progress.stop()
                    scan_progress.pack_forget()
                    self.progress.stop()
                    self.progress.pack_forget()
                    run_btn.config(state=tk.NORMAL)
                    stop_scan_btn.config(state=tk.DISABLED)
                    self.weakness_scan_btn.config(
                        text="AI Weakness Scan", command=self._open_online_weakness_scan,
                        bg="#14635b", state=tk.NORMAL,
                    )
                    if scan_cancelled["value"]:
                        action_status_var.set("Stopped")
                        status_var.set(f"Stopped - retained {len(display_positive_items)} positive-side and {len(display_negative_items)} negative-side weaknesses")
                        self.weakness_status_var.set(f"Stopped: {len(display_positive_items)} / {len(display_negative_items)} weaknesses")
                    else:
                        action_status_var.set("Complete")
                        status_var.set(f"Complete - {len(display_positive_items)} positive-side and {len(display_negative_items)} negative-side weaknesses")
                        self.weakness_status_var.set(f"Complete: {len(display_positive_items)} / {len(display_negative_items)} weaknesses")
                    win.deiconify()
                    win.lift()
                    win.focus_force()
                self.root.after(0, finish)
            threading.Thread(target=worker, daemon=True).start()

        run_btn.config(command=start_scan)
        win.after_idle(start_scan)

    def _open_single_point_ai_review(self):
        from Nido_Advanced_Single_Point_2R_EN import show_single_point_mode_dialog

        show_single_point_mode_dialog(
            self.root,
            self._open_standard_single_point_ai_review,
            self._open_advanced_single_point_ai_review,
        )

    def _choose_main_opposition_mode(self):
        from Nido_Advanced_Main_Opposition_2R_EN import show_main_opposition_mode_dialog

        show_main_opposition_mode_dialog(
            self.root,
            self._run,
            self._open_advanced_main_opposition_review,
        )

    def _open_advanced_main_opposition_review(self):
        from Nido_Advanced_Main_Opposition_2R_EN import open_advanced_main_opposition_review

        if not self._validate():
            return

        use_redaction = self.v_anonymize.get()
        if not use_redaction:
            use_redaction = self._ask_enable_data_redaction()
            if use_redaction:
                self.v_anonymize.set(True)

        context = (
            f"CASE NAME: {self._gt(self.v_name)}\nJURISDICTION: {self._gt(self.v_jur)}\n\n"
            f"FULL CASE:\n{self._gt(self.t_bg)}\n\n"
            f"POSITIVE ARGUMENTS:\n{self._gt(self.t_pos_args)}\n\n"
            f"POSITIVE EVIDENCE:\n{self._gt(self.t_pos_ev)}\n\n"
            f"NEGATIVE ARGUMENTS:\n{self._gt(self.t_neg_args)}\n\n"
            f"NEGATIVE EVIDENCE:\n{self._gt(self.t_neg_ev)}"
        )
        privacy_label = "Original matter mode is active. Confirm that external processing is authorized."
        if use_redaction and context.strip():
            context = PIIAnonymizer().anonymize(context)
            privacy_label = "Data Redaction is enabled; the prepared redacted matter will be used for all 36 calls."

        routes = []
        for row in self.providers:
            try:
                if row["verified"].get() and row["key"].get().strip():
                    routes.append({"name": row["name"].get().strip() or "custom",
                                   "key": row["key"].get().strip()})
            except Exception:
                continue

        open_advanced_main_opposition_review(
            self.root,
            context,
            routes,
            self.v_name.get().strip() or "Current Matter",
            privacy_label,
        )

    def _open_advanced_single_point_ai_review(self):
        from Nido_Advanced_Single_Point_2R_EN import open_advanced_single_point_review

        use_redaction = self.v_anonymize.get()
        if not use_redaction:
            use_redaction = self._ask_enable_data_redaction()
            if use_redaction:
                self.v_anonymize.set(True)

        context = (
            f"CASE NAME: {self._gt(self.v_name)}\nJURISDICTION: {self._gt(self.v_jur)}\n\n"
            f"FULL CASE:\n{self._gt(self.t_bg)}\n\n"
            f"POSITIVE ARGUMENTS:\n{self._gt(self.t_pos_args)}\n\n"
            f"POSITIVE EVIDENCE:\n{self._gt(self.t_pos_ev)}\n\n"
            f"NEGATIVE ARGUMENTS:\n{self._gt(self.t_neg_args)}\n\n"
            f"NEGATIVE EVIDENCE:\n{self._gt(self.t_neg_ev)}"
        )
        privacy_label = "Original matter mode is active. Confirm that external processing is authorized."
        if use_redaction and context.strip():
            context = PIIAnonymizer().anonymize(context)
            privacy_label = "Data Redaction is enabled; the prepared redacted matter will be used for all 36 calls."

        routes = []
        for row in self.providers:
            try:
                if row["verified"].get() and row["key"].get().strip():
                    routes.append({"name": row["name"].get().strip() or "custom",
                                   "key": row["key"].get().strip()})
            except Exception:
                continue

        open_advanced_single_point_review(
            self.root,
            context,
            routes,
            self.v_name.get().strip() or "Current Matter",
            privacy_label,
        )

    def _open_standard_single_point_ai_review(self):
        win = tk.Toplevel(self.root)
        win.title("Online Single-Point AI Review")
        win.geometry("1120x780")
        win.configure(bg=self.C["bg"])

        tk.Label(
            win,
            text="Single-Point AI Review",
            bg=self.C["bg"], fg=self.C["gold"],
            font=("Helvetica", 17, "bold"),
        ).pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(
            win,
            text="AI counsel reviews one selected point against the full case, both sides' arguments, and both sides' evidence. Output is reference material for lawyer review.",
            bg=self.C["bg"], fg=self.C["muted"], wraplength=1060, justify=tk.LEFT,
        ).pack(anchor="w", padx=16, pady=(0, 10))

        cfg = tk.Frame(win, bg=self.C["panel"], padx=12, pady=10)
        cfg.pack(fill=tk.X, padx=16)
        tk.Label(cfg, text="Point belongs to:", bg=self.C["panel"], fg=self.C["text"]).pack(side=tk.LEFT)
        side_var = tk.StringVar(value="Positive side")
        ttk.Combobox(cfg, textvariable=side_var, values=["Positive side", "Negative side"], state="readonly", width=18).pack(side=tk.LEFT, padx=(8, 18))
        tk.Label(cfg, text="Selected dimensions and all verified providers will be used.", bg=self.C["panel"], fg=self.C["muted"]).pack(side=tk.LEFT)

        panes = tk.PanedWindow(win, orient=tk.HORIZONTAL, bg=self.C["bg"], sashwidth=6)
        panes.pack(fill=tk.BOTH, expand=True, padx=16, pady=10)
        left = tk.Frame(panes, bg=self.C["panel"], padx=10, pady=10)
        right = tk.Frame(panes, bg=self.C["panel"], padx=10, pady=10)
        panes.add(left, minsize=360)
        panes.add(right, minsize=600)
        tk.Label(left, text="Point, argument, evidence item, or question - weakness cards may be dropped here", bg=self.C["panel"], fg=self.C["text"], font=("Helvetica", 11, "bold")).pack(anchor="w")
        point_text = scrolledtext.ScrolledText(left, bg=self.C["entry"], fg=self.C["text"], wrap=tk.WORD, font=("Helvetica", 11), height=22)
        self._bind_local_scroll(point_text)
        point_text.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        tk.Label(right, text="AI attack, defence, and counter-response", bg=self.C["panel"], fg=self.C["text"], font=("Helvetica", 11, "bold")).pack(anchor="w")
        result_text = scrolledtext.ScrolledText(right, bg=self.C["entry"], fg=self.C["text"], wrap=tk.WORD, font=("Helvetica", 11))
        self._bind_local_scroll(result_text)
        result_text.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

        actions = tk.Frame(win, bg=self.C["panel"], padx=16, pady=10)
        actions.pack(fill=tk.X)
        run_btn = tk.Button(actions, text="Run AI Single-Point Review", bg=self.C["accent"], fg="white", relief="flat", padx=18, pady=8)
        run_btn.pack(side=tk.LEFT)
        status_var = tk.StringVar(value="Ready")
        tk.Label(actions, textvariable=status_var, bg=self.C["panel"], fg=self.C["teal"]).pack(side=tk.LEFT, padx=14)
        tk.Button(actions, text="Copy Result", command=lambda: (self.root.clipboard_clear(), self.root.clipboard_append(result_text.get("1.0", tk.END).strip())), bg="#334155", fg="white", relief="flat", padx=14, pady=8).pack(side=tk.RIGHT)

        def accept_weakness_drop(item, affected_side):
            if not isinstance(item, dict) or str(run_btn.cget("state")) == str(tk.DISABLED):
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
            existing = point_text.get("1.0", tk.END).strip()
            if dropped_text.lower() in existing.lower():
                win.lift()
                point_text.focus_set()
                return False
            side_var.set("Positive side" if str(affected_side).lower() == "positive" else "Negative side")
            point_text.insert(tk.END if existing else "1.0", ("\n\n" if existing else "") + dropped_text)
            point_text.see(tk.END)
            status_var.set("Weakness card added - ready for single-point review")
            win.lift()
            point_text.focus_set()
            return True

        drop_targets = getattr(self.root, "_nido_weakness_drop_targets", None)
        if drop_targets is None:
            drop_targets = []
            self.root._nido_weakness_drop_targets = drop_targets
        drop_target_record = {"window": win, "accept": accept_weakness_drop}
        drop_targets.append(drop_target_record)

        def close_single_point_window():
            targets = getattr(self.root, "_nido_weakness_drop_targets", [])
            if drop_target_record in targets:
                targets.remove(drop_target_record)
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", close_single_point_window)

        def format_result(provider_name, data):
            if not isinstance(data, dict) or data.get("_error"):
                return f"# {provider_name}\n\nModel failed: {data.get('_error', 'invalid response') if isinstance(data, dict) else 'invalid response'}"
            lines = [f"# {provider_name}", ""]
            fields = [
                ("Point in plain language", "point_summary"),
                ("How the opposing side can attack it", "attack_analysis"),
                ("Main-case materials that support the point", "supporting_materials"),
                ("Main-case materials that weaken the point", "weakening_materials"),
                ("Questions counsel can ask", "attack_questions"),
                ("How the point-owning side can respond", "defence_response"),
                ("Likely counter-response and how to answer it", "counter_response"),
                ("Evidence or facts still needed", "missing_materials"),
                ("Lawyer review note", "lawyer_note"),
            ]
            for title, key in fields:
                value = data.get(key, "")
                lines.extend([f"## {title}"])
                if isinstance(value, list):
                    lines.extend(f"- {item}" for item in value if str(item).strip())
                else:
                    lines.append(str(value or "No material response returned."))
                lines.append("")
            return "\n".join(lines)

        def start_review():
            point = point_text.get("1.0", tk.END).strip()
            if not point:
                messagebox.showwarning("Missing Point", "Enter one point, argument, evidence item, or question first.", parent=win)
                return
            rows = [r for r in self.providers if r["key"].get().strip() and r.get("verified") and r["verified"].get()]
            if not rows:
                messagebox.showerror("No Verified Provider", "Verify at least one model provider first.", parent=win)
                return
            use_redaction = self.v_anonymize.get()
            if not use_redaction:
                use_redaction = self._ask_enable_data_redaction()
                if use_redaction:
                    self.v_anonymize.set(True)
            dims = [d for d, _desc in ALL_DIMENSIONS if self.dim_vars.get(d, tk.BooleanVar()).get()]
            context = (
                f"CASE NAME: {self._gt(self.v_name)}\nJURISDICTION: {self._gt(self.v_jur)}\n\n"
                f"FULL CASE:\n{self._gt(self.t_bg)}\n\n"
                f"POSITIVE ARGUMENTS:\n{self._gt(self.t_pos_args)}\n\nPOSITIVE EVIDENCE:\n{self._gt(self.t_pos_ev)}\n\n"
                f"NEGATIVE ARGUMENTS:\n{self._gt(self.t_neg_args)}\n\nNEGATIVE EVIDENCE:\n{self._gt(self.t_neg_ev)}"
            )
            anonymizer = PIIAnonymizer() if use_redaction else None
            send_point = anonymizer.anonymize(point) if anonymizer else point
            send_context = anonymizer.anonymize(context) if anonymizer else context
            prompt = f"""You are conducting a focused legal-preparation review for a lawyer. The selected point belongs to the {side_var.get()}.
Review this one point in the context of the entire matter. Do not isolate it from other arguments or evidence. Identify material from either side that supports, contradicts, qualifies, or changes the point.
The opposing side must attack the point; the point-owning side must respond; then give the likely counter-response and an effective answer. This is lawyer reference material, not legal advice or a final legal conclusion.
Review dimensions: {json.dumps(dims, ensure_ascii=False)}

SELECTED POINT:\n{send_point}\n\nFULL MATTER CONTEXT:\n{send_context}

Return strict JSON with exactly these keys: point_summary (string), attack_analysis (string), supporting_materials (array), weakening_materials (array), attack_questions (array), defence_response (string), counter_response (string), missing_materials (array), lawyer_note (string). Be concrete and use the actual facts, documents, dates, amounts, and party roles available in the matter. Do not invent missing facts or authorities."""
            run_btn.config(state=tk.DISABLED)
            status_var.set(f"Running {len(rows)} verified provider(s)...")
            result_text.delete("1.0", tk.END)

            def worker():
                reports = []
                for idx, row in enumerate(rows):
                    client = LLMClient(row["name"].get(), row["key"].get().strip(), personality_idx=idx)
                    data = client.chat_json(prompt, temperature=0.35, max_tokens=5000)
                    if anonymizer and isinstance(data, dict):
                        data = json.loads(anonymizer.deanonymize(json.dumps(data, ensure_ascii=False)))
                    reports.append(format_result(row["name"].get(), data))
                final = "\n\n".join(reports)
                self.root.after(0, lambda: (result_text.insert("1.0", final), run_btn.config(state=tk.NORMAL), status_var.set("Complete - lawyer review required")))
            threading.Thread(target=worker, daemon=True).start()

        run_btn.config(command=start_review)

    def _build_output(self):
        p = tk.Frame(self.sf, bg=self.C["panel"], padx=10, pady=8)
        p.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.set_help(p, "Opposition results: attack details, summary, live progress, raw data, and local citation audit.")
        title_row = tk.Frame(p, bg=self.C["panel"])
        title_row.pack(fill=tk.X)
        tk.Label(title_row, text="📊 Opposition Results", bg=self.C["panel"], fg=self.C["text"],
                 font=("Helvetica", 12, "bold")).pack(side=tk.LEFT)
        tk.Button(title_row, text="Fullscreen", command=self._open_fullscreen,
                  bg=self.C["accent"], fg="white", relief="flat",
                  padx=10, pady=2, font=("Helvetica", 13), cursor="hand2").pack(side=tk.RIGHT, padx=4)
        self.nb = ttk.Notebook(p)
        self.nb.pack(fill=tk.BOTH, expand=True, pady=4)
        self._fullscreen_win = None
        self._fs_callbacks = {}
        self._fs_widgets = {}

        def tab(title):
            f = ttk.Frame(self.nb)
            self.nb.add(f, text=title)
            t = scrolledtext.ScrolledText(f, bg=self.C["entry"], fg=self.C["text"],
                                          font=("Microsoft YaHei", 14), wrap=tk.WORD, relief="flat")
            self._bind_local_scroll(t)
            t.pack(fill=tk.BOTH, expand=True)
            return t

        self.t_attacks = tab("⚔ Attack Details")
        self.t_attacks.config(bg="#132033", fg="#e7edf8", insertbackground="#e7edf8")
        self.t_summary = tab("📋 Summary")
        self.t_log = tab("📡 Live Progress")
        self.t_raw = tab("🔧 Raw Data")

    def _open_fullscreen(self):
        if self._fullscreen_win and self._fullscreen_win.winfo_exists():
            self._fullscreen_win.lift()
            return
        win = tk.Toplevel(self.root)
        self._fullscreen_win = win
        win.title("StrikeOver v2.11 - Fullscreen")
        win.state("zoomed")
        win.configure(bg="#132033")
        top = tk.Frame(win, bg="#132033")
        top.pack(fill=tk.X, padx=8, pady=4)
        tk.Label(top, text="📊 Opposition Results (Fullscreen)", bg="#132033", fg="#e7edf8",
                 font=("Helvetica", 13, "bold")).pack(side=tk.LEFT)
        tk.Button(top, text="Close", command=win.destroy,
                  bg=self.C["red"], fg="white", relief="flat",
                  padx=12, pady=3, font=("Helvetica", 14), cursor="hand2").pack(side=tk.RIGHT)
        nb2 = ttk.Notebook(win)
        nb2.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._fs_widgets = {}
        for title, src in [("⚔ Attack Details", self.t_attacks), ("📋 Summary", self.t_summary),
                            ("📡 Live Progress", self.t_log), ("🔧 Raw Data", self.t_raw)]:
            f = ttk.Frame(nb2)
            nb2.add(f, text=title)
            bg = "#132033" if title == "⚔ Attack Details" else self.C["entry"]
            fg = "#e7edf8" if title == "⚔ Attack Details" else self.C["text"]
            t = scrolledtext.ScrolledText(f, bg=bg, fg=fg,
                                          font=("Microsoft YaHei", 15), wrap=tk.WORD, relief="flat")
            t.pack(fill=tk.BOTH, expand=True)
            self._fs_widgets[title] = (t, src)
        self._fs_sync(win)
        win.protocol("WM_DELETE_WINDOW", win.destroy)

    def _fs_sync(self, win):
        if not win.winfo_exists():
            return
        for title, (t, src) in self._fs_widgets.items():
            try:
                new_txt = src.get("1.0", tk.END)
                if new_txt == t.get("1.0", tk.END):
                    continue
                ypos = t.yview()
                at_bottom = ypos[1] >= 0.99
                t.config(state='normal')
                t.delete("1.0", tk.END)
                t.insert("1.0", new_txt)
                for tag in src.tag_names():
                    try:
                        cfg = {k: v[-1] for k, v in src.tag_configure(tag).items()
                               if v and v[-1] not in ('', None)}
                        if cfg:
                            t.tag_configure(tag, **cfg)
                    except Exception:
                        pass
                for tag in src.tag_names():
                    try:
                        ranges = src.tag_ranges(tag)
                        for i in range(0, len(ranges), 2):
                            t.tag_add(tag, str(ranges[i]), str(ranges[i+1]))
                    except Exception:
                        pass
                for utag, cb in self._fs_callbacks.items():
                    try:
                        t.tag_bind(utag, '<Button-1>', cb)
                    except Exception:
                        pass
                if at_bottom:
                    t.see(tk.END)
                else:
                    t.yview_moveto(ypos[0])
            except Exception:
                pass
        win.after(1000, lambda: self._fs_sync(win))

    # ========== 草稿保存 ==========
    def _save_draft(self):
        if not AUTO_SAVE_CASE_CONTENT:
            return
        try:
            data = {
                "name": self.v_name.get(),
                "jurisdiction": self.v_jur.get(),
                "background": self.t_bg.get("1.0", tk.END).strip(),
                "pos_args": self.t_pos_args.get("1.0", tk.END).strip(),
                "pos_ev": self.t_pos_ev.get("1.0", tk.END).strip(),
                "neg_args": self.t_neg_args.get("1.0", tk.END).strip(),
                "neg_ev": self.t_neg_ev.get("1.0", tk.END).strip(),
                "timestamp": datetime.now().isoformat(),
            }
            with open(DRAFT_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except:
            pass

    def _load_draft(self):
        if not AUTO_SAVE_CASE_CONTENT:
            self.v_name.set("")
            self.v_jur.set("Australia / New South Wales")
            return
        try:
            if os.path.exists(DRAFT_FILE):
                with open(DRAFT_FILE, encoding="utf-8") as f:
                    d = json.load(f)
                self.v_name.set(d.get("name", ""))
                self.v_jur.set(d.get("jurisdiction", "Australia / New South Wales"))
                for w, k in [(self.t_bg, "background"), (self.t_pos_args, "pos_args"),
                    (self.t_pos_ev, "pos_ev"), (self.t_neg_args, "neg_args"),
                    (self.t_neg_ev, "neg_ev")]:
                    w.delete("1.0", tk.END)
                    w.insert("1.0", self._clean_system_labels(d.get(k, "")))
        except:
            pass

    def _load_config(self):
        try:
            self.loading_config = True
            session_active = self._provider_session_active()
            # 先清空现有行，防止重复加载
            for r in self.providers:
                r["_frame"].destroy()
            self.providers.clear()

            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, encoding="utf-8-sig") as f:
                    d = json.load(f)
                saved = d.get("providers", [])
                for prov in saved:
                    pname = prov.get("name", "")
                    key = prov.get("key", "") if session_active else ""
                    if prov.get("base_url") or prov.get("model"):
                        PROVIDER_PRESETS[pname] = {
                            "base_url": (prov.get("base_url") or "").rstrip("/"),
                            "model": prov.get("model") or pname,
                            "rate_input": 0.0,
                            "rate_output": 0.0,
                        }
                    self._add_provider_row(
                        prov.get("name", ""), key,
                        prov.get("enabled", True), False) # 启动时强制未认证，用户必须手动认证
                if saved:
                    self._anon_reminder_shown = d.get("anon_reminder_shown", False)
                    alloc = d.get("side_provider_allocation") or {}
                    self.side_provider_allocation = {
                        "positive": list(alloc.get("positive") or []),
                        "negative": list(alloc.get("negative") or []),
                    }
                    if not self.side_provider_allocation["positive"]:
                        old_pos = d.get("positive_provider_route")
                        if old_pos and old_pos != "Full verified providers":
                            self.side_provider_allocation["positive"] = [x.strip() for x in str(old_pos).split(",") if x.strip()]
                    if not self.side_provider_allocation["negative"]:
                        old_neg = d.get("negative_provider_route")
                        if old_neg and old_neg != "Full verified providers":
                            self.side_provider_allocation["negative"] = [x.strip() for x in str(old_neg).split(",") if x.strip()]
                    self._update_count_label()
                    self._refresh_side_provider_routes()
                    return
            # config不存在或为空，加默认行；Gemini first for the competition route.
            for name in ["gemini", "deepseek", "openai", "anthropic"]:
                self._add_provider_row(name, "", True, False)
            self._update_count_label()
            self._refresh_side_provider_routes()
        except Exception as e:
            # 出错时加默认行
            for name in ["gemini", "deepseek", "openai", "anthropic"]:
                self._add_provider_row(name, "")
            self._update_count_label()
            self._refresh_side_provider_routes()
        finally:
            self.loading_config = False

    def _save_config(self):
        try:
            if not self._provider_session_active():
                return
            data = self._provider_config_data()
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.cloud_backend.run_async(self.cloud_backend.sync_provider_profile, data)
            self.cloud_backend.run_async(
                self.cloud_backend.record_event,
                "provider_profile_saved",
                {"provider_count": len(data.get("providers") or [])},
            )
            # 静默保存，不弹窗
        except Exception as e:
            pass # 静默失败

    def _on_close(self):
        try:
            self._save_draft()
        except Exception:
            pass
        self.cloud_backend.run_async(
            self.cloud_backend.record_event,
            "online_application_closed",
            {"running": bool(self.running)},
        )
        self.root.destroy()

    # ========== 工具方法 ==========
    def _gt(self, w):
        return w.get("1.0", tk.END).strip() if isinstance(w, tk.Text) else w.get().strip()

    def _clean_system_labels(self, text):
        text = str(text or "")
        return (text
                .replace("跨Jurisdiction", "Cross-Jurisdiction")
                .replace("跨法域武器", "Cross-Jurisdiction Weapon")
                .replace("跨界", "Cross-Boundary")
                .replace("战术组合包：用于攻击反方弱点", "Tactic package for attacking negative-side weaknesses")
                .replace("战术组合包：用于攻击正方弱点", "Tactic package for attacking positive-side weaknesses"))

    def _log(self, msg):
        self.t_log.insert(tk.END, msg + "\n")
        self.t_log.see(tk.END)
        lower = str(msg or "").lower()
        if any(marker in lower for marker in ("failed", "http 429", "complete", "export", "provider")):
            event = "application_log_event"
            if "failed" in lower:
                event = "model_or_workflow_failed"
            elif "complete" in lower:
                event = "workflow_completed"
            self.cloud_backend.run_async(
                self.cloud_backend.record_event,
                event,
                {"message_code": hashlib.sha256(str(msg).encode("utf-8")).hexdigest()[:16]},
            )

    def _write(self, w, txt):
        """写入widget，自动处理disabled状态"""
        try:
            txt = str(txt or "")
            txt = txt.replace("跨Jurisdiction", "Cross-Jurisdiction")
            txt = txt.replace("跨法域武器", "Cross-Jurisdiction Weapon")
            txt = txt.replace("跨界", "Cross-Boundary")
            w.config(state='normal')
            w.delete("1.0", tk.END)
            w.insert("1.0", txt)
            w.config(state='normal')
        except Exception:
            pass

    def _clear_results(self):
        """清空所有结果tab，强制解锁"""
        for w in [self.t_attacks, self.t_summary, self.t_log, self.t_raw]:
            try:
                w.config(state='normal')
                w.delete("1.0", tk.END)
            except Exception:
                pass

    def _dim_en(self, dim):
        dim = str(dim or "?").strip()
        dim = re.sub(r"\s*律师\s*$", "", dim).strip()
        if dim in DIMENSION_LABELS_EN:
            return DIMENSION_LABELS_EN[dim]
        for chinese_name, english_name in DIMENSION_LABELS_EN.items():
            if chinese_name in dim:
                dim = dim.replace(chinese_name, english_name)
        return dim

    def _validate(self):
        verified = [r for r in self.providers
                    if r["key"].get().strip() and r.get("verified", tk.BooleanVar(value=False)).get()]
        if not verified:
            messagebox.showerror("Error", "Please verify at least one provider.\nRows without a key or verification are skipped automatically.")
            return False
        if not self._gt(self.t_bg):
            messagebox.showerror("Error", "Please enter the case background.")
            return False
        return True

    # ========== 运行 ==========
    def _stop(self):
        """停止当前辩论流程"""
        self.running = False
        self._log("\nRun interrupted by user")
        self.root.after(0, lambda: self.status_label.config(text="Stopped"))
        self.root.after(0, lambda: self.stop_btn.config(state=tk.DISABLED))

    def _run(self):
        if not self._validate():
            return
        self.running = True
        self._clear_results()
        self._set_analysis_ui_locked(True)
        threading.Thread(target=self._thread_wrapper, daemon=True).start()

    def _thread_wrapper(self):
        try:
            self._thread()
        finally:
            self.running = False
            self.root.after(0, lambda: (
                self._set_analysis_ui_locked(False),
                self.progress.stop(), self.progress.pack_forget(),
                self.stop_btn.config(state=tk.DISABLED),
            ))

    def _thread(self):
        """4轮交替辩论 + 法官叠加画框"""
        try:
            # 检查中断标志
            if not self.running:
                return

            active_rows = [r for r in self.providers
                           if r["key"].get().strip() and r.get("verified", tk.BooleanVar(value=False)).get()]
            skipped = [r["name"].get() for r in self.providers
                       if not r["key"].get().strip() or not r.get("verified", tk.BooleanVar(value=False)).get()]
            providers = []
            for i, r in enumerate(active_rows):
                client = LLMClient(r["name"].get(), r["key"].get().strip(), personality_idx=i)
                client.source_name = r["name"].get().strip()
                providers.append(client)

            # 按综合费率排序（输入+输出均价），最便宜的排前面
            providers.sort(key=lambda c: (
                c.provider.get("rate_input", 999) + c.provider.get("rate_output", 999)
            ))
            if providers:
                cheapest = providers[0].provider_key
            self._log(f"Cost routing: cheapest provider -> {cheapest}; using it first")

            if skipped:
                self._log(f"Skipped automatically: {', '.join(skipped)}")

            negative_clients = self._select_provider_clients_for_side(
                providers,
                self.v_negative_provider_route.get(),
                "Negative side",
            )
            positive_clients = self._select_provider_clients_for_side(
                providers,
                self.v_positive_provider_route.get(),
                "Positive side",
            )
            self._log("Provider routing:")
            self._log("  Negative side -> " + ", ".join(getattr(c, "source_name", c.provider_key) for c in negative_clients))
            self._log("  Positive side -> " + ", ".join(getattr(c, "source_name", c.provider_key) for c in positive_clients))

            dims = [(d, desc) for (d, desc) in ALL_DIMENSIONS if self.dim_vars.get(d, tk.BooleanVar()).get()]

            case_bg = "Case: " + self._gt(self.v_name) + "\nCourt / Jurisdiction: " + self._gt(self.v_jur) + "\n\n" + self._gt(self.t_bg)
            pos_sub = "Positive-side arguments:\n" + self._gt(self.t_pos_args) + "\n\nPositive-side evidence:\n" + self._gt(self.t_pos_ev)
            neg_sub = "Negative-side arguments:\n" + self._gt(self.t_neg_args) + "\n\nNegative-side evidence:\n" + self._gt(self.t_neg_ev)
            use_search = self.v_search.get()
            jur = self._gt(self.v_jur)

            # ===== 首次脱敏提醒（v2.11: 每次启动只弹一次） =====
            use_anon = self.v_anonymize.get()
            if not use_anon and not self._anon_reminder_shown:
                self._anon_reminder_shown = True
                # 子线程不能直接弹 messagebox，用 after + Event 实现
                import threading as _th
                _anon_evt = _th.Event()
                def _do_reminder():
                    result = self._ask_enable_data_redaction()
                    if result:
                        self.v_anonymize.set(True)
                        use_anon_local[0] = True
                    _anon_evt.set()
                use_anon_local = [use_anon]
                self.root.after(0, _do_reminder)
                _anon_evt.wait(timeout=120)  # 最多等2分钟
                use_anon = use_anon_local[0]

            # ===== 脱敏处理（v2.9: 逐轮脱敏，不再一次性脱敏所有输入） =====
            anonymizer = None
            if use_anon:
                anonymizer = PIIAnonymizer()
                # 预扫描中文人名（仅建立映射表，不立即替换）
                case_raw = self._gt(self.t_bg) + self._gt(self.t_pos_args) + self._gt(self.t_neg_args)
                cn_surnames = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏窦章苏潘葛范彭郎鲁韦昌马苗凤花方俞任袁柳丰鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯管卢莫经房干解应宗丁宣贲邓郁单杭洪包诸左石崔吉钮龚程嵇邢滑裴陆荣翁荀羊甄家封芮储靳邴"
                anonymizer.set_cn_surnames(cn_surnames)
                cn_stop = set("的了在和是有不为于与也从这就而着被将让把向给很已还能只又即更最该其但如因由")
                for m in re.finditer(r'[' + cn_surnames + r'][\u4e00-\u9fff]{1,2}', case_raw):
                    name = m.group()
                    if len(name) >= 2 and name[-1] not in cn_stop and name not in ("案件", "法院", "被告", "原告", "证人", "律师", "法官", "当事人", "被害人", "申请人", "被申请人", "上诉人", "被上诉人"):
                        anonymizer.add_manual(name, "人名")
                # v2.9: 不再在这里脱敏，移到每轮发送前

            M, N = len(providers), len(dims)

            self._log("=" * 55)
            self._log("StrikeOver v2.12 - 2-round opposition + per-round redaction")
            self._log("M=" + str(M) + " provider(s) x N=" + str(N) + " dimension(s)")
            self._log("Case authority search: " + ("On" if use_search else "Off"))
            self._log("Data redaction: " + ("On" if use_anon else "Off"))
            if use_anon and anonymizer:
                self._log("Redaction report: " + anonymizer.get_report())
            self._log("Flow: R1 negative attack -> R2 positive rebuttal -> judge overlay")
            self._log("=" * 55)

            engine = MxNEngine(max_workers=16, use_search=use_search)

            # 历史记录
            history = {"pos_initial": pos_sub, "neg_initial": neg_sub}
            success_providers = set(providers)

            # 计时器
            t_start = time.time()
            t_r1 = t_r2 = t_r3 = t_r4 = t_judge = 0.0

            # Round 1: 反方攻击
            if not self.running: return
            self._log("\n[Round 1] Negative side attacks the positive side...")
            self.root.after(0, lambda: self.status_label.config(text="Round 1: Negative attack..."))

            # v2.9: R1发送前脱敏输入
            if anonymizer:
                case_bg_anon = anonymizer.anonymize(case_bg)
                pos_sub_anon = anonymizer.anonymize(pos_sub)
                neg_sub_anon = anonymizer.anonymize(neg_sub)
                jur_anon = anonymizer.anonymize(jur)
                self._log("🔒 [R1] Input redaction complete")
            else:
                case_bg_anon, pos_sub_anon, neg_sub_anon, jur_anon = case_bg, pos_sub, neg_sub, jur

            t0 = time.time()
            r1_results, r1_success = engine.run(negative_clients, dims, case_bg_anon, neg_sub_anon, pos_sub_anon, jur_anon, self._log, "negative side")
            t_r1 = time.time() - t0
            history["r1_neg_attack"] = r1_results
            r1_success_providers = set(r1_success)

            flat_r1 = self._flatten(r1_results)
            self._audit_r1_items(flat_r1, target_context=pos_sub_anon + "\n" + case_bg_anon)
            self._log("OK Round 1: " + str(len(flat_r1)) + " attack item(s)")
            self._log("Local function audit R1: " + self._audit_count_line(flat_r1))
            if anonymizer:
                self._log("🔒 [R1->R2] Redaction mappings: " + str(len(anonymizer.map_forward)))
            self.t_attacks.tag_config('header', font=('Microsoft YaHei', 14, 'bold'), foreground='#89dceb')
            self.t_attacks.tag_config('subheader', font=('Microsoft YaHei', 12, 'bold'), foreground='#f9e2af')
            self.t_attacks.tag_config('label', font=('Microsoft YaHei', 13), foreground='#a6adc8')
            self.t_attacks.tag_config('link', font=('Microsoft YaHei', 11, 'underline'), foreground='#f5a0b8')
            self.t_attacks.tag_config('pos', font=('Microsoft YaHei', 13), foreground='#89b4fa')
            self.t_attacks.tag_config('neg', font=('Microsoft YaHei', 13), foreground='#f5a0b8')
            self._stream_attacks("=" * 55 + "\n", 'header')
            self._stream_attacks("StrikeOver v2.12 - 2-round opposition (per-round redaction)\n", 'header')
            self._stream_attacks("=" * 55 + "\n\n", 'header')
            self._stream_attacks("## Round 1: Negative Attack\n", 'subheader')
            for atk in flat_r1[:20]:
                dim = self._dim_en(atk.get('_dimension', '?'))
                prov = atk.get('_provider', '?')
                full = str(atk.get('attack', '?'))
                preview = full[:200] + "..." if len(full) > 200 else full
                self._stream_attacks(f"\n[{dim}][{prov}]\n", 'neg')
                self._stream_attacks(f"  Target: {str(atk.get('targeting', '?'))}\n", 'label')
                self._stream_attacks(f"  Function audit: {FunctionItemAuditor.summarize(atk.get('_function_audit'))}\n", 'label')
                self._stream_attacks(f"  Attack: {preview}", 'neg')
                self._stream_link(full, f"R1 attack - {dim} [{prov}]")
                self._stream_attacks("\n")

            # 提取已验证的真实案例名称
            verified_cases = set()
            for res in r1_results:
                for vc in res.get("_verified_cases", []):
                    verified_cases.add(vc)
            verified_cases_text = "、".join(sorted(verified_cases)) if verified_cases else "无"

            if not r1_success_providers:
                self._log("All providers failed in Round 1")
                return

            # Round 2: 正方反驳（所有模型并行）
            if not self.running: return
            self._log("\n[Round 2] Positive rebuttal (" + str(len(positive_clients)) + " provider(s) in parallel)...")
            self.root.after(0, lambda: self.status_label.config(text="Round 2: Positive rebuttal..."))

            r2_results = []
            r2_lock = threading.Lock()
            failed_in_r2 = set()
            atk_json_r2 = json.dumps(self._without_function_audit(flat_r1), ensure_ascii=False)

            def run_r2(client):
                if not self.running or client.failed:
                    failed_in_r2.add(client)
                    self._log(f"Warning: [R2] {client.provider_key} skipped because it is not available")
                    return
                prompt = (
                    f"## Regulator Notice\n"
                    f"Your client is the positive side. You are the positive side's legal team.\n"
                    f"The positive side has already submitted its arguments and evidence.\n"
                    f"The opposing lawyers have attacked your side's case. Respond point-by-point and defend the positive side's position.\n\n"
                    f"## Role\n"
                    f"- You work for the positive side; your output serves the positive side's interests.\n"
                    f"- Your goal is to persuade the judge to accept the positive side's position.\n"
                    f"- Truth-finding is the judge's job, not yours.\n\n"
                    f"## Case\n{case_bg_anon[:600]}\n\n"
                    f"## Positive Side's Submitted Arguments\n{pos_sub_anon[:500]}\n\n"
                    f"## All Opposing Attacks Against the Positive Side\n{atk_json_r2}\n\n"
                    f"## Rebuttal Requirements\n"
                    f"Do not limit yourself to only one rebuttal. Review every opposing attack item.\n"
                    f"For each opposing attack item, return one corresponding item.\n"
                    f"If the point requires a substantive response, answer it directly.\n"
                    f"If the point does not require a substantive response, explain neutrally why no expanded response is required without ranking the threat level.\n"
                    f"If no good rebuttal exists, still return an item and state that the attack creates an unresolved risk.\n"
                    f"Each rebuttal must directly address the specific attack point identified in the targeting field.\n\n"
                    f"## Critical Constraints\nVerified authorities available: {verified_cases_text}\n"
                    f"Do not invent case names, legislation, section numbers, regulations, or rule numbers.\n"
                    f"If no verified authority is available, use general legal principles only.\n"
                    f"Every JSON string value must be in English. Preserve proper names, court names, dates, amounts, and citations.\n\n"
                    f"Return strict JSON only: {{\"rebuttals\": [{{\"targeting\": \"which attack is being answered\", \"response_status\": \"answered|not_required_explained|unresolved_risk\", \"rebuttal\": \"rebuttal in English, or neutral explanation why no expanded response is required\", \"why_fails\": \"why the attack fails, why no expanded response is required, or why the risk remains, in English\"}}]}}"
                )
                # v2.9: 逐轮脱敏——对完整prompt二次扫描，捕获R1输出中可能泄露的新PII
                if anonymizer:
                    prompt = anonymizer.anonymize(prompt)
                self._log(f" -> [R2] calling {client.provider_key}...")
                res = client.chat_json(prompt, temperature=0.65, max_tokens=6000)
                if res.get("_error"):
                    failed_in_r2.add(client)
                    self._log(f"Warning: [R2] {client.provider_key} failed: {str(res.get('_error', ''))[:120]}")
                else:
                    res["_provider"] = client.provider_key
                    with r2_lock: r2_results.append(res)
                    count = len(res.get("rebuttals", []) or [])
                    self._log(f" ✓ [R2] {client.provider_key} returned {count} rebuttal item(s)")

            t0 = time.time()
            r2_threads = [threading.Thread(target=run_r2, args=(c,)) for c in positive_clients]
            for t in r2_threads: t.start()
            for t in r2_threads: t.join()
            t_r2 = time.time() - t0
            r2_success_providers = set(positive_clients) - failed_in_r2
            success_providers = r1_success_providers | r2_success_providers

            self._ensure_r2_covers_r1(r2_results, flat_r1)
            # 内部分析 (静默)
            CapitulationDetector.scan_round(r2_results, content_keys=["rebuttal", "why_fails"])
            self._audit_r2_items(r2_results, target_context=atk_json_r2 + "\n" + pos_sub_anon,
                                 verified_cases=sorted(verified_cases))

            history["r2_pos_rebuttal"] = r2_results
            self._log("OK Round 2: " + str(len(r2_results)) + " provider(s) complete")
            self._log("Local function audit R2: " + self._audit_count_line(r2_results))
            if anonymizer:
                self._log("🔒 [R2->Judge] Redaction mappings: " + str(len(anonymizer.map_forward)))
            self._stream_attacks("\n## Round 2: Positive Rebuttal\n", 'subheader')
            if not r2_results:
                self._stream_attacks("\nNo Round 2 rebuttal was returned. Check Live Progress for provider errors.\n", 'label')
                self.root.after(0, lambda: self.status_label.config(text="Round 2 failed - see Live Progress"))
                return
            for r in r2_results:
                prov = r.get('_provider', r.get('provider', '?'))
                rebuttals = r.get('rebuttals', [])
                self._stream_attacks(f"\n[{prov}] {len(rebuttals)} rebuttal item(s)\n", 'pos')
                for i, reb in enumerate(rebuttals, 1):
                    if isinstance(reb, dict):
                        targeting = reb.get('targeting', '?')
                        rebuttal_text = reb.get('rebuttal', '')
                        status = reb.get('response_status', '')
                        preview = rebuttal_text[:200] + "..." if len(rebuttal_text) > 200 else rebuttal_text
                        status_text = f" Response: {status}" if status else ""
                        self._stream_attacks(f"  {i}. Target [{targeting}]{status_text}\n", 'label')
                        self._stream_attacks(f"     Function audit: {FunctionItemAuditor.summarize(reb.get('_function_audit'))}\n", 'label')
                        self._stream_attacks(f"     {preview}", 'pos')
                        full_rebuttal = json.dumps(self._without_function_audit(reb), ensure_ascii=False, indent=2)
                        self._stream_link(full_rebuttal, f"R2 rebuttal {i} - {prov}")
                        self._stream_attacks("\n")
                    else:
                        full_rebuttal = str(reb)
                        preview = full_rebuttal[:200] + "..." if len(full_rebuttal) > 200 else full_rebuttal
                        self._stream_attacks(f"  {i}. {preview}", 'pos')
                        self._stream_link(full_rebuttal, f"R2 rebuttal {i} - {prov}")
                        self._stream_attacks("\n")
                self._stream_link(json.dumps(self._without_function_audit(rebuttals), ensure_ascii=False, indent=2), f"R2 all rebuttals - {prov}")
                self._stream_attacks("\n")

            # Round 3 / Round 4 已取消：R2 后直接进入法官叠加
            r3_results = []
            r4_results = []
            history["r3_neg_response"] = r3_results
            history["r4_pos_final"] = r4_results

            # 法官叠加
            if not self.running: return
            self._log("\n[Judge] Overlay analysis...")
            self.root.after(0, lambda: self.status_label.config(text="Judge overlay analysis..."))

            verdict_list = []
            verdict_lock = threading.Lock()

            # 整理完整攻防记录（按条目截断，不硬切JSON）
            def build_judge_context():
                parts = []
                parts.append(f"## Initial Positive-Side Arguments\n{pos_sub_anon[:600]}")
                parts.append(f"## Initial Negative-Side Arguments\n{neg_sub_anon[:600]}")
                # R1攻击摘要
                r1_summary = []
                for res in history.get("r1_neg_attack", []):
                    for dim_res in (res if isinstance(res, list) else [res]):
                        for atk in dim_res.get("attacks", [])[:3]:
                            r1_summary.append(f"[{dim_res.get('_dimension','?')}] {atk.get('attack','')[:150]}")
                parts.append("## Round 1 Negative Attack Summary\n" + "\n".join(r1_summary[:20]))
                # R2反驳摘要
                r2_summary = []
                for res in r2_results:
                    for rb in res.get("rebuttals", [])[:3]:
                        r2_summary.append(f"[{res.get('_provider','?')}] {rb.get('rebuttal','')[:120]}")
                parts.append("## Round 2 Positive Rebuttal Summary\n" + "\n".join(r2_summary[:15]))
                return "\n\n".join(parts)

            judge_context = build_judge_context()

            def run_judge(client):
                if not self.running or client.failed: return
                prompt = (
                    f"You are a trial weakness-analysis expert. You have reviewed the case materials, Round 1 negative attacks, and Round 2 positive rebuttals.\n"
                    f"Your job is to map each weakness to concrete case facts. Do not write academic summaries or generic legal theory.\n"
                    f"Analyze weaknesses on both sides. Do not decide the winner; identify vulnerabilities only.\n"
                    f"All JSON string values must be in English. Preserve proper names, court names, dates, amounts, and citations.\n\n"
                    f"{judge_context}\n\n"
                    f"## Critical Constraints\n"
                    f"1. Verified authorities available: {verified_cases_text}\n"
                    f"2. Do not invent case names, legislation, section numbers, regulations, or rule numbers.\n"
                    f"3. If no verified authority is available, use general legal principles only.\n\n"
                    f"## Surface Card Rules\n"
                    f"- Return no more than 5 weaknesses for each side.\n"
                    f"- Each name must be short, concrete, and non-duplicative. Avoid names such as Rule-to-fact gap or Generic evidence gap.\n"
                    f"- one_sentence_summary must say: who/which side claims what, and what specific evidence, date, clause, amount, record, or step is missing.\n\n"
                    f"## Full Card Rules\n"
                    f"- Do not use placeholders, ellipses, or template phrases such as Case can argue that, The legal element supposedly satisfied by, or real-case materials should be checked.\n"
                    f"- Do not use system labels such as Evidence angle, Contract angle, Argument 1, or Dimension in content fields.\n"
                    f"- Do not refer only to broad evidence categories. If the record names a document, message, payment, clause, date, location, or amount, use it.\n"
                    f"- Every weakness must include at least one concrete case marker: party identity, date, period, document/record, clause, amount, location, or specific evidence content.\n"
                    f"- If a weakness cannot be mapped to concrete case facts, omit it.\n"
                    f"- The attack_script must be usable as direct questions by a lawyer who just received the case.\n\n"
                    f"Return strict JSON only with this exact shape: {{\"pos_weaknesses\": [{{\"id\": \"PW-01\", \"name\": \"short concrete weakness name\", \"one_sentence_summary\": \"case-specific two-sentence surface summary\", \"target_claim_or_element\": \"specific claim, clause, issue, or element under attack\", \"mapping_checklist\": {{\"specific_rule_or_clause\": \"specific rule, clause, or issue if available\", \"rule_elements\": [\"case-specific element\"], \"opponent_proved_elements\": [\"element plus evidence already shown\"], \"opponent_unproved_elements\": [\"element plus missing concrete proof\"], \"case_specific_missing_evidence\": [\"specific missing document, date, witness, record, amount, or step\"]}}, \"missing_evidence_or_step\": [\"specific missing evidence or step\"], \"attack_script\": [\"specific question containing case facts\"], \"signal_of_success\": \"concrete reaction or missing record that shows the weakness was hit\", \"defence_preparation\": [\"specific evidence or step to prepare\"], \"severity\": \"fatal|high|medium\"}}], "
                    f"\"neg_weaknesses\": [{{\"id\": \"NW-01\", \"name\": \"short concrete weakness name\", \"one_sentence_summary\": \"case-specific two-sentence surface summary\", \"target_claim_or_element\": \"specific claim, clause, issue, or element under attack\", \"mapping_checklist\": {{\"specific_rule_or_clause\": \"specific rule, clause, or issue if available\", \"rule_elements\": [\"case-specific element\"], \"opponent_proved_elements\": [\"element plus evidence already shown\"], \"opponent_unproved_elements\": [\"element plus missing concrete proof\"], \"case_specific_missing_evidence\": [\"specific missing document, date, witness, record, amount, or step\"]}}, \"missing_evidence_or_step\": [\"specific missing evidence or step\"], \"attack_script\": [\"specific question containing case facts\"], \"signal_of_success\": \"concrete reaction or missing record that shows the weakness was hit\", \"defence_preparation\": [\"specific evidence or step to prepare\"], \"severity\": \"fatal|high|medium\"}}], "
                    f"\"summary\": \"judge summary in English without deciding the winner\", "
                    f"\"pos_urgent\": [\"urgent positive-side action in English\"], \"neg_urgent\": [\"urgent negative-side action in English\"]}}"
                )
                # v2.9: 逐轮脱敏——法官prompt也可能包含PII
                if anonymizer:
                    prompt = anonymizer.anonymize(prompt)
                res = client.chat_json(prompt, max_tokens=3000)
                if not res.get("_error"):
                    res["_provider"] = client.provider_key
                    with verdict_lock: verdict_list.append(res)
                    summary_p = str(res.get('summary', ''))[:60]
                    self._log(f" ✓ Judge [{client.provider_key}] summary={repr(summary_p)}")

            t0 = time.time()
            judge_threads = [threading.Thread(target=run_judge, args=(c,)) for c in success_providers]
            for t in judge_threads: t.start()
            for t in judge_threads: t.join()
            t_judge = time.time() - t0
            t_total = time.time() - t_start
            self._log("OK judge analysis: " + str(len(verdict_list)) + " judge result(s)")
            self._stream_attacks("\n## Judge Comments\n", 'subheader')
            for v in verdict_list[:3]:
                prov = v.get('_provider', v.get('provider', '?'))
                self._stream_attacks(f"\n{prov}:\n", 'label')
                pos_fmt = self._format_weaknesses(v.get('pos_weaknesses', []))
                neg_fmt = self._format_weaknesses(v.get('neg_weaknesses', []))
                pos_full = self._format_weaknesses_full(v.get('pos_weaknesses', []))
                neg_full = self._format_weaknesses_full(v.get('neg_weaknesses', []))
                pos_p = pos_fmt[:200] + "..." if len(pos_fmt) > 200 else pos_fmt
                neg_p = neg_fmt[:200] + "..." if len(neg_fmt) > 200 else neg_fmt
                self._stream_attacks(f"  Positive weaknesses:\n{pos_p}")
                self._stream_link(pos_full, f"Judge - {prov} positive weaknesses")
                self._stream_attacks("\n")
                self._stream_attacks(f"  Negative weaknesses:\n{neg_p}")
                self._stream_link(neg_full, f"Judge - {prov} negative weaknesses")
                self._stream_attacks("\n")
                summary = str(v.get('summary', ''))
                sum_p = summary[:200] + "..." if len(summary) > 200 else summary
                self._stream_attacks(f"  Comment: {sum_p}")
                self._stream_link(summary, f"Judge - {prov} comment")
                self._stream_attacks("\n")

            # 脱敏还原：将结果中的占位符替换回原始PII
            if anonymizer and anonymizer.map_backward:
                self._log("🔒 Restoring redacted data (" + str(len(anonymizer.map_backward)) + " mappings)...")
                # 还原flat_r1
                for atk in flat_r1:
                    for key in ('attack', 'targeting', 'legal_basis', 'kill_shot'):
                        if isinstance(atk.get(key), str):
                            atk[key] = anonymizer.deanonymize(atk[key])
                # 还原r2
                for r in r2_results:
                    for rb in r.get('rebuttals', []):
                        if isinstance(rb, dict):
                            for key in ('rebuttal', 'targeting', 'why_fails'):
                                if isinstance(rb.get(key), str):
                                    rb[key] = anonymizer.deanonymize(rb[key])
                # 还原r3
                for r in r3_results:
                    for rp in r.get('responses', []):
                        if isinstance(rp, dict):
                            for key in ('response', 'targeting'):
                                if isinstance(rp.get(key), str):
                                    rp[key] = anonymizer.deanonymize(rp[key])
                # 还原r4
                for r in r4_results:
                    for key in ('final_position',):
                        if isinstance(r.get(key), str):
                            r[key] = anonymizer.deanonymize(r[key])
                # 还原法官
                for v in verdict_list:
                    for side in ('pos_weaknesses', 'neg_weaknesses'):
                        for w in v.get(side, []):
                            if isinstance(w, dict):
                                for key in ('point', 'reason', 'fix'):
                                    if isinstance(w.get(key), str):
                                        w[key] = anonymizer.deanonymize(w[key])
                    for key in ('summary',):
                        if isinstance(v.get(key), str):
                            v[key] = anonymizer.deanonymize(v[key])
                    for key in ('pos_urgent', 'neg_urgent'):
                        items = v.get(key, [])
                        if isinstance(items, list):
                            v[key] = [anonymizer.deanonymize(i) if isinstance(i, str) else i for i in items]

            # 渲染（必须在主线程执行）
            # 保存到 self 供报告使用
            self.last_history = history
            self.last_r2_results = r2_results
            self.last_r3_results = r3_results
            self.last_r4_results = r4_results
            self.last_flat_r1 = flat_r1
            self.last_verdict_list = verdict_list
            self.last_citation_audit = self._build_citation_audit(flat_r1, r2_results, verdict_list)
            self._render_4round(history, flat_r1, r2_results, r3_results, r4_results, verdict_list, M, N,
                                providers, t_r1, t_r2, t_r3, t_r4, t_judge, t_total)

            # Keep results visible in the UI. Do not auto-save matter content to disk
            # unless the user explicitly uses an export/save action.
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            result_data = {
                "timestamp": ts,
                "case": self._gt(self.v_name),
                "history": {k: str(v)[:2000] for k, v in history.items()},
                "verdict": verdict_list,
                "local_citation_audit": getattr(self, "last_citation_audit", {}),
            }
            raw_json = json.dumps(result_data, ensure_ascii=False, indent=2)
            self._write(self.t_raw, raw_json)
            if AUTO_SAVE_CASE_CONTENT:
                jpath = os.path.join(CASES_DIR, f"battle_{ts}.json")
                with open(jpath, "w", encoding="utf-8") as f:
                    json.dump(result_data, f, ensure_ascii=False, indent=2)
                self._log("\nOK saved: " + jpath)
            else:
                self._log("\nPrivacy mode: case content was not auto-saved to disk.")

            total_cost = sum(c.total_cost for c in providers)
            self.root.after(0, lambda: self.status_label.config(text="Complete  Cost $" + f"{total_cost:.4f}"))

        except Exception as e:
            import traceback
            err_msg = str(e)[:40]
            self._log("\nError: " + str(e) + "\n" + traceback.format_exc())
            self.root.after(0, lambda msg=err_msg: self.status_label.config(text="Error: " + msg))

    def _flatten(self, results):
        flat = []
        for res in (results or []):
            for a in res.get("attacks", []):
                a["_dimension"] = res.get("_dimension", "?")
                a["_provider"] = res.get("_provider", "?")
                flat.append(a)
        return flat

    def _audit_r1_items(self, flat_r1, target_context=""):
        for item in flat_r1 or []:
            item["_function_audit"] = FunctionItemAuditor.audit_attack(
                item,
                target_context=target_context,
                verified_cases=item.get("_verified_cases", []),
            )
        self.last_function_audit_r1 = [x.get("_function_audit", {}) for x in (flat_r1 or [])]
        return flat_r1

    def _audit_r2_items(self, r2_results, target_context="", verified_cases=None):
        for result in r2_results or []:
            for item in result.get("rebuttals", []) or []:
                if isinstance(item, dict):
                    item["_function_audit"] = FunctionItemAuditor.audit_rebuttal(
                        item,
                        target_context=target_context,
                        verified_cases=verified_cases or [],
                    )
        audits = []
        for result in r2_results or []:
            for item in result.get("rebuttals", []) or []:
                if isinstance(item, dict):
                    audits.append(item.get("_function_audit", {}))
        self.last_function_audit_r2 = audits
        return r2_results

    def _attack_response_key(self, item):
        if not isinstance(item, dict):
            return ""
        target = str(item.get("targeting") or item.get("target") or "").strip()
        dim = str(item.get("_dimension") or item.get("dimension") or "").strip()
        attack = str(item.get("attack") or item.get("finding") or "").strip()
        basis = target or attack[:160]
        return re.sub(r"\s+", " ", f"{dim} {basis}").strip().lower()

    def _ensure_r2_covers_r1(self, r2_results, flat_r1):
        expected = []
        for idx, atk in enumerate(flat_r1 or [], 1):
            key = self._attack_response_key(atk)
            if key:
                expected.append((idx, key, atk))
        if not expected:
            return r2_results

        for result in r2_results or []:
            rebuttals = result.get("rebuttals")
            if not isinstance(rebuttals, list):
                rebuttals = []
                result["rebuttals"] = rebuttals
            covered = set()
            for rb in rebuttals:
                if not isinstance(rb, dict):
                    continue
                rb_key = self._attack_response_key(rb)
                rb_text = " ".join(str(rb.get(k, "")) for k in ("targeting", "rebuttal", "why_fails")).lower()
                for idx, key, atk in expected:
                    attack_target = str(atk.get("targeting") or atk.get("attack") or "")[:100].strip().lower()
                    if key and (key in rb_key or rb_key in key or (attack_target and attack_target in rb_text)):
                        covered.add(idx)
            for idx, key, atk in expected:
                if idx in covered:
                    continue
                dim = self._dim_en(atk.get("_dimension") or atk.get("dimension") or f"Item {idx}")
                target = str(atk.get("targeting") or atk.get("attack") or f"R1 item {idx}").strip()
                rebuttals.append({
                    "targeting": f"{dim}: {target[:180]}",
                    "response_status": "not_returned_for_review",
                    "rebuttal": "No model-generated expanded response was returned for this specific attack item.",
                    "why_fails": "This is a coverage notice, not a merits judgment. Counsel should decide whether the point needs a substantive response or can be left without expansion.",
                    "_coverage_notice": True,
                })
        return r2_results

    def _audit_count_line(self, obj):
        audits = []
        def collect(value):
            if isinstance(value, dict):
                if "_function_audit" in value:
                    audits.append(value.get("_function_audit") or {})
                for child in value.values():
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)
        collect(obj)
        counts = {"pass": 0, "caution": 0, "review": 0}
        for audit in audits:
            status = str(audit.get("status", "review")).lower()
            counts[status] = counts.get(status, 0) + 1
        return f"PASS {counts.get('pass', 0)} / CAUTION {counts.get('caution', 0)} / REVIEW {counts.get('review', 0)}"

    def _without_function_audit(self, obj):
        if isinstance(obj, dict):
            return {k: self._without_function_audit(v) for k, v in obj.items() if k != "_function_audit"}
        if isinstance(obj, list):
            return [self._without_function_audit(x) for x in obj]
        return obj

    def _format_weaknesses(self, items):
        if not items or not isinstance(items, list):
            return str(items)[:300] if items else ''
        sev_map = {'fatal': 'fatal', 'high': 'high', 'medium': 'medium', 'low': 'low'}
        out = []
        for item in items[:5]:
            if isinstance(item, dict):
                sev = sev_map.get(item.get('severity',''), item.get('severity',''))
                title = item.get('name') or item.get('point') or item.get('target_claim_or_element') or 'Weakness'
                summary = item.get('one_sentence_summary') or item.get('reason') or ''
                out.append(f"  [{sev}] {title}")
                if summary:
                    out.append(f"    Summary: {str(summary)[:220]}")
                if item.get('target_claim_or_element'):
                    out.append(f"    Target: {str(item['target_claim_or_element'])[:160]}")
                if item.get('fix'):
                    out.append(f"    Fix: {item['fix'][:100]}")
            else:
                out.append(f"  {str(item)[:100]}")
        return '\n'.join(out)

    def _format_weaknesses_full(self, items):
        if not items or not isinstance(items, list):
            return str(items) if items else ''
        sev_map = {'fatal': 'fatal', 'high': 'high', 'medium': 'medium', 'low': 'low'}
        out = []
        for item in items[:5]:
            if isinstance(item, dict):
                sev = sev_map.get(item.get('severity',''), item.get('severity',''))
                title = item.get('name') or item.get('point') or item.get('target_claim_or_element') or 'Weakness'
                out.append(f"  [{sev}] {title}")
                if item.get('one_sentence_summary'):
                    out.append(f"    Summary: {item['one_sentence_summary']}")
                elif item.get('reason'):
                    out.append(f"    Reason: {item['reason']}")
                if item.get('target_claim_or_element'):
                    out.append(f"    Target: {item['target_claim_or_element']}")
                checklist = item.get('mapping_checklist') or {}
                if isinstance(checklist, dict) and checklist:
                    out.append("    Mapping checklist:")
                    for key, value in checklist.items():
                        if isinstance(value, list):
                            value = "; ".join(str(x) for x in value)
                        out.append(f"      - {key}: {value}")
                missing = item.get('missing_evidence_or_step') or []
                if isinstance(missing, str):
                    missing = [missing]
                if missing:
                    out.append("    Missing evidence or step:")
                    out.extend(f"      - {x}" for x in missing)
                script = item.get('attack_script') or []
                if isinstance(script, str):
                    script = [script]
                if script:
                    out.append("    Attack script:")
                    out.extend(f"      - {x}" for x in script)
                if item.get('signal_of_success'):
                    out.append(f"    Signal of success: {item['signal_of_success']}")
                prep = item.get('defence_preparation') or item.get('fix') or []
                if isinstance(prep, str):
                    prep = [prep]
                if prep:
                    out.append("    Defence preparation:")
                    out.extend(f"      - {x}" for x in prep)
            else:
                out.append(f"  {str(item)}")
        return '\n'.join(out)

    def _collect_strings(self, obj, acc):
        if isinstance(obj, str):
            acc.append(obj)
        elif isinstance(obj, dict):
            for value in obj.values():
                self._collect_strings(value, acc)
        elif isinstance(obj, list):
            for value in obj:
                self._collect_strings(value, acc)

    def _unique_keep_order(self, items):
        seen = set()
        out = []
        for item in items:
            item = str(item or "").strip()
            if not item:
                continue
            key = re.sub(r"\s+", " ", item).lower()
            if key not in seen:
                seen.add(key)
                out.append(item)
        return out

    def _clean_citation_candidate(self, text):
        text = re.sub(r"\s+", " ", str(text or "")).strip(" .,:;")
        text = re.sub(r"^(?:see|under|in|relying on|citing)\s+", "", text, flags=re.I)
        return text.strip(" .,:;")

    def _build_citation_audit(self, flat_r1=None, r2_results=None, verdict_list=None):
        flat_r1 = flat_r1 or []
        r2_results = r2_results or []
        verdict_list = verdict_list or []

        verified_cases = []
        unverified_cases_from_search = []
        for item in flat_r1:
            verified_cases.extend(item.get("_verified_cases", []) or [])
            unverified_cases_from_search.extend(item.get("_unverified_cases", []) or [])
        verified_cases = self._unique_keep_order(verified_cases)
        unverified_cases_from_search = self._unique_keep_order(unverified_cases_from_search)
        verified_lookup = {x.lower() for x in verified_cases}

        texts = []
        self._collect_strings(flat_r1, texts)
        self._collect_strings(r2_results, texts)
        self._collect_strings(verdict_list, texts)
        full_text = "\n".join(texts)

        case_patterns = [
            r"\b[A-Z][A-Za-z'&.-]+(?:[ \t]+[A-Z][A-Za-z'&.-]+){0,5}[ \t]+v\.?[ \t]+[A-Z][A-Za-z'&.-]+(?:[ \t]+[A-Z][A-Za-z'&.-]+){0,5}\b",
            r"\[\d{4}\][ \t]+[A-Z]{2,}[ \t]+\d+",
        ]
        statute_patterns = [
            r"\b[A-Z][A-Za-z& ]{2,80}[ \t]+(?:Act|Regulation|Rules|Code)[ \t]+\d{4}\b",
            r"\b(?:s|ss|section|sections)\s*\d+[A-Za-z0-9()\-]*(?:\s*[-,]\s*\d+[A-Za-z0-9()\-]*)?",
            r"[\u4e00-\u9fff]{1,20}(?:法|条例|规则|规定)第?\s*[一二三四五六七八九十百千万\d]+\s*条",
        ]

        extracted_cases = []
        for pattern in case_patterns:
            extracted_cases.extend(re.findall(pattern, full_text))
        extracted_cases = [self._clean_citation_candidate(x) for x in extracted_cases]
        extracted_cases = self._unique_keep_order(extracted_cases)

        extracted_statutes = []
        for pattern in statute_patterns:
            extracted_statutes.extend(re.findall(pattern, full_text, flags=re.I))
        extracted_statutes = [self._clean_citation_candidate(x) for x in extracted_statutes]
        extracted_statutes = self._unique_keep_order(extracted_statutes)

        verified_found = []
        needs_case_review = []
        for case in extracted_cases:
            if case.lower() in verified_lookup:
                verified_found.append(case)
            else:
                needs_case_review.append(case)

        for case in unverified_cases_from_search:
            if case.lower() not in {x.lower() for x in needs_case_review}:
                needs_case_review.append(case)

        warnings = []
        if needs_case_review:
            warnings.append("Model output contains case names or neutral citations not confirmed by local authority search.")
        if extracted_statutes:
            warnings.append("Model output contains statute numbers, sections, Acts, Regulations, or rule numbers that require lawyer review.")
        if not verified_cases:
            warnings.append("No locally confirmed authority search result is available; all model citations should be treated as unverified.")

        return {
            "verified_cases": self._unique_keep_order(verified_found or verified_cases),
            "needs_case_review": self._unique_keep_order(needs_case_review),
            "needs_statute_review": extracted_statutes,
            "warnings": warnings,
        }

    def _format_citation_audit(self, audit=None):
        audit = audit or getattr(self, "last_citation_audit", {}) or {}
        lines = []
        lines.append("Local Citation Audit")
        lines.append("This local function does not validate the legal conclusion. It flags citations that need lawyer review, especially invented cases, statutes, or sections.")
        verified = audit.get("verified_cases") or []
        case_review = audit.get("needs_case_review") or []
        statute_review = audit.get("needs_statute_review") or []
        warnings = audit.get("warnings") or []

        lines.append("\nConfirmed by local search:")
        lines.extend([f"- {x}" for x in verified[:20]] or ["- None"])

        lines.append("\nCases / neutral citations needing review:")
        lines.extend([f"- {x}" for x in case_review[:40]] or ["- None detected"])

        lines.append("\nStatutes / sections / rule numbers needing review:")
        lines.extend([f"- {x}" for x in statute_review[:40]] or ["- None detected"])

        if warnings:
            lines.append("\nWarnings:")
            lines.extend([f"- {x}" for x in warnings])
        return "\n".join(lines)

    def _at_bottom(self):
        try:
            return self.t_attacks.yview()[1] >= 0.99
        except Exception:
            return True

    def _stream_attacks(self, text, tag=None):
        try:
            at_bottom = self._at_bottom()
            self.t_attacks.insert(tk.END, text, tag)
            if at_bottom:
                self.t_attacks.see(tk.END)
        except Exception:
            pass

    def _stream_link(self, full_content, title):
        if len(str(full_content)) <= 200:
            return
        try:
            at_bottom = self._at_bottom()
            utag = f'lnk_{self.t_attacks.index(tk.END).replace(".", "_")}'
            cb = lambda e, c=full_content, t=title: self._show_full_content(t, c)
            self._fs_callbacks[utag] = cb
            self.t_attacks.insert(tk.END, ' [view full]', ('link', utag))
            self.t_attacks.tag_bind(utag, '<Button-1>', cb)
            if at_bottom:
                self.t_attacks.see(tk.END)
        except Exception:
            pass

    def _render_4round(self, history, flat_r1, r2_results, r3_results, r4_results, verdict_list, M, N,
                       providers=None, t_r1=0, t_r2=0, t_r3=0, t_r4=0, t_judge=0, t_total=0):
        try:
            self.t_summary.config(state='normal')
            self.t_summary.delete('1.0', tk.END)

            lines = []
            lines.append("=" * 55)
            lines.append("StrikeOver v2.6  Summary")
            lines.append("=" * 55)
            lines.append(f"\n{M} provider(s) x {N} dimension(s)")
            lines.append(f"R1 negative attacks: {len(flat_r1)} item(s)")
            lines.append(f"R2 positive rebuttals: {len(r2_results)} provider(s)")

            # ── 耗时统计 ──────────────────────────────────────────
            if t_total > 0:
                lines.append("\n" + "─" * 40)
                lines.append("Time")
                lines.append("─" * 40)
                lines.append(f"  R1 negative attack:     {t_r1:>7.1f} sec")
                lines.append(f"  R2 positive rebuttal:   {t_r2:>7.1f} sec")
                lines.append(f"  Judge analysis:         {t_judge:>7.1f} sec")
                lines.append(f"  ─────────────────────────────")
                lines.append(f"  Total time:             {t_total:>7.1f} sec  ({t_total/60:.1f} min)")

            # ── 费用统计 ──────────────────────────────────────────
            if providers:
                lines.append("\n" + "─" * 40)
                lines.append("Cost")
                lines.append("─" * 40)

                total_cost = 0.0
                total_tokens_in = 0
                total_tokens_out = 0

                for c in providers:
                    cost = getattr(c, 'total_cost', 0.0)
                    tok_in = getattr(c, 'total_tokens_in', 0)
                    tok_out = getattr(c, 'total_tokens_out', 0)
                    tok_total = tok_in + tok_out
                    total_cost += cost
                    total_tokens_in += tok_in
                    total_tokens_out += tok_out
                    name = getattr(c, 'provider_key', str(c))
                    lines.append(
                        f"  {name:<18}  "
                        f"${cost:.4f}   "
                        f"({tok_in:,} in + {tok_out:,} out = {tok_total:,} tokens)"
                    )

                lines.append(f"  {'─'*42}")
                lines.append(
                    f"  {'Total':<18}  "
                    f"${total_cost:.4f}   "
                    f"({total_tokens_in:,} in + {total_tokens_out:,} out)"
                )

                # 换算成人民币参考
                cny = total_cost * 7.25
                lines.append(f"\n  Approx. CNY: ¥{cny:.4f}")

            # ── 法官裁决 ──────────────────────────────────────────
            lines.append("\n" + "─" * 40)
            lines.append("Judge Review")
            lines.append("─" * 40)
            for v in verdict_list:
                p = v.get('_provider', v.get('provider', '?'))
                lines += [
                    f"\n[{p}]",
                    f"  Positive weaknesses:\n{self._format_weaknesses(v.get('pos_weaknesses', []))}",
                    f"  Negative weaknesses:\n{self._format_weaknesses(v.get('neg_weaknesses', []))}",
                    f"  Overall comment: {str(v.get('summary', ''))[:500]}"
                ]

            audit = getattr(self, "last_citation_audit", None) or self._build_citation_audit(flat_r1, r2_results, verdict_list)
            self.last_citation_audit = audit
            lines.append("\n" + "─" * 40)
            lines.append("Local Citation Audit")
            lines.append("─" * 40)
            lines.append(self._format_citation_audit(audit))

            lines.append("\n" + "=" * 55)
            self.t_summary.insert('1.0', "\n".join(lines))
            self.t_summary.config(state='disabled')
        except Exception:
            pass

    def _show_full_content(self, title, content):
        """弹出窗口显示完整内容"""
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry("800x500")
        win.configure(bg='#2a2a3e')

        # 标题
        title_lbl = tk.Label(win, text=title, font=('Microsoft YaHei', 14, 'bold'),
            fg='#f9e2af', bg='#2a2a3e')
        title_lbl.pack(pady=10)

        # 内容区
        text = scrolledtext.ScrolledText(win, font=('Microsoft YaHei', 14), bg='#2a2a3e', fg='#cdd6f4',
            wrap=tk.WORD, state='normal', insertbackground='#cdd6f4')
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        safe_content = str(content) if content else ''
        text.insert('1.0', safe_content)
        text.config(state='disabled')

        # 关闭按钮
        btn = tk.Button(win, text="Close", command=win.destroy,
            font=('Microsoft YaHei', 14), bg='#f38ba8', fg='#1e1e2e')
        btn.pack(pady=10)

    # ========== 其他功能 ==========
    def _swap_sides(self):
        pos_args = self.t_pos_args.get("1.0", tk.END)
        pos_ev = self.t_pos_ev.get("1.0", tk.END)
        neg_args = self.t_neg_args.get("1.0", tk.END)
        neg_ev = self.t_neg_ev.get("1.0", tk.END)
        self.t_pos_args.delete("1.0", tk.END)
        self.t_pos_args.insert("1.0", neg_args.strip())
        self.t_pos_ev.delete("1.0", tk.END)
        self.t_pos_ev.insert("1.0", neg_ev.strip())
        self.t_neg_args.delete("1.0", tk.END)
        self.t_neg_args.insert("1.0", pos_args.strip())
        self.t_neg_ev.delete("1.0", tk.END)
        self.t_neg_ev.insert("1.0", pos_ev.strip())

    def _save_case(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            data = {
                "name": self.v_name.get(),
                "jurisdiction": self.v_jur.get(),
                "background": self._gt(self.t_bg),
                "pos_args": self._gt(self.t_pos_args),
                "pos_ev": self._gt(self.t_pos_ev),
                "neg_args": self._gt(self.t_neg_args),
                "neg_ev": self._gt(self.t_neg_ev),
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.cloud_backend.run_async(self.cloud_backend.save_case_index, data, path)
            self.cloud_backend.run_async(
                self.cloud_backend.record_event,
                "case_saved",
                {"file_type": "json", "jurisdiction": data.get("jurisdiction", "")},
            )
            messagebox.showinfo("Success", "Case saved.")

    def _load_case(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if path:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            self.v_name.set(d.get("name", ""))
            self.v_jur.set(d.get("jurisdiction", ""))
            self._write(self.t_bg, d.get("background", ""))
            self._write(self.t_pos_args, d.get("pos_args", ""))
            self._write(self.t_pos_ev, d.get("pos_ev", ""))
            self._write(self.t_neg_args, d.get("neg_args", ""))
            self._write(self.t_neg_ev, d.get("neg_ev", ""))
            self.cloud_backend.run_async(self.cloud_backend.save_case_index, d, path)
            self.cloud_backend.run_async(
                self.cloud_backend.record_event,
                "case_loaded",
                {"file_type": "json", "jurisdiction": d.get("jurisdiction", "")},
            )

    def _run_blind(self):
        """盲测模式：正反方完全隔离，各自独立API调用，互不知情"""
        if not self._validate():
            return
        self.running = True
        self._clear_results()
        self._set_analysis_ui_locked(True)
        threading.Thread(target=self._blind_thread, daemon=True).start()

    def _blind_thread(self):
        """盲测核心：正反方完全隔离的两个独立API调用"""
        try:
            if not self.running:
                return

            active_rows = [r for r in self.providers
                           if r["key"].get().strip() and r.get("verified", tk.BooleanVar(value=False)).get()]
            providers = [LLMClient(r["name"].get(), r["key"].get().strip(), i) for i, r in enumerate(active_rows)]
            dims = [(d, desc) for (d, desc) in ALL_DIMENSIONS if self.dim_vars.get(d, tk.BooleanVar()).get()]

            # v2.11: 首次脱敏提醒（可能已在_thread中弹过）
            use_anon = self.v_anonymize.get()
            if not use_anon and not self._anon_reminder_shown:
                self._anon_reminder_shown = True
                import threading as _th3
                _anon_evt3 = _th3.Event()
                use_anon_local3 = [use_anon]
                def _do_reminder3():
                    result = self._ask_enable_data_redaction()
                    if result:
                        self.v_anonymize.set(True)
                        use_anon_local3[0] = True
                    _anon_evt3.set()
                self.root.after(0, _do_reminder3)
                _anon_evt3.wait(timeout=120)
                use_anon = use_anon_local3[0]

            case_bg = "案件：" + self._gt(self.v_name) + "\n法院：" + self._gt(self.v_jur) + "\n\n" + self._gt(self.t_bg)
            pos_sub = "我方论点：\n" + self._gt(self.t_pos_args) + "\n\n我方证据：\n" + self._gt(self.t_pos_ev)
            neg_sub = "对方论点：\n" + self._gt(self.t_neg_args) + "\n\n对方证据：\n" + self._gt(self.t_neg_ev)
            jur = self._gt(self.v_jur)
            M, N = len(providers), len(dims)

            self._log("=" * 55)
            self._log("Blind test mode - positive and negative sides are fully isolated")
            self._log("Positive API: sees only positive-side information")
            self._log("Negative API: sees only negative-side information")
            self._log("Purpose: test whether frame isolation is working")
            self._log("=" * 55)

            engine = MxNEngine(max_workers=16, use_search=False)

            # ===== 正方盲测：完全不给反方任何信息 =====
            if not self.running: return
            self._log("\n[Blind test - positive] Independent API call without negative-side information...")
            self.root.after(0, lambda: self.status_label.config(text="Blind test: positive side independent analysis..."))

            pos_blind_prompt_override = (
                f"你是一套法律分析系统，内含{len(dims)}名独立律师。\n"
                f"每名律师在自己的画框内独立工作，画框之间完全隔离。\n\n"
                f"## 你的身份：正方律师团\n"
                f"## 重要：你只能看到正方信息，反方信息对你完全不可见\n\n"
                f"## 案件背景\n{case_bg[:2500]}\n\n"
                f"## 正方论点与证据（这是你唯一能看到的立场信息）\n{pos_sub[:2000]}\n\n"
                f"## 任务：从以下各维度分析正方立场的强弱，找出自身弱点\n"
                f"⚠️ 禁止推测或假设反方会说什么\n\n"
            )

            pos_results_blind = []
            pos_lock = threading.Lock()

            frames_text = "\n".join([
                f"═══ 画框{i+1}：【{dim}律师】═══\n专属维度：{dim}\n说明：{desc}\n"
                for i, (dim, desc) in enumerate(dims)
            ])

            def run_pos_blind(client):
                if not self.running or client.failed: return
                prompt = pos_blind_prompt_override + f"## 各律师画框定义\n{frames_text}\n\n"
                prompt += ('输出JSON：{"results": [{"dimension": "维度名称", '
                    '"attacks": [{"targeting": "正方自身哪个弱点", "attack": "弱点分析", '
                    '"strength": "high|medium|low"}], "summary": "本维度评估"}]}')
                res = client.chat_json(prompt, temperature=0.8, max_tokens=8000)
                if not res.get("_error"):
                    res["_provider"] = client.provider_key
                    for dim_res in res.get("results", []):
                        dim_res["_provider"] = client.provider_key
                    with pos_lock: pos_results_blind.append(res)
                    self._log(f" ✓ [Blind positive] {client.provider_key} complete")

            pos_threads = [threading.Thread(target=run_pos_blind, args=(c,)) for c in providers]
            for t in pos_threads: t.start()
            for t in pos_threads: t.join()
            self._log(f"OK positive blind test: {len(pos_results_blind)} provider(s) complete")

            # ===== 反方盲测：完全不给正方任何信息 =====
            if not self.running: return
            self._log("\n[Blind test - negative] Independent API call without positive-side information...")
            self.root.after(0, lambda: self.status_label.config(text="Blind test: negative side independent analysis..."))

            neg_blind_prompt_override = (
                f"你是一套法律分析系统，内含{len(dims)}名独立律师。\n"
                f"每名律师在自己的画框内独立工作，画框之间完全隔离。\n\n"
                f"## 你的身份：反方律师团\n"
                f"## 重要：你只能看到反方信息，正方信息对你完全不可见\n\n"
                f"## 案件背景\n{case_bg[:2500]}\n\n"
                f"## 反方论点与证据（这是你唯一能看到的立场信息）\n{neg_sub[:2000]}\n\n"
                f"## 任务：从以下各维度分析反方立场的强弱，找出自身弱点\n"
                f"⚠️ 禁止推测或假设正方会说什么\n\n"
            )

            neg_results_blind = []
            neg_lock = threading.Lock()

            def run_neg_blind(client):
                if not self.running or client.failed: return
                prompt = neg_blind_prompt_override + f"## 各律师画框定义\n{frames_text}\n\n"
                prompt += ('输出JSON：{"results": [{"dimension": "维度名称", '
                    '"attacks": [{"targeting": "反方自身哪个弱点", "attack": "弱点分析", '
                    '"strength": "high|medium|low"}], "summary": "本维度评估"}]}')
                res = client.chat_json(prompt, temperature=0.8, max_tokens=8000)
                if not res.get("_error"):
                    res["_provider"] = client.provider_key
                    for dim_res in res.get("results", []):
                        dim_res["_provider"] = client.provider_key
                    with neg_lock: neg_results_blind.append(res)
                    self._log(f" ✓ [Blind negative] {client.provider_key} complete")

            neg_threads = [threading.Thread(target=run_neg_blind, args=(c,)) for c in providers]
            for t in neg_threads: t.start()
            for t in neg_threads: t.join()
            self._log(f"OK negative blind test: {len(neg_results_blind)} provider(s) complete")

            # ===== Jaccard污染检测 =====
            if not self.running: return
            self._log("\n[Contamination check] Calculating positive/negative Jaccard similarity...")

            import re as _re
            def extract_keywords(results):
                words = set()
                for res in results:
                    for dim_res in res.get("results", []):
                        for atk in dim_res.get("attacks", []):
                            text = atk.get("attack", "") + " " + atk.get("targeting", "")
                            for w in _re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{4,}', text):
                                words.add(w)
                return words

            pos_words = extract_keywords(pos_results_blind)
            neg_words = extract_keywords(neg_results_blind)
            intersection = pos_words & neg_words
            union = pos_words | neg_words
            jaccard = len(intersection) / len(union) if union else 0.0

            self._log(f"Positive keyword count: {len(pos_words)}")
            self._log(f"Negative keyword count: {len(neg_words)}")
            self._log(f"Intersection / overlapping terms: {len(intersection)}")
            self._log(f"Jaccard similarity: {jaccard:.4f}")
            if jaccard < 0.05:
                self._log("Conclusion: low contamination (Jaccard < 0.05); frame isolation is effective")
            elif jaccard < 0.15:
                self._log("Conclusion: medium contamination (0.05 <= Jaccard < 0.15); review recommended")
            else:
                self._log("Conclusion: high contamination (Jaccard >= 0.15); isolation may have failed")

            if intersection:
                self._log(f"Overlapping keyword sample: {list(intersection)[:20]}")

            # 渲染盲测结果
            self.root.after(0, lambda: self._render_blind(
                pos_results_blind, neg_results_blind, jaccard, intersection))

            total_cost = sum(c.total_cost for c in providers)
            self.root.after(0, lambda: self.status_label.config(
                text=f"Blind test complete  Jaccard={jaccard:.4f}  Cost ${total_cost:.4f}"))

        except Exception as e:
            import traceback
            self._log(f"\nError: {e}\n{traceback.format_exc()}")
        finally:
            self.running = False
            self.root.after(0, lambda: (
                self._set_analysis_ui_locked(False),
                self.progress.stop(), self.progress.pack_forget(),
                self.stop_btn.config(state=tk.DISABLED)))

    def _render_blind(self, pos_results, neg_results, jaccard, intersection):
        """Render blind-test results."""
        self.t_attacks.config(state='normal')
        self.t_attacks.delete('1.0', tk.END)

        self.t_attacks.tag_config('header', font=('Microsoft YaHei', 14, 'bold'), foreground='#89dceb')
        self.t_attacks.tag_config('subheader', font=('Microsoft YaHei', 12, 'bold'), foreground='#f9e2af')
        self.t_attacks.tag_config('pos', font=('Microsoft YaHei', 13), foreground='#89b4fa')
        self.t_attacks.tag_config('neg', font=('Microsoft YaHei', 13), foreground='#f5a0b8')
        self.t_attacks.tag_config('result', font=('Microsoft YaHei', 13, 'bold'),
            foreground='#00ff00' if jaccard < 0.05 else '#ffaa00' if jaccard < 0.15 else '#ff0000')

        def add(text, tag=None):
            self.t_attacks.insert(tk.END, text, tag)

        add("=" * 60 + "\n", 'header')
        add("Blind Test Result - Frame Isolation Contamination Check\n", 'header')
        add("=" * 60 + "\n\n", 'header')

        verdict = "Low contamination; isolation is effective" if jaccard < 0.05 else "Medium contamination" if jaccard < 0.15 else "High contamination; isolation may have failed"
        add(f"Jaccard similarity: {jaccard:.4f} -> {verdict}\n\n", 'result')
        add(f"Positive result groups: {len(pos_results)} | Negative result groups: {len(neg_results)} | Overlap: {len(intersection)} term(s)\n\n")

        if intersection:
            add(f"Overlapping keywords: {', '.join(list(intersection)[:30])}\n\n", 'subheader')

        add("## Positive Blind Test (positive information only)\n", 'subheader')
        for res in pos_results[:3]:
            provider = res.get('_provider', '?')
            for dim_res in res.get('results', [])[:5]:
                dim = self._dim_en(dim_res.get('dimension', dim_res.get('_dimension', '?')))
                for atk in dim_res.get('attacks', [])[:2]:
                    attack = atk.get('attack', '')
                    preview = attack[:500] + "..." if len(attack) > 500 else attack
                    add(f"\n[{provider}][{dim}] {preview}\n", 'pos')

        add("\n## Negative Blind Test (negative information only)\n", 'subheader')
        for res in neg_results[:3]:
            provider = res.get('_provider', '?')
            for dim_res in res.get('results', [])[:5]:
                dim = self._dim_en(dim_res.get('dimension', dim_res.get('_dimension', '?')))
                for atk in dim_res.get('attacks', [])[:2]:
                    attack = atk.get('attack', '')
                    preview = attack[:500] + "..." if len(attack) > 500 else attack
                    add(f"\n[{provider}][{dim}] {preview}\n", 'neg')

        self.t_attacks.config(state='disabled')

        # 综合总结
        self.t_summary.config(state='normal')
        self.t_summary.delete('1.0', tk.END)
        self.t_summary.insert('1.0',
            f"Blind Test Contamination Report\n{'='*40}\n"
            f"Jaccard similarity: {jaccard:.4f}\n"
            f"Conclusion: {verdict}\n\n"
            f"Notes:\n"
            f"- Jaccard measures keyword overlap between positive and negative outputs\n"
            f"- The two sides call the API independently and cannot see each other\n"
            f"- Lower Jaccard means stronger frame isolation\n"
            f"- < 0.05: low contamination\n"
            f"- 0.05-0.15: medium contamination\n"
            f"- > 0.15: high contamination\n\n"
            f"Overlapping keywords ({len(intersection)}):\n"
            f"{', '.join(list(intersection)[:50]) if intersection else 'None'}")
        self.t_summary.config(state='disabled')

    def _format_full_round1_markdown(self):
        items = getattr(self, "last_flat_r1", []) or []
        if not items:
            return self.t_attacks.get("1.0", tk.END).strip() or "(No Round 1 data)"
        lines = []
        for i, atk in enumerate(items, 1):
            dim = self._dim_en(atk.get("_dimension") or atk.get("dimension") or "?")
            prov = atk.get("_provider", "?")
            lines.append(f"### {i}. [{dim}] {prov}")
            lines.append(f"- Target: {atk.get('targeting', '')}")
            lines.append(f"- Strength: {atk.get('strength', '')}")
            lines.append(f"- Fatal: {atk.get('is_fatal', '')}")
            lines.append(f"- Legal basis: {atk.get('legal_basis', '')}")
            lines.append(f"- Kill shot: {atk.get('kill_shot', '')}")
            lines.append("")
            lines.append(str(atk.get("attack", "")).strip())
            lines.append("")
        return "\n".join(lines).strip()

    def _format_full_round2_markdown(self):
        results = getattr(self, "last_r2_results", []) or []
        if not results:
            return "(No Round 2 rebuttal data)"
        lines = []
        for res in results:
            prov = res.get("_provider", res.get("provider", "?"))
            rebuttals = res.get("rebuttals", []) or []
            lines.append(f"### {prov} - {len(rebuttals)} rebuttal item(s)")
            for i, rb in enumerate(rebuttals, 1):
                if not isinstance(rb, dict):
                    lines.append(f"{i}. {rb}")
                    continue
                lines.append(f"{i}. Target: {rb.get('targeting', '')}")
                if rb.get("response_status"):
                    lines.append(f"   Response status: {rb.get('response_status', '')}")
                lines.append(f"   Rebuttal: {rb.get('rebuttal', '')}")
                lines.append(f"   Reason / remaining issue: {rb.get('why_fails', '')}")
                lines.append("")
        return "\n".join(lines).strip()

    def _format_full_judge_markdown(self):
        verdicts = getattr(self, "last_verdict_list", []) or []
        if not verdicts:
            return self.t_summary.get("1.0", tk.END).strip() or "(No judge analysis data)"
        lines = []
        for v in verdicts:
            prov = v.get("_provider", v.get("provider", "?"))
            lines.append(f"### {prov}")
            lines.append("Positive weaknesses:")
            lines.append(self._format_weaknesses_full(v.get("pos_weaknesses", [])) or "- None")
            lines.append("")
            lines.append("Negative weaknesses:")
            lines.append(self._format_weaknesses_full(v.get("neg_weaknesses", [])) or "- None")
            lines.append("")
            if v.get("pos_urgent"):
                lines.append("Positive urgent actions:")
                lines.extend([f"- {x}" for x in v.get("pos_urgent", [])])
                lines.append("")
            if v.get("neg_urgent"):
                lines.append("Negative urgent actions:")
                lines.extend([f"- {x}" for x in v.get("neg_urgent", [])])
                lines.append("")
            lines.append("Overall comment:")
            lines.append(str(v.get("summary", "")).strip() or "(No comment)")
            lines.append("")
        return "\n".join(lines).strip()

    def _report_html_from_markdown(self, title, content):
        import html
        raw = str(content or "")
        parts = re.split(r"(?=^## Round [12]: .*$)", raw, flags=re.M)
        body_parts = []
        for part in parts:
            if not part:
                continue
            safe = html.escape(part)
            if part.startswith("## Round 1: Negative"):
                body_parts.append(f'<section class="negative"><pre>{safe}</pre></section>')
            elif part.startswith("## Round 2: Positive"):
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

    def _export_report(self):
        path = filedialog.asksaveasfilename(defaultextension=".md", filetypes=[("Markdown", "*.md")])
        if path:
            # 提取对方攻击奏效点 (基于内部标记)
            key_attack_points = self._extract_key_attack_points()

            content = f"""# {self.v_name.get()}

## Jurisdiction
{self.v_jur.get()}

## Case Background
{self._gt(self.t_bg)}

## Positive Arguments
{self._gt(self.t_pos_args)}

## Positive Evidence
{self._gt(self.t_pos_ev)}

## Negative Arguments
{self._gt(self.t_neg_args)}

## Negative Evidence
{self._gt(self.t_neg_ev)}

## Round 1: Negative Attack - Full Output
{self._format_full_round1_markdown()}

## Round 2: Positive Rebuttal - Full Output
{self._format_full_round2_markdown()}

## Final Summary and Judge-Side Analysis
{self._format_full_judge_markdown()}

## Local Citation Audit
{self._format_citation_audit()}

## Hearing Preparation (Effective Opposition Attack Points)
{key_attack_points}
"""
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            html_path = os.path.splitext(path)[0] + ".html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(self._report_html_from_markdown(self.v_name.get(), content))
            self.cloud_backend.run_async(self.cloud_backend.upload_report, path, self.v_name.get())
            self.cloud_backend.run_async(self.cloud_backend.upload_report, html_path, self.v_name.get())
            self.cloud_backend.run_async(
                self.cloud_backend.record_event,
                "report_exported",
                {"formats": ["md", "html"]},
            )
            messagebox.showinfo("Success", "Report exported.")

    def _extract_key_attack_points(self):
        """从内部分析数据中提取对方攻击奏效点, 不暴露技术原理"""
        try:
            r2_results = getattr(self, 'last_r2_results', [])
            r3_results = getattr(self, 'last_r3_results', [])
            r4_results = getattr(self, 'last_r4_results', [])
        except Exception:
            return "(No data)"

        if not any([r2_results, r3_results, r4_results]):
            return "(No opposition run yet)"

        report_lines = []

        # 统计反方哪些攻击点导致正方反应异常
        if r2_results:
            r2_compromised = [r for r in r2_results if r.get("_capitulation", {}).get("capitulated")]
            if r2_compromised:
                report_lines.append("### Round 2 (Positive Rebuttal) - Key Negative Attack Points")
                report_lines.append("The following provider outputs showed position weakening while rebutting negative attacks. Prepare these attack directions carefully:")
                report_lines.append("")
                for r in r2_compromised:
                    prov = r.get("_provider", "?")
                    sev = r.get("_capitulation", {}).get("severity", "")
                    # 提取被攻击的具体点
                    rebuttals = r.get("rebuttals", [])
                    targets = []
                    for rb in rebuttals[:3]:
                        if isinstance(rb, dict):
                            t = rb.get("targeting", "")
                            if t:
                                targets.append(t[:80])
                    sev_label = {"fatal": "High Priority", "high": "Medium-High Priority", "medium": "Needs Review"}.get(sev, "Needs Review")
                    report_lines.append(f"- **[{prov}] - {sev_label}**")
                    if targets:
                        for t in targets:
                            report_lines.append(f"  - Negative attack direction: {t}")
                    report_lines.append("")

        # R3 反方在面对正方反驳时是否出现立场弱化
        if r3_results:
            r3_compromised = [r for r in r3_results if r.get("_capitulation", {}).get("capitulated")]
            if r3_compromised:
                report_lines.append("### Round 3 (Negative Response) - Key Positive Rebuttal Points")
                report_lines.append("The following provider outputs showed position weakening while responding to positive rebuttals:")
                report_lines.append("")
                for r in r3_compromised:
                    prov = r.get("_provider", "?")
                    sev = r.get("_capitulation", {}).get("severity", "")
                    responses = r.get("responses", [])
                    targets = []
                    for rsp in responses[:3]:
                        if isinstance(rsp, dict):
                            t = rsp.get("targeting", "")
                            if t:
                                targets.append(t[:80])
                    sev_label = {"fatal": "High Priority", "high": "Medium-High Priority", "medium": "Needs Review"}.get(sev, "Needs Review")
                    report_lines.append(f"- **[{prov}] - {sev_label}**")
                    if targets:
                        for t in targets:
                            report_lines.append(f"  - Positive rebuttal direction: {t}")
                    report_lines.append("")

        # R4 最终陈述阶段
        if r4_results:
            r4_compromised = [r for r in r4_results if r.get("_capitulation", {}).get("capitulated")]
            if r4_compromised:
                report_lines.append("### Round 4 (Positive Final Statement) - Residual Risk Points")
                report_lines.append("The following provider outputs still showed uncertainty in final expression. Strengthen these arguments before hearing:")
                report_lines.append("")
                for r in r4_compromised:
                    prov = r.get("_provider", "?")
                    sev = r.get("_capitulation", {}).get("severity", "")
                    sev_label = {"fatal": "High Priority", "high": "Medium-High Priority", "medium": "Needs Review"}.get(sev, "Needs Review")
                    report_lines.append(f"- **[{prov}] - {sev_label}**: final statement showed weakened expression")
                    report_lines.append("")

        if not report_lines:
            return "(No obvious effective opposition attack point was detected in this run.)"

        return "\n".join(report_lines)

    def _open_evidence_assistant(self):
        point = simpledialog.askstring(
            "Evidence Assistant",
            "Enter one new argument, evidence item, or attack point:",
            parent=self.root,
        )
        if not point or not point.strip():
            return
        point = point.strip()

        win = tk.Toplevel(self.root)
        win.title("Evidence Assistant Result")
        win.geometry("860x560")
        result_bg = "#111827"
        result_fg = "#e7edf8"
        win.configure(bg=result_bg)
        result_text = scrolledtext.ScrolledText(
            win, bg=result_bg, fg=result_fg, insertbackground=result_fg,
            font=("Microsoft YaHei", 12), wrap=tk.WORD, relief=tk.FLAT, bd=1,
        )
        result_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 6))
        result_text.tag_config("header", font=("Microsoft YaHei", 13, "bold"), foreground="#89dceb")
        result_text.tag_config("neg", foreground="#f5a0b8")
        result_text.tag_config("pos", foreground="#89b4fa")
        result_text.tag_config("label", foreground="#f9e2af")
        result_text.tag_config("muted", foreground="#a6adc8")

        controls = tk.Frame(win, bg=result_bg, padx=10, pady=8)
        controls.pack(fill=tk.X)
        status = tk.Label(controls, text="Preparing local preview...", bg=result_bg, fg="#a6adc8")
        status.pack(side=tk.LEFT)

        def append(text, tag=None):
            result_text.insert(tk.END, text, tag) if tag else result_text.insert(tk.END, text)
            result_text.see(tk.END)

        def local_dimension(text):
            lower = str(text or "").lower()
            checks = [
                ("Missing Evidence", ["missing", "absence", "no record", "inspection log", "not shown", "unavailable"]),
                ("Damage Causation", ["cause", "causation", "caused", "injury", "medical", "impairment", "recovery", "earning capacity", "damage", "loss"]),
                ("Quantum Dispute", ["amount", "quantum", "future earning", "cost", "money", "damages"]),
                ("Procedural Defect", ["notice", "time", "date", "deadline", "service", "inspection"]),
                ("Legal Application", ["duty", "breach", "rule", "law", "legal", "element", "liability"]),
                ("Fact Challenge", ["evidence", "proof", "prove", "record", "witness", "fact"]),
            ]
            for dim, needles in checks:
                if any(x in lower for x in needles):
                    return dim
            return "Logic Gap"

        def local_report(text):
            dim = local_dimension(text)
            attack_map = {
                "Missing Evidence": "The negative side should require the original source record, chain of custody, and an explanation for any missing material before this point carries weight.",
                "Damage Causation": "The negative side should separate breach, causation, and loss, then require the positive side to exclude alternative causes and prove the causal link.",
                "Quantum Dispute": "The negative side should require particulars, calculation method, assumptions, mitigation, and a direct link between the point and each claimed amount.",
                "Procedural Defect": "The negative side should test timing, notice, inspection, authority, and whether the relevant procedure was actually followed.",
                "Legal Application": "The negative side should break the legal rule into elements and require one proved fact for each element before liability follows.",
                "Fact Challenge": "The negative side should ask whether this is a fact, inference, opinion, or conclusion, then require the source and reliability of the record.",
                "Logic Gap": "The negative side should force the point back to premise, evidence source, rule application, and causal step.",
            }
            defence_map = {
                "Missing Evidence": "The positive side should identify available records, explain why any absent material is not essential, and show how existing evidence still proves the fact.",
                "Damage Causation": "The positive side should tie the point to duty, breach, harm, and loss, while preserving alternative support if one causal link is narrowed.",
                "Quantum Dispute": "The positive side should separate liability from quantum and provide the calculation path, documents, and fallback amount.",
                "Procedural Defect": "The positive side should answer with the timeline, responsible person, record path, and why any procedural criticism does not change the substance.",
                "Legal Application": "The positive side should map each element to concrete facts and evidence, avoiding abstract fairness arguments.",
                "Fact Challenge": "The positive side should anchor the answer in source evidence, witness reliability, continuity, and consistency with the wider record.",
                "Logic Gap": "The positive side should close the path step by step: premise, evidence, rule, causation, and remedy.",
            }
            materials = {
                "Missing Evidence": ["Original source record", "Alternative corroboration", "Reason missing material is not essential"],
                "Damage Causation": ["Causation timeline", "Alternative cause checklist", "Medical or factual support"],
                "Quantum Dispute": ["Calculation schedule", "Invoices or loss records", "Mitigation evidence"],
                "Procedural Defect": ["Notice/inspection record", "Timeline", "Authority record"],
                "Legal Application": ["Element table", "Fact-to-rule mapping", "Exceptions check"],
                "Fact Challenge": ["Original record", "Source reliability", "Completeness check"],
                "Logic Gap": ["Factual premise", "Evidence source", "Rule application", "Causal link"],
            }.get(dim, [])
            return {"focus": dim, "attack": attack_map.get(dim, attack_map["Logic Gap"]), "defence": defence_map.get(dim, defence_map["Logic Gap"]), "materials": materials}

        def render_payload(payload, provider="local"):
            if not isinstance(payload, dict):
                payload = local_report(point)
            result_text.config(state=tk.NORMAL)
            result_text.delete("1.0", tk.END)
            append("Evidence Assistant - Single Point\n", "header")
            append(f"Provider: {provider}\n", "muted")
            append(f"Point: {point}\n", "muted")
            append(f"Focus: {payload.get('focus', 'General')}\n\n", "label")
            append("R1 Negative Attack\n", "header")
            append(str(payload.get("attack", "")) + "\n\n", "neg")
            append("R2 Positive Defence\n", "header")
            append(str(payload.get("defence", "")) + "\n\n", "pos")
            append("Materials to Check\n", "label")
            for item in payload.get("materials", []) or []:
                append(f"- {item}\n")
            result_text.config(state=tk.DISABLED)

        def run_online():
            active = [r for r in self.providers if r["enabled"].get() and r["key"].get().strip()]
            if not active:
                win.after(0, lambda: status.config(text="Done - local only; no verified API provider is connected"))
                return
            active.sort(key=lambda r: r["name"].get().lower() != "deepseek")
            row = active[0]
            client = LLMClient(row["name"].get(), row["key"].get().strip())
            case_bg = self._gt(self.t_bg)[:1200]
            pos = (self._gt(self.t_pos_args) + "\n" + self._gt(self.t_pos_ev))[:1000]
            neg = (self._gt(self.t_neg_args) + "\n" + self._gt(self.t_neg_ev))[:1000]
            prompt = (
                "You are running the English Evidence Assistant. Analyze exactly one new argument/evidence point.\n"
                "Return strict JSON only with keys: focus, attack, defence, materials.\n"
                "All values must be in English. Do not cite unverified cases or legislation.\n\n"
                f"Case background:\n{case_bg}\n\n"
                f"Positive side material:\n{pos}\n\n"
                f"Negative side material:\n{neg}\n\n"
                f"Single point:\n{point}\n\n"
                "JSON shape: {\"focus\":\"dimension or issue\",\"attack\":\"R1 negative attack\",\"defence\":\"R2 positive defence\",\"materials\":[\"material to check\"]}"
            )
            try:
                win.after(0, lambda: status.config(text=f"Calling {client.provider_key}..."))
                payload = client.chat_json(prompt, temperature=0.45, max_tokens=1200)
                if not isinstance(payload, dict) or payload.get("_error"):
                    err_note = payload.get("_error", "provider returned invalid JSON") if isinstance(payload, dict) else "provider returned invalid JSON"
                    win.after(0, lambda err_note=err_note: status.config(text=f"Provider failed; local preview kept ({err_note[:70]})"))
                else:
                    win.after(0, lambda: (render_payload(payload, provider=client.provider_key), status.config(text="Done")))
            except Exception as exc:
                err_note = str(exc)
                win.after(0, lambda err_note=err_note: status.config(text=f"Provider failed; local preview kept ({err_note[:70]})"))

        render_payload(local_report(point), provider="local preview")
        status.config(text="Local preview shown; checking API provider...")
        threading.Thread(target=run_online, daemon=True).start()

# ========== 主入口 ==========
if __name__ == "__main__":
    app = StrikeOverGUI()
    app.root.mainloop()
