---
tags: [map, scorer, benchmark, research, l1, 0420]
summary: Hub for copy scorer benchmark work, legacy mutation loops, deployment decisions, and canonical research artifacts
status: active
last_updated: 2026-04-21
---
# Copy Scorer Research Hub

## Purpose

This page is the KB entry point for the copy-scorer research stream.

Use it when you need to recover:

- what the real target is
- which benchmark is safe to trust
- what the current deployment default is
- which legacy-centered loops have already been tried
- where the latest research artifacts live

## North Star

The real target is:

- given one media asset and multiple copy variants
- choose the real winner with high probability

Not:

- global virality regression by itself

## Current Benchmark Policy

Main reading order:

1. Strict pseudo Tier1
2. Recent live-report validation (`0415~0417`)
3. Tier 0 only as a guardrail

Current benchmark caveats:

- strict pseudo Tier1 is only `19` groups and should be treated as an in-corpus probe
- `0414` was requested as a bridge validation file but was not found locally
- recent validation is therefore `0415~0417` only right now

## Deployment Policy

Current runtime default:

- legacy `reg` and `hurdle`
- promoted `highlow_raw_only` tournament
- online wrapper: [copy_scorer_v4_highlow_online.py](/c:/Users/ding9/Desktop/madoyo/backend/copy_scorer_v4_highlow_online.py)

Preserved for rollback and reference:

- legacy scorer logic and artifacts remain intact
- legacy remains the reference line for Tier 0 frozen compatibility

Why this default was promoted:

- strict pseudo Tier1 exact top1 stayed tied with legacy
- recent `0415~0417` operational metrics improved clearly
- Tier 0 rolling improved
- Tier 0 frozen still favors legacy, so legacy is preserved instead of overwritten

Runtime traceability now also depends on:

- [[L2-Atomic/engines/benchmark_record_flow|Benchmark Record Flow]]

That record is the bridge between online candidate ranking and later user or post-performance labels.

## Canonical Research Notes

- [Master benchmark lab](/c:/Users/ding9/Desktop/madoyo/?곌뎄??copy_scorer_benchmark_lab.md)
- [0420 benchmarking lessons](/c:/Users/ding9/Desktop/madoyo/knowledge_base/L3-Insights/Reasoning/copy_scorer_benchmarking_0420.md)
- [Visual pseudo Tier1 lab](/c:/Users/ding9/Desktop/madoyo/?곌뎄??visual_pseudo_tier1_lab.md)
- [Outcome pairwise lab](/c:/Users/ding9/Desktop/madoyo/?곌뎄??outcome_pairwise_lab.md)
- [Expanded live-report benchmark lab](/c:/Users/ding9/Desktop/madoyo/?곌뎄??expanded_live_report_benchmark_lab.md)
- [Cross-benchmark transfer lab](/c:/Users/ding9/Desktop/madoyo/?곌뎄??cross_benchmark_transfer_lab.md)
- [Legacy v4 strict eval](/c:/Users/ding9/Desktop/madoyo/?곌뎄??legacy_v4_strict_eval.md)

## Canonical Benchmarks And Results

- [Strict pseudo Tier1 benchmark](/c:/Users/ding9/Desktop/madoyo/?곌뎄??visual_pseudo_tier1_best_benchmark.json)
- [Expanded recent v4 eval](/c:/Users/ding9/Desktop/madoyo/?곌뎄??expanded_live_report_v4_eval.json)
- [Expanded recent text-model eval](/c:/Users/ding9/Desktop/madoyo/?곌뎄??expanded_live_report_text_model_eval.json)
- [Cross-benchmark transfer eval](/c:/Users/ding9/Desktop/madoyo/?곌뎄??cross_benchmark_transfer_eval.json)
- [Legacy v4 on strict pseudo Tier1](/c:/Users/ding9/Desktop/madoyo/?곌뎄??legacy_v4_on_strict_pseudo_tier1.json)
- [Legacy v4 time-sensitivity check](/c:/Users/ding9/Desktop/madoyo/?곌뎄??legacy_v4_on_strict_pseudo_tier1_time_sensitivity.json)
- [Legacy pairing mutation search](/c:/Users/ding9/Desktop/madoyo/?곌뎄??legacy_pairing_mutation_search.json)
- [Legacy vs promoted highlow compare](/c:/Users/ding9/Desktop/madoyo/?곌뎄??legacy_vs_highlow_compare.json)

## Legacy Mutation Loop Artifacts

These are the main legacy-centered Ralph-loop outputs.

