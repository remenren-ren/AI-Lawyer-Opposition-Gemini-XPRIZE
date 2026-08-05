import html
import io
from datetime import datetime, timezone
from typing import Any, Dict, Iterable

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer


INK = colors.HexColor("#172033")
MUTED = colors.HexColor("#687386")
BRAND = colors.HexColor("#3157d5")
POSITIVE = colors.HexColor("#087f8c")
NEGATIVE = colors.HexColor("#b42355")
LINE = colors.HexColor("#dbe1ea")


def _safe(value: Any) -> str:
    return html.escape(str(value or "").strip()).replace("\n", "<br/>")


def _findings(report: Dict[str, Any], key: str) -> Iterable[Dict[str, Any]]:
    for item in report.get(key) or []:
        if isinstance(item, dict) and str(item.get("conclusion") or "").strip():
            yield item


def _model_details(report: Dict[str, Any]) -> Dict[str, str]:
    metadata = report.get("analysis_metadata") if isinstance(report.get("analysis_metadata"), dict) else {}
    return {
        "provider": str(metadata.get("provider_display_name") or report.get("provider") or "Not recorded"),
        "model": str(metadata.get("model_name") or "Not recorded"),
        "source": str(metadata.get("engine_source") or report.get("engine_source") or "Not recorded"),
    }


def build_client_weakness_pdf(record: Dict[str, Any], firm_name: str) -> bytes:
    report = record.get("deep_report") or {}
    case = record.get("free_report") or {}
    positive = list(_findings(report, "positive_side_weaknesses"))
    negative = list(_findings(report, "negative_side_weaknesses"))
    output = io.BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="18-Dimension Weakness Review",
        author=firm_name,
    )
    base = getSampleStyleSheet()
    title = ParagraphStyle(
        "ClientTitle", parent=base["Title"], fontName="Helvetica-Bold",
        fontSize=22, leading=27, textColor=INK, alignment=TA_CENTER, spaceAfter=8,
    )
    subtitle = ParagraphStyle(
        "ClientSubtitle", parent=base["Normal"], fontSize=10, leading=14,
        textColor=MUTED, alignment=TA_CENTER, spaceAfter=18,
    )
    heading = ParagraphStyle(
        "ClientHeading", parent=base["Heading2"], fontName="Helvetica-Bold",
        fontSize=16, leading=20, textColor=INK, spaceBefore=8, spaceAfter=10,
    )
    pos_heading = ParagraphStyle("PositiveHeading", parent=heading, textColor=POSITIVE)
    neg_heading = ParagraphStyle("NegativeHeading", parent=heading, textColor=NEGATIVE)
    card_title = ParagraphStyle(
        "FindingTitle", parent=base["Heading3"], fontName="Helvetica-Bold",
        fontSize=12, leading=16, textColor=BRAND, spaceBefore=10, spaceAfter=4,
    )
    body = ParagraphStyle(
        "FindingBody", parent=base["BodyText"], fontSize=10.5, leading=15,
        textColor=INK, spaceAfter=7,
    )
    notice = ParagraphStyle(
        "Notice", parent=body, fontSize=9, leading=13, textColor=MUTED,
        borderColor=LINE, borderWidth=0.5, borderPadding=8, spaceBefore=15,
    )
    notice_heading = ParagraphStyle(
        "NoticeHeading", parent=base["Heading3"], fontName="Helvetica-Bold",
        fontSize=11, leading=14, textColor=INK, spaceBefore=18, spaceAfter=6,
    )

    generated = datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")
    case_name = str(case.get("case_name") or "Client matter")
    jurisdiction = str(case.get("jurisdiction") or "Not specified")
    model = _model_details(report)
    story = [
        Paragraph(_safe(firm_name), subtitle),
        Paragraph("18-Dimension Weakness Review", title),
        Paragraph(
            f"<b>Matter:</b> {_safe(case_name)}<br/><b>Jurisdiction:</b> {_safe(jurisdiction)}<br/>"
            f"<b>AI provider:</b> {_safe(model['provider'])}<br/><b>Model:</b> {_safe(model['model'])}<br/>"
            f"<b>Engine:</b> {_safe(model['source'])}<br/><b>Generated:</b> {_safe(generated)}",
            subtitle,
        ),
        Paragraph(
            f"This report identifies <b>{len(positive)}</b> issue{'s' if len(positive) != 1 else ''} in the client's position and "
            f"<b>{len(negative)}</b> issue{'s' if len(negative) != 1 else ''} in the other side's position.",
            body,
        ),
        Spacer(1, 5 * mm),
        Paragraph("Weaknesses in Your Position", pos_heading),
    ]

    if positive:
        for index, item in enumerate(positive, 1):
            story.append(Paragraph(f"{index}. {_safe(item.get('conclusion'))}", card_title))
            story.append(Paragraph(_safe(item.get("analysis")), body))
    else:
        story.append(Paragraph("No material weakness was identified from the information currently available.", body))

    story.extend([PageBreak(), Paragraph("Weaknesses in the Other Side's Position", neg_heading)])
    if negative:
        for index, item in enumerate(negative, 1):
            story.append(Paragraph(f"{index}. {_safe(item.get('conclusion'))}", card_title))
            story.append(Paragraph(_safe(item.get("analysis")), body))
    else:
        story.append(Paragraph("No material weakness was identified from the information currently available.", body))

    story.append(Paragraph("LAWYER REFERENCE MATERIAL - IMPORTANT DISCLAIMER", notice_heading))
    story.append(Paragraph(
        "This AI-generated document is preliminary reference material for a lawyer's review. It is based only on the "
        "material supplied by the user, which may be incomplete, inaccurate, mistranslated or disputed. It is not legal "
        "advice, is not a final legal opinion, does not determine the merits or likely outcome of the matter, and does not "
        "create a lawyer-client relationship. A qualified lawyer must independently verify the facts, original evidence, "
        "governing law, jurisdiction, limitation periods, court dates and procedural requirements before this document is "
        "relied upon or any action is taken. AI Lawyer Opposition is not affiliated with or endorsed by any law firm unless "
        "that relationship is expressly stated in writing.",
        notice,
    ))
    document.build(story)
    return output.getvalue()


