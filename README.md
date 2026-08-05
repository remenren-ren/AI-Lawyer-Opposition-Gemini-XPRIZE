# NIDO StrikeOver — Judge Test Build (English)

NIDO StrikeOver is a dual-line legal matter-preparation system. It combines a
simple public client-reception workflow with a lawyer-facing workbench for
offline preparation, authorised Gemini analysis, 18-dimension review,
two-sided attack-and-defence analysis, evidence mapping, weakness review and
professional report export.

This repository is the complete English judge build prepared for the 2026
Build with Gemini XPRIZE. It contains both the desktop workbench and the source
for the deployed client-reception service.

## Fastest working-product test

Open the deployed public demonstration:

https://ai-lawyer-opposition-cloud-1075289303183.australia-southeast1.run.app/client

Use only the synthetic example shown on the page or the synthetic case in
`samples/SYNTHETIC_HARBORBUILD_CASE.txt`. Do not upload real client material.

The public demonstration provides the easiest way to verify the live Gemini
workflow without installing software or supplying a personal API key.

## Desktop judge test on Windows

Requirements:

- Windows 10 or 11
- Python 3.10 or later
- Internet access only for the authorised online line

Setup:

```powershell
py -3.10 -m pip install -r requirements-desktop.txt
```

Then run:

```text
START_JUDGE_DEMO.bat
```

The launcher exposes both routes:

- Offline line: local matter preparation and privacy-first analysis. It starts
  without a model key and can be inspected with the included synthetic case.
- Online line: the complete multi-provider workbench. Local reviewer access and
  live model calls require credentials supplied through the documented
  environment configuration; credentials are deliberately not stored in this
  repository. The public Cloud Run demonstration is the no-install judge path.

Direct launchers are also included:

- `START_Offline_EN.bat`
- `START_Online_EN.bat`
- `START_GEMINI_RECEPTION_DEMO.bat`

## Core capabilities

- client intake with explicit AI-processing consent;
- focused missing-information questions;
- structured background, positions and evidence inventory;
- privacy-first offline preparation;
- Gemini-enabled online analysis;
- 18 independent legal and evidentiary review dimensions;
- weakness cards and evidence-gap identification;
- whole-matter, two-sided attack and rebuttal preparation;
- single-point review without losing the surrounding case context;
- professional Markdown, PDF, DOCX and structured-data reports;
- lawyer-review boundary and non-legal-advice notices;
- synthetic-data test path and no requirement to retain client case files.

## Repository structure

- Root Python files: complete English dual-line desktop workbench.
- `cloud_service/`: source for the Cloud Run client-reception service.
- `samples/`: synthetic test material only.
- `docs/`: architecture, operation and competition documentation.
- `TESTING_INSTRUCTIONS.md`: exact judge test sequence.
- `RELEASE_VERIFICATION.md`: build provenance and verification results.

## Demo videos

- Three-minute competition demonstration: https://youtu.be/xx0bSwki22s
- Complete dual-line English guide: https://youtu.be/MUeWr3WbtXE

## Privacy and professional boundary

All included case material is synthetic. The software is a legal-preparation
and lawyer-review support tool. It does not provide legal advice, determine a
case, replace a qualified lawyer or create a lawyer-client relationship.

Do not submit real personal, confidential, privileged or client material during
competition testing. The production customer controls its own deployment,
retention, access, model-provider and professional-review policies.

## Intellectual property

Copyright © 2026 Ren Xiaojun. All rights reserved. This publicly accessible
evaluation copy is provided only for testing and evaluation under the Build
with Gemini XPRIZE rules. Public visibility does not grant an open-source
licence. See `LICENSE.md`.
# AI-Lawyer-Opposition-Gemini-XPRIZE
Gemini-powered privacy-first dual-line legal matter preparation system. Copyright Ren Xiaojun; evaluation use only under LICENSE.md.