- [Legacy full-method mutations](/c:/Users/ding9/Desktop/madoyo/?곌뎄??legacy_method_mutation_search.json)
- [Legacy component mutations](/c:/Users/ding9/Desktop/madoyo/?곌뎄??legacy_component_mutation_search.json)
- [Legacy tournament gate search](/c:/Users/ding9/Desktop/madoyo/?곌뎄??legacy_tournament_gate_search.json)
- [Legacy pairwise aggregation search](/c:/Users/ding9/Desktop/madoyo/?곌뎄??legacy_pairwise_aggregation_search.json)
- [Legacy pairwise blend focus](/c:/Users/ding9/Desktop/madoyo/?곌뎄??legacy_pairwise_blend_focus.json)
- [Legacy top1 policy search](/c:/Users/ding9/Desktop/madoyo/?곌뎄??legacy_top1_policy_search.json)
- [Legacy top1 policy search log](/c:/Users/ding9/Desktop/madoyo/?곌뎄??legacy_top1_policy_search.jsonl)
- [Legacy pairing mutation search](/c:/Users/ding9/Desktop/madoyo/?곌뎄??legacy_pairing_mutation_search.json)

## Reusable Scripts

- [Build Threads Excel embeddings from links](/c:/Users/ding9/Desktop/madoyo/backend/build_threads_excel_embeddings_from_links.py)
- [Legacy method mutation search](/c:/Users/ding9/Desktop/madoyo/backend/legacy_method_mutation_search.py)
- [Legacy component mutation search](/c:/Users/ding9/Desktop/madoyo/backend/legacy_component_mutation_search.py)
- [Legacy tournament gate search](/c:/Users/ding9/Desktop/madoyo/backend/legacy_tournament_gate_search.py)
- [Legacy pairwise aggregation search](/c:/Users/ding9/Desktop/madoyo/backend/legacy_pairwise_aggregation_search.py)
- [Legacy pairwise blend focus](/c:/Users/ding9/Desktop/madoyo/backend/legacy_pairwise_blend_focus.py)
- [Legacy top1 policy search](/c:/Users/ding9/Desktop/madoyo/backend/legacy_top1_policy_search.py)
- [Legacy pairing mutation search](/c:/Users/ding9/Desktop/madoyo/backend/legacy_pairing_mutation_search.py)
- [Legacy vs promoted highlow compare](/c:/Users/ding9/Desktop/madoyo/backend/compare_legacy_vs_highlow.py)
- [Export promoted highlow tournament artifact](/c:/Users/ding9/Desktop/madoyo/backend/export_highlow_tournament_model.py)
- [Promoted online scorer wrapper](/c:/Users/ding9/Desktop/madoyo/backend/copy_scorer_v4_highlow_online.py)

## Current Reality Check

What is currently true:

- legacy v4.5 is still the strict pseudo Tier1 incumbent on exact top1
- the promoted online default is now `legacy reg/hurdle + highlow_raw_only tournament`
- pair construction is now a confirmed lever
- the current bottleneck is still `winner retrieval`
- legacy artifacts remain preserved for rollback and for Tier 0 frozen reference

Current best-known readings:

- strict benchmark comparison:
  - legacy exact top1: `13 / 19 = 68.4%`
  - promoted exact top1: `13 / 19 = 68.4%`
  - promoted scorer wins on average regret
- recent operational comparison (`0415~0417`):
  - legacy `chosen_true_rank_mean = 17.33`
  - promoted `chosen_true_rank_mean = 8.33`
  - legacy `chosen_top5_mean = 0.0`
  - promoted `chosen_top5_mean = 0.3333`
  - legacy `winner_pred_rank_mean = 21.33`
  - promoted `winner_pred_rank_mean = 11.67`
- benchmark-stack summary:
  - strict pseudo Tier1: tie on exact top1, promoted scorer wins on regret
  - recent `0415~0417`: promoted scorer wins clearly
  - Tier 0 frozen: legacy wins
  - Tier 0 rolling: promoted scorer wins

## What To Read First Next Session

1. [Master benchmark lab](/c:/Users/ding9/Desktop/madoyo/?곌뎄??copy_scorer_benchmark_lab.md)
2. [0420 benchmarking lessons](/c:/Users/ding9/Desktop/madoyo/knowledge_base/L3-Insights/Reasoning/copy_scorer_benchmarking_0420.md)
3. [Legacy vs promoted highlow compare](/c:/Users/ding9/Desktop/madoyo/?곌뎄??legacy_vs_highlow_compare.json)

## Next Branch

Do not repeat a broad family sweep first.

The next harder branch is:

- deeper pair construction around `highlow_raw_only`
- stronger reranking over the improved shortlist
- or a new data-collection loop that creates real sibling-winner labels
