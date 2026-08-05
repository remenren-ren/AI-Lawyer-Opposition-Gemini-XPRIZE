# Judge Testing Instructions

## Route A — live working project

1. Open:
   https://ai-lawyer-opposition-cloud-1075289303183.australia-southeast1.run.app/client
2. Select `Describe a legal matter`.
3. Use the synthetic HarborBuild scenario displayed on the page or copy the
   content from `samples/SYNTHETIC_HARBORBUILD_CASE.txt`.
4. Confirm the AI-processing consent box.
5. Continue through the focused missing-information questions.
6. Review the organised case material, both-side positions, evidence inventory,
   disclaimer and controlled review route.
7. Do not enter real personal or client data.

Expected result: the service converts an unstructured synthetic request into a
structured, lawyer-ready matter and exposes the controlled next-stage review.

## Route B — complete desktop workbench

1. Install Python 3.10+.
2. From the repository root, run:

   `py -3.10 -m pip install -r requirements-desktop.txt`

3. Double-click `START_JUDGE_DEMO.bat`.
4. Choose the offline line to inspect the privacy-first workbench without any
   external model credential.
5. Load or paste `samples/SYNTHETIC_HARBORBUILD_CASE.txt`.
6. Inspect the positive and negative positions, evidence areas, review
   dimensions, weakness workflow, opposition workflow and report exports.
7. Choose the online line to inspect the authorised Gemini/provider workflow.
   The local reviewer route is `demo` / `demo`. Live external model calls need
   a reviewer-controlled key; no secret is embedded in the repository.

## Automated verification

Run `RUN_TESTS.bat` from the repository root.

Expected success markers:

- `OFFLINE_PROFESSIONAL_REPORT_OK`
- `OFFLINE_GUI_REPORT_BRIDGE_OK`
- `STANDARD_REPORT_SYSTEM_OK`
- `DEEP88_FLOW_OK`
- `FUNNEL_VISIBILITY_OK`
- `PROFESSIONAL_OUTPUTS_OK`

## Testing limits

- Use synthetic materials only.
- Do not rely on generated material as legal advice.
- Do not add or commit API keys, tokens, passwords, customer records or reports.
- The public service is free for competition evaluation during the judging
  period, subject to reasonable testing and provider quotas.

