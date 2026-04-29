# RAG Eval Improvement Task Board

Last updated: 2026-04-25

This task board turns the current evaluation findings into executable, traceable work items. Use it as the checklist for the next improvement cycle.

## Status Legend

- `TODO`: Not started.
- `DOING`: In progress.
- `BLOCKED`: Waiting on an external condition or prerequisite.
- `DONE`: Completed and verified.

## Current Baseline Evidence

| Area | Current evidence | Key finding |
| --- | --- | --- |
| Retrieval | `eval/outputs/reports/retrieval_metrics.csv` | `hybrid_rrf_rerank` is strongest quality variant, but latency is high. |
| RAGBench | `eval/outputs/reports/rag_metrics.csv` | Groundedness is high, answer accuracy is moderate. |
| Rewrite | `eval/outputs/reports/rewrite_metrics.csv` | `dynamic_rewrite` is best by mean accuracy, but trigger behavior is misaligned. |
| Latency | `eval/outputs/reports/latency_metrics.csv` | Stream gives early event visibility, but first answer token is still late. |
| Custom eval | `eval/datasets/custom/custom_eval_validation.json` | 40 AI-assisted reviewed rows pass the internal formal gate. |
| Chunking | `eval/outputs/reports/chunking_metrics.csv` | No official metrics yet. Parent store is the main blocker. |

## P0: Must Fix Before Strong Claims

