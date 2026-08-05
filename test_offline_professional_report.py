import io
import json
import zipfile

from offline_professional_report import (
    REPORT_TYPES,
    build_professional_docx,
    build_professional_markdown,
    build_professional_pdf,
    normalise_professional_record,
    record_as_json,
)


def synthetic_record(report_type="lawyer_working_paper"):
    return {
        "report_type": report_type,
        "matter_name": "Synthetic delivery dispute",
        "jurisdiction": "NSW, Australia",
        "engine_metadata": {
            "provider": "Google Gemini",
            "model": "gemini-synthetic-test",
            "source": "Synthetic test metadata only",
        },
        "executive_summary": "A fictional record used only to verify professional report formatting.",
        "case_profile": {"workflow_mode": "synthetic test", "selected_dimensions": 18},
        "chronology": [{"date": "1 July 2026", "event": "Fictional agreement signed", "source_reference": "synthetic-case.txt"}],
        "positions": {"positive_side_arguments": "Synthetic claimant position", "negative_side_arguments": "Synthetic respondent position"},
        "evidence_index": [{"item": "P1", "document_or_evidence": "Fictional agreement", "source_reference": "synthetic-case.txt", "status": "synthetic"}],
        "issues_and_weaknesses": [{"id": "W-01", "dimension": "Fact Challenge", "issue": "A fictional date requires verification", "review_status": "lawyer review"}],
        "dimension_analysis": [{"dimension": "Fact Challenge", "identified_issue": "Synthetic issue", "response_or_counterpoint": "Synthetic response", "needed_material": "Synthetic source"}],
        "missing_information": ["No real client material was used."],
        "risk_and_confidence": [{"dimension": "Fact Challenge", "confidence": "not independently scored", "note": "synthetic"}],
        "lawyer_verification_tasks": ["Verify all facts, law and source documents."],
        "scope_and_limits": ["Synthetic software test only."],
        "include_contents": True,
        "include_page_numbers": True,
        "include_source_references": True,
        "include_evidence_index": True,
    }


def main():
    for report_type in REPORT_TYPES:
        record = synthetic_record(report_type)
        normalised = normalise_professional_record(record)
        assert normalised["report_title"] == REPORT_TYPES[report_type]
        markdown = build_professional_markdown(record)
        assert REPORT_TYPES[report_type] in markdown
        assert "Important Professional Review Notice" in markdown

    chronology = build_professional_markdown(synthetic_record("chronology_evidence"))
    assert "Chronology" in chronology and "Evidence Index" in chronology
    assert "Analysis by Selected Dimension" not in chronology

    client = build_professional_markdown(synthetic_record("client_readable"))
    assert "Positions and Contentions" in client
    assert "Risk and Confidence Notes" not in client

    without_sources = synthetic_record()
    without_sources["include_source_references"] = False
    assert "synthetic-case.txt" not in build_professional_markdown(without_sources)

    record = synthetic_record()
    pdf = build_professional_pdf(record)
    docx = build_professional_docx(record)
    assert pdf.startswith(b"%PDF") and len(pdf) > 4000
    assert docx.startswith(b"PK") and len(docx) > 10000
    with zipfile.ZipFile(io.BytesIO(docx)) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
        footer_xml = "".join(
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.startswith("word/footer") and name.endswith(".xml")
        )
    assert "Google Gemini" in document_xml
    assert "PAGE" in footer_xml
    structured = json.loads(record_as_json(record))
    assert structured["matter_name"] == "Synthetic delivery dispute"
    print("OFFLINE_PROFESSIONAL_REPORT_OK pdf_bytes=%d docx_bytes=%d modes=%d" % (len(pdf), len(docx), len(REPORT_TYPES)))


if __name__ == "__main__":
    main()
