---
tags: [data_collection, reembedding, cleanup, pkl, operations]
summary: 2026-05-22 body correction, reembedding completion, pkl replacement, Excel quarantine, and next collection cutoff.
status: stable
last_updated: 2026-05-22
---
# 2026-05-22 data collection and reembedding cleanup

## Operational conclusion

- Body correction and reembedding work through the 2026-05-22 batch is complete.
- Next Threads data collection should start from posts uploaded after `2026-05-22 02:00 KST`.
- Agent 02 is no longer part of the active operation. `correctbody` is now a handoff/archive source, not an ongoing split-review workspace.
- Active automation/search should keep using `작동중코드/embeddings_v2_final.pkl`.

## PKL handling

- Pulled `correctbody` to `0757ce5 fix: treat invalid posts as completed media reviews`.
- New files received from `correctbody/embedding_outputs`:
  - `original_update_113_candidate.pkl`: 113 corrected original-final candidates.
  - `excel_not_in_pkl_1930.pkl`: 1,930 URL 신규 추가 pkl, kept separate.
  - `my_accounts_ml_1083.pkl`: 1,083 내계정 통합 ML pkl, kept separate.
- Active final pkl was not expanded with the separate datasets. Only `original_update_113_candidate.pkl` was overlaid onto the existing final pkl.
- Overlay result:
  - Existing final count before: `text=4290`, `multi=4290`, `metadata=4290`, `visual=4161`.
  - Updated rows: `113`.
  - Exact URL matches: `92`.
  - `threads.com`/`threads.net` domain-normalized post-id matches: `21`.
  - Active final count after: `text=4290`, `multi=4290`, `metadata=4290`, `visual=4160`.
- Backup and audit paths:
  - Backup: `C:\Users\ding9\Desktop\폐기\madoyo_cleanup_20260522\pkl_backups\embeddings_v2_final_before_20260522.pkl`
  - Active replacement: `C:\Users\ding9\Desktop\madoyo\작동중코드\embeddings_v2_final.pkl`
  - E-drive final copy: `E:\madoyo_embeddings\20260522\final\embeddings_v2_final_20260522_overlay113.pkl`
  - Summary: `knowledge_base/L3-Insights/Reasoning/reembedding_cleanup_20260522_manifests/pkl_overlay113_summary.json`

## Separate PKL storage

The following are intentionally outside the active final pkl:

- New-added pkl:
  - `E:\madoyo_embeddings\20260522\separate\new_added\excel_not_in_pkl_1930.pkl`
- My-account combined ML pkl:
  - `E:\madoyo_embeddings\20260522\separate\my_accounts_combined\my_accounts_ml_1083.pkl`
- Legacy text-only my-account pkl copies:
  - `E:\madoyo_embeddings\20260522\separate\my_accounts_text_only_legacy\threads_slow_report_0430_0112_text_embeddings_20260501.pkl`
  - `E:\madoyo_embeddings\20260522\separate\my_accounts_text_only_legacy\threads_slow_report_0430_1258_text_embeddings_20260501.pkl`
  - `E:\madoyo_embeddings\20260522\separate\my_accounts_text_only_legacy\threads_slow_report_0430_1724_text_embeddings_20260501.pkl`
- Overlay source audit copy:
  - `E:\madoyo_embeddings\20260522\separate\original_update_candidate\original_update_113_candidate.pkl`

## Excel cleanup

- Existing E-drive Excel scan found 94 files, but URL coverage was not enough to prove that madoyo Excel was already fully integrated.
- URL coverage scan result:
  - madoyo unique Threads post keys: `15204`
  - E-drive unique Threads post keys: `1594`
  - madoyo post keys missing from E-drive scan: `13642`
- Because that failed the integration check, madoyo Excel files were first archived to E-drive with relative paths preserved.
- Archive and quarantine result:
  - Archived to: `E:\madoyo_excel_archive_20260522\from_madoyo`
  - Quarantined to: `C:\Users\ding9\Desktop\폐기\madoyo_cleanup_20260522\excel_from_madoyo`
  - Normal Excel files moved by PowerShell manifest: `316`
  - Residual Excel lock/temp files moved by Python scan: `4`
  - Total Excel-like files moved: `320`
  - Move errors: `0`
  - Remaining Excel files under madoyo: `0`
- Main manifests:
  - `knowledge_base/L3-Insights/Reasoning/reembedding_cleanup_20260522_manifests/excel_url_coverage_summary.json`
  - `knowledge_base/L3-Insights/Reasoning/reembedding_cleanup_20260522_manifests/madoyo_excel_archive_and_move_summary.json`
  - `knowledge_base/L3-Insights/Reasoning/reembedding_cleanup_20260522_manifests/madoyo_excel_archive_and_move_manifest.csv`
  - `knowledge_base/L3-Insights/Reasoning/reembedding_cleanup_20260522_manifests/madoyo_excel_residual_move_summary.json`

## Temporary-code quarantine

- Quarantined only obvious temporary code/artifacts:
  - `test_*.py`
  - `debug_*.py`
  - dated one-off schedule/watch scripts
  - `검토후삭제_0428_본문검증`
  - `codex_scratch`
  - `threads_debug_*`
- Result:
  - Candidates moved: `26`
  - Errors: `0`
  - Destination: `C:\Users\ding9\Desktop\폐기\madoyo_cleanup_20260522\temp_scripts_from_madoyo`
  - Manifest: `knowledge_base/L3-Insights/Reasoning/reembedding_cleanup_20260522_manifests/temp_scripts_move_manifest.csv`
- Important: stable operation paths were not moved: `자동화/scraper.py`, `자동화/threads_auto_pipeline.py`, `자동화/publisher.py`, `수동화/manual_pipeline.py`, `반자동/semi_auto_publish.py`, and `작동중코드`.

## Useful attempts and decisions from this run

- Recipe classification should be a future automation branch, not part of ordinary body-only review. Recipe posts need body text plus first-comment recipe/material text because that gives a natural reason to click ingredient links.
- Body review scraper must stay separate from automation scraper. The review tool only needs URL open and body extraction; first-comment checks, media collection, and upload fallback logic make it heavier than necessary.
- For body extraction, line breaks matter. The useful direction was DOM candidate text -> climb to a common content container -> collect descendant text blocks, instead of extracting only the first matching span.
- Invalid posts should be labeled explicitly, not mixed into scraping failures.
- 429 handling for review work remains: stop immediately, record URL/agent/progress, rest, and resume slower.
- Generated-copy scoring does not run the pkl-building DOM parser. Candidate copies are parsed from generated `[FINAL_COPY]` output and then cleaned/guarded before embedding/scoring. The pkl parser is for source Threads posts.
- When replacing pkl content, URL equality alone is not enough because old final data can use `threads.net` while new review output uses `threads.com`. Use post code as the canonical matching key and preserve the active final key.
