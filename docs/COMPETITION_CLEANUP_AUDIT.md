# Competition Copy Cleanup Audit

Scope: `AI_Lawyer_Opposition_Gemini_Copy` only. Original software was not edited.

| Area checked | Finding | Action |
|---|---|---|
| Real API keys / token-looking strings | No retained real API key pattern after cleanup scan. | Cleared local provider key fields and verified with keyword scan. |
| Local screenshot/file path accidentally stored as key | `api_profiles.local.json` and `api_config.local.json` had a local ScreenClip path in the key field. | Replaced with empty key values. |
| Old backup source files | Multiple `.bak` / backup `.py` files from older online builds were present. | Removed from the competition copy. |
| Python cache | `__pycache__` was created by compile checks. | Removed after final verification. |
| Local Firebase auth stub file | `firebase_auth.local.json` existed as a local machine config file. | Removed; only `admin_cloud_config.example.json` remains as a non-secret template. |
| Local user/case history | `online_user_data`, `runs`, old regression output, and tactic export folders were present. | Removed from the competition copy. |
| SOP/training data files | `personal_sop`, `personal_sop_approved.jsonl`, and `personal_sop_candidates.json` exposed old training records. | Removed from the competition copy. |
| SOP/training UI entry points | Offline UI exposed SOP Center / Virtual Training / SOP health text. | Removed visible entry points. |
| SOP/training implementation | Offline code retained the reusable SOP/training database implementation. | Replaced with competition-disabled stubs so weak scan remains available but reusable training storage is absent. |
| Old commercial README | Old README referenced the wrong package framing. | Replaced with `README_Competition_EN.txt`. |
| Offline local engine dependency | `nido_strikeover_v4_function_lawyer_gui.py` is required by the offline app. | Restored and kept. |
| Firebase/Firestore integration | Needs to remain as optional Google Cloud-backed account/config restore. | Kept in launcher code and documented as admin-configured; not hard-coded with real project settings. |

Verification performed:

- `python -m py_compile` on launcher, online app, and offline app.
- Keyword scan for common secret patterns, old backups, local screenshot paths, and removed SOP/training labels.

