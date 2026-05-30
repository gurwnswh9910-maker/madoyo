---
tags: [copy, prompt, scorer, confidence-gate, data-manual, l3, 2026-05-05]
summary: Data-manual prompt upgrade loop and operating decision to collect data with upgrade_v10 plus repetition-only hygiene gate
status: active
last_updated: 2026-05-05
---
# 2026-05-05 Copy Prompt Upgrade

## Latest Operating Decision

`upgrade_v10` is now connected as the operating generator version for local automation and data-manual collection.

The operating hygiene gate keeps only the abnormal repeated-character cutoff: any non-space character repeated 6 or more times is rejected before scoring. The dynamic max-length hardcut was removed because the v10 hygiene rerun rejected too many otherwise useful candidates and degraded top-band results.

- Connected default version: `upgrade_v10`
- Connected paths: `작동중코드/optimize_copy_v2.py`, `작동중코드/copy_generator_v2.py`, `데이터수동화/data_manual_pipeline.py`
- Kept hard gate: `same_char_repeat_6`
- Removed hard gate: dynamic max length `1.2x`
- Evidence: `compare_upgrade_v9_vs_upgrade_v10_20260505_193430`, `compare_upgrade_v9_vs_upgrade_v10_hygiene_20260505_202929`

Interpretation: v10 had enough top-band strength to operate and collect real data, but its known failure mode is emotional/repeated-character runaway. The first production guardrail should target that specific failure mode, not broad length pressure.

## Context

This note records the prompt-upgrade loop run on the saved data-manual source set.

- Source run: `data_manual_20260503_205802`
- Baseline: `legacy_current_v1`
- Candidate versions tested here: `upgrade_v4` through `upgrade_v9`
- Evaluation path: local `데이터수동화/compare_prompt_versions.py`
- Scorer path: local confidence-gated copy scorer in the active automation working-code path

The user revised the success criterion during the loop: original top50 dominance was no longer the primary target; the key target became "push the original copy down."

## Main Result

`upgrade_v9` was the best original-push candidate in the first benchmark loop. After the persona and hygiene experiments, the operating branch moved to `upgrade_v10` for data collection because its top-band result was strong enough and the failure mode can be targeted with a narrower hygiene gate.

- Original rank lowered: `9 / 10`
- Original rank improved: `0 / 10`
- Baseline original-rank-1 rows cleared: `2 / 2`
- Delta sum: `+167`
- Top5 challenger share: `50 / 50 = 100%`
- Top50 challenger share: `300 / 480 = 62.5%`
- Compare artifact: `compare_legacy_current_v1_vs_upgrade_v9_20260505_175900`
- Prompt run: `prompt_eval_upgrade_v9_20260505_174030`

This passes the revised original-push objective and the top5 condition. It does not pass the older top50 `90%` condition.

## Version Reading

| version | reading |
|---|---|
| `upgrade_v2` | strongest earlier original-push baseline: `9 / 10`, rank1 cleared `2 / 2`, top5 `76%` |
| `upgrade_v5` | top-heavy: top5 `88%`, rank1 cleared `2 / 2`, but original lowered only `7 / 10` |
| `upgrade_v7` | strong raw original push but poor top bands and output leaks |
| `upgrade_v8` | first candidate to reach top5 `90%`, but markdown leaks appeared |
| `upgrade_v9` | best combined result: original lowered `9 / 10`, top5 `100%`, no simple hygiene-pattern hits |

## Hard Case

Row `2`, URL `https://www.threads.com/@lemon_bbubbu/post/DX1s48iGsCJ`, remained unchanged at original rank `10 -> 10`.

Original text:

`너 때문에!!!! 내 주식!!!! 다 말아먹고!!!!!!`

Product name:

`도널드 트럼프 욕실 청소 브러시 재미 있은 화장실 선물 변기 도구, 2. White C, 1개 - 씽크선반/진열대`

The next prompt branch should specifically attack this short rage-quote format without inventing fake context.

## Hygiene And Caveat

- `upgrade_v7`: `Explanation:` and repeated filler leaks appeared.
- `upgrade_v8`: markdown emphasis markers appeared frequently.
- `upgrade_v9`: searched raw candidates for `Explanation:`, `**`, repeated filler fragments, `IMPROVEMENT`, and `FINAL_COPY`; no hits.
- `upgrade_v9` generation did hit Gemini embedding `429 RESOURCE_EXHAUSTED`; the run completed with `raw=492`, `accepted=489`. Re-run once under stable quota before treating it as a locked production prompt.

## Artifact

Detailed lab note:

- [20260505 copy prompt upgrade report](/c:/Users/ding9/Desktop/madoyo/연구소/ml연구소/20260505_copy_prompt_upgrade/prompt_iteration_report_20260505.md)
