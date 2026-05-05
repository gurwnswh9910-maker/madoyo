# 2026-05-05 Copy Prompt Upgrade Iteration Report

## Latest Operating Note

`upgrade_v10` is now the operating prompt version to collect more data. Earlier sections keep the v9 benchmark history intact; the later operating decision records why v10 was connected and why the length hardcut was removed.

## Scope

- Branch: `copy_upgrade`
- Source data run: `data_manual_20260503_205802`
- Baseline prompt/version label: `legacy_current_v1`
- Evaluation script: `데이터수동화/compare_prompt_versions.py`
- Rows: 10 saved Threads URLs, no fresh scraping
- Primary revised goal: push the original copy lower in the confidence-gated local scorer ranking.
- Secondary guardrails: keep top5 share high, clear URLs where the original was rank 1, and avoid output hygiene leaks.

## Result

`upgrade_v9` is the current best candidate.

- Original rank lowered: `9 / 10`
- Original rank improved: `0 / 10`
- Original-rank-1 rows cleared: `2 / 2`
- Original-rank delta sum: `+167`
- Mean delta: `+16.7`
- Top5 challenger share: `50 / 50 = 100%`
- Top50 challenger share: `300 / 480 = 62.5%`

This passes the revised "original push-down" goal and the top5 condition. It does not pass the older top50 `90%` condition.

## Leaderboard

Sorted by original-lowered count, then top5 share, then delta.

| version | original lowered | original improved | rank1 cleared | sum delta | mean delta | top5 | top50 | compare id |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `upgrade_v9` | 9/10 | 0/10 | 2/2 | 167 | 16.7 | 100.0% | 62.5% | `compare_legacy_current_v1_vs_upgrade_v9_20260505_175900` |
| `upgrade_v2` | 9/10 | 0/10 | 2/2 | 126 | 12.6 | 76.0% | 42.8% | `compare_legacy_current_v1_vs_upgrade_v2_20260504_000958` |
| `upgrade_v8` | 8/10 | 1/10 | 2/2 | 143 | 14.3 | 90.0% | 47.0% | `compare_legacy_current_v1_vs_upgrade_v8_20260505_173505` |
| `upgrade_v7` | 8/10 | 1/10 | 2/2 | 245 | 24.5 | 54.0% | 26.3% | `compare_legacy_current_v1_vs_upgrade_v7_20260505_171457` |
| `upgrade_v5` | 7/10 | 2/10 | 2/2 | 71 | 7.1 | 88.0% | 55.8% | `compare_legacy_current_v1_vs_upgrade_v5_20260505_162940` |
| `upgrade_v4` | 7/10 | 1/10 | 1/2 | 94 | 9.4 | 70.0% | 47.6% | `compare_legacy_current_v1_vs_upgrade_v4_20260505_160658` |
| `upgrade_v6` | 7/10 | 1/10 | 1/2 | 96 | 9.6 | 66.0% | 46.4% | `compare_legacy_current_v1_vs_upgrade_v6_20260505_165234` |
| `upgrade_v1` | 6/10 | 2/10 | 1/2 | 55 | 5.5 | 72.0% | 48.8% | `compare_legacy_current_v1_vs_upgrade_v1_20260503_234840` |
| `upgrade_v3` | 5/10 | 3/10 | 1/2 | 28 | 2.8 | 54.0% | 42.9% | `compare_legacy_current_v1_vs_upgrade_v3_20260504_003907` |

## Row-Level Notes For `upgrade_v9`

| row | baseline original rank | v9 original rank | delta | reading |
|---:|---:|---:|---:|---|
| 0 | 17 | 40 | +23 | cleared strongly |
| 1 | 34 | 45 | +11 | cleared |
| 2 | 10 | 10 | 0 | unchanged; Trump toilet-brush stock-loss original remains the hard case |
| 3 | 14 | 40 | +26 | cleared strongly |
| 4 | 13 | 32 | +19 | cleared |
| 5 | 1 | 39 | +38 | original rank-1 cleared |
| 6 | 8 | 26 | +18 | cleared |
| 7 | 51 | 52 | +1 | already weak original, still slightly lower |
| 8 | 1 | 18 | +17 | original rank-1 cleared |
| 9 | 2 | 16 | +14 | strong original cleared |