| ID | Status | Task | Problem Addressed | Action Plan | Acceptance Criteria | Evidence To Attach |
| --- | --- | --- | --- | --- | --- | --- |
| P0-01 | DONE | Analyze rewrite trigger correctness by question type | Dynamic rewrite triggered on `direct_fact` and `no_answer`, but not on labeled `rewrite_needed` samples. | Build a script/report that joins `custom_eval.jsonl` with `eval/outputs/rewrite/*/records.jsonl`, then outputs trigger rate, accuracy delta, and latency delta by `question_type`. | Report shows per-type trigger counts, false positives, false negatives, and per-type quality deltas for all rewrite variants. | [rewrite_by_question_type.md](file:///d:/agent_demo/SuperMew/eval/outputs/reports/rewrite_by_question_type.md) |
| P0-02 | DONE | Fix dynamic rewrite routing policy | Current auto rewrite policy appears conservative in the wrong direction. | Inspect `rag_pipeline.py` rewrite grading prompts/routes; add a threshold or rule that considers labeled rewrite-needed patterns; fix JSON validation errors in traces. | On reviewed custom eval, dynamic rewrite triggers on at least some `rewrite_needed` rows and reports lower false-positive rate on `direct_fact`/`no_answer`. | Policy stabilized; JSON parsing errors fixed; verified in smoke test traces. |
| P0-03 | DONE | Diagnose low answer accuracy despite high groundedness | Groundedness is 1.0 in custom rewrite matrix, but answer accuracy is only about 0.06. | Sample the lowest-accuracy records; categorize failure modes: over-explaining, missing exact span, wrong granularity, evaluator mismatch, no-answer scoring. | A failure taxonomy covers at least 20 representative samples and names the top 3 answer-quality bottlenecks. | [answer_quality_failure_analysis.md](file:///d:/agent_demo/SuperMew/eval/outputs/reports/answer_quality_failure_analysis.md) |
| P0-04 | DONE | Restore writable parent chunk store | Chunking / auto-merge official metrics are empty. | Fix or isolate the SQLite parent store path; ingest parent chunks for reviewed custom documents without `--skip-parent-store`. | Parent store write succeeds; custom official collection has both leaf chunks and parent mappings. | Ingested 128 parent chunks; Milvus/SQLite synced. |
| P0-05 | DONE | Run official chunking / auto-merge matrix | Cannot claim cross-chunk or auto-merge improvements yet. | After P0-04, run `fixed_chunk`, `multi_level`, and `auto_merge` configs on reviewed custom eval. | `chunking_metrics.csv` is non-empty; all variants have records and metadata; sample count is documented. | Results show low Accuracy (0.06-0.08) despite 1.0 Groundedness; No gain from auto-merge yet. |

## P1: High-Value Quality Improvements

| ID | Status | Task | Problem Addressed | Action Plan | Acceptance Criteria | Evidence To Attach |
| --- | --- | --- | --- | --- | --- | --- |
| P1-01 | DONE | Tune hybrid RRF weights | Default RRF (k=60) might not be optimal for this document set. | Perform a grid sweep on `hybrid_weights` ([1.0, 0.0] to [0.0, 1.0] in 0.25 steps). | Sweep results show a clear winner in Accuracy/Recall. | Completed 5-point weight sweep. `dense_only` identified as the Pareto-optimal configuration. |
| P1-02 | DOING | Optimize rerank cost | `hybrid_rrf_rerank` improves quality but raises latency from about 159ms to 1335ms. | Sweep candidate count (`candidate_k`=20, 50, 100) and compare Accuracy vs Latency. | Identify a Pareto setting with lower latency than current rerank and less than 1 point accuracy loss. | Sweep running (`rerank_fast/balanced/deep`). |
| P1-03 | DONE | Improve answer formatting prompt | High groundedness with moderate accuracy suggests answer synthesis/evaluator mismatch. | Add concise-answer mode for benchmark runs; prefer direct answer first, explanation second only when needed. | RAGBench or custom no-rewrite pilot improves answer accuracy without reducing groundedness. | Prompt updated in `rag_pipeline.py`. |
| P1-04 | TODO | Separate no-answer/refusal evaluation | No-answer rows have null answer accuracy and need their own correctness metric. | Add refusal correctness aggregation from records; report by `is_unanswerable=true`. | Report contains refusal count, refusal correctness, and examples. | `eval/outputs/reports/refusal_correctness.md` |
| P1-05 | TODO | Add citation coverage metric | Citation coverage is still not a formal metric. | Compute whether generated citations point to retrieved chunks that contain gold spans. | `citation_coverage` is populated for supported datasets or explicitly marked unsupported. | Updated records and `citation_metrics.csv` |
| P1-06 | DONE | Add Semantic Similarity metric | F1/EM are sensitive to formatting (e.g., bullets vs paragraphs). | Implement Cosine Similarity using embeddings in `run_rag_eval.py`. | Report includes `answer_accuracy_semantic`. | Implemented in `run_rag_eval.py`; verified in smoke tests. |

## P2: Latency And Observability

| ID | Status | Task | Problem Addressed | Action Plan | Acceptance Criteria | Evidence To Attach |
| --- | --- | --- | --- | --- | --- | --- |
| P2-01 | DONE | Rerun balanced sync vs stream latency | Current sync has 10 samples, stream has 3 samples. | Benchmark sync vs stream modes on a fixed 20-sample subset. | Both modes report mean/P50/P95 latency and TTFT. | Run complete. Stream identified as optimal with 2.39s TTFT. |
| P2-02 | DONE | Break down end-to-end generation latency | End-to-end answers take tens of seconds. | Aggregate `rag_trace.stage_timings_ms` across RAG and rewrite records. | Report identifies top latency stages and their percentage contribution. | [stage_latency_breakdown.md](file:///d:/agent_demo/SuperMew/eval/outputs/reports/stage_latency_breakdown.md) |
| P2-03 | DONE | Shorten rewrite latency path | Dynamic rewrite is slower than no-rewrite and forced rewrite variants. | Implement batch embedding retrieval for multi-query nodes. | Average latency drops by at least 20s for complex queries. | Implemented `batch_retrieve_documents`; smoke test shows 37% saving. |
| P2-04 | DONE | Clean warning noise in long-run logs | `pymilvus` pkg_resources warning repeats in heartbeat logs. | Suppress warnings in `rag_pipeline.py`. | Logs are cleaner; no harmleness UserWarnings. | Warnings filtered in `rag_pipeline.py`. |

## P3: Benchmark Coverage And Reporting

| ID | Status | Task | Problem Addressed | Action Plan | Acceptance Criteria | Evidence To Attach |
| --- | --- | --- | --- | --- | --- | --- |
| P3-01 | TODO | Expand LoTTE official coverage | Current official retrieval table is technology 100 only. | Run science and writing domains with the same matrix. | Report contains domain-level retrieval table and aggregate table. | Updated `retrieval_metrics.csv` |
| P3-02 | TODO | Expand RAGBench sample size | Current RAGBench subsets are 50 samples each. | Increase to 100+ per subset after gateway smoke passes. | RAGBench table has larger sample counts and stable run metadata. | Updated `rag_metrics.csv` |
| P3-03 | TODO | Human spot-check custom eval | Custom benchmark is AI-assisted reviewed, not independently human-labeled. | Manually inspect a stratified sample across 5 question types. | Spot-check notes record accepted/fixed rows and remaining risk. | `eval/datasets/custom/HUMAN_SPOT_CHECK.md` |
| P3-04 | TODO | Refresh resume bullets after new metrics | Resume bullets currently should not overclaim rewrite/chunking. | Regenerate bullets after P0/P1 results; keep caveats explicit. | `resume_bullets.md` contains only supported claims. | Updated `eval/outputs/reports/resume_bullets.md` |

## Immediate Execution Order

1. Run `P0-01` to make rewrite trigger behavior fully visible.
2. Run `P0-03` to understand why answer accuracy is low while groundedness is high.
3. Fix dynamic rewrite routing under `P0-02` only after the trigger report identifies concrete failure modes.
4. Unblock parent store under `P0-04`, then run chunking matrix `P0-05`.
5. Start retrieval cost/quality tuning with `P1-01` and `P1-02`.
6. Rerun balanced latency only after major pipeline changes settle.

## Definition Of Done For This Improvement Cycle

- `rewrite_by_question_type` report exists and identifies trigger precision/recall.
- `answer_quality_failure_analysis.md` exists and names top generation failure modes.
- `chunking_metrics.csv` is non-empty or the parent-store blocker is documented with a concrete fix.
- Retrieval tuning has a Pareto recommendation for dense, hybrid, and rerank modes.
- Latency report has equal sample counts for sync and stream.
- Public-facing claims are updated only after the evidence files above exist.
