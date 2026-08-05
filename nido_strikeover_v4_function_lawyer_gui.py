import datetime as _dt
import hashlib
import json
import re
import sys
import tkinter as tk
import urllib.parse
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

VENDOR_DIR = Path(__file__).resolve().parent / "vendor"
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:
    DND_FILES = "DND_Files"
    TkinterDnD = None


APP_TITLE = "Nido StrikeOver v4 - 律师团攻防系统（客户版）"


DIMENSIONS = [
    ("事实质疑", "攻击事实基础、时间线、主体关系和关键前提。"),
    ("法律适用", "检查适用法律、构成要件、例外和适用边界。"),
    ("先例对抗", "寻找可区分先例、相反裁判思路和审查路径。"),
    ("逻辑漏洞", "检查因果跳跃、循环论证、概念偷换和结论过度。"),
    ("程序瑕疵", "检查管辖、时限、送达、证据规则和程序性缺口。"),
    ("损害因果关系", "攻击损害是否真实、是否由对方行为导致、是否可量化。"),
    ("量化争议", "检查金额、比例、概率、样本、计算过程和替代算法。"),
    ("举证责任", "识别谁负担证明责任、对方是否已完成证明门槛。"),
    ("法律文本解释", "围绕合同、法条、权利要求或文本字义与目的解释攻防。"),
    ("过失比较", "分析双方责任比例、共同原因和减损义务。"),
    ("公共政策", "检查裁判结果是否产生不良激励、行业风险或公共利益冲突。"),
    ("逆向思维", "从对方最强叙事反推我方最危险漏洞。"),
    ("跨法域武器", "参考其他法域或审查体系中的可类比攻击。"),
    ("反事实推演", "构造如果没有该行为/条款/技术特征时结果是否改变。"),
    ("比例原则检验", "检查手段、目的、必要性、最小侵害和均衡性。"),
    ("叙事解构", "拆解故事线、情绪诱导、标签化表达和隐含归因。"),
    ("系统性风险放大", "把单点漏洞放大到产品、流程、合规或行业层面。"),
    ("沉默证据", "寻找没有出现但应当出现的证据、记录、日志或反证。"),
]


MODE_HINTS = {
    "普通案件攻防": "按一般争议路径生成正反方四轮攻防。",
    "专利无效攻防": "优先审查新颖性、创造性、support、best method、清楚性和绕开风险。",
    "合同证据攻防": "优先审查条款解释、履约事实、证据链和损害量化。",
    "客户演示": "输出更短、更像客户演示材料的摘要。",
}


LAWYER_ATTACK_PRINCIPLE = (
    "律师攻防不是科研验证，也不是裁判谁对谁错。"
    "律师代表各自客户，在合法合规范围内争取最大利益；"
    "攻防的核心不是接受对方道理，而是在对方事实、证据、法律适用、因果链、金额和叙事中寻找漏洞，"
    "同时把我方立场整理成可证明、可补强、可限缩、可持续推进的路径。"
)


DIMENSION_PERSONA_ANCHORS = {
    "事实质疑": {
        "memory": "我以前输过一次，就是因为没有追原始视频、连续时间戳和封条状态；所以任何事实证据我都先问原件、连续性和介入因素。",
        "habit": "逐项拆事实来源、时间线、主体关系和证明目的。",
        "boundary": "不把对方提交的材料自动当成真实完整事实。",
    },
    "法律适用": {
        "memory": "我见过很多案件败在只背法条、不拆构成要件；我一定先问规则前提是否真的落到本案事实。",
        "habit": "把法条拆成适用条件、例外、边界和补救方式。",
        "boundary": "不承认对方引用法律就等于对方已经满足法律前提。",
    },
    "先例对抗": {
        "memory": "我处理过相似案，关键不是找一个像的案例，而是把对方案例和本案差异钉出来。",
        "habit": "寻找可区分事实、不同法域、不同程序阶段和不同裁判目的。",
        "boundary": "不让对方用一般原则替代本案的具体证明。",
    },
    "逻辑漏洞": {
        "memory": "我最警惕结果倒推原因；发现不等于交付时存在，损失不等于由我方造成。",
        "habit": "抓因果跳跃、概念偷换、循环论证和结论过度。",
        "boundary": "不让对方把一个结果包装成唯一原因。",
    },
    "程序瑕疵": {
        "memory": "程序节点经常决定攻防空间；错过通知、申请、送达或提交节点，会让实体论点变弱。",
        "habit": "把事件做成时间轴，逐个检查时限、流程、通知和材料完整性。",
        "boundary": "不把程序问题说成纯形式问题，它会影响证明力和补救范围。",
    },
    "损害因果关系": {
        "memory": "我见过对方把所有费用都甩给我方，但最后败在没有证明直接因果。",
        "habit": "拆损害、原因、介入因素、可预见性和直接性。",
        "boundary": "不承认有损失就等于我方负责。",
    },
    "量化争议": {
        "memory": "金额没有明细就是攻击点；数字必须有来源、算法、样本和替代口径。",
        "habit": "要求发票、账单、计算表、比例、概率和折价路径。",
        "boundary": "不让对方用情绪化金额替代可核算损失。",
    },
    "举证责任": {
        "memory": "我一直记得：谁主张谁举证。对方没有完成门槛前，我方不能替他补证明链。",
        "habit": "先锁证明责任，再问证明标准，再查对方是否达到门槛。",
        "boundary": "不主动承担对方本应承担的证明责任。",
    },
    "法律文本解释": {
        "memory": "合同、法条、权利要求都怕被对方改写；我先守住文字，再谈目的。",
        "habit": "按字义、上下文、提示显著性、目的和强制规则逐层解释。",
        "boundary": "不接受对方单方重写文本边界。",
    },
    "过失比较": {
        "memory": "很多案件不是一方全责；对方自己的检查、保存、减损和使用行为必须放进责任比例。",
        "habit": "寻找共同原因、注意义务、减损义务和责任分配。",
        "boundary": "不把对方包装成完全无过失的一方。",
    },
    "公共政策": {
        "memory": "公共政策不能当口号，但可以把个案结果放到行业激励和系统成本里看。",
        "habit": "把裁判后果扩展到行业规则、诚信交易、运营成本和司法资源。",
        "boundary": "不让公共政策盖过本案事实和证据主线。",
    },
    "逆向思维": {
        "memory": "我会先替法官和对方找我方最危险点，再准备退路；最坏情况先想清楚。",
        "habit": "假设对方最强证据成立，再找剩余防线和限缩路线。",
        "boundary": "不因为发现风险就投降，风险要转成可防守路径。",
    },
    "跨法域武器": {
        "memory": "跨法域工具可以施压，但乱扣帽子会反噬；必须保守、可证、可落地。",
        "habit": "寻找平台规则、监管路径、其他法域类比和诉讼外压力点。",
        "boundary": "不把未经证明的事实升级成犯罪或恶意指控。",
    },
    "反事实推演": {
        "memory": "如果去掉对方声称的关键事实，结果还成立吗？这个问题常常能打断对方因果链。",
        "habit": "构造替代原因、去除关键环节、比较结果是否改变。",
        "boundary": "不接受对方只有一种解释的叙事。",
    },
    "比例原则检验": {
        "memory": "即便对方赢一部分，也不等于赢全部补救；补救必须相称。",
        "habit": "拆目的、手段、必要性、最小侵害和均衡性。",
        "boundary": "不让轻微问题自动变成全额赔偿或极端补救。",
    },
    "叙事解构": {
        "memory": "对方会讲故事，我要拆故事：谁被标签化、谁被隐去、哪个因果被情绪替代。",
        "habit": "拆选择性呈现、情绪诱导、标签化表达和隐含归因。",
        "boundary": "不让情绪叙事替代证据链。",
    },
    "系统性风险放大": {
        "memory": "单案漏洞如果被裁判接受，可能变成行业规则风险；这个维度负责把风险放大给法官看。",
        "habit": "把单点漏洞推演到合规、流程、行业成本和未来案件激励。",
        "boundary": "不脱离本案证据空喊系统风险。",
    },
    "沉默证据": {
        "memory": "真正存在的事实，通常会留下该出现的记录；缺席的证据本身就是追问入口。",
        "habit": "列出应有但未出现的原始记录、第三方材料、日志和反证。",
        "boundary": "不说缺失就等于不存在，但要求对方解释为什么缺失。",
    },
}


def short_hash(text):
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:12]


def compact(text, max_len=140):
    text = re.sub(r"\s+", " ", text.strip())
    if not text:
        return "未填写。"
    return text[:max_len] + ("..." if len(text) > max_len else "")


def read_text_file(path):
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "big5", "latin-1"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace"), "utf-8-replace"


def extract_case_file_text(path):
    path_obj = Path(path)
    suffix = path_obj.suffix.lower()
    if suffix in {".txt", ".md", ".json", ".py", ".csv", ".log"}:
        return read_text_file(path)
    if suffix == ".pdf":
        try:
            import pdfplumber
            with pdfplumber.open(path_obj) as pdf:
                text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            return text, "pdfplumber"
        except ImportError:
            try:
                import PyPDF2
                with path_obj.open("rb") as handle:
                    reader = PyPDF2.PdfReader(handle)
                    text = "\n".join(page.extract_text() or "" for page in reader.pages)
                return text, "PyPDF2"
            except ImportError as exc:
                raise RuntimeError("缺少 PDF 解析库：请安装 pdfplumber 或 PyPDF2。") from exc
    if suffix == ".docx":
        try:
            import docx
        except ImportError as exc:
            raise RuntimeError("缺少 Word 解析库：请安装 python-docx。") from exc
        doc = docx.Document(path_obj)
        return "\n".join(p.text for p in doc.paragraphs), "python-docx"
    if suffix == ".doc":
        raise RuntimeError("暂不直接读取旧 .doc 文件，请先另存为 .docx 或 .txt。")
    raise RuntimeError(f"暂不支持该文件格式：{suffix or '无扩展名'}")


