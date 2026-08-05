# Release Verification Record

Build: `NIDO_StrikeOver_Judge_Test_Build_EN_20260804`

Prepared: 4 August 2026, Australia/Sydney

Source composition:

- Complete English desktop dual-line workbench from
  `离线律师软件专业报告版`.
- Current deployed client-reception service from
  `法律软件专业性改版`.
- Backup variants, caches, generated reports, local profiles, user data and
  secrets were excluded.

Verification performed with Python 3.10:

- Python compilation of the desktop core: passed.
- Offline professional report PDF/DOCX export: passed.
- Offline GUI-to-report bridge: passed.
- Standard report contract and GUI bridges: passed.
- Cloud service compilation: passed.
- 18-report client workflow: passed.
- Funnel visibility test: passed.
- Professional online PDF/DOCX outputs: passed.

Observed success markers:

```text
OFFLINE_PROFESSIONAL_REPORT_OK
OFFLINE_GUI_REPORT_BRIDGE_OK
STANDARD_REPORT_SYSTEM_OK
DEEP88_FLOW_OK
FUNNEL_VISIBILITY_OK
PROFESSIONAL_OUTPUTS_OK
```

Live working-project check:

- URL: https://ai-lawyer-opposition-cloud-1075289303183.australia-southeast1.run.app/client
- Page title: `Participating Law Firm AI Reception`
- Verified reachable on 4 August 2026.
- Verified with the displayed synthetic contract dispute only.

