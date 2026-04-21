---
tags: [engine, benchmark, feedback, labels, traceability, generation, l2]
summary: Generation-scoped benchmark record flow that carries candidate rankings into user feedback, published URLs, and post-performance labels
status: active
last_updated: 2026-04-21
---
# Benchmark Record Flow

## Purpose

`benchmark_runs/*.json` is the runtime trace that keeps one generation's candidate ranking and its later labels connected.

This exists so the system can recover:

- what the generator proposed
- which candidate the user preferred
- which copy rank was actually published
- what the published post later scored

Without this record, generation-time ranking and post-publication labels drift apart.

## Canonical Pointer

The API stores the path in:

- `Generation.results.benchmark_record_path`

That field is the canonical bridge from app-visible generations to the offline benchmark trace.

## Lifecycle

### 1. Generation completed

`optimize_copy_online.py` writes one record containing:

- task and user ids
- mode (`text` or `multimodal`)
- original input
- candidate list with rank, strategy, and scorer outputs
- original rank and top candidate ids

### 2. User feedback submitted

`/api/feedback` patches the same record with:

- `user_feedback.rating`
- `user_feedback.reasons`
- `user_feedback.copy_rank`

It also appends an audit event so later review can distinguish direct user feedback from inferred outcomes.

### 3. Published URL linked

`/api/generations/{gen_id}/submit-url` patches:

- `published_url`
- `published_rank`
- `label_state = published_linked`

`published_rank` and `feedback_copy_rank` must stay separate. One is user preference during review; the other is the copy actually shipped.

### 4. Performance staged

`/api/process-rewards` phase 1 patches:

- published post text
- scraped metrics
- temporary Gemini File API metadata, including `mime_type`
- `label_state = performance_staged`

This stage exists because File API uploads can be ready before multimodal embedding is ready.

### 5. Performance completed

`/api/process-rewards` phase 2 patches:

- final published-post metrics
- completed label state
- trailing audit event for the finished label

At this point the benchmark record becomes the most compact end-to-end trace for that generation.

## Operational Rules

- Benchmark record syncing is a side effect, not the primary transaction. API success must not depend on the JSON patch succeeding.
- Prefer one merged patch plus one appended event instead of multiple independent file rewrites.
- Keep event history append-only so debugging can reconstruct state transitions.
- Store media `mime_type` whenever a Gemini File API URI is reused later. The delayed embedding path depends on it.

## Related Files

- [benchmark_recorder.py](/c:/Users/ding9/Desktop/madoyo/backend/benchmark_recorder.py)
- [optimize_copy_online.py](/c:/Users/ding9/Desktop/madoyo/backend/optimize_copy_online.py)
- [generation.py](/c:/Users/ding9/Desktop/madoyo/backend/api/routers/generation.py)
- [feedback.py](/c:/Users/ding9/Desktop/madoyo/backend/api/routers/feedback.py)