class NidoFunctionLawyerEngine:
    def __init__(self, dimensions):
        self.dimensions = dimensions

    def run(self, mode, jurisdiction, case_text, my_position, opponent_position, selected, options):
        run_id = _dt.datetime.now().strftime("nido_strikeover_v4_%Y%m%d_%H%M%S")
        case_key = short_hash("\n".join([mode, jurisdiction, case_text, my_position, opponent_position]))
        selected_dims = [d for d in self.dimensions if d[0] in selected]
        signals = self.scan(case_text, my_position, opponent_position, mode)
        stance_frame = self.build_stance_frame(my_position, opponent_position, mode)
        persona_anchors = self.build_persona_anchors(selected_dims)
        signals["stance_frame"] = stance_frame
        signals["persona_anchors"] = persona_anchors
        signals["options"] = options
        r1 = [self.attack(name, desc, signals, mode) for name, desc in selected_dims]
        if options.get("strategy_enhanced"):
            r1 = [self.apply_strategy_enhancement(item) for item in r1]
        r2 = [self.defend(item, signals, mode) for item in r1]
        r3 = [self.counter(item, signals, mode) for item in r2]
        r4 = [self.final(item, signals, mode) for item in r3]
        stance_reviews = self.review_stance_continuity(r1, r2, r3, r4, stance_frame, persona_anchors)
        review = self.review(selected_dims, signals, mode, options, stance_reviews)
        p4_trace = self.build_execution_trace(selected_dims, signals, options)
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
                "rule": "本地引擎负责状态、路由、审查和最终写回；外部模型只在授权时作为辅助。",
            },
            "selected_dimensions": [name for name, _ in selected_dims],
            "stance_frame": stance_frame,
            "persona_anchors": persona_anchors,
            "stance_reviews": stance_reviews,
            "execution_trace": p4_trace,
            "signals": signals,
            "rounds": {
                "round1_opponent_attack": r1,
                "round2_my_rebuttal": r2,
                "round3_opponent_response": r3,
                "round4_my_final": r4,
                "final_reviewer": review,
            },
        }

    def build_execution_trace(self, selected_dims, signals, options):
        profile = signals.get("profile", {}).get("dispute_type", "")
        if profile == "consumer_return_acl":
            base_route = "case_profile_first"
            route_note = "matched saved consumer-return profile before generic analysis"
            profile_hit_count = len(selected_dims)
            field_compute_count = 0
        else:
            base_route = "dimension_signal_first"
            route_note = "used local dimension signal before optional expression layer"
            profile_hit_count = 0
            field_compute_count = len(selected_dims)
        strategy_count = len(selected_dims) if options.get("strategy_enhanced") else 0
        cloud_call_count = int(options.get("cloud_parse_count") or 0)
        return {
            "patent4_like_path_active": True,
            "customer_summary": "Local case and profile signals are checked before generic analysis for the current review workflow.",
            "counts": {
                "selected_dimensions": len(selected_dims),
                "profile_hits": profile_hit_count,
                "field_compute_routes": field_compute_count,
                "strategy_enhanced_routes": strategy_count,
                "cloud_calls_for_case_text": cloud_call_count,
            },
            "route_order": [
                "case_structuring",
                "dimension_or_profile_signal",
                "local_attack_defense_execution",
                "optional_strategy_enhancement",
                "stance_continuation_review",
            ],
                        "review_notes": [
                "case profile",
                "evidence gap pattern",
                "attack dimension",
                "rebuttal pattern",
                "missing material request",
                "residual risk label",
            ],
            "strategy_enhanced": bool(options.get("strategy_enhanced")),
            "dimensions": [
                {
                    "dimension": name,
                    "route": base_route,
                    "route_note": route_note,
                    "direct_cloud_call": False,
                }
                for name, _ in selected_dims
            ],
        }

    def build_stance_frame(self, my_position, opponent_position, mode):
        my_core = compact(my_position, 260)
        opponent_core = compact(opponent_position, 260)
        return {
            "purpose": "锁定双方总立场，避免攻防中折中、串位或替对方补强。",
            "my_client_frame": {
                "role": "我方代理",
                "global_position": my_core,
                "must_protect": [
                    "不把对方叙事当成中立事实",
                    "不主动替对方补足证明责任",
                    "不轻易承认对方关键前提",
                    "所有补证、限缩和替代论证都服务于我方客户利益",
                ],
            },
            "opponent_frame": {
                "role": "反方攻击",
                "global_attack_direction": opponent_core,
                "allowed_behavior": [
                    "从对方利益最大化角度寻找漏洞",
                    "把我方事实、证据、法律适用、因果链和叙事具体化追问",
                    "不需要替我方公平评价，只负责找可攻击点",
                ],
            },
            "round_rules": {
                "R1": "反方只负责攻击我方立场，输出对方会怎么问、怎么逼证据、怎么压缩我方空间。",
                "R2": "我方只负责维护客户立场，压住对方证明责任，寻找反击和补证路径。",
                "R3": "反方继续攻击 R2 反驳中的漏洞，不接受我方解释为当然成立。",
                "R4": "我方最终固定可守立场，保留补证、限缩、替代论证和庭审准备路径。",
            },
            "mode": mode,
        }

    def build_persona_anchors(self, selected_dims):
        anchors = {}
        for name, _ in selected_dims:
            anchor = DIMENSION_PERSONA_ANCHORS.get(name, {})
            anchors[name] = {
                "name": name,
                "past_statement": anchor.get("memory", f"我曾经说过：从{name}切入时，不能替对方补强，必须追到底层漏洞。"),
                "attack_habit": anchor.get("habit", f"围绕{name}把对方主张具体化追问。"),
                "red_line": anchor.get("boundary", "不向中间折中，不主动承认对方关键前提。"),
                "stance_rule": "反方使用该画像时只负责攻击；我方使用该画像时只负责把攻击转成防守、补证和反击路径。",
            }
        return anchors

    STRATEGY_PRIMITIVES = {
        "集中优势": "不要平均攻击所有点，优先集中火力打会牵动全案的关键节点。",
        "避实击虚": "不正面否认对方最强口号，而攻击其适用前提、证明门槛和边界条件。",
        "断其粮道": "先切断对方证据供给：原始文件、连续性、来源、封条、签收、第三方验证缺一项，就降低证明力。",
        "先为不可胜": "先建立最坏情形下仍能守住的防线，再争取完全胜诉。",
        "知可以战": "证据不足的高风险标签不硬打，只作为压力线索或备选路径。",
        "以迂为直": "不直接说对方撒谎，而通过缺失证据、替代因果和证明责任逼对方自证。",
        "夺其势": "把对方有利叙事改写为证据完整性、诚信交易、因果链和补救比例的审查框架。",
        "知己知彼": "预设对方最强证据成立，反推我方仍能维持的备用防线和最低可接受结果。",
    }

    STRATEGY_DIMENSION_MAP = {
        "事实质疑": ["断其粮道", "集中优势"],
        "法律适用": ["避实击虚"],
        "先例对抗": ["避实击虚", "知可以战"],
        "逻辑漏洞": ["以迂为直", "集中优势"],
        "程序瑕疵": ["断其粮道"],
        "损害因果关系": ["以迂为直", "避实击虚"],
        "量化争议": ["先为不可胜", "断其粮道"],
        "举证责任": ["断其粮道", "避实击虚"],
        "法律文本解释": ["避实击虚"],
        "过失比较": ["以迂为直"],
        "公共政策": ["夺其势"],
        "逆向思维": ["知己知彼", "先为不可胜"],
        "跨法域武器": ["知可以战"],
        "反事实推演": ["以迂为直"],
        "比例原则检验": ["先为不可胜", "避实击虚"],
        "叙事解构": ["夺其势"],
        "系统性风险放大": ["夺其势"],
        "沉默证据": ["断其粮道"],
    }

    def apply_strategy_enhancement(self, item):
        enhanced = dict(item)
        dimension = enhanced.get("dimension", "")
        primitives = self.STRATEGY_DIMENSION_MAP.get(dimension, ["集中优势"])
        strategy_text = " ".join(self.STRATEGY_PRIMITIVES[name] for name in primitives)
        enhanced["strategy_enhanced"] = True
        enhanced["strategy_primitives"] = primitives
        enhanced["strategy_layer"] = strategy_text
        enhanced["attack"] = (enhanced.get("attack", "") + "\n策略增强：" + strategy_text).strip()
        enhanced["question"] = (
            enhanced.get("question", "")
            + " 同时要求对方说明：如果关键证据链或适用前提不能补齐，其主张还剩哪一条可独立成立的路径？"
        ).strip()
        return enhanced

    def scan(self, case_text, my_position, opponent_position, mode):
        combined_raw = "\n".join([case_text, my_position, opponent_position])
        combined = combined_raw.lower()
        missing = []
        if not re.search(r"(证据|evidence|附件|合同|记录|日志|测试|数据|报告)", combined):
            missing.append("关键证据类型未明确")
        if not re.search(r"(时间|日期|deadline|before|after|when|202\d|20\d\d)", combined):
            missing.append("关键时间线未明确")
        if not re.search(r"(损失|损害|金额|damage|loss|cost|费用|利润)", combined):
            missing.append("损害或商业后果未明确")
        patent_gaps = []
        if mode == "专利无效攻防":
            for term in ["新颖性", "创造性", "support", "best method", "清楚性", "enablement", "claim"]:
                if term.lower() not in combined:
                    patent_gaps.append(term)
        weak = [p for p in ["可能没办法", "只能", "没有办法", "我承认", "确实不足", "perhaps", "maybe"] if p in combined]
        profile = self.extract_case_profile(combined_raw)
        return {
            "case_summary": compact(case_text),
            "my_position_summary": compact(my_position),
            "opponent_position_summary": compact(opponent_position),
            "missing_evidence": missing,
            "patent_terms_to_check": patent_gaps,
            "weak_language_hits": weak,
            "profile": profile,
            "risk_level": "high" if missing or patent_gaps else "medium",
        }

    def extract_case_profile(self, text):
        lower = text.lower()

        def has_any(*terms):
            return any(term.lower() in lower or term in text for term in terms)

        evidence = []
        for label, terms in [
            ("拆箱视频", ["拆箱视频", "unboxing video"]),
            ("出货前质检记录", ["质检记录", "出货前", "quality control", "qc record"]),
            ("聊天记录", ["聊天记录", "chat", "message"]),
            ("物流/签收记录", ["物流", "签收", "快递", "delivery", "courier"]),
            ("外包装/封条", ["外包装", "封条", "seal", "package"]),
            ("第三方鉴定/公证", ["第三方", "鉴定", "公证", "expert report"]),
            ("退货历史", ["6个月", "三次退货", "3次退货", "退货记录"]),
        ]:
            if has_any(*terms):
                evidence.append(label)

        legal_refs = []
        for label, terms in [
            ("ACL Section 54", ["acl", "section 54", "澳大利亚消费者法"]),
            ("7天无理由/退货期限", ["7天", "七天", "无理由", "退货期限"]),
            ("下单日起算", ["下单日", "下单日起算"]),
            ("收货日起算", ["收货日", "收货日起算"]),
            ("合理时间", ["合理时间", "reasonable time"]),
        ]:
            if has_any(*terms):
                legal_refs.append(label)

        issues = []
        for label, terms in [
            ("手机划痕", ["手机", "划痕", "scratch"]),
            ("退货退款", ["退货", "退款", "return", "refund"]),
            ("律师费", ["律师费", "legal costs", "attorney"]),
            ("商誉损失", ["商誉", "信誉", "reputation"]),
            ("开机使用", ["开机", "使用后", "used"]),
            ("收货次日通知", ["收货次日", "次日通知", "next day"]),
        ]:
            if has_any(*terms):
                issues.append(label)

        dispute_type = "general"
        if has_any("acl", "澳大利亚消费者法", "section 54", "退货", "退款", "划痕", "手机"):
            dispute_type = "consumer_return_acl"
        elif has_any("claim", "support", "best method", "权利要求", "专利"):
            dispute_type = "patent"
        elif has_any("合同", "违约", "付款", "履行", "contract", "breach"):
            dispute_type = "contract"
        return {
            "dispute_type": dispute_type,
            "evidence": evidence,
            "legal_refs": legal_refs,
            "issues": issues,
        }

    def attack(self, name, desc, signals, mode):
        if signals.get("profile", {}).get("dispute_type") == "consumer_return_acl":
            return self.consumer_return_attack(name, signals)
        persona = signals.get("persona_anchors", {}).get(name, {})
        stance_frame = signals.get("stance_frame", {})
        opponent_direction = stance_frame.get("opponent_frame", {}).get("global_attack_direction", "")
        if name in {"事实质疑", "沉默证据"} and signals["missing_evidence"]:
            finding = "对方可以抓住证据空白，要求补齐：" + "；".join(signals["missing_evidence"])
        elif mode == "专利无效攻防" and name in {"法律适用", "先例对抗", "法律文本解释"}:
            finding = "对方会集中攻击权利要求与说明书支持、best method、清楚性和现有技术差异。"
        elif name == "逆向思维":
            finding = "从对方视角看，我方最危险处不是立场本身，而是关键前提是否可证明。"
        elif name == "系统性风险放大":
            finding = "对方会把单点漏洞放大为系统不可靠、不可复现或不可审计。"
        else:
            finding = desc
        return {
            "dimension": name,
            "role": "opponent_attack",
            "global_stance": opponent_direction,
            "persona_anchor": persona,
            "targeting": "我方核心立场、证据链或说明文字中最容易被具体化追问的位置",
            "finding": finding,
            "question": self.attack_question(name, finding, mode),
            "attack": self.attack_line(name, finding, mode),
        }

    def consumer_return_attack(self, name, signals):
        profile = signals.get("profile", {})
        stance_frame = signals.get("stance_frame", {})
        opponent_direction = stance_frame.get("opponent_frame", {}).get("global_attack_direction", "")
        persona = signals.get("persona_anchors", {}).get(name, {})
        evidence = profile.get("evidence") or ["对方证据"]
        legal_refs = profile.get("legal_refs") or ["消费者保护规则/退货条款"]
        issues = profile.get("issues") or ["商品瑕疵和退货期限"]
        ev = "、".join(evidence)
        law = "、".join(legal_refs)
        issue = "、".join(issues)
        templates = {
            "事实质疑": (
                "对方拆箱视频和瑕疵事实",
                f"请对方证明{ev}具备连续性、原始性和未剪辑性；若不能排除摆拍、编辑或开箱后使用，如何证明划痕在交付时已经存在？",
                f"围绕{issue}，攻击重点是视频/照片是否完整、是否显示外包装和封条状态、是否能排除物流或收货后使用造成的介入因素。",
            ),
            "法律适用": (
                law,
                f"对方援引{law}时，能否证明瑕疵在交付时已存在、通知在合理时间内作出，并且退货期限解释优先于页面明示条款？",
                "把 ACL/退货规则拆成前提：商品不合格、瑕疵交付时存在、通知及时、补救方式相称；缺一项就不能直接跳到全额退货。",
            ),
            "先例对抗": (
                "合理退货条件和电商条款",
                "若页面已明示退货期限从下单日计算，对方凭什么把它改写成收货日起算？是否有直接先例否定该类明示条款？",
                "攻击方向是把对方的一般消费者保护主张，压回到本案的页面提示、点击同意、合理时间和条款有效性。",
            ),
            "逻辑漏洞": (
                "从发现划痕倒推交付瑕疵",
                "收货后发现划痕，为什么必然等于出货前存在？物流碰撞、外包装破损、收货后开机使用是否都被排除？",
                "核心攻击是因果跳跃：对方把“发现结果”直接倒推为“交付原因”，中间介入因素没有排除。",
            ),
            "程序瑕疵": (
                "退货通知时间和退货流程",
                "对方是否在明示退货期限和平台流程内提交完整申请？如果没有，为什么商家必须接受迟延或不完整退货？",
                "程序攻击集中在通知时间、申请形式、证据提交节点和是否遵守退货流程。",
            ),
            "损害因果关系": (
                "退款、律师费和商家责任",
                "即使存在划痕，为什么损害一定由商家造成？律师费又为什么是商家行为的直接后果，而不是对方自行起诉选择造成？",
                "攻击因果链：合格出货记录、物流/使用介入因素、退货流程不完整，都会削弱退款和律师费请求。",
            ),
            "量化争议": (
                "退款金额、律师费、商誉损失",
                "对方的律师费、退款范围和损害金额是否有明细、发票、计算表和合理性说明？",
                "量化攻击要求对方把金额拆成价款、维修价值、折价、诉讼成本和可证明损失，不能只报结论。",
            ),
            "举证责任": (
                "划痕交付时存在",
                "谁主张划痕在交付时已存在，谁就要证明；对方除了拆箱视频和聊天记录，还有没有第三方鉴定、物流签收状态或封条证明？",
                "攻击点是证明责任没有完成：投诉时间只能证明“何时投诉”，不能自动证明“瑕疵何时产生”。",
            ),
            "法律文本解释": (
                "7天无理由条款",
                "页面写明的“7天从下单日算”是否清楚、显著、已被点击同意？如果是，对方凭什么单方解释为收货日起算？",
                "文本解释攻击围绕明示条款、合理提示、合同合意和是否违反强制法展开。",
            ),
            "过失比较": (
                "消费者收货检查和使用行为",
                "对方收货后是否立即检查？是否先开机使用？过去退货记录是否显示其注意义务或诚信交易习惯存在问题？",
                "攻击方向是把责任从单一商家责任，拆成消费者检查义务、使用介入和比较过失。",
            ),
            "公共政策": (
                "先用后退和电商确定性",
                "如果任何收货后发现的外观问题都能直接推定为交付瑕疵，是否会鼓励先用后退并提高全体消费者成本？",
                "公共政策攻击把个案扩展为电商退货期限确定性、消费者诚信和商家运营成本。",
            ),
            "逆向思维": (
                "我方最大风险",
                "如果拆箱视频经鉴定为原始连续、且能显示封条和首次开箱，我方还剩哪些防守路径？",
                "逆向攻击承认风险：视频若被证实完整，质检记录和条款解释仍要能独立支撑防守。",
            ),
            "跨法域武器": (
                "平台规则/公平交易监管/滥用退货",
                "是否可以把对方频繁退货、证据不完整和恶意投诉风险，转化为平台规则、监管投诉或诉讼外施压材料？",
                "跨法域攻击只作为策略提示，不默认指控犯罪；重点是平台规则、监管规则和诚信交易义务。",
            ),
            "反事实推演": (
                "没有消费者使用介入时结果是否不同",
                "如果划痕出货前就存在，质检记录为什么没有发现？如果物流造成，责任为什么直接归商家？如果消费者未开机使用，证据链会不会更清楚？",
                "反事实攻击用多个替代原因打断对方单一路径。",
            ),
            "比例原则检验": (
                "全额退款和律师费是否过度",
                "即便存在轻微外观划痕，是否当然达到全额退款加律师费的程度？维修、折价或部分补偿是否更相称？",
                "比例攻击把补救方式从全额退货拉回功能影响、瑕疵程度和替代补救。",
            ),
            "叙事解构": (
                "受害消费者叙事",
                "对方是否选择性展示拆箱视频，却弱化退货历史、开机使用、通知时间和封条/物流状态缺失？",
                "叙事攻击拆掉“弱者维权”的单线故事，改成证据完整性和诚信交易的双向审查。",
            ),
            "系统性风险放大": (
                "退货规则被架空",
                "若法院支持对方解释，是否会让明示退货期限失去确定性，并造成电子产品行业大量人为瑕疵退货？",
                "系统性攻击把个案风险放大到行业规则、价格成本和司法资源。",
            ),
            "沉默证据": (
                "没有出现但应当出现的材料",
                f"如果对方说法真实，为什么没有补充{ev}之外的第三方鉴定、物流签收状态、完整封条、当天照片或证人证言？",
                "沉默证据攻击不是说对方一定撒谎，而是要求其解释关键证据为何缺席。",
            ),
        }
        targeting, question, attack = templates.get(name, (
            issue,
            f"围绕{name}，对方能否把主张具体化到证据、时间线、规则和因果链？",
            f"从{name}角度压缩对方主张，要求其补足可验证材料。",
        ))
        finding = attack
        return {
            "dimension": name,
            "role": "opponent_attack",
            "global_stance": opponent_direction,
            "persona_anchor": persona,
            "targeting": targeting,
            "finding": finding,
            "question": question,
            "attack": attack,
        }

    def attack_question(self, dimension, finding, mode):
        if mode == "专利无效攻防":
            templates = {
                "事实质疑": "请指出每一个核心技术效果对应的原始记录、实验条件和可重复验证来源；没有记录的部分凭什么成立？",
                "法律适用": "你主张的技术特征到底落在说明书哪一段、哪一个实施例、哪一个权利要求元素上？",
                "先例对抗": "现有技术已经公开相近结构时，你如何证明差异不是常规替换或普通组合？",
                "逻辑漏洞": "你的结论是不是从功能效果直接跳到了技术结构，中间缺少可验证步骤？",
                "程序瑕疵": "申请日之前你是否已经知道更具体的实施方式，却没有在文本中充分披露？",
                "法律文本解释": "权利要求中的关键术语边界在哪里？竞争者读完能否知道什么落入、什么不落入？",
                "沉默证据": "如果这个效果真实存在，为什么文本里没有对应数据、对照组或失败边界？",
            }
            return templates.get(dimension, f"围绕{dimension}，请说明文本中哪一处能直接支撑你的核心主张？")
        templates = {
            "事实质疑": "你方主张依赖哪些具体事实？每个事实的来源、时间和证明责任在哪里？",
            "法律适用": "你方引用的规则是否真的覆盖本案事实，还是忽略了例外和适用边界？",
            "逻辑漏洞": "你方从事实到结论之间是否存在跳步、循环论证或偷换概念？",
            "举证责任": "在这个问题上究竟是谁负证明责任？你方是否已经达到证明门槛？",
            "沉默证据": "如果你方说法真实，为什么应当出现的记录、日志、通知或反证没有出现？",
        }
        return templates.get(dimension, f"如果从{dimension}切入，你方最薄弱、最需要证明的地方是什么？")

    def attack_line(self, dimension, finding, mode):
        if mode == "专利无效攻防":
            return f"对方会把“{finding}”具体化为 support、best method、清楚性、现有技术差异或可实施性追问。"
        return f"对方会把“{finding}”具体化为事实、证据、规则适用或因果链追问。"

    def defend(self, attack, signals, mode):
        dimension = attack["dimension"]
        if signals.get("profile", {}).get("dispute_type") == "consumer_return_acl":
            response = self.consumer_return_defense(dimension, signals)
        elif dimension in {"事实质疑", "沉默证据", "举证责任"}:
            response = "不直接退让，先把证据需求拆成清单：事实、时间线、来源、可验证记录、反证缺口。"
        elif mode == "专利无效攻防":
            response = "把攻击点映射到 claim element、实施例、技术效果和替代实施方式，避免只用概念回应。"
        elif dimension in {"逻辑漏洞", "反事实推演"}:
            response = "明确因果链和反事实边界：没有该事实/特征时，结果是否仍成立。"
        else:
            response = "不替对方补强，也不把对方叙事当成中立事实；先压住对方证明责任，再给出我方可补证、可限缩或可替代的防守路径。"
        stance_frame = signals.get("stance_frame", {})
        return {
            "dimension": dimension,
            "role": "my_rebuttal",
            "global_stance": stance_frame.get("my_client_frame", {}).get("global_position", ""),
            "persona_anchor": signals.get("persona_anchors", {}).get(dimension, {}),
            "answer_to": attack.get("attack", attack.get("finding", "")),
            "response": response,
            "needed_material": self.needed_material(dimension, signals, mode),
            "strategy_primitives": attack.get("strategy_primitives", []),
            "strategy_response": self.strategy_response_line(attack.get("strategy_primitives", []), side="my"),
        }

    def strategy_response_line(self, primitives, side):
        if not primitives:
            return ""
        joined = " / ".join(primitives)
        if side == "my":
            return f"针对对方的【{joined}】策略，我方不正面迎合叙事，而是回到证据链、证明责任、适用前提和备用防线。"
        if side == "opponent":
            return f"反方继续沿用【{joined}】策略，压迫我方提交原始材料、解释证据缺口并说明备用路径为何仍成立。"
        return f"最终阶段保留【{joined}】对应防线：主防线、备用防线和补证清单分开陈述。"

    def consumer_return_defense(self, dimension, signals):
        profile = signals.get("profile", {})
        evidence = "、".join(profile.get("evidence") or ["拆箱视频", "质检记录", "物流签收材料"])
        templates = {
            "事实质疑": f"不承认视频当然无效，先要求对方提交原始文件、时间戳、连续帧、封条和物流状态；同时用我方质检记录反证出货状态，形成“视频完整性 vs 质检记录”的证据对照。",
            "法律适用": "把 ACL/消费者保护规则限缩到法定前提：交付时存在瑕疵、合理时间通知、补救方式相称。不否认法律框架存在，但坚决否认对方已满足适用条件。",
            "先例对抗": "不泛称契约自由，改为准备页面截图、下单确认、退货政策提示记录，证明条款已明示且未被强制法排除。",
            "逻辑漏洞": "抓住因果链：发现划痕不等于交付时有划痕。逐项列出物流、开机使用、保存不当等介入因素，要求对方排除。",
            "程序瑕疵": "把退货流程做成时间轴：下单、发货、签收、通知、申请、证据提交。只攻击明确迟延或缺件的节点，避免过度程序化显得不公平。",
            "损害因果关系": "把责任和金额分开：即便存在外观瑕疵，也未必支持律师费或全额退款；要求对方证明损害由我方行为直接造成。",
            "量化争议": "要求律师费账单、维修/折价估算、手机功能影响、商誉损失依据；没有明细则只能作为待证主张。",
            "举证责任": f"坚持谁主张谁举证：对方需证明交付时瑕疵存在。我方用{evidence}回应后，不承担证明消费者未使用造成的无限责任。",
            "法律文本解释": "把“7天”争议回到页面文字和提示显著性。若条款确实清楚，主张应尊重明示条款；若提示不够明显，则准备替代防守：合理时间和瑕疵因果仍未证明。",
            "过失比较": "谨慎使用退货历史，不把消费者标签化；只把收货检查、开机使用、证据保存义务作为比较过失或因果减弱因素。",
            "公共政策": "公共政策只作辅助，不替代证据。主线仍是证据完整性、条款明示和补救比例。",
            "逆向思维": "预设最坏情况：若视频被鉴定为连续真实，立刻转入补救比例、条款期限、开机使用和律师费不合理四条防线。",
            "跨法域武器": "避免直接上升到刑事或恶意投诉指控；先用平台规则、监管投诉和诚信交易义务作为压力工具，措辞保守。",
            "反事实推演": "列三条替代路径：出货前存在、物流造成、收货后造成。逐项要求证据，防止对方只拿一个结果反推唯一原因。",
            "比例原则检验": "即便瑕疵成立，也把补救从全额退款拉回折价、维修、换货或部分补偿；律师费单独审查。",
            "叙事解构": "拆掉“受害消费者 vs 无良商家”的单线叙事，换成“证据是否完整、条款是否明示、瑕疵何时产生”的三问题结构。",
            "系统性风险放大": "系统风险只在结尾使用：若法院忽视证据完整性和条款明示，会提高电商不确定性。不要让它盖过本案事实。",
            "沉默证据": "把缺失证据列成表：第三方鉴定、完整封条、物流签收状态、当天照片、原始视频。每缺一项，对应降低哪一段证明力。",
        }
        return templates.get(dimension, "把对方攻击拆成事实、证据、规则和补救四段，逐段回应，不做泛泛否认。")

    def counter(self, defense, signals, mode):
        dimension = defense["dimension"]
        needed = defense.get("needed_material") or []
        if isinstance(needed, str):
            needed = [needed]
        answer_to = defense.get("answer_to", "")
        response = defense.get("response", "")
        profile = signals.get("profile", {})

        if profile.get("dispute_type") == "consumer_return_acl":
            counter, risk, pressure = self.consumer_return_counter(dimension, answer_to, response, needed)
        elif mode == "专利无效攻防":
            counter, risk, pressure = self.patent_counter(dimension, answer_to, response, needed)
        else:
            counter, risk, pressure = self.generic_counter(dimension, answer_to, response, needed)

        return {
            "dimension": dimension,
            "role": "opponent_response",
            "counter": counter,
            "residual_risk": risk,
            "pressure_point": pressure,
            "attack_basis": response,
            "missing_material_target": needed[:6],
            "strategy_primitives": defense.get("strategy_primitives", []),
            "strategy_response": self.strategy_response_line(defense.get("strategy_primitives", []), side="opponent"),
        }

    def consumer_return_counter(self, dimension, answer_to, response, needed):
        missing = "、".join(needed[:4]) if needed else "原始视频、质检记录、物流状态和条款记录"
        templates = {
            "事实质疑": (
                "对方不会只听我方说“要核验原始视频”，而会继续压：消费者收货后次日即发现划痕这一时间点如何解释？"
                "我方质检记录是否能对应到同一台手机、同一出货批次、同一时间点？如果对应不上，对方会说内部质检不能压过开箱状态。",
                "high" if needed else "medium",
                "把质检记录和具体机器、具体出货节点绑定起来。",
            ),
            "法律适用": (
                "对方会说我方把 ACL 前提说得过窄：页面退货期限不能当然排除 consumer guarantee。"
                "他们会继续追问：即便“7天从下单日算”成立，是否也只能限制无理由退货，而不能排除不合格商品的法定补救？",
                "high",
                "区分无理由退货条款与不合格商品法定补救。",
            ),
            "先例对抗": (
                "对方会要求我方拿出直接支持“下单日起算且可压过收货后即时瑕疵投诉”的案例或监管指引。"
                "如果只有平台惯例，对方会说那只是商业做法，不是法律规则。",
                "medium",
                "把平台惯例升级为可引用规则或直接案例。",
            ),
            "逻辑漏洞": (
                "对方会反攻：物流碰撞、收货后使用、保存不当都只是替代可能性，不是已证明事实。"
                "他们会说我方只是列出“可能有别的原因”，但没有证明这些介入因素实际发生。",
                "high",
                "替代原因必须落到具体证据，不能停留在可能性。",
            ),
            "程序瑕疵": (
                "对方会说其发现瑕疵后已经及时联系，程序流程不能压倒消费者保障。"
                "他们会继续追问：退货流程是否在下单时清楚、显著、可保存地提示？迟延是否真的造成商家防御困难？",
                "medium",
                "证明流程提示清楚且对本案实体权利有影响。",
            ),
            "损害因果关系": (
                "对方会把因果链压回商家控制范围：商品到手即有划痕，商家最有能力证明出货状态。"
                "他们还会说律师费和维权成本来自商家拒绝补救，而不是消费者任意起诉。",
                "medium",
                "把损害发生点从“收货发现”拉回到物流/使用/证明链。",
            ),
            "量化争议": (
                "对方会说金额争议不改变退货权基础：手机价款明确，退款金额天然可算；律师费明细可以后补。"
                "反过来，我方商誉损失若没有计算表，会被说成更空泛。",
                "medium",
                "别只质疑对方金额，也要补我方反诉量化基础。",
            ),
            "举证责任": (
                "对方会说拆箱视频和次日投诉已完成初步证明，举证负担转向商家说明质检记录与具体机器的对应关系。"
                "他们会攻击我方把证明责任过度推给消费者，要求其证明所有不存在的介入因素。",
                "high",
                "明确消费者证据是否达到初步门槛，以及我方如何反证。",
            ),
            "法律文本解释": (
                "对方会攻击格式条款：下单日起算若实际吞掉运输时间、显著缩短退货窗口，就可能不公平或未充分提示。"
                "他们会要求展示页面位置、字体、勾选过程和用户确认记录。",
                "high",
                "证明条款显著、合理，且不限制法定 consumer guarantee。",
            ),
            "过失比较": (
                "对方会说开机检查是正常验货行为，不等于造成划痕；过去退货记录也不能直接证明本案不诚信。"
                "他们会要求排除人格化攻击，把争点拉回本次瑕疵证据。",
                "medium",
                "把退货历史和本案诚信/因果的连接讲清楚。",
            ),
            "公共政策": (
                "对方会反称消费者保障的公共政策高于商家降低退货成本的利益：若支持商家用内部质检和格式期限拒绝即时瑕疵投诉，会削弱消费者保护。",
                "medium",
                "公共政策不能只讲商家成本，也要回应消费者保护。",
            ),
            "逆向思维": (
                "对方会抓住我方备用路线：既然承认视频若完整会增强证明力，就会要求先做视频鉴定。"
                "一旦视频通过，我方就必须解释为什么仍可限缩补救，而不能继续否认证据。",
                "high",
                "为视频鉴定通过后的次级防线准备比例/补救方案。",
            ),
            "跨法域武器": (
                "对方会说监管、平台投诉或诚信施压与商品是否合格无关，甚至显示商家试图压制消费者投诉。"
                "他们会要求法院不要把诉讼外压力当成实体抗辩。",
                "medium",
                "跨法域/平台策略只能辅助，不能替代本案实体证明。",
            ),
            "反事实推演": (
                "对方会说多种替代原因只是可能性：质检未发现不代表不存在，物流可能造成也不代表消费者承担，开机使用也不等于造成划痕。"
                "每条反事实路径都需要证据落点。",
                "high",
                "把反事实从“可能”变成有证据的替代链。",
            ),
            "比例原则检验": (
                "对方会说手机是新机，外观瑕疵影响商品价值和购买选择，全额退款仍可能相称。"
                "他们会追问为什么消费者必须接受维修或折价，而不能解除交易。",
                "medium",
                "准备功能影响、瑕疵程度和替代补救的比例表。",
            ),
            "叙事解构": (
                "对方会把我方叙事解构为污名化消费者：用退货历史和开机使用转移本案瑕疵核心。"
                "他们会要求回到本次交易证据，而不是消费者身份标签。",
                "medium",
                "叙事攻击必须服务证据链，不能变成人格攻击。",
            ),
            "系统性风险放大": (
                "对方会反击：如果支持商家用下单日起算和内部质检压倒即时投诉，会让运输时间吞掉退货期，系统性削弱电商消费者保障。",
                "medium",
                "回应“消费者保障被系统性削弱”的反向风险。",
            ),
            "沉默证据": (
                f"对方会把沉默证据反打给商家：若出货前真的无划痕，为什么缺少更完整的{missing}？"
                "为什么没有设备序列号对应、出货照片、质检视频、包装封条记录和物流交接状态？",
                "high" if needed else "medium",
                "沉默证据要双向列，不要只列消费者缺失。",
            ),
        }
        return templates.get(dimension, self.generic_counter(dimension, answer_to, response, needed))

    def patent_counter(self, dimension, answer_to, response, needed):
        missing = "、".join(needed[:4]) if needed else "说明书原文定位和技术效果数据"
        if dimension in {"事实质疑", "沉默证据", "举证责任"}:
            return (f"对方会继续要求把每个技术效果压到原文段落和原始记录：没有{missing}，就会主张只是申请后的解释或商业包装。", "high", "补 claim/support/evidence 三列表。")
        if dimension in {"法律适用", "法律文本解释", "先例对抗"}:
            return ("对方会把争点压到 support、best method、清楚性和现有技术差异：要求说明每个 claim element 的原文根、实施例和可替代边界。", "high", "把权利要求元素逐条定位到说明书。")
        if dimension in {"逻辑漏洞", "反事实推演"}:
            return ("对方会攻击从功能效果跳到技术结构：即使结果好，也要证明该结果由权利要求中的具体结构造成，而不是普通自动化、RAG、agent 或本地 LLM 常规组合。", "high", "建立结构-效果因果链。")
        return self.generic_counter(dimension, answer_to, response, needed)

    def generic_counter(self, dimension, answer_to, response, needed):
        missing = "、".join(needed[:4]) if needed else "关键证据"
        if dimension in {"事实质疑", "沉默证据", "举证责任"}:
            return (f"对方会继续把反驳压回证据原件和时间线：没有{missing}，会说我方只是把事实重新包装，没有完成证明。", "medium", "补原件、时间线、来源和连续性。")
        if dimension in {"法律适用", "法律文本解释", "先例对抗"}:
            return ("对方会要求指出直接规则、条文、案例或合同文本依据；如果只是一般原则，会说我方没有把原则落到本案。", "medium", "补规则出处和本案适用桥梁。")
        if dimension in {"逻辑漏洞", "反事实推演", "损害因果关系"}:
            return ("对方会攻击替代解释只是可能性：如果没有证据证明替代链真实发生，就不能打断对方主张的因果路径。", "medium", "把替代解释变成可证明的替代原因。")
        if dimension in {"量化争议", "比例原则检验"}:
            return ("对方会说金额、比例或风险可以后补，不能因此推翻基础权利；同时追问我方自己的金额和比例依据是否更薄。", "medium", "补金额、比例、样本和替代补救表。")
        if dimension in {"公共政策", "系统性风险放大"}:
            return ("对方会要求量化法律效果或行业影响，否则公共政策论点容易被视为口号；还会提出反向公共政策叙事。", "medium", "准备反向政策回应和量化依据。")
        return ("对方会继续逼问边界：这套说法在哪些事实条件、证据条件或法律条件下不成立？若边界说不清，就会被攻击为事后包装。", "low", "给出适用边界和例外条件。")

    def final(self, counter, signals, mode):
        if counter["residual_risk"] == "medium":
            final = "最终陈述不硬说无风险，而是把风险转成可补证、可审查、可限缩的待办。"
        else:
            final = "最终陈述强调结构稳定性、证据路径和对方攻击未能击穿核心链条。"
        return {
            "dimension": counter["dimension"],
            "role": "my_final",
            "final_position": final,
            "trial_note": f"{counter['dimension']}：准备一页式回应和证据索引。",
            "strategy_primitives": counter.get("strategy_primitives", []),
            "strategy_response": self.strategy_response_line(counter.get("strategy_primitives", []), side="final"),
        }

    def needed_material(self, dimension, signals, mode):
        material = []
        if signals.get("profile", {}).get("dispute_type") == "consumer_return_acl":
            if dimension in {"事实质疑", "沉默证据", "举证责任", "逻辑漏洞"}:
                material.extend(["原始拆箱视频文件", "出货前质检记录", "物流签收/外包装状态", "封条照片或说明"])
            if dimension in {"法律适用", "法律文本解释", "程序瑕疵"}:
                material.extend(["退货政策页面截图", "下单确认记录", "ACL Section 54 / consumer guarantee 检索结果", "退货申请时间轴"])
            if dimension in {"损害因果关系", "量化争议", "比例原则检验"}:
                material.extend(["律师费明细", "维修/折价估算", "手机功能检测记录", "退款金额计算表"])
        if dimension in {"事实质疑", "沉默证据", "举证责任"}:
            material.extend(signals["missing_evidence"])
        if mode == "专利无效攻防" and dimension in {"法律适用", "先例对抗", "法律文本解释"}:
            material.extend(["claim chart", "support table", "prior-art difference table"])
        return list(dict.fromkeys([m for m in material if m]))

    def review_stance_continuity(self, r1, r2, r3, r4, stance_frame, persona_anchors):
        drift_terms = ["公平地说", "双方都有道理", "各退一步", "折中", "中立看", "我方也应承认", "对方说得有道理"]
        opponent_help_terms = ["替对方补充", "对方可以进一步证明", "帮助对方", "主动补足对方", "对方若补强"]
        my_protect = stance_frame.get("my_client_frame", {}).get("must_protect", [])
        reviews = []

        def check_text(text, side, dimension):
            hits = []
            for term in drift_terms:
                if term in text:
                    hits.append(f"疑似折中/中立化：{term}")
            for term in opponent_help_terms:
                if term in text:
                    hits.append(f"疑似替对方补强：{term}")
            my_defense_terms = ["证明责任", "补证", "限缩", "反击", "材料", "证据", "防守", "回应", "准备", "要求", "记录", "质检", "原始"]
            opponent_attack_terms = ["漏洞", "证明", "攻击", "追问", "逼问", "要求", "材料", "边界", "事后解释", "不能提交", "风险"]
            if side == "my" and not any(term in text for term in my_defense_terms):
                hits.append("我方回应缺少证明责任、补证、限缩或反击路径")
            if side == "opponent" and not any(term in text for term in opponent_attack_terms):
                hits.append("反方攻击缺少具体追问或漏洞指向")
            anchor = persona_anchors.get(dimension, {})
            if anchor and anchor.get("red_line") and len(text.strip()) < 20:
                hits.append("维度画像锚未充分展开")
            return hits

        for item in r1:
            text = " ".join(str(item.get(k, "")) for k in ("targeting", "finding", "question", "attack"))
            hits = check_text(text, "opponent", item.get("dimension", ""))
            reviews.append({
                "round": "R1",
                "dimension": item.get("dimension", ""),
                "side": "反方攻击",
                "status": "warning" if hits else "locked",
                "findings": hits or ["反方保持攻击立场，未发现明显折中。"],
            })
        for item in r2:
            text = " ".join(str(item.get(k, "")) for k in ("answer_to", "response", "needed_material"))
            hits = check_text(text, "my", item.get("dimension", ""))
            reviews.append({
                "round": "R2",
                "dimension": item.get("dimension", ""),
                "side": "我方反驳",
                "status": "warning" if hits else "locked",
                "findings": hits or ["我方保持客户立场，未发现明显替对方补强。"],
            })
        for item in r3:
            text = str(item.get("counter", ""))
            hits = check_text(text, "opponent", item.get("dimension", ""))
            reviews.append({
                "round": "R3",
                "dimension": item.get("dimension", ""),
                "side": "反方继续追问",
                "status": "warning" if hits else "locked",
                "findings": hits or ["反方继续保持追问姿态。"],
            })
        for item in r4:
            text = " ".join(str(item.get(k, "")) for k in ("final_position", "trial_note"))
            hits = check_text(text, "my", item.get("dimension", ""))
            reviews.append({
                "round": "R4",
                "dimension": item.get("dimension", ""),
                "side": "我方最终固定",
                "status": "warning" if hits else "locked",
                "findings": hits or ["我方最终立场保持固定。"],
            })
        warning_count = sum(1 for x in reviews if x["status"] == "warning")
        return {
            "overall": "warning" if warning_count else "locked",
            "warning_count": warning_count,
            "must_protect": my_protect,
            "items": reviews,
        }

    def review(self, selected_dims, signals, mode, options, stance_reviews=None):
        items = []
        if signals["missing_evidence"]:
            items.append("先补证据索引：" + "；".join(signals["missing_evidence"]))
        if mode == "专利无效攻防":
            items.append("准备 claim element 对照表、support 表、现有技术差异表。")
        if signals["weak_language_hits"]:
            items.append("清理退让性措辞：" + "；".join(signals["weak_language_hits"]))
        if stance_reviews and stance_reviews.get("warning_count"):
            items.append(f"复查立场延续：发现 {stance_reviews['warning_count']} 个可能折中、替对方补强或输出过弱的位置。")
        else:
            items.append("立场延续复审：双方总立场保持锁定，未发现明显向中间对齐。")
        items.append("每个维度保留一句最强攻击、一句最短防守、一条补证动作。")
        return {
            "reviewer_role": "nido_local_reviewer",
            "selected_dimension_count": len(selected_dims),
            "frame_count": len(selected_dims) * 2,
            "top_trial_preparation": items,
            "capitulation_scan": "发现退让措辞" if signals["weak_language_hits"] else "未发现明显退让措辞",
            "stance_continuity": stance_reviews or {},
            "local_only": options.get("local_only", True),
            "note": "本版评委只做本地复审；云端语言润色、真实判例/API以后接入。",
        }


