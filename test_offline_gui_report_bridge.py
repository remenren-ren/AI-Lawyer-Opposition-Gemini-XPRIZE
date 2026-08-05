import tkinter as tk

from Nido_StrikeOver_Offline_EN import DIMENSIONS, NidoOldSkinApp
from offline_professional_report import build_professional_docx, build_professional_pdf


def main():
    app = NidoOldSkinApp()
    app.root.withdraw()
    try:
        raw_dimension = DIMENSIONS[0][0]
        app.case_name_var.set("Synthetic offline matter")
        app.jur_var.set("Australia / AU - Commonwealth")
        app.set_text(app.t_bg, "On 1 July 2026 a fictional agreement was signed. Synthetic test only.")
        app.set_text(app.t_pos_args, "The fictional claimant says delivery was due.")
        app.set_text(app.t_neg_args, "The fictional respondent disputes the delivery term.")
        app.set_text(app.t_pos_ev, "[P1] Synthetic agreement\nCreated only for software testing.")
        app.set_text(app.t_neg_ev, "[D1] Synthetic response message")
        app.last_state = {
            "case_key": "synthetic-offline",
            "mode": "synthetic verification",
            "workflow_mode": "synthetic verification",
            "selected_dimensions": [raw_dimension],
            "options": {
                "confidentiality_mode": "Local-only confidentiality",
                "strategy_enhanced": False,
            },
            "case_search_context": {"enabled": False, "region": "Australia / AU"},
            "execution_trace": {"counts": {"cloud_calls_for_case_text": 0}},
            "rounds": {
                "final_reviewer": {"next_step": "Qualified counsel verifies the synthetic record."},
                "round1_opponent_attack": [{
                    "dimension": raw_dimension,
                    "finding": "The fictional date requires source verification.",
                    "confidence": "not independently scored",
                }],
                "round2_my_rebuttal": [{
                    "dimension": raw_dimension,
                    "response": "The fictional source document should be checked.",
                    "needed_material": ["Original synthetic agreement"],
                }],
            },
        }
        record = app.build_offline_professional_record()
        assert record["matter_name"] == "Synthetic offline matter"
        assert record["engine_metadata"]["provider"] == "Offline local workflow"
        assert record["chronology"][0]["date"] == "1 July 2026"
        assert record["evidence_index"][0]["item"] == "P1"
        assert record["issues_and_weaknesses"]
        assert record["dimension_analysis"]
        assert "Original synthetic agreement" in record["missing_information"]
        assert build_professional_pdf(record).startswith(b"%PDF")
        assert build_professional_docx(record).startswith(b"PK")
        print("OFFLINE_GUI_REPORT_BRIDGE_OK sections=10 evidence=%d" % len(record["evidence_index"]))
    finally:
        app.root.destroy()


if __name__ == "__main__":
    main()