def build_independent_review_pdf(record: Dict[str, Any], firm_name: str) -> bytes:
    report = record.get("independent_report") or {}
    case = record.get("free_report") or {}
    complete_reports = [item for item in (report.get("complete_reports") or []) if isinstance(item, dict)]
    output = io.BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Independent 18-Dimension Deep Review",
        author=firm_name,
    )
    base = getSampleStyleSheet()
    title = ParagraphStyle(
        "IndependentTitle", parent=base["Title"], fontName="Helvetica-Bold",
        fontSize=21, leading=26, textColor=INK, alignment=TA_CENTER, spaceAfter=8,
    )
    subtitle = ParagraphStyle(
        "IndependentSubtitle", parent=base["Normal"], fontSize=10, leading=14,
        textColor=MUTED, alignment=TA_CENTER, spaceAfter=18,
    )
    dimension_heading = ParagraphStyle(
        "DimensionHeading", parent=base["Heading2"], fontName="Helvetica-Bold",
        fontSize=16, leading=20, textColor=BRAND, spaceBefore=8, spaceAfter=8,
    )
    finding_heading = ParagraphStyle(
        "IndependentFinding", parent=base["Heading3"], fontName="Helvetica-Bold",
        fontSize=11, leading=15, textColor=INK, spaceBefore=9, spaceAfter=4,
    )
    body = ParagraphStyle(
        "IndependentBody", parent=base["BodyText"], fontSize=10.5, leading=15,
        textColor=INK, spaceAfter=7,
    )
    notice = ParagraphStyle(
        "IndependentNotice", parent=body, fontSize=9, leading=13, textColor=MUTED,
        borderColor=LINE, borderWidth=0.5, borderPadding=8, spaceBefore=15,
    )
    generated = datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")
    model = _model_details(report)
    story = [
        Paragraph(_safe(firm_name), subtitle),
        Paragraph("Independent 18-Dimension Deep Review", title),
        Paragraph(
            f"<b>Matter:</b> {_safe(case.get('case_name') or 'Client matter')}<br/>"
            f"<b>Jurisdiction:</b> {_safe(case.get('jurisdiction') or 'Not specified')}<br/>"
            f"<b>AI provider:</b> {_safe(model['provider'])}<br/>"
            f"<b>Model:</b> {_safe(model['model'])}<br/>"
            f"<b>Engine:</b> {_safe(model['source'])}<br/>"
            f"<b>Generated:</b> {_safe(generated)}<br/>"
            f"<b>Method:</b> Each of the {len(complete_reports)} dimensions independently reread the complete matter.",
            subtitle,
        ),
    ]
    for index, item in enumerate(complete_reports, 1):
        if index > 1:
            story.append(PageBreak())
        story.append(Paragraph(f"{index:02d}. {_safe(item.get('dimension'))}", dimension_heading))
        if item.get("report_title"):
            story.append(Paragraph(_safe(item.get("report_title")), finding_heading))
        story.append(Paragraph(_safe(item.get("full_analysis")), body))
        findings = [value for value in (item.get("findings") or []) if isinstance(value, dict)]
        if findings:
            story.append(Paragraph("Highlighted findings", finding_heading))
            for number, finding in enumerate(findings, 1):
                story.append(Paragraph(f"{number}. {_safe(finding.get('conclusion'))}", finding_heading))
                story.append(Paragraph(_safe(finding.get("analysis")), body))
        limits = [str(value).strip() for value in (item.get("limits") or []) if str(value).strip()]
        if limits:
            story.append(Paragraph("Limits", finding_heading))
            for value in limits:
                story.append(Paragraph("- " + _safe(value), body))
    story.append(PageBreak())
    story.append(Paragraph("LAWYER REFERENCE MATERIAL - IMPORTANT DISCLAIMER", dimension_heading))
    story.append(Paragraph(
        "This AI-generated document is preliminary reference material for a lawyer's review. It is based only on the "
        "material supplied by the user, which may be incomplete, inaccurate, mistranslated or disputed. It is not legal "
        "advice, is not a final legal opinion, does not determine the merits or likely outcome of the matter, and does not "
        "create a lawyer-client relationship. A qualified lawyer must independently verify the facts, original evidence, "
        "governing law, jurisdiction, limitation periods, court dates and procedural requirements before this document is "
        "relied upon or any action is taken.",
        notice,
    ))
    document.build(story)
    return output.getvalue()