## Output Hygiene

- `upgrade_v7`: `Explanation:` leaks found in 2 raw candidates; repeated filler-pattern hits found in 2 raw candidates.
- `upgrade_v8`: markdown emphasis marker `**` found in 118 raw-candidate lines.
- `upgrade_v9`: searched for `Explanation:`, markdown marker `**`, repeated filler fragments, `IMPROVEMENT`, and `FINAL_COPY`; 0 hits in raw candidates.

## Caveats

- `upgrade_v9` generation logged Gemini embedding `429 RESOURCE_EXHAUSTED` during one row. The run still completed, but `raw=492` and `accepted=489`, so three generated candidates were not accepted into the final pool.
- The result is a local confidence-gated scorer optimization result, not a live post-performance claim.
- The old top50 `90%` target remains unmet. The current success claim is specifically for the revised "push down the original" objective.

## Decision

Use `upgrade_v9` as the current prompt-upgrade candidate for the next data-manual copy upgrade branch. Keep `upgrade_v2` as the strongest prior baseline for original push-down, because it also lowered `9 / 10` originals and had no observed quota caveat in this comparison set.

Next useful experiment: target row 2 specifically with a prompt branch that attacks the "short rage quote" pattern without adding fake context, then compare it against `upgrade_v9`.

## 2026-05-05 운영 연결 결정: v10 + 반복문자 위생 게이트

사용자 판단과 후속 비교 결과를 반영해 운영 기본 생성 프롬프트는 `upgrade_v10`으로 연결한다. v10은 v9 대비 원본 밀어내기에서는 다소 혼합적이었지만, top band에서 우세 경향이 충분히 보였고 특히 top5 성과가 좋았다.

핵심 비교 결과:

| 비교 | challenger | top50 | top5 | 해석 |
|---|---|---:|---:|---|
| `compare_upgrade_v9_vs_upgrade_v10_20260505_193430` | `upgrade_v10` | `292 / 471 = 62.0%` | `39 / 50 = 78.0%` | v9 대비 상위권 경쟁력이 있음 |
| `compare_upgrade_v9_vs_upgrade_v11_20260505_201304` | `upgrade_v11` | `176 / 453 = 38.9%` | `2 / 50 = 4.0%` | 이중 페르소나와 압축 방향이 과하게 작동 |
| `compare_upgrade_v9_vs_upgrade_v10_hygiene_20260505_202929` | `upgrade_v10` + 길이 하드컷 | `152 / 277 = 54.9%` | `22 / 50 = 44.0%` | 길이 하드컷이 과도하게 후보를 제거 |

위생 문제의 실제 원인은 v10 자체의 전반 품질 저하라기보다, 감정 루프에 빠진 일부 후보가 같은 문자를 비정상적으로 반복하면서 scorer가 이를 강하게 오판한 케이스였다. 대표 케이스는 `prompt_eval_upgrade_v10_20260505_191326`의 row 0 `DYN_2_3_C`로, `ㅜ` 반복이 수만 자까지 이어졌고 scorer에서 1위로 올라갔다.

따라서 이번 운영 연결에서는 최대 글자수 기반 하드컷을 제거하고, `same_char_repeat_6`만 하드 위생 게이트로 유지한다.

- 운영 기본 생성 버전: `upgrade_v10`
- 적용 경로: `작동중코드/optimize_copy_v2.py`, `작동중코드/copy_generator_v2.py`, `데이터수동화/data_manual_pipeline.py`
- 유지하는 위생 컷: 공백이 아닌 같은 글자 6회 이상 반복
- 제거한 위생 컷: 동적 최대 글자수의 1.2배 초과 후보 제거

다음 운영 데이터는 v10 기본 생성과 반복문자 컷만 적용한 상태로 쌓고, 실제 축적 데이터에서 반복문자 컷 발생률, 원본 순위 분포, top5 점유율을 다시 본다.
