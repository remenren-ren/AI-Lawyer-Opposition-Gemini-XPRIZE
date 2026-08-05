import json
import tempfile
import tkinter as tk
from pathlib import Path

from Nido_StrikeOver_Offline_EN import DIMENSIONS, NidoOldSkinApp
from standard_report_contract import (
    REVIEW_STATUSES,
    SCHEMA_VERSION,
    build_standard_report,
    render_standard_markdown,
    write_standard_companions,
)


def test_contract():
    report = build_standard_report(
        "weakness_scan",
        "synthetic_contract_test",
        "Synthetic contract matter",
        "Australia / AU",
        findings=[{
            "id": "SYN-001",
            "dimension": "Evidence",
            "title": "Synthetic record gap",
            "finding": "A fictional source document has not been supplied.",
            "affected_side": "Positive side",
            "provider": "Gemini",
            "model": "gemini-test-recorded",
            "review_status": "ai_generated_unverified",
        }],
        provider_runs=[{
            "provider": "Gemini",
            "model": "gemini-test-recorded",
            "engine_source": "Synthetic test fixture",
            "run_reference": "fixture-1",
        }],
        missing_material=["Fictional source document"],
        synthetic=True,
        generated_at_utc="2026-08-01T00:00:00+00:00",
    )
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["report_id"].startswith("RPT-")
    assert report["matter"]["synthetic_demonstration"] is True
    assert report["findings"][0]["review_status"] in REVIEW_STATUSES
    assert report["provider_runs"][0]["provider"] == "Gemini"
    markdown = render_standard_markdown(report)
    assert "Synthetic demonstration:** YES" in markdown
    assert "ai_generated_unverified" in markdown
    with tempfile.TemporaryDirectory() as directory:
        paths = write_standard_companions(directory, "synthetic-contract", report)
        loaded = json.loads(Path(paths["json"]).read_text(encoding="utf-8-sig"))
        assert loaded["report_id"] == report["report_id"]
        assert Path(paths["markdown"]).exists()


def test_gui_bridges():
    app = NidoOldSkinApp()
    app.root.withdraw()
    try:
        dimension = DIMENSIONS[0][0]
        app.case_name_var.set("Synthetic all-report matter")
        app.jur_var.set("Australia / AU - Commonwealth")
        app.set_text(app.t_bg, "On 1 August 2026 a fictional delivery event occurred. Synthetic test only.")
        app.set_text(app.t_pos_args, "The fictional claimant relies on a delivery promise.")
        app.set_text(app.t_neg_args, "The fictional respondent disputes that promise.")
        app.set_text(app.t_pos_ev, "[P1] Fictional agreement")
        app.set_text(app.t_neg_ev, "[D1] Fictional response")

        single = app.generate_simple_single_point_report("A fictional agreement is missing its source page.")
        assert "Single-Issue Attack and Response Matrix" in single
        assert "Report ID:" in single
        assert "ai_generated_unverified" in single
        assert "No external model recorded" in single

        multi = app.generate_single_point_multi_dimension_report(
            "A fictional agreement is missing its source page.",
            "Argument",
            [dimension],
        )
        assert "Report ID:" in multi
        assert "Lawyer Verification" in multi

        synthetic_result = {
            "analysis_mode": "synthetic_fixture",
            "engine_metadata": {"provider": "Gemini", "model": "gemini-test-recorded"},
            "positive_side_weakness_patterns": [{
                "id": "SYN-P-001",
                "dimension": "Evidence",
                "name": "Fictional evidence gap",
                "pattern": "The fictional case omits a source page.",
                "source_case": "Synthetic Case 1",
            }],
            "negative_side_weakness_patterns": [],
        }
        synthetic_markdown = app.render_synthetic_weakness_summary_report(synthetic_result)
        assert "Synthetic demonstration:** YES" in synthetic_markdown
        assert "Gemini | gemini-test-recorded" in synthetic_markdown
        assert "real_case_analysed_or_mapped" in synthetic_markdown

        local_synthetic = app.render_synthetic_analogue_report({
            "synthetic_cases": [{"title": "Synthetic Case 1"}],
            "privacy_note": "No real client material is retained.",
        })
        assert "Synthetic demonstration:** YES" in local_synthetic
        assert "No external model recorded" in local_synthetic

        tactic_report = app.build_standard_tactic_frame_report(
            {"run_id": "synthetic-run", "case_key": "synthetic"},
            [{
                "tactic_name": "Evidence completeness pressure",
                "family": "Evidence chain",
                "opponent_move": "The opponent relies on a partial fictional record.",
                "counter_principle": "Require the complete fictional chain.",
                "counter_moves": ["Request the fictional source."],
                "example_snippets": ["Synthetic snippet"],
                "source_run_id": "synthetic-run",
                "score": 1,
                "follow_up_questions": [],
            }],
        )
        assert tactic_report["report_type"] == "tactic_frame_suggestions"
        assert tactic_report["findings"][0]["review_status"] == "ai_generated_unverified"
        assert tactic_report["provider_runs"][0]["provider"] == "Offline local workflow"
    finally:
        app.root.destroy()


def main():
    test_contract()
    test_gui_bridges()
    print("STANDARD_REPORT_SYSTEM_OK contract=1 gui_bridges=5 privacy=synthetic_only")


if __name__ == "__main__":
    main()