class NidoStrikeOverApp:
    def __init__(self):
        self.root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("1320x820")
        self.root.minsize(1100, 720)
        self.bg = "#121820"
        self.panel = "#1c2530"
        self.panel2 = "#22303d"
        self.fg = "#edf3f7"
        self.muted = "#9fb1bf"
        self.accent = "#22c7b8"
        self.root.configure(bg=self.bg)
        self.dimension_vars = {}
        self.dnd_available = TkinterDnD is not None
        self.drop_status_var = tk.StringVar()
        self.drag_active = False
        self.engine = NidoFunctionLawyerEngine(DIMENSIONS)
        self.last_state = None
        self.last_run_dir = None
        self.parsed_case = {}
        self.fullscreen_win = None
        self.fullscreen_widgets = {}
        self.setup_style()
        self.build()
        self.setup_drag_drop()

    def setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=self.bg, foreground=self.fg, fieldbackground=self.panel)
        style.configure("TFrame", background=self.bg)
        style.configure("Panel.TFrame", background=self.panel)
        style.configure("TLabel", background=self.bg, foreground=self.fg)
        style.configure("Panel.TLabel", background=self.panel, foreground=self.fg)
        style.configure("Muted.TLabel", background=self.panel, foreground=self.muted)
        style.configure("TButton", background=self.panel2, foreground=self.fg, padding=6)
        style.configure("Accent.TButton", background=self.accent, foreground="#001b1b", padding=8)
        style.configure("TCheckbutton", background=self.panel, foreground=self.fg)
        style.configure("TCombobox", fieldbackground="#0c1117", background=self.panel2, foreground=self.fg, arrowcolor=self.accent)
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", "#0c1117"), ("!disabled", "#0c1117")],
            foreground=[("readonly", self.fg), ("!disabled", self.fg)],
            selectbackground=[("readonly", "#0c1117")],
            selectforeground=[("readonly", self.fg)],
        )
        style.configure("TNotebook.Tab", background=self.panel2, foreground=self.fg, padding=(12, 6))
        style.map("TNotebook.Tab", background=[("selected", self.accent)], foreground=[("selected", "#001b1b")])

    def build(self):
        header = ttk.Frame(self.root, style="Panel.TFrame", padding=12)
        header.pack(fill=tk.X, padx=10, pady=10)
        ttk.Label(header, text=APP_TITLE, font=("Microsoft YaHei UI", 16, "bold"), style="Panel.TLabel").pack(anchor=tk.W)
        ttk.Label(header, text="旧版 StrikeOver 的18维律师团界面 + Nido本地攻防状态对象。目标不是判谁对错，而是找漏洞、守立场、争取客户最大利益。", style="Muted.TLabel").pack(anchor=tk.W, pady=(4, 0))

        main = ttk.Frame(self.root)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        left = ttk.Frame(main, style="Panel.TFrame", padding=10)
        left.pack(side=tk.LEFT, fill=tk.Y)
        right = ttk.Frame(main, style="Panel.TFrame", padding=10)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))
        self.build_left(left)
        self.build_right(right)

    def build_left(self, parent):
        ttk.Label(parent, text="Step 1：执行资源 / 辅助模型", font=("Microsoft YaHei UI", 11, "bold"), style="Panel.TLabel").pack(anchor=tk.W)
        self.local_only = tk.BooleanVar(value=True)
        self.use_anonymizer = tk.BooleanVar(value=True)
        self.use_case_search = tk.BooleanVar(value=False)
        self.use_cloud_polish = tk.BooleanVar(value=False)
        self.confidentiality_mode = tk.StringVar(value="完全本地保密")
        for text, var in [
            ("本地保密攻防（固定）", self.local_only),
            ("逐轮脱敏 / 去标签", self.use_anonymizer),
            ("判例/API参照（占位）", self.use_case_search),
            ("云端语言润色（占位）", self.use_cloud_polish),
        ]:
            ttk.Checkbutton(parent, text=text, variable=var).pack(anchor=tk.W, pady=2)
        ttk.Separator(parent).pack(fill=tk.X, pady=10)
        ttk.Label(parent, text="Step 2：选择攻防维度", font=("Microsoft YaHei UI", 11, "bold"), style="Panel.TLabel").pack(anchor=tk.W)
        btns = ttk.Frame(parent, style="Panel.TFrame")
        btns.pack(fill=tk.X, pady=(6, 6))
        ttk.Button(btns, text="全选", command=self.select_all).pack(side=tk.LEFT)
        ttk.Button(btns, text="清空", command=self.clear_all).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="维度说明", command=self.show_dimensions).pack(side=tk.LEFT)
        dim_box = tk.Frame(parent, bg=self.panel)
        dim_box.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(dim_box, bg=self.panel, highlightthickness=0, width=360, height=420)
        scrollbar = ttk.Scrollbar(dim_box, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=self.panel)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        for name, _ in DIMENSIONS:
            var = tk.BooleanVar(value=True)
            self.dimension_vars[name] = var
            ttk.Checkbutton(inner, text=name, variable=var, command=self.update_count).pack(anchor=tk.W, pady=1)
        ttk.Separator(parent).pack(fill=tk.X, pady=10)
        self.count_label = ttk.Label(parent, text="", style="Muted.TLabel", wraplength=360)
        self.count_label.pack(anchor=tk.W)
        self.update_count()

    def build_right(self, parent):
        controls = ttk.Frame(parent, style="Panel.TFrame")
        controls.pack(fill=tk.X)
        ttk.Label(controls, text="模式", style="Panel.TLabel").pack(side=tk.LEFT)
        self.mode_var = tk.StringVar(value="专利无效攻防")
        self.mode_combo = ttk.Combobox(controls, textvariable=self.mode_var, values=list(MODE_HINTS), width=18, state="readonly")
        self.mode_combo.pack(side=tk.LEFT, padx=6)
        self.mode_combo.bind("<<ComboboxSelected>>", lambda e: self.mode_hint())
        ttk.Label(controls, text="法域", style="Panel.TLabel").pack(side=tk.LEFT, padx=(14, 0))
        self.jurisdiction_var = tk.StringVar(value="Australia / AU")
        ttk.Entry(controls, textvariable=self.jurisdiction_var, width=18).pack(side=tk.LEFT, padx=6)
        ttk.Label(controls, text="保密", style="Panel.TLabel").pack(side=tk.LEFT, padx=(14, 0))
        self.conf_combo = ttk.Combobox(
            controls,
            textvariable=self.confidentiality_mode,
            values=["完全本地保密", "只发送公开检索词", "授权云端专家"],
            width=16,
            state="readonly",
        )
        self.conf_combo.pack(side=tk.LEFT, padx=6)
        ttk.Button(controls, text="导入材料", command=self.import_material).pack(side=tk.LEFT, padx=(12, 6))
        ttk.Button(controls, text="开始 Nido 攻防", style="Accent.TButton", command=self.run_attack).pack(side=tk.LEFT, padx=6)
        ttk.Button(controls, text="生成公开检索词", command=self.generate_public_search).pack(side=tk.LEFT, padx=6)
        ttk.Button(controls, text="保存当前报告", command=self.save_again).pack(side=tk.LEFT, padx=6)
        ttk.Button(controls, text="打开结果目录", command=self.open_results).pack(side=tk.LEFT, padx=6)
        ttk.Button(controls, text="攻防全屏", command=self.open_fullscreen_outputs).pack(side=tk.LEFT, padx=6)
        ttk.Button(controls, text="逐条反驳", command=self.open_point_rebuttal).pack(side=tk.LEFT, padx=6)
        self.mode_hint_label = ttk.Label(parent, text=MODE_HINTS[self.mode_var.get()], style="Muted.TLabel")
        self.mode_hint_label.pack(anchor=tk.W, pady=(8, 8))
        drop_text = (
            "拖拽案件材料到窗口任意位置，Nido 会本地拆分：案情 / 我方立场 / 对方攻击。"
            if self.dnd_available
            else "当前未安装 tkinterdnd2，拖拽不可用；请先用“导入材料”，同样会自动拆分。"
        )
        self.drop_status_var.set(drop_text)
        self.drop_panel = tk.Frame(parent, bg="#182432", highlightthickness=2, highlightbackground="#314657", padx=14, pady=10)
        self.drop_panel.pack(fill=tk.X, pady=(0, 8))
        self.drop_icon = tk.Label(self.drop_panel, text="⬇", bg="#182432", fg=self.accent, font=("Microsoft YaHei UI", 26, "bold"))
        self.drop_icon.pack(side=tk.LEFT, padx=(0, 12))
        self.drop_label = tk.Label(
            self.drop_panel,
            textvariable=self.drop_status_var,
            bg="#182432",
            fg=self.muted,
            justify=tk.LEFT,
            anchor=tk.W,
            font=("Microsoft YaHei UI", 12, "bold"),
        )
        self.drop_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        meta = ttk.Frame(parent, style="Panel.TFrame")
        meta.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(meta, text="案件名称", style="Panel.TLabel").pack(side=tk.LEFT)
        self.case_name_var = tk.StringVar()
        ttk.Entry(meta, textvariable=self.case_name_var, width=38).pack(side=tk.LEFT, padx=6)

        form = ttk.Frame(parent, style="Panel.TFrame")
        form.pack(fill=tk.X)
        self.case_text = self.labeled_text(form, "案情 / 申请文本 / 争议事实", 5)
        self.my_position = self.labeled_text(form, "我方立场", 4)
        self.opp_position = self.labeled_text(form, "对方立场 / 可能攻击", 4)
        self.case_text.insert("1.0", "这里粘贴或导入案件事实、专利草案、合同争议、旧报告或对方材料。")
        self.my_position.insert("1.0", "我方希望维持核心结构稳定，保留补证和限缩空间，不轻易退让。")
        self.opp_position.insert("1.0", "对方会从新颖性、创造性、支持性、清楚性、best method 和绕开路径攻击。")

        side_frame = ttk.Frame(parent, style="Panel.TFrame")
        side_frame.pack(fill=tk.X, pady=(8, 0))
        pos_frame = tk.Frame(side_frame, bg="#0a3d1f")
        pos_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        neg_frame = tk.Frame(side_frame, bg="#3d1a1a")
        neg_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        tk.Label(pos_frame, text="⚖ 我方panel — 论点与证据", bg="#0a3d1f", fg="#56d364", font=("Microsoft YaHei UI", 11, "bold")).pack(fill=tk.X)
        tk.Label(neg_frame, text="⚖ 对方panel — 论点与证据", bg="#3d1a1a", fg="#f85149", font=("Microsoft YaHei UI", 11, "bold")).pack(fill=tk.X)
        pos_body = tk.Frame(pos_frame, bg=self.panel, padx=8, pady=8)
        pos_body.pack(fill=tk.BOTH, expand=True)
        neg_body = tk.Frame(neg_frame, bg=self.panel, padx=8, pady=8)
        neg_body.pack(fill=tk.BOTH, expand=True)
        self.pos_args = self.labeled_text(pos_body, "我方论点", 3)
        self.pos_ev = self.labeled_text(pos_body, "我方证据（可用 [P1][P2] 标记）", 3)
        self.neg_args = self.labeled_text(neg_body, "对方论点 / 可能攻击", 3)
        self.neg_ev = self.labeled_text(neg_body, "对方证据（可用 [D1][D2] 标记）", 3)

        self.tabs = ttk.Notebook(parent)
        self.tabs.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        self.outputs = {}
        for key, title in [
            ("summary", "总报告"),
            ("r1", "R1 反方攻击"),
            ("r2", "R2 我方反驳"),
            ("r3", "R3 反方回应"),
            ("r4", "R4 我方最终"),
            ("review", "评委复审"),
            ("json", "状态对象 JSON"),
        ]:
            frame = ttk.Frame(self.tabs, style="Panel.TFrame")
            default_fg = {"r1": "#f5a0b8", "r2": "#89b4fa", "r3": "#f5a0b8", "r4": "#89b4fa"}.get(key, self.fg)
            text = scrolledtext.ScrolledText(frame, wrap=tk.WORD, bg="#0c1117", fg=default_fg, insertbackground=self.fg, relief=tk.FLAT)
            self.configure_output_tags(text)
            text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
            self.tabs.add(frame, text=title)
            self.outputs[key] = text

    def configure_output_tags(self, text):
        text.tag_configure("title", foreground="#89dceb", font=("Microsoft YaHei UI", 14, "bold"))
        text.tag_configure("subheader", foreground="#f9e2af", font=("Microsoft YaHei UI", 12, "bold"))
        text.tag_configure("label", foreground="#a6adc8", font=("Microsoft YaHei UI", 11, "bold"))
        text.tag_configure("neg", foreground="#f5a0b8", font=("Microsoft YaHei UI", 11))
        text.tag_configure("pos", foreground="#89b4fa", font=("Microsoft YaHei UI", 11))
        text.tag_configure("note", foreground="#94e2d5", font=("Microsoft YaHei UI", 11))

    def labeled_text(self, parent, label, height):
        ttk.Label(parent, text=label, style="Panel.TLabel").pack(anchor=tk.W, pady=(6, 2))
        text = scrolledtext.ScrolledText(parent, height=height, wrap=tk.WORD, bg="#0c1117", fg=self.fg, insertbackground=self.fg, relief=tk.FLAT)
        text.pack(fill=tk.X)
        return text

    def import_material(self):
        path = filedialog.askopenfilename(
            title="导入案件/专利/旧报告材料",
            filetypes=[
                ("可导入材料", "*.pdf *.docx *.doc *.txt *.md *.json *.py *.csv *.log"),
                ("PDF 文件", "*.pdf"),
                ("Word 文件", "*.docx *.doc"),
                ("文本文件", "*.txt *.md *.log"),
                ("JSON 状态对象", "*.json"),
                ("所有文件", "*.*"),
            ],
        )
        if not path:
            return
        self.load_material_path(path)

    def load_material_path(self, path):
        try:
            text, enc = extract_case_file_text(path)
            loaded_state = None
            if Path(path).suffix.lower() == ".json":
                try:
                    loaded_state = json.loads(text)
                except json.JSONDecodeError:
                    loaded_state = None
            if isinstance(loaded_state, dict) and "rounds" in loaded_state:
                self.last_state = loaded_state
                self.render_state(loaded_state)
                self.tabs.select(self.outputs["json"].master)
                messagebox.showinfo("导入完成", f"已导入 Nido 状态对象：\n{path}")
                return

            parsed = self.auto_split_case_material(text, path, enc)
            self.apply_imported_case(parsed)
            self.tabs.select(0)
            self.drop_status_var.set(f"已导入并本地拆分：{Path(path).name} / {parsed['source_note']}")
            messagebox.showinfo("导入完成", f"已导入并自动拆分：\n{path}")
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc))

    def setup_drag_drop(self):
        if not self.dnd_available:
            return
        targets = [self.root]
        for attr in ("drop_panel", "drop_label", "drop_icon", "case_text", "my_position", "opp_position", "tabs"):
            widget = getattr(self, attr, None)
            if widget is not None:
                targets.append(widget)
        for widget in targets:
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<DropEnter>>", self.on_drag_enter)
                widget.dnd_bind("<<DropLeave>>", self.on_drag_leave)
                widget.dnd_bind("<<Drop>>", self.on_file_drop)
            except Exception:
                pass

    def set_drag_visual(self, active, text=None):
        self.drag_active = active
        bg = "#d8dde3" if active else "#182432"
        fg = "#101820" if active else self.muted
        icon_fg = "#00796b" if active else self.accent
        border = "#22c7b8" if active else "#314657"
        icon = "松开" if active else "⬇"
        if text is None:
            text = "松开鼠标导入案件材料，Nido 会自动拆分案情 / 我方立场 / 对方攻击。" if active else (
                "拖拽案件材料到窗口任意位置，Nido 会本地拆分：案情 / 我方立场 / 对方攻击。"
                if self.dnd_available
                else "当前未安装 tkinterdnd2，拖拽不可用；请先用“导入材料”，同样会自动拆分。"
            )
        self.drop_status_var.set(text)
        for widget in (getattr(self, "drop_panel", None), getattr(self, "drop_label", None), getattr(self, "drop_icon", None)):
            if widget is None:
                continue
            try:
                widget.configure(bg=bg)
            except tk.TclError:
                pass
        try:
            self.drop_panel.configure(highlightbackground=border, highlightcolor=border)
            self.drop_label.configure(fg=fg, font=("Microsoft YaHei UI", 14 if active else 12, "bold"))
            self.drop_icon.configure(text=icon, fg=icon_fg, font=("Microsoft YaHei UI", 22 if active else 26, "bold"))
        except tk.TclError:
            pass

    def on_drag_enter(self, event):
        self.set_drag_visual(True)
        return event.action

    def on_drag_leave(self, event):
        self.set_drag_visual(False)
        return event.action

    def on_file_drop(self, event):
        self.set_drag_visual(False, "正在导入并拆分材料...")
        paths = self.split_drop_paths(event.data)
        if not paths:
            messagebox.showwarning("拖拽为空", "没有识别到可导入文件。")
            self.set_drag_visual(False)
            return
        self.load_material_path(paths[0])
        if len(paths) > 1:
            self.drop_status_var.set(f"已导入第 1 个文件：{Path(paths[0]).name}；其余 {len(paths) - 1} 个暂未导入。")

    def split_drop_paths(self, data):
        try:
            return list(self.root.tk.splitlist(data))
        except Exception:
            return [data.strip().strip("{}")] if data and data.strip() else []

    def apply_imported_case(self, parsed):
        self.parsed_case = parsed
        self.case_name_var.set(parsed.get("case_name", ""))
        self.case_text.delete("1.0", tk.END)
        self.case_text.insert("1.0", parsed["case_text"].strip())
        self.my_position.delete("1.0", tk.END)
        self.my_position.insert("1.0", parsed["my_position"].strip())
        self.opp_position.delete("1.0", tk.END)
        self.opp_position.insert("1.0", parsed["opponent_position"].strip())
        for widget, key in [
            (getattr(self, "pos_args", None), "pos_args"),
            (getattr(self, "pos_ev", None), "pos_ev"),
            (getattr(self, "neg_args", None), "neg_args"),
            (getattr(self, "neg_ev", None), "neg_ev"),
        ]:
            if widget is not None:
                widget.delete("1.0", tk.END)
                widget.insert("1.0", parsed.get(key, "").strip())
        if parsed.get("jurisdiction"):
            self.jurisdiction_var.set(parsed["jurisdiction"])

    def auto_split_case_material(self, raw_text, path, encoding):
        text = raw_text.strip()
        if not text:
            raise RuntimeError("文件中没有提取到文字内容。")
        structured = self.parse_case_structure(text, path)
        buckets = self.collect_case_sections(text)
        buckets.update(self.extract_explicit_sections(text))
        case_text = structured.get("background") or buckets.get("case") or self.first_reasonable_excerpt(text)
        pos_args = structured.get("pos_args") or buckets.get("my") or ""
        pos_ev = structured.get("pos_ev") or ""
        neg_args = structured.get("neg_args") or buckets.get("opponent") or ""
        neg_ev = structured.get("neg_ev") or ""
        my_position = self.compose_side_position("我方", pos_args, pos_ev, buckets.get("my") or self.guess_my_position(text))
        opponent_position = self.compose_side_position("对方", neg_args, neg_ev, buckets.get("opponent") or self.guess_opponent_position(text))
        jurisdiction = structured.get("jurisdiction") or self.guess_jurisdiction(text)
        header = f"【导入文件】{path}\n【读取方式】{encoding}\n\n"
        return {
            "case_name": structured.get("case_name") or Path(path).stem,
            "case_text": header + case_text,
            "my_position": my_position,
            "opponent_position": opponent_position,
            "pos_args": pos_args,
            "pos_ev": pos_ev,
            "neg_args": neg_args,
            "neg_ev": neg_ev,
            "jurisdiction": jurisdiction,
            "source_note": structured.get("source_note") or "本地自动拆案",
        }

    def compose_side_position(self, side, args, evidence, fallback):
        lines = []
        if args.strip():
            lines.extend([f"{side}论点：", args.strip()])
        if evidence.strip():
            lines.extend(["", f"{side}证据：", evidence.strip()])
        if not lines:
            return fallback
        return "\n".join(lines)

    def parse_case_structure(self, text, path):
        data = None
        try:
            loaded = json.loads(text)
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            data = None
        if data:
            mapped = self.normalise_case_json(data, path)
            if any(mapped.get(k) for k in ("pos_args", "pos_ev", "neg_args", "neg_ev", "background")):
                return mapped
        return self.heuristic_case_structure(text, path)

    def normalise_case_json(self, data, path):
        def pick(*keys):
            for key in keys:
                value = data.get(key)
                if isinstance(value, (list, tuple)):
                    value = "\n".join(str(x) for x in value)
                if value:
                    return str(value).strip()
            return ""
        return {
            "case_name": pick("case_name", "name", "案件名称", "title") or Path(path).stem,
            "jurisdiction": pick("jurisdiction", "管辖区", "法院", "court") or self.guess_jurisdiction(json.dumps(data, ensure_ascii=False)),
            "background": pick("background", "case_bg", "facts", "summary", "案件背景", "案情", "事实经过"),
            "pos_args": pick("pos_args", "positive_args", "plaintiff_args", "my_args", "正方论点", "原告论点", "我方论点"),
            "pos_ev": pick("pos_ev", "positive_evidence", "plaintiff_evidence", "my_evidence", "正方证据", "原告证据", "我方证据"),
            "neg_args": pick("neg_args", "negative_args", "defendant_args", "opponent_args", "反方论点", "被告论点", "对方论点"),
            "neg_ev": pick("neg_ev", "negative_evidence", "defendant_evidence", "opponent_evidence", "反方证据", "被告证据", "对方证据"),
            "source_note": "旧版 JSON 结构化导入",
        }

    def heuristic_case_structure(self, text, path):
        profile = NidoFunctionLawyerEngine(DIMENSIONS).extract_case_profile(text)
        if profile.get("dispute_type") == "consumer_return_acl":
            return self.consumer_return_case_structure(text, path, profile)
        sections = self.extract_explicit_sections(text)
        return {
            "case_name": self.guess_case_name(text, path),
            "jurisdiction": self.guess_jurisdiction(text),
            "background": sections.get("case") or self.first_reasonable_excerpt(text, 2200),
            "pos_args": sections.get("my") or self.extract_numbered_block(text, ["我方", "正方", "原告", "申请人"]),
            "pos_ev": self.extract_evidence_lines(text, positive=True),
            "neg_args": sections.get("opponent") or self.extract_numbered_block(text, ["对方", "反方", "被告", "无效方"]),
            "neg_ev": self.extract_evidence_lines(text, positive=False),
            "source_note": "本地规则结构化导入",
        }

    def consumer_return_case_structure(self, text, path, profile):
        evidence = profile.get("evidence", [])
        legal_refs = profile.get("legal_refs", [])
        has = lambda term: term in text.lower() or term in text
        pos_args = [
            "划痕可能是收货时已经存在的产品瑕疵，商品不符合消费者合理期待。",
            "消费者可依据消费者保护规则主张退货、退款或其他合理补救。",
            "退货期限应结合实际收货、发现瑕疵和合理通知时间判断。",
            "商家拒绝退货可能造成消费者额外维权成本。",
        ]
        neg_args = [
            "出货前质检合格，划痕可能由物流、收货后开机使用或保存不当造成。",
            "平台退货规则和页面提示可证明消费者下单时已接受退货期限安排。",
            "收货后才发现划痕，不能直接倒推出货前存在瑕疵。",
            "拆箱视频需要证明原始性、连续性、封条状态和首次开箱过程。",
        ]
        if has("律师费") or has("legal costs"):
            pos_args.append("消费者可能主张律师费或维权费用由商家拒退行为导致。")
            neg_args.append("律师费需单独证明合理性、必要性和与商家行为的直接因果关系。")
        if has("商誉") or has("reputation"):
            neg_args.append("消费者频繁退货或不完整投诉可能对商家信誉造成额外损害。")
        pos_ev = []
        neg_ev = []
        if "拆箱视频" in evidence:
            pos_ev.append("[P1] 收货/拆箱视频，用于证明发现划痕时间和商品状态。")
            neg_ev.append("[D1] 要求调取原始视频、时间戳、连续帧、封条和外包装状态，用于质疑视频证明力。")
        if "聊天记录" in evidence:
            pos_ev.append("[P2] 与商家客服聊天记录，用于证明通知时间和维权经过。")
        if legal_refs:
            pos_ev.append("[P3] " + "、".join(legal_refs) + "，用于支持消费者补救主张。")
        if "出货前质检记录" in evidence:
            neg_ev.append("[D2] 出货前质检记录，用于证明出库时无明显瑕疵。")
        if "物流/签收记录" in evidence:
            neg_ev.append("[D3] 物流签收/包裹完整性材料，用于排查运输和签收状态。")
        if "退货历史" in evidence:
            neg_ev.append("[D4] 退货历史记录，用于提示诚信交易、过失比较或滥用退货风险。")
        return {
            "case_name": self.guess_case_name(text, path, default="手机退货消费者纠纷"),
            "jurisdiction": self.guess_jurisdiction(text),
            "background": self.first_reasonable_excerpt(text, 1800),
            "pos_args": "\n".join(f"{i+1}. {x}" for i, x in enumerate(pos_args)),
            "pos_ev": "\n".join(pos_ev) or "1. 消费者提交的视频、照片、聊天记录或消费者法规材料。",
            "neg_args": "\n".join(f"{i+1}. {x}" for i, x in enumerate(neg_args)),
            "neg_ev": "\n".join(neg_ev) or "1. 商家质检、平台规则、物流签收和消费者使用记录。",
            "source_note": "本地规则结构化导入：消费者退货纠纷",
        }

    def guess_case_name(self, text, path, default=None):
        for pattern in [
            r'"name"\s*:\s*"([^"]+)"',
            r'"case_name"\s*:\s*"([^"]+)"',
            r"案件名称\s*[:：]\s*(.+)",
            r"案名\s*[:：]\s*(.+)",
        ]:
            m = re.search(pattern, text)
            if m:
                return compact(m.group(1), 60)
        if "退货" in text and "手机" in text:
            return default or "网购手机退货纠纷"
        return default or Path(path).stem

    def extract_numbered_block(self, text, side_terms):
        lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if any(term in stripped for term in side_terms) and any(k in stripped for k in ["主张", "认为", "要求", "抗辩", "论点"]):
                lines.append(stripped)
        return "\n".join(lines[:8])

    def extract_evidence_lines(self, text, positive=True):
        terms = ["证据", "视频", "照片", "聊天记录", "质检", "物流", "签收", "合同", "页面截图", "法条", "报告"]
        lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if any(term in stripped for term in terms):
                lines.append(stripped)
        return "\n".join(lines[:8])

    def collect_case_sections(self, text):
        buckets = {"case": [], "my": [], "opponent": []}
        current = "case"
        heading_patterns = [
            ("my", re.compile(r"^\s*(我方|正方|申请人|原告|权利人|专利权人|proponent|applicant|plaintiff|claimant).{0,12}(立场|主张|论点|证据|argument|position|evidence)?\s*[:：]?\s*$", re.I)),
            ("opponent", re.compile(r"^\s*(对方|反方|被告|无效方|攻击|异议方|opponent|respondent|defendant|invalidity|attack).{0,12}(立场|主张|论点|证据|argument|position|evidence)?\s*[:：]?\s*$", re.I)),
            ("case", re.compile(r"^\s*(案情|案件背景|事实|争议事实|材料全文|background|facts|summary|case).{0,12}\s*[:：]?\s*$", re.I)),
        ]
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line:
                loose = re.sub(r"[\s:：#【】\[\]（）()]+", "", line).lower()
                section_marker = any(k in loose for k in ["立场", "主张", "论点", "证据", "案情", "背景", "事实", "argument", "position", "evidence", "background", "facts", "summary"])
                has_sentence_punctuation = any(p in line for p in "。，；.!?？;")
                looks_like_heading = len(loose) <= 36 and (
                    line.endswith((":", "：")) or (section_marker and not has_sentence_punctuation)
                )
                if looks_like_heading:
                    if any(k in loose for k in ["我方", "正方", "申请人", "原告", "权利人", "proponent", "applicant", "plaintiff", "claimant"]):
                        current = "my"
                        continue
                    if any(k in loose for k in ["对方", "反方", "被告", "无效方", "攻击", "异议方", "opponent", "respondent", "defendant", "invalidity", "attack"]):
                        current = "opponent"
                        continue
                    if any(k in loose for k in ["案情", "案件背景", "争议事实", "材料全文", "background", "facts", "summary", "case"]):
                        current = "case"
                        continue
                matched = False
                for bucket, pattern in heading_patterns:
                    if pattern.search(line):
                        current = bucket
                        matched = True
                        break
                if matched:
                    continue
            buckets[current].append(raw_line)
        return {k: "\n".join(v).strip() for k, v in buckets.items() if "\n".join(v).strip()}

    def extract_explicit_sections(self, text):
        headings = {
            "case": ["案情", "案件背景", "争议事实", "事实", "background", "facts", "summary"],
            "my": ["我方立场", "我方主张", "正方立场", "申请人立场", "原告立场", "权利人立场", "my position", "applicant position", "plaintiff position"],
            "opponent": ["对方立场", "反方立场", "被告立场", "无效方立场", "攻击观点", "对方攻击", "opponent position", "respondent position", "defendant position", "invalidity attack"],
        }
        all_names = [(bucket, re.escape(name)) for bucket, names in headings.items() for name in names]
        heading_re = re.compile(r"(?im)^\s*(?P<head>" + "|".join(name for _, name in all_names) + r")\s*[:：]?\s*$")
        matches = list(heading_re.finditer(text))
        if not matches:
            return {}
        result = {}
        name_to_bucket = {name.replace("\\ ", " "): bucket for bucket, name in all_names}
        for idx, match in enumerate(matches):
            raw_head = match.group("head").lower()
            bucket = None
            for name, candidate_bucket in name_to_bucket.items():
                if raw_head == name.lower():
                    bucket = candidate_bucket
                    break
            if bucket is None:
                continue
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if body:
                result[bucket] = body
        return result

    def first_reasonable_excerpt(self, text, limit=6500):
        return text[:limit] + ("\n\n【提示】全文较长，已先放入前半部分；完整文件仍建议保留原件。" if len(text) > limit else "")

    def guess_my_position(self, text):
        lowered = text.lower()
        if "support" in lowered or "best method" in lowered or "claim" in lowered or "专利" in text:
            return "我方初始立场：维持技术方案/权利要求的可支持性、清楚性、可实施性和核心区别；请根据导入材料继续补充具体 claim element、实施例和技术效果。"
        if "合同" in text or "履约" in text or "违约" in text:
            return "我方初始立场：围绕合同文本、履约事实、证据链、损失因果关系和减损义务进行防守；请继续补充我方希望法院/对方接受的结论。"
        return "我方初始立场：请在这里补充我方要维持的结论、核心事实、关键证据和不可退让边界。"

    def guess_opponent_position(self, text):
        lowered = text.lower()
        if "support" in lowered or "best method" in lowered or "claim" in lowered or "专利" in text:
            return "对方可能攻击：新颖性、创造性、support、best method、清楚性、enablement、现有技术差异和绕开路径。"
        if "合同" in text or "履约" in text or "违约" in text:
            return "对方可能攻击：合同解释、违约事实、证据真实性、损失量化、因果关系、时效和程序瑕疵。"
        return "对方可能攻击：事实基础、证据缺口、因果链、法律适用、程序问题、量化依据和公共政策风险。"

    def guess_jurisdiction(self, text):
        lowered = text.lower()
        if "australia" in lowered or "澳洲" in text or "澳大利亚" in text:
            return "Australia / AU"
        if "china" in lowered or "中国" in text:
            return "China / CN"
        if "united states" in lowered or "usa" in lowered or "美国" in text:
            return "United States / US"
        return self.jurisdiction_var.get()

    def selected_dimensions(self):
        return [name for name, var in self.dimension_vars.items() if var.get()]

    def run_attack(self):
        selected = self.selected_dimensions()
        if not selected:
            messagebox.showwarning("未选择维度", "请至少选择一个攻防维度。")
            return
        case_text = self.case_text.get("1.0", tk.END).strip()
        if not case_text:
            messagebox.showwarning("缺少案情", "请填写或导入案情/申请文本。")
            return
        pos_args = self.pos_args.get("1.0", tk.END).strip() if hasattr(self, "pos_args") else ""
        pos_ev = self.pos_ev.get("1.0", tk.END).strip() if hasattr(self, "pos_ev") else ""
        neg_args = self.neg_args.get("1.0", tk.END).strip() if hasattr(self, "neg_args") else ""
        neg_ev = self.neg_ev.get("1.0", tk.END).strip() if hasattr(self, "neg_ev") else ""
        my_position = self.my_position.get("1.0", tk.END).strip()
        opp_position = self.opp_position.get("1.0", tk.END).strip()
        if pos_args or pos_ev:
            my_position = "\n\n".join(x for x in [
                my_position,
                "【我方结构化论点】\n" + pos_args if pos_args else "",
                "【我方结构化证据】\n" + pos_ev if pos_ev else "",
            ] if x)
        if neg_args or neg_ev:
            opp_position = "\n\n".join(x for x in [
                opp_position,
                "【对方结构化论点】\n" + neg_args if neg_args else "",
                "【对方结构化证据】\n" + neg_ev if neg_ev else "",
            ] if x)
        state = self.engine.run(
            self.mode_var.get(),
            self.jurisdiction_var.get().strip(),
            case_text,
            my_position,
            opp_position,
            selected,
            {
                "local_only": self.local_only.get(),
                "anonymizer": self.use_anonymizer.get(),
                "case_search": self.use_case_search.get(),
                "cloud_polish": self.use_cloud_polish.get(),
                "confidentiality_mode": self.confidentiality_mode.get(),
                "case_name": self.case_name_var.get().strip() if hasattr(self, "case_name_var") else "",
                "structured_case": {
                    "pos_args": pos_args,
                    "pos_ev": pos_ev,
                    "neg_args": neg_args,
                    "neg_ev": neg_ev,
                },
            },
        )
        self.last_state = state
        self.render_state(state)
        self.save_state(state, show_message=True)

    def render_state(self, state):
        for text in self.outputs.values():
            text.delete("1.0", tk.END)
        self.insert_marked(self.outputs["summary"], self.render_summary(state))
        self.insert_marked(self.outputs["r1"], self.render_items(state["rounds"]["round1_opponent_attack"], "反方攻击"))
        self.insert_marked(self.outputs["r2"], self.render_items(state["rounds"]["round2_my_rebuttal"], "我方反驳"))
        self.insert_marked(self.outputs["r3"], self.render_items(state["rounds"]["round3_opponent_response"], "反方回应"))
        self.insert_marked(self.outputs["r4"], self.render_items(state["rounds"]["round4_my_final"], "我方最终"))
        self.insert_marked(self.outputs["review"], self.render_review(state["rounds"]["final_reviewer"]))
        self.outputs["json"].insert(tk.END, json.dumps(state, ensure_ascii=False, indent=2))

    def insert_marked(self, widget, content):
        for line in content.splitlines(True):
            tag = None
            plain = line
            if line.startswith("[[TITLE]]"):
                tag, plain = "title", line.replace("[[TITLE]]", "", 1)
            elif line.startswith("[[SUB]]"):
                tag, plain = "subheader", line.replace("[[SUB]]", "", 1)
            elif line.startswith("[[NEG]]"):
                tag, plain = "neg", line.replace("[[NEG]]", "", 1)
            elif line.startswith("[[POS]]"):
                tag, plain = "pos", line.replace("[[POS]]", "", 1)
            elif line.startswith("[[LABEL]]"):
                tag, plain = "label", line.replace("[[LABEL]]", "", 1)
            elif line.startswith("[[NOTE]]"):
                tag, plain = "note", line.replace("[[NOTE]]", "", 1)
            widget.insert(tk.END, plain, tag if tag else ())

    def strip_render_markers(self, content):
        for marker in ("[[TITLE]]", "[[SUB]]", "[[NEG]]", "[[POS]]", "[[LABEL]]", "[[NOTE]]"):
            content = content.replace(marker, "")
        return content

    def render_summary(self, state):
        review = state["rounds"]["final_reviewer"]
        lines = [
            "[[TITLE]]# Nido StrikeOver v4 攻防总报告",
            "",
            f"- Run ID: {state['run_id']}",
            f"- Case key: {state['case_key']}",
            f"- 模式: {state['mode']}",
            f"- 法域: {state['jurisdiction']}",
            f"- 保密模式: {state.get('options', {}).get('confidentiality_mode', '完全本地保密')}",
            f"- 已选维度: {len(state['selected_dimensions'])}",
            f"- 攻防panel: {review['frame_count']}",
            f"- 处理模式: 本地保密攻防",
            "",
            "[[SUB]]## 案情摘要",
            state["signals"]["case_summary"],
            "",
            "[[SUB]]## 攻防原则",
            LAWYER_ATTACK_PRINCIPLE,
            "",
            "[[SUB]]## 总立场panel",
            self.render_stance_frame(state.get("stance_frame", {})),
            "",
            "[[SUB]]## 律师团画像锚",
            self.render_persona_anchors(state.get("persona_anchors", {})),
            "",
            "[[SUB]]## 立场延续复审",
            self.render_stance_reviews(state.get("stance_reviews", {}), compact_view=True),
            "",
            "[[SUB]]## 当前最高优先级",
        ]
        lines.extend([f"{i+1}. {x}" for i, x in enumerate(review["top_trial_preparation"])])
        lines.extend(["", "[[SUB]]## 结论边界", "本版本用于本地攻防预演；不替代律师意见，也未联网检索真实判例。"])
        lines.extend([
            "",
            "[[SUB]]## 保密边界",
            "- 完全本地保密：不联网，不发送案情、客户材料、专利全文或攻防结果。",
            "- 只发送公开检索词：仅把本地生成的关键词交给搜索引擎，不上传全文。",
            "- 授权云端专家：必须由用户明确切换后，才允许把必要片段交给外部模型/API。",
        ])
        return "\n".join(lines)

    def render_persona_anchors(self, anchors):
        if not anchors:
            return "未生成律师团画像锚。"
        lines = []
        for name, anchor in anchors.items():
            lines.append(f"- {name}: {anchor.get('past_statement', '')}")
            lines.append(f"  固定习惯: {anchor.get('attack_habit', '')}")
            lines.append(f"  不可越界: {anchor.get('red_line', '')}")
        return "\n".join(lines)

    def render_stance_reviews(self, stance_reviews, compact_view=False):
        if not stance_reviews:
            return "未生成立场延续复审。"
        status = stance_reviews.get("overall", "unknown")
        warning_count = stance_reviews.get("warning_count", 0)
        lines = [f"总体状态: {status}；警告数: {warning_count}"]
        items = stance_reviews.get("items", [])
        if compact_view:
            warnings = [x for x in items if x.get("status") == "warning"]
            if not warnings:
                lines.append("- 未发现明显折中、串位或替对方补强。")
            else:
                for item in warnings[:12]:
                    lines.append(f"- {item.get('round')} / {item.get('dimension')} / {item.get('side')}: {'；'.join(item.get('findings', []))}")
            return "\n".join(lines)
        for item in items:
            lines.append(f"- {item.get('round')} / {item.get('dimension')} / {item.get('side')} / {item.get('status')}: {'；'.join(item.get('findings', []))}")
        return "\n".join(lines)

    def render_stance_frame(self, frame):
        if not frame:
            return "未生成总立场panel。"
        my_frame = frame.get("my_client_frame", {})
        opponent_frame = frame.get("opponent_frame", {})
        rules = frame.get("round_rules", {})
        lines = [
            f"我方总立场: {my_frame.get('global_position', '未填写')}",
            f"反方总攻击方向: {opponent_frame.get('global_attack_direction', '未填写')}",
            "",
            "我方不可越界:",
        ]
        lines.extend([f"- {x}" for x in my_frame.get("must_protect", [])])
        lines.extend(["", "四轮锁定规则:"])
        for key in ("R1", "R2", "R3", "R4"):
            if key in rules:
                lines.append(f"- {key}: {rules[key]}")
        return "\n".join(lines)

    def render_items(self, items, title):
        lines = [f"[[TITLE]]# {title}", ""]
        for i, item in enumerate(items, 1):
            dimension = item.get("dimension", f"第{i}点")
            if title == "反方攻击":
                lines.append(f"[[SUB]]## {i}. 反方会从【{dimension}】这样问")
                if item.get("global_stance"):
                    lines.append(f"[[LABEL]]反方总立场: {item.get('global_stance')}")
                anchor = item.get("persona_anchor") or {}
                if anchor:
                    lines.append(f"[[NOTE]]画像锚: {anchor.get('past_statement', '')}")
                    lines.append(f"[[NOTE]]维度习惯: {anchor.get('attack_habit', '')}")
                lines.append(f"[[LABEL]]针对: {item.get('targeting', '我方核心立场或证据链')}")
                lines.append(f"[[NEG]]对方问法: {item.get('question', '')}")
                lines.append(f"[[NEG]]攻击导向: {item.get('attack', item.get('finding', ''))}")
                lines.append(f"[[NOTE]]准备动作: 把这个问题拆成原文定位、证据来源、规则依据和补证空间。")
            elif title == "我方反驳":
                material = item.get("needed_material", [])
                material_text = "；".join(material) if material else "暂无必须补充材料，但仍建议准备定位页码和证据索引。"
                lines.append(f"[[SUB]]## {i}. 我方回应【{dimension}】")
                if item.get("global_stance"):
                    lines.append(f"[[LABEL]]我方总立场: {item.get('global_stance')}")
                anchor = item.get("persona_anchor") or {}
                if anchor:
                    lines.append(f"[[NOTE]]画像锚: {anchor.get('past_statement', '')}")
                    lines.append(f"[[NOTE]]不可越界: {anchor.get('red_line', '')}")
                lines.append(f"[[LABEL]]针对对方: {item.get('answer_to', '')}")
                lines.append(f"[[POS]]反驳路径: {item.get('response', '')}")
                lines.append(f"[[NOTE]]需要材料: {material_text}")
            elif title == "反方回应":
                lines.append(f"[[SUB]]## {i}. 反方继续追问【{dimension}】")
                lines.append(f"[[NEG]]追问: {item.get('counter', '')}")
                lines.append(f"[[LABEL]]残余风险: {item.get('residual_risk', 'unknown')}")
            elif title == "我方最终":
                lines.append(f"[[SUB]]## {i}. 我方最终固定【{dimension}】")
                lines.append(f"[[POS]]最终立场: {item.get('final_position', '')}")
                lines.append(f"[[NOTE]]庭审准备: {item.get('trial_note', '')}")
            else:
                lines.append(f"[[SUB]]## {i}. {dimension}")
                for k, v in item.items():
                    if k == "dimension":
                        continue
                    if isinstance(v, list):
                        v = "；".join(v) if v else "无"
                    lines.append(f"- {k}: {v}")
            lines.append("")
        return "\n".join(lines)

    def open_fullscreen_outputs(self):
        if self.fullscreen_win is not None and self.fullscreen_win.winfo_exists():
            self.fullscreen_win.lift()
            self.sync_fullscreen_outputs()
            return
        win = tk.Toplevel(self.root)
        self.fullscreen_win = win
        win.title("Nido StrikeOver v4 - 攻防全屏阅读")
        try:
            win.state("zoomed")
        except tk.TclError:
            win.geometry("1280x820")
        top = ttk.Frame(win, padding=8)
        top.pack(fill=tk.X)
        ttk.Label(top, text="攻防全屏：同步主界面各轮结果，适合逐条看攻击和反驳。", style="Panel.TLabel").pack(side=tk.LEFT)
        ttk.Button(top, text="立即同步", command=self.sync_fullscreen_outputs).pack(side=tk.RIGHT, padx=4)
        ttk.Button(top, text="关闭", command=win.destroy).pack(side=tk.RIGHT, padx=4)

        notebook = ttk.Notebook(win)
        notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.fullscreen_widgets = {}
        for key, title in [
            ("summary", "总报告"),
            ("r1", "R1 反方攻击"),
            ("r2", "R2 我方反驳"),
            ("r3", "R3 反方回应"),
            ("r4", "R4 我方最终"),
            ("review", "评委复审"),
            ("json", "状态对象 JSON"),
        ]:
            frame = ttk.Frame(notebook, style="Panel.TFrame")
            default_fg = {"r1": "#f5a0b8", "r2": "#89b4fa", "r3": "#f5a0b8", "r4": "#89b4fa"}.get(key, self.fg)
            text = scrolledtext.ScrolledText(
                frame,
                wrap=tk.WORD,
                bg="#071018",
                fg=default_fg,
                insertbackground=self.fg,
                relief=tk.FLAT,
                font=("Microsoft YaHei UI", 14),
            )
            self.configure_output_tags(text)
            text.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
            notebook.add(frame, text=title)
            self.fullscreen_widgets[key] = text
        self.sync_fullscreen_outputs()

    def sync_fullscreen_outputs(self):
        if self.fullscreen_win is None or not self.fullscreen_win.winfo_exists():
            return
        for key, widget in self.fullscreen_widgets.items():
            source = self.outputs.get(key)
            if source is None:
                continue
            source_text = source.get("1.0", tk.END)
            if widget.get("1.0", tk.END) != source_text:
                widget.delete("1.0", tk.END)
                widget.insert("1.0", source_text)

    def open_point_rebuttal(self):
        win = tk.Toplevel(self.root)
        win.title("Nido StrikeOver v4 - 逐条反驳工作台")
        win.geometry("1180x760")
        top = ttk.Frame(win, padding=8)
        top.pack(fill=tk.X)
        ttk.Label(
            top,
            text="从 R1 反方攻击中选择一条，生成本地反驳路线；也可以手动粘贴对方攻击。",
            style="Panel.TLabel",
        ).pack(side=tk.LEFT)

        body = ttk.Panedwindow(win, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        left = ttk.Frame(body, style="Panel.TFrame")
        right = ttk.Frame(body, style="Panel.TFrame")
        body.add(left, weight=1)
        body.add(right, weight=2)

        ttk.Label(left, text="R1 攻击点", style="Panel.TLabel").pack(anchor=tk.W)
        attack_list = tk.Listbox(left, bg="#0c1117", fg=self.fg, selectbackground=self.accent, height=12)
        attack_list.pack(fill=tk.BOTH, expand=False, pady=(4, 8))

        attacks = self.collect_round1_attacks()
        for label, _ in attacks:
            attack_list.insert(tk.END, label)

        ttk.Label(left, text="攻击原文 / 可手动修改", style="Panel.TLabel").pack(anchor=tk.W)
        attack_text = scrolledtext.ScrolledText(left, wrap=tk.WORD, height=16, bg="#0c1117", fg=self.fg, insertbackground=self.fg)
        attack_text.pack(fill=tk.BOTH, expand=True, pady=(4, 8))

        ttk.Label(right, text="Nido 本地逐条反驳", style="Panel.TLabel").pack(anchor=tk.W)
        rebuttal_text = scrolledtext.ScrolledText(right, wrap=tk.WORD, bg="#071018", fg=self.fg, insertbackground=self.fg, font=("Microsoft YaHei UI", 12))
        rebuttal_text.pack(fill=tk.BOTH, expand=True, pady=(4, 8))

        def load_selected(event=None):
            selection = attack_list.curselection()
            if not selection:
                return
            _, content = attacks[selection[0]]
            attack_text.delete("1.0", tk.END)
            attack_text.insert("1.0", content)

        def generate_one():
            target = attack_text.get("1.0", tk.END).strip()
            if not target:
                messagebox.showwarning("缺少攻击点", "请先选择 R1 攻击点，或手动粘贴对方攻击。")
                return
            rebuttal_text.delete("1.0", tk.END)
            rebuttal_text.insert("1.0", self.generate_point_rebuttal_text(target))

        def generate_all():
            if not attacks:
                messagebox.showwarning("暂无 R1", "请先运行一次攻防，或导入 state_object.json。")
                return
            blocks = []
            for label, content in attacks:
                blocks.append(f"# {label}\n\n{self.generate_point_rebuttal_text(content)}")
            rebuttal_text.delete("1.0", tk.END)
            rebuttal_text.insert("1.0", "\n\n---\n\n".join(blocks))

        def copy_result():
            self.root.clipboard_clear()
            self.root.clipboard_append(rebuttal_text.get("1.0", tk.END).strip())

        attack_list.bind("<<ListboxSelect>>", load_selected)
        controls = ttk.Frame(win, padding=(8, 0, 8, 8))
        controls.pack(fill=tk.X)
        ttk.Button(controls, text="载入选中攻击", command=load_selected).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="生成本条反驳", style="Accent.TButton", command=generate_one).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="生成全部 R1 逐条反驳", command=generate_all).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="复制结果", command=copy_result).pack(side=tk.LEFT, padx=4)
        if attacks:
            attack_list.selection_set(0)
            load_selected()

    def collect_round1_attacks(self):
        if not self.last_state:
            return []
        items = self.last_state.get("rounds", {}).get("round1_opponent_attack", [])
        attacks = []
        for i, item in enumerate(items, 1):
            dimension = item.get("dimension", f"攻击点 {i}")
            lines = [f"维度：{dimension}"]
            for key, value in item.items():
                if key == "dimension":
                    continue
                if isinstance(value, list):
                    value = "；".join(str(x) for x in value) if value else "无"
                lines.append(f"{key}: {value}")
            attacks.append((f"{i}. {dimension}", "\n".join(lines)))
        return attacks

    def generate_point_rebuttal_text(self, target):
        case_text = self.case_text.get("1.0", tk.END).strip()
        my_position = self.my_position.get("1.0", tk.END).strip()
        lowered = target.lower()
        is_patent = any(k in lowered for k in ["claim", "support", "enablement", "best method", "novelty", "inventive", "s40"]) or any(k in target for k in ["专利", "权利要求", "新颖性", "创造性", "支持性", "最佳方法"])
        is_evidence = any(k in target for k in ["证据", "证明", "因果", "损失", "真实性", "披露"]) or any(k in lowered for k in ["evidence", "causation", "damage", "disclosure"])
        is_contract = any(k in target for k in ["合同", "违约", "付款", "履行"]) or any(k in lowered for k in ["contract", "breach", "payment", "performance"])

        lines = [
            "# 单点反驳工作稿",
            "",
            "## 对方攻击点",
            target,
            "",
            "## 我方底线",
            my_position or "请补充我方要维持的结论、不可退让边界和可补证空间。",
            "",
            "## 反驳路线",
            "1. 先限缩攻击范围：要求对方说明攻击对应的具体事实、具体权利要求/合同条款/证据链节点，而不是泛泛质疑。",
            "2. 再拆成可验证问题：把对方说法拆成事实问题、规则问题、证据问题、因果问题和补正问题。",
            "3. 本地引擎只接受可验证缺口：没有对应文本、证据或法条来源的攻击，标记为推测性攻击。",
        ]
        if is_patent:
            lines.extend([
                "4. 专利方向反驳：逐项映射 claim element、说明书 support、实施例、技术效果和可替代实施方式。",
                "5. 对 best method / support 攻击：区分“未披露最佳理由”和“未披露可实施手段”；要求对方指出申请日已知且被扣留的具体手段。",
                "6. 对新颖性/创造性攻击：要求对方给出单一现有技术或组合动机，并逐项比对差异特征和技术效果。",
            ])
        elif is_contract:
            lines.extend([
                "4. 合同方向反驳：先回到合同文字，再看履行事实、通知记录、付款/交付节点和减损义务。",
                "5. 对违约攻击：要求对方证明义务存在、期限届满、违反行为、损失和因果链同时成立。",
            ])
        elif is_evidence:
            lines.extend([
                "4. 证据方向反驳：要求对方补充原始来源、形成时间、完整链路、真实性和关联性。",
                "5. 对因果/损失攻击：把“有问题”拆成“哪个行为导致哪个具体损失”，没有量化则不接受结论跳跃。",
            ])
        else:
            lines.extend([
                "4. 通用反驳：把对方结论拆成前提、证据、规则适用和推理链四段，逐段要求其承担证明责任。",
            ])
        lines.extend([
            "",
            "## 反问清单",
            "- 对方攻击对应哪一句原文、哪一个证据、哪一个权利要求/条款？",
            "- 对方是否把“可以补充说明的问题”说成了“无法成立的问题”？",
            "- 对方是否遗漏了我方已经披露的实施例、替代路径、边界条件或补证空间？",
            "",
            "## 需要补的材料",
            "- 原文定位：页码/段落/权利要求/合同条款。",
            "- 证据定位：形成时间、来源、完整链路、对方承认或未否认部分。",
            "- 反证材料：可实施例、实验/数据、通信记录、付款/交付记录、公开资料检索结果。",
            "",
            "## 风险边界",
            "- 不直接说对方一定错误，只说其攻击需要被具体化、证据化、条款化。",
            "- 若确有缺口，优先给出限缩、补证、解释和替代论证，不做无根据硬撑。",
        ])
        if case_text:
            lines.extend(["", "## 案情定位提示", case_text[:900] + ("..." if len(case_text) > 900 else "")])
        return "\n".join(lines)

    def render_review(self, review):
        lines = [
            "# Nido 评委复审",
            "",
            f"- 复审角色: {review['reviewer_role']}",
            f"- 维度数量: {review['selected_dimension_count']}",
            f"- 状态panel: {review['frame_count']}",
            f"- 退让扫描: {review['capitulation_scan']}",
            f"- 立场延续: {review.get('stance_continuity', {}).get('overall', 'unknown')} / 警告 {review.get('stance_continuity', {}).get('warning_count', 0)}",
            f"- 本地保密攻防: {review['local_only']}",
            "",
            "## 庭审/攻防重点准备",
        ]
        lines.extend([f"{i+1}. {x}" for i, x in enumerate(review["top_trial_preparation"])])
        lines.extend([
            "",
            "## 立场延续复审明细",
            self.render_stance_reviews(review.get("stance_continuity", {}), compact_view=False),
            "",
            "## 备注",
            review["note"],
        ])
        return "\n".join(lines)

    def save_state(self, state, show_message=False):
        base = Path(__file__).resolve().parent / "runs" / state["run_id"]
        base.mkdir(parents=True, exist_ok=True)
        (base / "state_object.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8-sig")
        (base / "report.md").write_text(self.strip_render_markers(self.render_summary(state)), encoding="utf-8-sig")
        for key, title, file_name in [
            ("round1_opponent_attack", "反方攻击", "round1_opponent_attack.md"),
            ("round2_my_rebuttal", "我方反驳", "round2_my_rebuttal.md"),
            ("round3_opponent_response", "反方回应", "round3_opponent_response.md"),
            ("round4_my_final", "我方最终", "round4_my_final.md"),
        ]:
            (base / file_name).write_text(self.strip_render_markers(self.render_items(state["rounds"][key], title)), encoding="utf-8-sig")
        (base / "final_reviewer.md").write_text(self.strip_render_markers(self.render_review(state["rounds"]["final_reviewer"])), encoding="utf-8-sig")
        self.last_run_dir = base
        if show_message:
            messagebox.showinfo("完成", f"Nido 攻防已完成。\n\n结果目录：\n{base}")

    def save_again(self):
        if not self.last_state:
            messagebox.showwarning("暂无报告", "请先运行一次攻防，或导入 state_object.json。")
            return
        self.save_state(self.last_state, show_message=True)

    def open_results(self):
        path = self.last_run_dir or (Path(__file__).resolve().parent / "runs")
        path.mkdir(parents=True, exist_ok=True)
        try:
            import subprocess
            subprocess.Popen(["explorer", str(path)])
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc))

    def build_public_query(self):
        mode = self.mode_var.get()
        jurisdiction = self.jurisdiction_var.get().strip() or "Australia"
        case_text = self.case_text.get("1.0", tk.END).strip().lower()
        terms = [jurisdiction]
        if mode == "专利无效攻防":
            terms.extend(["patent", "support", "best method", "novelty", "inventive step", "section 40"])
        elif mode == "合同证据攻防":
            terms.extend(["contract", "evidence", "damages", "case law"])
        else:
            terms.extend(["law", "case law", "statute"])

        keyword_map = [
            ("best method", ["best method"]),
            ("support", ["support", "enablement", "sufficiency"]),
            ("divisional application", ["divisional", "分案"]),
            ("provisional patent", ["provisional", "临时申请"]),
            ("damages causation", ["damage", "loss", "损害"]),
            ("evidence burden of proof", ["evidence", "burden", "证据", "举证"]),
            ("privacy confidentiality legal software", ["privacy", "confidential", "保密"]),
        ]
        for public_term, needles in keyword_map:
            if any(n in case_text for n in needles):
                terms.append(public_term)
        return " ".join(dict.fromkeys(terms))

    def generate_public_search(self):
        query = self.build_public_query()
        notice = (
            "Nido 将只打开公开检索词，不发送案情全文。\n\n"
            f"公开检索词：\n{query}\n\n"
            "如果材料敏感，请不要把全文粘贴到网页搜索框。"
        )
        if not messagebox.askyesno("公开检索确认", notice + "\n\n是否打开浏览器搜索？"):
            self.outputs["summary"].delete("1.0", tk.END)
            self.outputs["summary"].insert(tk.END, notice)
            return
        url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
        webbrowser.open(url)

    def select_all(self):
        for var in self.dimension_vars.values():
            var.set(True)
        self.update_count()

    def clear_all(self):
        for var in self.dimension_vars.values():
            var.set(False)
        self.update_count()

    def update_count(self):
        n = sum(1 for var in self.dimension_vars.values() if var.get())
        self.count_label.configure(text=f"已选 {n}/18 维度；攻防状态panel：{n} × 2方 = {n * 2}；外加四轮攻防与评委复审。")

    def mode_hint(self):
        self.mode_hint_label.configure(text=MODE_HINTS.get(self.mode_var.get(), ""))

    def show_dimensions(self):
        msg = "\n".join([f"{i+1}. {name}：{desc}" for i, (name, desc) in enumerate(DIMENSIONS)])
        messagebox.showinfo("18维度说明", msg)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    NidoStrikeOverApp().run()
